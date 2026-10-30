"""Verifica candidatos alinhados em dados globais, sem alterar a memória."""
import sys,struct,hashlib,json,ctypes as C,time
from Crypto.Cipher import AES
import pefile
from probe_runtime import k,ROOT,OUT
def main(pid):
    with (ROOT/'Elliot/Content/Paks/Elliot-Windows.pak').open('rb') as f:
        f.seek(-512,2);tail=f.read();a=tail.index(struct.pack('<I',0x5a6f12e1));off,size=struct.unpack_from('<QQ',tail,a+8);expected=tail[a+24:a+44];f.seek(off);raw=f.read(size)
    pe=pefile.PE(str(ROOT/'Elliot/Binaries/Win64/Elliot-Win64-Shipping.exe'),fast_load=True)
    h=k.OpenProcess(0x410,False,pid);seen=set();count=0;found=False;start=time.monotonic()
    try:
        for s in pe.sections:
            if not s.Characteristics&0x80000000 or s.Characteristics&0x20000000:continue
            n=C.c_size_t();size=max(s.Misc_VirtualSize,s.SizeOfRawData);b=C.create_string_buffer(size);base=0x140000000+s.VirtualAddress
            k.ReadProcessMemory(h,base,b,size,C.byref(n));data=b.raw[:n.value]
            for at in range(0,len(data)-32,4):
                key=data[at:at+32]
                if len(set(key))<24 or key in seen:continue
                seen.add(key);count+=1
                if AES.new(key,AES.MODE_ECB).decrypt(raw[:16])[4:7]!=b'../':continue
                if hashlib.sha1(AES.new(key,AES.MODE_ECB).decrypt(raw)).digest()!=expected:continue
                (OUT.parent/'archive-key.local').write_text(key.hex(),encoding='ascii');found=True;print('CHAVE VALIDADA',hex(base+at),flush=True);break
            print(s.Name,count,round(time.monotonic()-start,2),flush=True)
            if found:break
        (OUT/f'global-data-{pid}.json').write_text(json.dumps(dict(pid=pid,candidates=count,found=found),indent=2),encoding='utf-8')
    finally:k.CloseHandle(h)
if __name__=='__main__':main(int(sys.argv[1]))
