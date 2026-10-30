"""Installer for an additive, structurally checked Elliot localization overlay."""
import hashlib,json,os,sys,time,threading,tkinter as tk
from pathlib import Path
from tkinter import ttk,filedialog,messagebox
from core import atomic_write,file_hash
from applicator import inside

HOME=Path(sys.executable).resolve().parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[1]/'AplicadorPTBR'

def load(home=HOME):
    m=json.loads((home/'manifest.json').read_text(encoding='utf-8'))
    if m['format']!='elliot-overlay-v1' or not m['structural_validation']:raise ValueError('Manifesto incompatível.')
    if m['target']!='Elliot/Content/Paks/Elliot_PTBR_P.pak':raise ValueError('Destino não autorizado.')
    payload=inside(home,m['payload'])
    if file_hash(payload)!=m['sha256']:raise ValueError('Pacote ausente ou alterado.')
    return m,payload

def running():
    import ctypes
    from ctypes import wintypes
    class Entry(ctypes.Structure):
        _fields_=[('dwSize',wintypes.DWORD),('cntUsage',wintypes.DWORD),('th32ProcessID',wintypes.DWORD),('th32DefaultHeapID',ctypes.c_size_t),('th32ModuleID',wintypes.DWORD),('cntThreads',wintypes.DWORD),('th32ParentProcessID',wintypes.DWORD),('pcPriClassBase',wintypes.LONG),('dwFlags',wintypes.DWORD),('szExeFile',wintypes.WCHAR*260)]
    k=ctypes.WinDLL('kernel32',use_last_error=True)
    k.CreateToolhelp32Snapshot.argtypes=[wintypes.DWORD,wintypes.DWORD];k.CreateToolhelp32Snapshot.restype=wintypes.HANDLE
    for name in ['Process32FirstW','Process32NextW']:
        f=getattr(k,name);f.argtypes=[wintypes.HANDLE,ctypes.POINTER(Entry)];f.restype=wintypes.BOOL
    k.CloseHandle.argtypes=[wintypes.HANDLE];k.CloseHandle.restype=wintypes.BOOL
    handle=k.CreateToolhelp32Snapshot(2,0)
    if handle==ctypes.c_void_p(-1).value:raise ctypes.WinError(ctypes.get_last_error())
    try:
        entry=Entry();entry.dwSize=ctypes.sizeof(entry)
        if not k.Process32FirstW(handle,ctypes.byref(entry)):raise ctypes.WinError(ctypes.get_last_error())
        while True:
            if entry.szExeFile.lower() in ['elliot.exe','elliot-win64-shipping.exe']:return True
            if not k.Process32NextW(handle,ctypes.byref(entry)):
                if ctypes.get_last_error()!=18:raise ctypes.WinError(ctypes.get_last_error())
                return False
    finally:k.CloseHandle(handle)

def verify(root,home=HOME):
    m,payload=load(home);root=Path(root).resolve()
    for c in m['base_checks']:
        f=inside(root,c['target'])
        if not f.is_file() or file_hash(f)!=c['sha256']:raise ValueError('Versão do jogo incompatível: '+c['target'])
    target=inside(root,m['target'])
    if not target.parent.is_dir():raise ValueError('Pasta Paks ausente.')
    if target.exists() and file_hash(target)!=m['sha256']:raise ValueError('Já existe outro pacote com esse nome; preservado sem alterações.')
    return m,payload,target

