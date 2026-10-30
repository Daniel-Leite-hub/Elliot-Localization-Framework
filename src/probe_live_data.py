"""Procura buffers LocRes e chaves AES expandidas no processo local autorizado."""
import sys,json,struct,hashlib,ctypes as C,ctypes.wintypes as W
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'pesquisa/python-libs'))
import numpy as np
from Crypto.Cipher import AES
from probe_live_regions import k,MBI,ROOT,OUT
from locres import MAGIC

def main(pid):
    with (ROOT/'Elliot/Content/Paks/Elliot-Windows.pak').open('rb') as f:
        f.seek(-512,2);tail=f.read();a=tail.index(struct.pack('<I',0x5a6f12e1));off,size=struct.unpack_from('<QQ',tail,a+8);expected=tail[a+24:a+44];f.seek(off);encrypted=f.read(size)
    h=k.OpenProcess(0x410,False,pid)
    if not h:raise OSError(C.get_last_error(),'OpenProcess')
    regions=[];addr=0;mb=MBI();candidates=0;hits=[];total=0;found=False
    def test(key,address):
        nonlocal found,candidates
        candidates+=1
        if AES.new(key,AES.MODE_ECB).decrypt(encrypted[:16])[4:7]!=b'../':return False
        if hashlib.sha1(AES.new(key,AES.MODE_ECB).decrypt(encrypted)).digest()!=expected:return False
        (OUT.parent/'archive-key.local').write_text(key.hex(),encoding='ascii');found=True
        print('CHAVE VALIDADA',hex(address),flush=True);return True
    try:
        while k.VirtualQueryEx(h,addr,C.byref(mb),C.sizeof(mb)):
            if mb.state==0x1000 and not mb.protect&0x101:regions.append((mb.base,mb.size,mb.protect,mb.type))
            nxt=(mb.base or 0)+mb.size
            if nxt<=addr:break
            addr=nxt
        regions.sort(key=lambda r:(not bool(r[2]&0x0c),-r[1]))
        chunk=8*1024*1024;buffer=C.create_string_buffer(chunk);n=C.c_size_t()
        for ri,(base,size,protect,kind) in enumerate(regions):
            exitcode=W.DWORD();k.GetExitCodeProcess(h,C.byref(exitcode))
            if exitcode.value!=259:break
            previous=b''
            for offset in range(0,size,chunk):
                n.value=0;k.ReadProcessMemory(h,base+offset,buffer,min(chunk,size-offset),C.byref(n));raw=buffer.raw[:n.value]
                if not raw:continue
                d=previous+raw;origin=base+offset-len(previous);total+=len(raw)
                # Relações universais de palavras AES-256 consecutivas, sem tabelas privadas.
                u=np.frombuffer(d[:len(d)//4*4],dtype='<u4');length=len(u)-12
                if length>0:
                    mask=((u[9:9+length]^u[8:8+length])==u[1:1+length]) & ((u[10:10+length]^u[9:9+length])==u[2:2+length]) & ((u[11:11+length]^u[10:10+length])==u[3:3+length]) & (u[:length]!=u[1:1+length]) & (u[1:1+length]!=0)
                    for pos in np.flatnonzero(mask):
                        key=d[int(pos)*4:int(pos)*4+32]
                        if len(set(key))<12:continue
                        if test(key,origin+int(pos)*4) or test(b''.join(key[i:i+4][::-1] for i in range(0,32,4)),origin+int(pos)*4):break
                    if not found:
                        # Chave padrão Unreal: GUID nulo seguido por FAESKey (32 bytes).
                        z=(u[:length]==0)&(u[1:1+length]==0)&(u[2:2+length]==0)&(u[3:3+length]==0)&(u[4:4+length]!=0)&(u[5:5+length]!=0)&(u[6:6+length]!=0)&(u[7:7+length]!=0)&(u[8:8+length]!=0)&(u[9:9+length]!=0)&(u[10:10+length]!=0)&(u[11:11+length]!=0)
                        for pos in np.flatnonzero(z):
                            key=d[int(pos)*4+16:int(pos)*4+48]
                            if len(set(key))<24:continue
                            if test(key,origin+int(pos)*4+16):break
                if found:break
                at=d.find(MAGIC)
                while at>=0:
                    hits.append(dict(address=origin+at,version=d[at+16] if at+16<len(d) else None))
                    # Buffer de pesquisa somente, tamanho limitado; não presume idioma/recurso.
                    part=d[at:at+min(4*1024*1024,len(d)-at)]
                    path=OUT/f'locres-buffer-{origin+at:x}.bin'
                    if not path.exists():path.write_bytes(part)
                    at=d.find(MAGIC,at+16)
                previous=d[-256:]
            if ri%500==0:print('Dados',ri,'MiB',total//1048576,'candidatos',candidates,'LocRes',len(hits),flush=True)
            if found:break
        (OUT/f'live-data-{pid}.json').write_text(json.dumps(dict(pid=pid,bytes_read=total,candidates=candidates,key_validated=found,locres_hits=hits),indent=2),encoding='utf-8')
        print('Dados concluídos',total//1048576,'MiB',candidates,'candidatos',len(hits),'LocRes',flush=True)
    finally:k.CloseHandle(h)
if __name__=='__main__':main(int(sys.argv[1]))
