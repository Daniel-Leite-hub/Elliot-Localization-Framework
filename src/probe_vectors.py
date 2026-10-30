"""Reconstrói candidatos de duas constantes SIMD separadas; valida SHA-1 do PAK."""
import sys,struct,re,hashlib,json,time
from pathlib import Path
from Crypto.Cipher import AES
import pefile
sys.stdout.reconfigure(encoding='utf-8')
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'FerramentaTraducao/pesquisa';started=time.monotonic()
with (ROOT/'Elliot/Content/Paks/Elliot-Windows.pak').open('rb') as f:
    f.seek(-512,2);tail=f.read();a=tail.index(struct.pack('<I',0x5a6f12e1));off,size=struct.unpack_from('<QQ',tail,a+8);expected=tail[a+24:a+44];f.seek(off);raw=f.read(size)
found=None;count=0;seen=set()
def test(key,where):
    global found,count
    if len(key)!=32 or key in seen:return False
    seen.add(key);count+=1
    if AES.new(key,AES.MODE_ECB).decrypt(raw[:16])[4:7]!=b'../':return False
    decoded=AES.new(key,AES.MODE_ECB).decrypt(raw)
    if hashlib.sha1(decoded).digest()!=expected:return False
    (OUT/'archive-key.local').write_text(key.hex(),encoding='ascii');found=where;print('CHAVE VALIDADA',where,flush=True);return True
for path in [ROOT/'Elliot/Binaries/Win64/Elliot-Win64-Shipping.exe',ROOT/'Elliot/Binaries/Win64/voices38.dll']:
    data=path.read_bytes();pe=pefile.PE(data=data,fast_load=True)
    def at_rva(rva):
        for s in pe.sections:
            if s.VirtualAddress<=rva<s.VirtualAddress+s.SizeOfRawData:return s.PointerToRawData+rva-s.VirtualAddress
        return None
    loads=[]
    for s in pe.sections:
        if not s.Characteristics&0x20000000:continue
        d=data[s.PointerToRawData:s.PointerToRawData+s.SizeOfRawData]
        pattern=rb'(?:\x0f[\x10\x28\x6f]|\xc5.[\x10\x28\x6f]|\xc4..[\x10\x28\x6f])([\x05\x0d\x15\x1d\x25\x2d\x35\x3d])(.{4})'
        for m in re.finditer(pattern,d,re.S):
            target=at_rva(s.VirtualAddress+m.end()+struct.unpack('<i',m.group(2))[0])
            if target is None:continue
            code=s.PointerToRawData+m.start();value=data[target:target+16]
            if test(data[target:target+32],dict(file=path.name,method='vector256',code=code,data=target)):break
            loads.append((code,target,value))
        if found:break
    if found:break
    loads.sort()
    for i,(code,target,value) in enumerate(loads):
        for code2,target2,value2 in loads[i+1:i+8]:
            if code2-code>160:break
            if test(value+value2,dict(file=path.name,method='vector-pair',code=code,code2=code2,data=target,data2=target2)):break
            if test(value2+value,dict(file=path.name,method='vector-pair-reverse',code=code,code2=code2,data=target,data2=target2)):break
        if found:break
    print('Vetores',path.name,len(loads),'candidatos',count,'segundos',round(time.monotonic()-started,2),flush=True)
    if found:break
(OUT/'probe-vectors.json').write_text(json.dumps(dict(found=found,candidates=count,elapsed=time.monotonic()-started),indent=2),encoding='utf-8')
