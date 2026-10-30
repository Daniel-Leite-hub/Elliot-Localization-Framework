"""Sonda estática adicional: oito stores C7, incluindo instruções entre metades."""
import re,struct,hashlib
from Crypto.Cipher import AES
from probe_base import ROOT,OUT

pak=ROOT/'Elliot/Content/Paks/Elliot-Windows.pak'
with pak.open('rb') as f:
    f.seek(-512,2);tail=f.read();a=tail.index(struct.pack('<I',0x5a6f12e1));off,size=struct.unpack_from('<QQ',tail,a+8);expected=tail[a+24:a+44];f.seek(off);raw=f.read(size)
d=(ROOT/'Elliot/Binaries/Win64/Elliot-Win64-Shipping.exe').read_bytes()
store=rb'\xc7(?:[\x40-\x7f].|[\x80-\xbf].{4}|[\x00-\x03\x06-\x07])(.{4})'
pattern=re.compile(store*4+rb'.{0,48}?'+store*4,re.S)
count=0
for m in pattern.finditer(d):
    key=b''.join(m.groups());count+=1
    if hashlib.sha1(AES.new(key,AES.MODE_ECB).decrypt(raw)).digest()==expected:
        (OUT/'archive-key.local').write_text(key.hex());print('Chave validada; indice hash correto.',flush=True);break
else:print('Nenhuma chave em stores separados.',flush=True)
print('Candidatos adicionais',count,flush=True)
