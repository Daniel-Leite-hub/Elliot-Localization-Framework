"""Two export forms for the current Elliot project. No install or DB mutation."""
import collections,hashlib,json,os,shutil,struct,time,zipfile
from pathlib import Path
from Crypto.Cipher import AES
from core import atomic_write,file_hash,validate
from deep_search import Pak,Reader
from locres import LocRes

TARGET='Elliot/Content/Paks/Elliot-Windows.pak'
RESOURCE='../../../Elliot/Content/Localization/Game/es/Game.locres'

class JoinedReader:
    def __init__(self,base,suffix):self.f=base.open('rb');self.size=base.stat().st_size;self.suffix=suffix;self.pos=0
    def __enter__(self):return self
    def __exit__(self,*args):self.f.close()
    def seek(self,offset,whence=0):
        self.pos=offset if whence==0 else self.pos+offset if whence==1 else self.size+len(self.suffix)+offset
        if self.pos<0:raise ValueError('Offset negativo.')
        return self.pos
    def read(self,n=-1):
        if n<0:n=self.size+len(self.suffix)-self.pos
        out=b''
        if self.pos<self.size:
            self.f.seek(self.pos);out=self.f.read(min(n,self.size-self.pos));self.pos+=len(out);n-=len(out)
        if n:
            part=self.suffix[max(0,self.pos-self.size):max(0,self.pos-self.size)+n];out+=part;self.pos+=len(part)
        return out

class JoinedPak:
    def __init__(self,base,suffix):self.base,self.suffix,self.name=base,suffix,base.name
    def open(self,mode):
        if mode!='rb':raise ValueError('Recurso virtual somente leitura.')
        return JoinedReader(self.base,self.suffix)

def check_cancel(cancel):
    if cancel and cancel.is_set():raise InterruptedError('Compartilhamento cancelado; nenhum arquivo do jogo foi alterado.')

def current_locres(store,project,mode):
    if mode not in ['reviewed','approved']:raise ValueError('Modo de seleção inválido.')
    es=LocRes((project/'Textos_para_leitura/originais/es/Game.locres').read_bytes())
    with store.lock:
        rows={tuple(json.loads(json.loads(r['meta'])['external_id'])):dict(r) for r in store.db.execute("SELECT * FROM entries WHERE active=1 AND language='EN'")}
    replacements={};audit=[]
    for r in es.records:
        key=(r['namespace'],r['key']);entry=rows[key];meta=json.loads(entry['meta'])
        if meta['auxiliary']['ES']['source_crc']!=r['source_crc']:raise ValueError('CRC de origem divergente.')
        source=entry['original'];preserved=source=='None' or entry['kind']!='traduzivel' or any('\u3040'<=c<='\u30ff' or '\u4e00'<=c<='\u9fff' for c in source)
        if preserved:text=source;state='original_preservado'
        elif mode=='reviewed' and entry['draft'] is not None:text=entry['draft'];state='rascunho'
        else:
            text,state,_=store.select(entry,approved_only=True)
        errors,_=validate(source,text,meta.get('restrictions'))
        if errors:raise ValueError(f'{key}: '+ '; '.join(errors))
        replacements[key]=text;audit.append(dict(namespace=key[0],key=key[1],source_crc=r['source_crc'],selection=state,translation=text))
    data=es.build(replacements);parsed=LocRes(data)
    if any(r['original']!=replacements[r['namespace'],r['key']] for r in parsed.records):raise ValueError('Releitura do LocRes divergente.')
    return data,audit

def original_pak(project,expected,notify,cancel):
    root=project.parent
    candidates=[root/TARGET]
    candidates.extend(sorted((root/'TraducaoBackups').glob('reinsercao-*/original.pak'),reverse=True))
    for p in candidates:
        check_cancel(cancel)
        if not p.is_file() or p.is_symlink() or p.parent.is_symlink() or p.parent.is_junction():continue
        notify('Conferindo a base original para compartilhamento…')
        if file_hash(p)==expected:return p
    raise ValueError('PAK original compatível não localizado. Preserve o backup original em TraducaoBackups.')

