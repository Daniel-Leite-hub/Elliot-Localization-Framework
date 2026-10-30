"""Aplicador independente de arquivos com manifesto de hashes. Sem DeepL."""
import argparse
import json
import os
import time
import tkinter as tk
import uuid
from pathlib import Path, PureWindowsPath
from tkinter import ttk, filedialog, messagebox
from core import VERSION, atomic_write, file_hash


def is_junction(path):
    try:
        return path.is_junction()
    except AttributeError:
        try:
            import stat
            return bool(path.lstat().st_file_attributes & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400))
        except Exception:
            return False


def inside(root, relative):
    root=Path(root).resolve()
    win=PureWindowsPath(relative)
    if not relative or win.is_absolute() or win.drive or '..' in win.parts or ':' in relative:
        raise ValueError('Caminho relativo inválido no manifesto.')
    target=(root/relative).resolve()
    if not target.is_relative_to(root) or target==root:
        raise ValueError('Destino fora da pasta selecionada.')
    cursor=target
    while cursor!=root:
        if cursor.exists() and (cursor.is_symlink() or is_junction(cursor)):
            raise ValueError('Links/reparse points não são aceitos.')
        cursor=cursor.parent
    return target


def validate_manifest(manifest_path, root):
    manifest_path=Path(manifest_path).resolve()
    obj=json.loads(manifest_path.read_text(encoding='utf-8-sig'))
    if obj.get('format')!='studio-patch-v1' or obj.get('game_validated') is not True:
        raise ValueError('Exigido manifesto studio-patch-v1 de patch já validado no jogo. O Studio não produz patch Elliot nesta versão.')
    if not isinstance(obj.get('files'),list) or not obj['files']:
        raise ValueError('Manifesto sem arquivos.')
    files=[]; destinations=set()
    for item in obj['files']:
        destination=inside(root,item['target'])
        source=inside(manifest_path.parent,item['payload'])
        if str(destination).casefold() in destinations:
            raise ValueError('Destino duplicado no manifesto.')
        destinations.add(str(destination).casefold())
        if not source.is_file() or file_hash(source)!=item['output_sha256']:
            raise ValueError('Arquivo de patch ausente ou hash incompatível: '+item['payload'])
        if not destination.is_file() or file_hash(destination)!=item['base_sha256']:
            raise ValueError('Base incompatível: '+item['target'])
        files.append((item,destination,source))
    for check in obj.get('base_checks',[]):
        target=inside(root,check['target'])
        if not target.is_file() or file_hash(target)!=check['sha256']:
            raise ValueError('Versão de base incompatível: '+check['target'])
    return obj,files


def apply(manifest_path, root):
    root=Path(root).resolve()
    obj,files=validate_manifest(manifest_path,root)
    backup=root/'TraducaoBackups'/('aplicacao-'+str(time.time_ns())+'-'+uuid.uuid4().hex[:8])
    backup.mkdir(parents=True,exist_ok=False)
    journal=dict(format='studio-application-v1',version=VERSION,root=str(root),patch=obj.get('name','sem nome'),state='preparando',files=[])
    journal_path=backup/'aplicacao.json'
    for i,(item,destination,source) in enumerate(files):
        original=destination.read_bytes()
        if file_hash(destination)!=item['base_sha256']:
            raise ValueError('A base mudou durante a preparação. Nenhum arquivo substituído.')
        name=f'{i:05d}.backup'
        atomic_write(backup/name,original)
        if file_hash(backup/name)!=item['base_sha256']:
            raise ValueError('Backup falhou na verificação.')
        journal['files'].append(dict(target=item['target'],backup=name,base_sha256=item['base_sha256'],output_sha256=item['output_sha256']))
    atomic_write(journal_path,json.dumps(journal,ensure_ascii=False,indent=2).encode())
    staged=[]
    try:
        for item,destination,source in files:
            payload=source.read_bytes()
            import hashlib
            if hashlib.sha256(payload).hexdigest()!=item['output_sha256']:
                raise ValueError('Payload mudou durante a preparação.')
            temp=destination.with_name(destination.name+'.traducao-'+uuid.uuid4().hex+'.tmp')
            atomic_write(temp,payload)
            staged.append((destination,temp,item))
        # Conferência de toda a base imediatamente antes do primeiro replace.
        for destination,temp,item in staged:
            if file_hash(destination)!=item['base_sha256']:
                raise ValueError('Base alterada antes da aplicação.')
        journal['state']='aplicando'
        atomic_write(journal_path,json.dumps(journal,ensure_ascii=False,indent=2).encode())
        applied=[]
        try:
            for destination,temp,item in staged:
                os.replace(temp,destination); applied.append(destination)
                if file_hash(destination)!=item['output_sha256']:
                    raise ValueError('Arquivo aplicado diverge do patch.')
        except Exception:
            for entry in journal['files']:
                destination=inside(root,entry['target'])
                if destination in applied:
                    atomic_write(destination,(backup/entry['backup']).read_bytes())
            journal['state']='revertida_por_erro'
            atomic_write(journal_path,json.dumps(journal,ensure_ascii=False,indent=2).encode())
            raise
        journal['state']='aplicada'
        atomic_write(journal_path,json.dumps(journal,ensure_ascii=False,indent=2).encode())
        return journal_path
    finally:
        for _,temp,_ in staged:
            temp.unlink(missing_ok=True)


