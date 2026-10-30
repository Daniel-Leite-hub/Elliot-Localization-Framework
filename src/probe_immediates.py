"""Candidatos de chave em movabs de 64 bits e representação base64."""
import sys,re,base64,struct,hashlib,json
from pathlib import Path
from Crypto.Cipher import AES
sys.stdout.reconfigure(encoding='utf-8')
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'FerramentaTraducao/pesquisa'
with (ROOT/'Elliot/Content/Paks/Elliot-Windows.pak').open('rb') as f:
    f.seek(-512,2);tail=f.read();a=tail.index(struct.pack('<I',0x5a6f12e1));off,size=struct.unpack_from('<QQ',tail,a+8);expected=tail[a+24:a+44];f.seek(off);raw=f.read(size)
seen=set();counts={};found=None
def test(key,method,offset):
    global found
    if len(key)!=32 or key in seen:return False
    seen.add(key);counts[method]=counts.get(method,0)+1
    if AES.new(key,AES.MODE_ECB).decrypt(raw[:16])[4:7]!=b'../':return False
    if hashlib.sha1(AES.new(key,AES.MODE_ECB).decrypt(raw)).digest()!=expected:return False
    (OUT/'archive-key.local').write_text(key.hex(),encoding='ascii');found=dict(method=method,offset=offset);print('CHAVE VALIDADA',found,flush=True);return True
for p in [ROOT/'Elliot/Binaries/Win64/Elliot-Win64-Shipping.exe',ROOT/'Elliot/Binaries/Win64/voices38.dll']:
    d=p.read_bytes();moves=list(re.finditer(rb'[\x48\x49][\xb8-\xbf](.{8})',d,re.S))
    for i in range(len(moves)-3):
        group=moves[i:i+4]
        if group[-1].start()-group[0].start()>160:continue
        parts=[m.group(1) for m in group]
        if test(b''.join(parts),'movabs',group[0].start()):break
        if test(b''.join(parts[::-1]),'movabs-reverse',group[0].start()):break
    if found:break
    for m in re.finditer(rb'(?<![A-Za-z0-9+/])([A-Za-z0-9+/]{43}=)(?![A-Za-z0-9+/])',d):
        if test(base64.b64decode(m.group(1)),'base64',m.start()):break
    if found:break
    print(p.name,counts,flush=True)
(OUT/'probe-immediates.json').write_text(json.dumps(dict(found=found,counts=counts),indent=2),encoding='utf-8')