def prepare(store,mode='reviewed',notify=lambda s:None,cancel=None):
    project=store.path.resolve().parents[1]
    check_cancel(cancel);payload,audit=current_locres(store,project,mode)
    template=json.loads((project/'AplicadorPTBR-v2/manifest.json').read_text(encoding='utf-8'))
    base=original_pak(project,template['base_sha256'],notify,cancel)
    key=(project/'pesquisa/archive-key.local').read_text().strip()
    old=Pak(base,key);entry=next(e for e in old.files if e['path']==RESOURCE)
    with base.open('rb') as f:
        f.seek(-221,2);footer=bytearray(f.read());assert struct.unpack_from('<II',footer,17)==(0x5a6f12e1,11)
        off,size=struct.unpack_from('<QQ',footer,25);f.seek(off);raw=f.read(size)
    aes=AES.new(bytes.fromhex(key.removeprefix('0x')),AES.MODE_ECB);index=bytearray(aes.decrypt(raw) if footer[16] else raw)
    r=Reader(index);r.string();r.number();r.number('Q')
    for _ in range(2):assert r.number()==1;r.pos+=36
    blobsize=r.number();blobstart=r.pos
    offset=base.stat().st_size;pad=b'\0'*((-offset)%16);offset+=len(pad)
    if offset>=2**32:raise ValueError('Base excede offset suportado.')
    pos=blobstart+entry['entry_offset'];assert entry['entry_offset']+12<=blobsize
    index[pos:pos+12]=struct.pack('<III',(1<<31)|(1<<30)|(1<<29)|(1<<22),offset,len(payload))
    header=struct.pack('<QQQI',0,len(payload),len(payload),0)+hashlib.sha1(payload).digest()+struct.pack('<BI',1,0)
    encrypted=aes.encrypt(payload+b'\0'*((-len(payload))%16));index_offset=offset+53+len(encrypted)
    struct.pack_into('<QQ',footer,25,index_offset,len(index));footer[41:61]=hashlib.sha1(index).digest()
    suffix=pad+header+encrypted+(aes.encrypt(bytes(index)) if footer[16] else bytes(index))+footer
    new=Pak(JoinedPak(base,suffix),key)
    differences=[a['path'] for a,b in zip(old.files,new.files) if {k:v for k,v in a.items() if k!='container'}!={k:v for k,v in b.items() if k!='container'}]
    assert len(old.files)==len(new.files) and differences==[RESOURCE]
    assert new.read_file(next(e for e in new.files if e['path']==RESOURCE))==payload
    h=hashlib.sha256();old_hash=hashlib.sha256()
    with base.open('rb') as f:
        for block in iter(lambda:f.read(8*1024*1024),b''):
            check_cancel(cancel);h.update(block);old_hash.update(block)
    assert old_hash.hexdigest()==template['base_sha256'];h.update(suffix)
    same=h.hexdigest()==template['output_sha256']
    manifest=dict(template,output_sha256=h.hexdigest(),output_size=base.stat().st_size+len(suffix),payload_sha256=hashlib.sha256(suffix).hexdigest(),entries=len(audit),runtime_menu_confirmed=bool(same and template.get('runtime_menu_confirmed')),runtime_confirmation_source=template.get('runtime_confirmation_source') if same else None,runtime_full_game_validated=False,editorial_mode=mode,selections=dict(collections.Counter(a['selection'] for a in audit)),font_policy='Fontes originais do jogo preservadas; nenhuma fonte personalizada foi preparada.')
    return project,base,suffix,manifest,audit

def guide(manual,manifest):
    common='Tradução Elliot PT-BR — idioma Espanhol\n\nFeche o jogo. Selecione Espanhol após instalar.\nFontes originais do jogo mantidas; não há fontes PT-BR personalizadas neste pacote. Acentos e encaixe durante o restante do jogo ainda precisam de teste.\n'
    if manual:
        return common+'\nZIP PARA COPIAR\n1. Confira a versão: o SHA-256 de Elliot/Content/Paks/Elliot-Windows.pak deve ser '+manifest['base_sha256']+'. No PowerShell: Get-FileHash -Algorithm SHA256 -LiteralPath "Elliot\\Content\\Paks\\Elliot-Windows.pak"\n2. Antes de extrair, copie esse PAK original para uma pasta de backup fora do jogo. Reserve espaço para o backup e o arquivo traduzido (cerca de 3,7 GB cada).\n3. Extraia a pasta Elliot deste ZIP na pasta que contém Elliot.exe, aceitando substituir apenas Elliot-Windows.pak.\n4. Se instalou o pacote v1, retire Elliot_PTBR_P.pak da pasta Paks e guarde-o fora dela.\n5. Para desfazer, feche o jogo e devolva o PAK original do backup ao mesmo caminho. Não há restauração automática neste ZIP.\n\nNão altera executáveis, saves, UCAS ou UTOC.\n'
    return common+'\nINSTALADOR EXE\nAbra ElliotAplicadorPTBR.exe, selecione a pasta que contém Elliot.exe e clique em Verificar e Instalar tradução. Reserve cerca de 4 GB livres. O instalador confere hashes, prepara o PAK e guarda o original em TraducaoBackups. Para desfazer, feche o jogo e clique em Restaurar original. Preserve toda esta pasta, incluindo _internal, payload e manifest.json. Não exige Python nem chave AES.\n'

