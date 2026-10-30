"""Busca estática por referências RIP e stores com saltos; valida no índice PAK."""
import sys,struct,re,hashlib,json,time
from pathlib import Path
import pefile
from Crypto.Cipher import AES

sys.stdout.reconfigure(encoding='utf-8')
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'FerramentaTraducao/pesquisa'

def main():
    start=time.monotonic();pak=ROOT/'Elliot/Content/Paks/Elliot-Windows.pak'
    with pak.open('rb') as f:
        f.seek(-512,2);tail=f.read();a=tail.index(struct.pack('<I',0x5a6f12e1));off,size=struct.unpack_from('<QQ',tail,a+8);expected=tail[a+24:a+44];f.seek(off);raw=f.read(size)
    tested=set();counts={};found=None
    def test(key,method,offset):
        nonlocal found
        if len(key)!=32 or key in tested:return False
        tested.add(key);counts[method]=counts.get(method,0)+1
        decoded=AES.new(key,AES.MODE_ECB).decrypt(raw[:16]);n=struct.unpack_from('<i',decoded)[0]
        if not 1<=n<=256 or decoded[4:7]!=b'../':return False
        decoded=AES.new(key,AES.MODE_ECB).decrypt(raw)
        matches=[pad for pad in range(16) if hashlib.sha1(decoded[:-pad] if pad else decoded).digest()==expected]
        if not matches:return False
        (OUT/'archive-key.local').write_text(key.hex(),encoding='ascii')
        found=dict(method=method,offset=offset,hash_padding=matches[0]);print('CHAVE VALIDADA',found,flush=True);return True
    for path in [ROOT/'Elliot/Binaries/Win64/Elliot-Win64-Shipping.exe',ROOT/'Elliot/Binaries/Win64/voices38.dll',ROOT/'Elliot.exe']:
        d=path.read_bytes();pe=pefile.PE(data=d,fast_load=True)
        def rva_to_raw(rva):
            for s in pe.sections:
                if s.VirtualAddress<=rva<s.VirtualAddress+s.SizeOfRawData:return rva-s.VirtualAddress+s.PointerToRawData
            return None
        def raw_to_rva(at):
            for s in pe.sections:
                if s.PointerToRawData<=at<s.PointerToRawData+s.SizeOfRawData:return at-s.PointerToRawData+s.VirtualAddress
            return None
        # LEA/MOV RIP e cargas vetoriais com dados de 16/32 bytes.
        pattern=rb'(?:[\x48-\x4f][\x8d\x8b]|\x0f[\x10\x28\x6f])([\x05\x0d\x15\x1d\x25\x2d\x35\x3d])(.{4})'
        for m in re.finditer(pattern,d,re.S):
            rv=raw_to_rva(m.end())
            if rv is None:continue
            target=rva_to_raw(rv+struct.unpack('<i',m.group(2))[0])
            if target is None:continue
            for delta in (0,-16,16):
                at=target+delta
                if at>=0 and test(d[at:at+32],'rip-reference',at):break
            if found:break
        if found:break
        # Stores C7 em [rcx] ou [rbp+disp8], com saltos E9/EB entre as partes.
        for m in re.finditer(rb'\xc7(?:\x01|\x45\xd0)',d):
            at=m.start();stack=d[at+1]==0x45;position=0;parts=[];visited=set()
            for step in range(80):
                if not 0<=at<len(d)-16 or at in visited:break
                visited.add(at)
                if d[at]==0xe9:
                    rv=raw_to_rva(at+5)
                    if rv is None:break
                    at=rva_to_raw(rv+struct.unpack_from('<i',d,at+1)[0])
                    if at is None:break
                    continue
                if d[at]==0xeb:
                    at+=2+struct.unpack_from('<b',d,at+1)[0];continue
                prefix=b'\xc7\x45'+bytes([0xd0+position*4]) if stack else b'\xc7\x01' if position==0 else b'\xc7\x41'+bytes([position*4])
                if d[at:at+len(prefix)]==prefix:
                    parts.append(d[at+len(prefix):at+len(prefix)+4]);at+=len(prefix)+4;position+=1
                    if position==8:
                        test(b''.join(parts),'stores-jumps',m.start());break
                else:
                    # Pequena região intercalada; candidatos falsos são rejeitados pelo SHA-1.
                    next_at=next((at+i for i in range(1,17) if d[at+i:at+i+len(prefix)]==prefix or d[at+i]==0xe9),None)
                    if next_at is None:break
                    at=next_at
            if found:break
        print(path.name,counts,'segundos',round(time.monotonic()-start,2),flush=True)
        if found:break
    (OUT/'probe-references.json').write_text(json.dumps(dict(found=found,candidates=counts,elapsed=time.monotonic()-start),indent=2),encoding='utf-8')

if __name__=='__main__':main()