def action(root,mode,home=HOME,check_running=True):
    if check_running and running():raise ValueError('Feche o jogo antes de instalar ou restaurar.')
    m,payload,target=verify(root,home)
    if mode=='verify':return 'Base e pacote conferidos. Selecione Espanhol no jogo após instalar.'
    if mode not in ['install','restore']:raise ValueError('Operação inválida.')
    if mode=='install' and target.exists():return 'Esta tradução já está instalada.'
    if mode=='restore' and not target.exists():return 'A tradução já está removida. Os arquivos originais permanecem intactos.'
    backup=inside(root,'TraducaoBackups/overlay-'+str(time.time_ns()));backup.mkdir(parents=True)
    journal=dict(format='elliot-overlay-operation-v1',operation=mode,target=m['target'],sha256=m['sha256'],original_archives_modified=False,state='preparada')
    def log():atomic_write(backup/'operacao.json',json.dumps(journal,ensure_ascii=False,indent=2).encode())
    log()
    if mode=='install':
        data=payload.read_bytes()
        if hashlib.sha256(data).hexdigest()!=m['sha256']:raise ValueError('Pacote mudou durante a preparação.')
        atomic_write(backup/'pacote.pak',data)
        # Exclusive creation cannot overwrite a file created after verification.
        try:
            with target.open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
            if file_hash(target)!=m['sha256']:raise ValueError('Conferência da instalação falhou.')
        except FileExistsError:raise ValueError('Destino criado por outro processo; não sobrescrito.')
        except Exception:
            target.unlink(missing_ok=True);journal['state']='revertida';log();raise
    else:
        data=target.read_bytes();atomic_write(backup/'pacote.pak',data)
        if file_hash(backup/'pacote.pak')!=m['sha256'] or file_hash(target)!=m['sha256']:raise ValueError('Pacote alterado durante restauração; preservado.')
        target.unlink()
    journal['state']='concluida';log()
    return ('Tradução instalada. Abra o jogo e selecione Espanhol.' if mode=='install' else 'Tradução removida; recursos originais voltam a ser usados.')+'\nRegistro: '+str(backup/'operacao.json')

def main(reinsertion=False):
    window=tk.Tk();window.title('Elliot — Aplicador PT-BR');window.geometry('660x310')
    default=next((p for p in HOME.parents if (p/'Elliot.exe').is_file()),HOME)
    root=tk.StringVar(value=str(default));status=tk.StringVar(value=('Reinserção v2 no PAK original, com backup restaurável. Reserve 4 GB livres. Teste no jogo ainda pendente.' if reinsertion else 'Pacote experimental: estrutura conferida; carregamento e aparência ainda precisam de teste no jogo.'))
    ttk.Label(window,text='Tradução PT-BR sobre o idioma Espanhol',font=('Segoe UI',13,'bold')).pack(pady=14)
    frame=ttk.Frame(window);frame.pack(fill='x',padx=18)
    ttk.Entry(frame,textvariable=root).pack(side='left',fill='x',expand=True)
    def choose():
        p=filedialog.askdirectory(title='Pasta que contém Elliot.exe')
        if p:root.set(p)
    ttk.Button(frame,text='Selecionar pasta',command=choose).pack(side='right',padx=8)
    ttk.Label(window,textvariable=status,wraplength=615).pack(padx=18,pady=20)
    controls=ttk.Frame(window);controls.pack();buttons=[]
    def run(mode):
        selected=root.get()
        prompt=('Reinserir o português no PAK original com backup? Reserve 4 GB livres e selecione Espanhol no jogo. Teste de carregamento ainda pendente.' if reinsertion else 'Instalar pacote experimental? Selecione Espanhol no jogo. O carregamento ainda não foi validado.') if mode=='install' else ('Restaurar o PAK original a partir do backup?' if reinsertion else 'Remover somente o pacote PT-BR e voltar aos recursos originais?')
        if mode!='verify' and not messagebox.askyesno('Instalar' if mode=='install' else 'Restaurar',prompt):return
        for b in buttons:b.configure(state='disabled')
        status.set('Conferindo arquivos e versão do jogo…')
        def done(text):
            status.set(text)
            for b in buttons:b.configure(state='normal')
        def worker():
            try:result=action(selected,mode)
            except Exception as e:result=str(e)
            window.after(0,lambda:done(result))
        threading.Thread(target=worker,daemon=True).start()
    for label,mode in [('Verificar','verify'),('Instalar tradução','install'),('Restaurar original','restore')]:
        b=ttk.Button(controls,text=label,command=lambda m=mode:run(m));b.pack(side='left',padx=5);buttons.append(b)
    ttk.Label(window,text='Feche o jogo. Preserve manifest.json, payload e _internal junto ao EXE.',wraplength=615).pack(pady=18)
    window.mainloop()

if __name__=='__main__':
    if len(sys.argv)==4 and sys.argv[1]=='--verify-report':
        result=verify(Path(sys.argv[2]));atomic_write(Path(sys.argv[3]),json.dumps({'verified':True,'target':str(result[2]),'game_validated':False}).encode())
    else:main()