def export_manual(store,destination,mode='reviewed',notify=lambda s:None,cancel=None):
    destination=Path(destination).resolve()
    if destination.exists():raise ValueError('Escolha um ZIP novo; arquivo existente preservado.')
    project,base,suffix,m,audit=prepare(store,mode,notify,cancel)
    if shutil.disk_usage(destination.parent).free<m['output_size']+64*1024*1024:raise ValueError('Reserve aproximadamente 4 GB livres para o ZIP de cópia direta.')
    temp=destination.with_name(destination.name+'.tmp-'+str(time.time_ns()))
    try:
        with zipfile.ZipFile(temp,'w',zipfile.ZIP_STORED,allowZip64=True) as z:
            with z.open(TARGET,'w',force_zip64=True) as out,base.open('rb') as source:
                count=0
                for block in iter(lambda:source.read(8*1024*1024),b''):
                    check_cancel(cancel);out.write(block);count+=len(block);notify(f'ZIP de cópia: {count/base.stat().st_size:.0%}')
                out.write(suffix)
            z.writestr('LEIA-ME.txt',guide(True,m));z.writestr('manifesto.json',json.dumps(m,ensure_ascii=False,indent=2));z.writestr('selecao-textos.json',json.dumps(audit,ensure_ascii=False))
        notify('Relendo o ZIP e conferindo o PAK completo…')
        with zipfile.ZipFile(temp) as z:
            h=hashlib.sha256()
            with z.open(TARGET) as f:
                for block in iter(lambda:f.read(8*1024*1024),b''):check_cancel(cancel);h.update(block)
            if h.hexdigest()!=m['output_sha256']:raise ValueError('PAK no ZIP divergiu da reconstrução.')
        if destination.exists():raise ValueError('O destino foi criado por outro processo.')
        os.rename(temp,destination)
        return str(destination)
    finally:temp.unlink(missing_ok=True)

def export_installer(store,destination,mode='reviewed',notify=lambda s:None,cancel=None):
    destination=Path(destination).resolve()
    if destination.exists():raise ValueError('Escolha uma pasta nova para o instalador.')
    project,base,suffix,m,audit=prepare(store,mode,notify,cancel)
    template=project/'AplicadorPTBR-v2/bin/ElliotAplicadorPTBRv2'
    if not (template/'ElliotAplicadorPTBRv2.exe').is_file():raise ValueError('Modelo do instalador EXE ausente.')
    temp=destination.with_name(destination.name+'.preparando-'+str(time.time_ns()))
    temp.mkdir()
    try:
        for source in template.rglob('*'):
            check_cancel(cancel)
            relative=source.relative_to(template)
            if relative.parts[0] in ['payload','manifest.json']:continue
            target=temp/relative
            if source.is_file():target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
        (temp/'ElliotAplicadorPTBRv2.exe').rename(temp/'ElliotAplicadorPTBR.exe')
        atomic_write(temp/'payload/reinsercao.bin',suffix)
        atomic_write(temp/'manifest.json',json.dumps(m,ensure_ascii=False,indent=2).encode())
        atomic_write(temp/'selecao-textos.json',json.dumps(audit,ensure_ascii=False).encode())
        atomic_write(temp/'LEIA-ME.txt',guide(False,m).encode())
        if file_hash(temp/'payload/reinsercao.bin')!=m['payload_sha256']:raise ValueError('Payload copiado divergiu.')
        os.rename(temp,destination)
        return str(destination/'ElliotAplicadorPTBR.exe')
    except Exception:
        # Preserve incomplete output for inspection; never erase another export.
        atomic_write(temp/'EXPORTACAO-INCOMPLETA.txt',b'Exportacao interrompida. Nao distribua esta pasta.')
        raise