def restore_application(journal_path):
    journal_path=Path(journal_path).resolve()
    obj=json.loads(journal_path.read_text(encoding='utf-8-sig'))
    if obj.get('format')!='studio-application-v1' or obj.get('state') not in ['aplicada','aplicando','restaurando']:
        raise ValueError('Registro não representa aplicação/restauração pendente.')
    root=Path(obj['root']).resolve()
    entries=[]
    for entry in obj['files']:
        source=inside(journal_path.parent,entry['backup'])
        destination=inside(root,entry['target'])
        if not source.is_file() or file_hash(source)!=entry['base_sha256']:
            raise ValueError('Backup inválido: '+entry['backup'])
        if not destination.is_file() or file_hash(destination) not in [entry['output_sha256'],entry['base_sha256']]:
            raise ValueError('Destino modificado por outra operação; restauração bloqueada: '+entry['target'])
        entries.append((entry,source,destination))
    obj['state']='restaurando'
    atomic_write(journal_path,json.dumps(obj,ensure_ascii=False,indent=2).encode())
    for entry,source,destination in entries:
        atomic_write(destination,source.read_bytes())
        if file_hash(destination)!=entry['base_sha256']:
            raise ValueError('Restauração não conferiu; use o registro para retomar.')
    obj['state']='restaurada'
    atomic_write(journal_path,json.dumps(obj,ensure_ascii=False,indent=2).encode())
    return len(entries)


def selftest():
    from core import file_hash
    root=Path.cwd()/'validacao-local'/('aplicador-'+uuid.uuid4().hex)
    game=root/'base'; patch=root/'patch'
    game.mkdir(parents=True); patch.mkdir()
    (game/'text.bin').write_bytes(b'original'); (patch/'text.bin').write_bytes('ação'.encode())
    manifest=dict(format='studio-patch-v1',name='Fixture; não é patch de jogo',game_validated=True,
                  files=[dict(target='text.bin',payload='text.bin',base_sha256=file_hash(game/'text.bin'),output_sha256=file_hash(patch/'text.bin'))])
    (patch/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
    log=apply(patch/'manifest.json',game)
    assert (game/'text.bin').read_bytes()=='ação'.encode()
    assert restore_application(log)==1 and (game/'text.bin').read_bytes()==b'original'
    for bad in ['../outside','C:\\outside','dir\\..\\outside','dir:file']:
        try: inside(game,bad)
        except ValueError: pass
        else: raise AssertionError('Caminho inseguro aceito')
    (game/'text.bin').write_bytes(b'outra base')
    try: validate_manifest(patch/'manifest.json',game)
    except ValueError: pass
    else: raise AssertionError('Base incompatível aceita')
    return dict(version=VERSION,passed=['aplicação com backup e hashes','restauração verificada','travessia de diretório bloqueada','base incompatível bloqueada'],real_game_patch=False)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--self-test',action='store_true'); parser.add_argument('--result')
    args=parser.parse_args()
    if args.self_test:
        data=json.dumps(selftest(),ensure_ascii=False,indent=2).encode()
        if args.result: atomic_write(args.result,data)
        return
    app=tk.Tk(); app.title('Aplicador independente PT-BR — '+VERSION); app.geometry('780x360')
    manifest=tk.StringVar(); root=tk.StringVar(); status=tk.StringVar(value='Não há patch Elliot validado incluído. Este aplicador exige um manifesto de patch compatível.')
    frame=ttk.Frame(app,padding=20); frame.pack(fill='both',expand=True)
    ttk.Label(frame,text='Aplicador de tradução • '+VERSION,font=('Segoe UI',16,'bold')).pack(anchor='w')
    ttk.Label(frame,text='Executável: '+__import__('sys').executable,wraplength=730).pack(anchor='w',pady=5)
    def choose_manifest():
        path=filedialog.askopenfilename(title='Manifesto studio-patch-v1',filetypes=[('Manifesto JSON','*.json')])
        if path: manifest.set(path)
    def choose_root():
        path=filedialog.askdirectory(title='Pasta do jogo/base')
        if path: root.set(path)
    for label,var,fn in [('Manifesto do patch',manifest,choose_manifest),('Pasta do jogo',root,choose_root)]:
        row=ttk.Frame(frame); row.pack(fill='x',pady=7)
        ttk.Label(row,text=label,width=19).pack(side='left')
        ttk.Entry(row,textvariable=var).pack(side='left',fill='x',expand=True)
        ttk.Button(row,text='Selecionar',command=fn).pack(side='left',padx=5)
    def perform(mode):
        try:
            if mode=='restore':
                path=filedialog.askopenfilename(title='Registro aplicacao.json para restaurar',filetypes=[('Registro','*.json')])
                if path:
                    if messagebox.askyesno('Restaurar','Restaurar os arquivos originais deste registro?'):
                        status.set(f'{restore_application(path)} arquivos restaurados e conferidos.')
                return
            if not manifest.get() or not root.get(): raise ValueError('Selecione manifesto e pasta de base.')
            obj,files=validate_manifest(manifest.get(),root.get())
            if mode=='verify': status.set(f'{len(files)} arquivos: base e payload conferem com os hashes. Validação no jogo é responsabilidade do autor do patch.'); return
            if messagebox.askyesno('Aplicar patch',f'Base compatível. Aplicar {len(files)} arquivos de {obj.get("name","patch")} com backup?\nFeche o jogo antes de continuar.'):
                log=apply(manifest.get(),root.get()); status.set('Aplicação conferida. Registro e backup: '+str(log))
        except Exception as exc: messagebox.showerror('Operação bloqueada',str(exc))
    buttons=ttk.Frame(frame); buttons.pack(fill='x',pady=15)
    for label,mode in [('Verificar compatibilidade','verify'),('Aplicar com backup','apply'),('Restaurar backup','restore')]:
        ttk.Button(buttons,text=label,command=lambda m=mode:perform(m)).pack(side='left',padx=5)
    ttk.Label(frame,textvariable=status,wraplength=730).pack(anchor='w')
    app.mainloop()


if __name__=='__main__': main()
