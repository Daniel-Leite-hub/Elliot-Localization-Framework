"""Leitura de regiões do processo do jogo: sem injeção ou modificação de memória."""
import ctypes as C,ctypes.wintypes as W,sys,struct,re,hashlib,json
from Crypto.Cipher import AES
from probe_runtime import k,ROOT,OUT
class MBI(C.Structure):
    _fields_=[('base',C.c_void_p),('allocation',C.c_void_p),('allocation_protect',W.DWORD),('partition',W.WORD),('size',C.c_size_t),('state',W.DWORD),('protect',W.DWORD),('type',W.DWORD)]
k.VirtualQueryEx.argtypes=[W.HANDLE,C.c_void_p,C.POINTER(MBI),C.c_size_t];k.VirtualQueryEx.restype=C.c_size_t
k.GetExitCodeProcess.argtypes=[W.HANDLE,C.POINTER(W.DWORD)];k.GetExitCodeProcess.restype=W.BOOL
def main(pid):
    with (ROOT/'Elliot/Content/Paks/Elliot-Windows.pak').open('rb') as f:
        f.seek(-512,2);tail=f.read();a=tail.index(struct.pack('<I',0x5a6f12e1));off,size=struct.unpack_from('<QQ',tail,a+8);expected=tail[a+24:a+44];f.seek(off);cipher=f.read(size)
    h=k.OpenProcess(0x410,False,pid)
    if not h:raise OSError(C.get_last_error(),'OpenProcess')
    regions=[];addr=0;mb=MBI();seen=set();candidates=0;found=False
    try:
        while k.VirtualQueryEx(h,addr,C.byref(mb),C.sizeof(mb)):
            if mb.state==0x1000 and not mb.protect&0x101:
                regions.append(dict(base=mb.base,size=mb.size,protect=mb.protect,type=mb.type))
            next_addr=(mb.base or 0)+mb.size
            if next_addr<=addr:break
            addr=next_addr
        regions.sort(key=lambda r:(not bool(r['protect']&0xf0),-r['size']))
        (OUT/'regions.json').write_text(json.dumps(regions,indent=2),encoding='utf-8')
        print('Regiões',len(regions),'bytes',sum(r['size'] for r in regions),flush=True)
        def test(key,where):
            nonlocal candidates,found
            if len(key)!=32 or key in seen:return False
            seen.add(key);candidates+=1
            if AES.new(key,AES.MODE_ECB).decrypt(cipher[:16])[4:7]!=b'../':return False
            if hashlib.sha1(AES.new(key,AES.MODE_ECB).decrypt(cipher)).digest()!=expected:return False
            (OUT.parent/'archive-key.local').write_text(key.hex(),encoding='ascii');found=True
            (OUT/'live-key-proof.json').write_text(json.dumps(dict(pid=pid,address=where,index_sha1_verified=True)),encoding='utf-8')
            print('CHAVE VALIDADA',hex(where),flush=True);return True
        store=rb'\xc7(?:[\x40-\x7f].|[\x80-\xbf].{4}|[\x00-\x03\x06-\x07])(.{4})'
        pat=re.compile(store*4+rb'.{0,48}?'+store*4,re.S)
        chunk=4*1024*1024;buffer=C.create_string_buffer(chunk);n=C.c_size_t();total=0
        completed=True
        for ri,r in enumerate(regions):
            exit_code=W.DWORD()
            if not k.GetExitCodeProcess(h,C.byref(exit_code)) or exit_code.value!=259:
                print('Processo encerrou; sondagem parcial interrompida.',flush=True);completed=False;break
            previous=b''
            for offset in range(0,r['size'],chunk):
                size=min(chunk,r['size']-offset);n.value=0
                k.ReadProcessMemory(h,r['base']+offset,buffer,size,C.byref(n))
                raw=buffer.raw[:n.value];data=previous+raw;origin=r['base']+offset-len(previous);total+=n.value
                if not raw:continue
                for m in pat.finditer(data):
                    if test(b''.join(m.groups()),origin+m.start()):break
                if found:break
                for m in re.finditer(rb'(?<![A-Fa-f0-9])(?:0x)?([A-Fa-f0-9]{64})(?![A-Fa-f0-9])',data):
                    if test(bytes.fromhex(m.group(1).decode()),origin+m.start()):break
                if found:break
                # Guarda somente código executável privado para análise estática posterior.
                if r['type']==0x20000 and r['protect']&0xf0:
                    path=OUT/f'private-code-{r["base"]:x}-{offset:x}.bin'
                    if not path.exists():path.write_bytes(raw)
                previous=data[-256:]
            if ri%500==0:print('Regiões lidas',ri,'MiB',total//1048576,'candidatos',candidates,flush=True)
            if found:break
        (OUT/f'live-scan-{pid}.json').write_text(json.dumps(dict(pid=pid,regions=len(regions),bytes_read=total,candidates=candidates,found=found,completed=completed),indent=2),encoding='utf-8')
    finally:k.CloseHandle(h)
if __name__=='__main__':main(int(sys.argv[1]))
