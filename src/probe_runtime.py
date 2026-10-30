"""Sondagem somente leitura da imagem do processo local do jogo; sem escrita/injeção."""
import ctypes as C,ctypes.wintypes as W,json,subprocess,time,sys,re,struct,hashlib
from pathlib import Path
from Crypto.Cipher import AES
sys.stdout.reconfigure(encoding='utf-8')
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'FerramentaTraducao/pesquisa/runtime'
k=C.WinDLL('kernel32',use_last_error=True)
k.OpenProcess.argtypes=[W.DWORD,W.BOOL,W.DWORD];k.OpenProcess.restype=W.HANDLE
k.ReadProcessMemory.argtypes=[W.HANDLE,C.c_void_p,C.c_void_p,C.c_size_t,C.POINTER(C.c_size_t)];k.ReadProcessMemory.restype=W.BOOL
k.K32EnumProcessModules.argtypes=[W.HANDLE,C.POINTER(W.HMODULE),W.DWORD,C.POINTER(W.DWORD)];k.K32EnumProcessModules.restype=W.BOOL
k.CloseHandle.argtypes=[W.HANDLE]
class ModuleInfo(C.Structure):_fields_=[('base',C.c_void_p),('size',W.DWORD),('entry',C.c_void_p)]
k.K32GetModuleInformation.argtypes=[W.HANDLE,W.HMODULE,C.POINTER(ModuleInfo),W.DWORD]

def snapshot(pid,label):
    handle=k.OpenProcess(0x410,False,pid)
    if not handle:raise OSError(C.get_last_error(),'OpenProcess')
    try:
        modules=(W.HMODULE*512)();needed=W.DWORD()
        if not k.K32EnumProcessModules(handle,modules,C.sizeof(modules),C.byref(needed)):raise OSError(C.get_last_error(),'EnumModules')
        info=ModuleInfo()
        if not k.K32GetModuleInformation(handle,modules[0],C.byref(info),C.sizeof(info)):raise OSError(C.get_last_error(),'ModuleInfo')
        if not 1_000_000<=info.size<=1_000_000_000:raise ValueError('Limite de imagem inesperado')
        out=OUT/(label+'.image');total=0;buffer=C.create_string_buffer(65536);n=C.c_size_t()
        with out.open('wb') as stream:
            for offset in range(0,info.size,65536):
                size=min(65536,info.size-offset);n.value=0
                k.ReadProcessMemory(handle,info.base+offset,buffer,size,C.byref(n))
                data=buffer.raw[:n.value] if n.value else b'';total+=len(data)
                stream.write(data+b'\0'*(size-len(data)))
        record=dict(pid=pid,base=info.base,size=info.size,readable=total,file=str(out),process_memory_modified=False)
        out.with_suffix('.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
        print(json.dumps(record),flush=True);return out
    finally:k.CloseHandle(handle)

def scan(path):
    pak=ROOT/'Elliot/Content/Paks/Elliot-Windows.pak'
    with pak.open('rb') as f:
        f.seek(-512,2);tail=f.read();a=tail.index(struct.pack('<I',0x5a6f12e1));off,size=struct.unpack_from('<QQ',tail,a+8);expected=tail[a+24:a+44];f.seek(off);raw=f.read(size)
    d=path.read_bytes();store=rb'\xc7(?:[\x40-\x7f].|[\x80-\xbf].{4}|[\x00-\x03\x06-\x07])(.{4})';count=0
    for m in re.finditer(store*4+rb'.{0,48}?'+store*4,d,re.S):
        key=b''.join(m.groups());count+=1
        plain=AES.new(key,AES.MODE_ECB).decrypt(raw[:16])
        if plain[4:7]!=b'../':continue
        decoded=AES.new(key,AES.MODE_ECB).decrypt(raw)
        if hashlib.sha1(decoded).digest()==expected:
            (OUT.parent/'archive-key.local').write_text(key.hex(),encoding='ascii')
            print('CHAVE VALIDADA NO INDICE',flush=True);return True
    print('Candidatos runtime:',count,flush=True);return False

if __name__=='__main__':
    OUT.mkdir(exist_ok=True)
    p=subprocess.Popen([str(ROOT/'Elliot/Binaries/Win64/Elliot-Win64-Shipping.exe'),'-nosound','-unattended','-nosplash','-UserDir='+str(OUT),'-abslog='+str(OUT/'runtime-probe.log')],cwd=ROOT,creationflags=subprocess.CREATE_NO_WINDOW)
    print('Processo',p.pid,flush=True);start=time.monotonic();paths=[]
    for delay in (0.5,2.0):
        time.sleep(max(0,delay-(time.monotonic()-start)))
        if p.poll() is not None:break
        try:paths.append(snapshot(p.pid,'startup-'+str(p.pid)+'-'+str(delay)))
        except Exception as e:print(type(e).__name__,str(e),flush=True)
    for path in reversed(paths):
        if scan(path):break
    print('Estado processo:',p.poll(),flush=True)
