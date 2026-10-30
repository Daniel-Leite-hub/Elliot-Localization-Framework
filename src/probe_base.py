"""Sondagem da base: leitura somente, índice e validação de candidatos AES locais."""
import hashlib, json, mmap, re, struct
import sys
from pathlib import Path
from Crypto.Cipher import AES

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding='utf-8')

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'FerramentaTraducao'/'pesquisa'

def main():
    OUT.mkdir(exist_ok=True)
    pak=ROOT/'Elliot/Content/Paks/Elliot-Windows.pak'
    with pak.open('rb') as f:
        f.seek(-512,2); tail=f.read(); at=tail.index(struct.pack('<I',0x5a6f12e1))
        offset,size=struct.unpack_from('<QQ',tail,at+8); expected=tail[at+24:at+44]
        f.seek(offset); encrypted=f.read(size)
    candidates=set()
    exe=ROOT/'Elliot/Binaries/Win64/Elliot-Win64-Shipping.exe'
    with exe.open('rb') as f, mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ) as d:
        versions=[m.group().decode(errors='replace') for m in re.finditer(rb'\+\+UE5\+Release-[0-9.]+|[0-9]\.[0-9]\.[0-9]-[0-9]+\+\+UE5',d)]
        # Chaves codificadas como oito stores de imediatos, com ou sem deslocamento longo.
        for m in re.finditer(rb'\xC7[\x00-\xFF]',d):
            start=m.start(); p=start; vals=[]
            for _ in range(8):
                if d[p:p+1]!=b'\xc7': break
                mod=d[p+1]; mode=mod>>6; rm=mod&7
                if mode==3: break
                h=2+(1 if rm==4 else 0)+(4 if mode==2 or (mode==0 and rm==5) else 1 if mode==1 else 0)
                vals.append(d[p+h:p+h+4]); p+=h+4
                if len(vals)==8: candidates.add(b''.join(vals))
        for m in re.finditer(rb'(?:0x)?([A-Fa-f0-9]{64})(?![A-Fa-f0-9])',d):
            candidates.add(bytes.fromhex(m.group(1).decode()))
        for m in re.finditer(rb'(?:0\x00x\x00)?((?:[A-Fa-f0-9]\x00){64})',d):
            candidates.add(bytes.fromhex(m.group(1).decode('utf-16-le')))
    print('Versões', sorted(set(versions)), 'candidatos',len(candidates),flush=True)
    for key in sorted(candidates):
        decoded=AES.new(key,AES.MODE_ECB).decrypt(encrypted)
        if hashlib.sha1(decoded).digest()==expected:
            (OUT/'archive-key.local').write_text(key.hex())
            print('Índice AES validado por SHA-1; chave somente local, fora do pacote.',flush=True)
            break
    else: print('Chave não encontrada por padrões conservadores.',flush=True)
    (OUT/'probe.json').write_text(json.dumps(dict(engine_versions=sorted(set(versions)),aes_candidates=len(candidates),pak_index_validated=(OUT/'archive-key.local').exists()),indent=2))

if __name__=='__main__':main()
