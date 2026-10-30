"""Percorre cabeçalhos físicos PAK v11 sem depender do índice cifrado.

Não inventa caminhos/idiomas. Confere tamanhos, blocos, SHA-1 e conserva offsets.
"""
import json,struct,hashlib,zlib
from core import atomic_write
from locres import MAGIC,LocRes
from deep_search import Ooz
from probe_base import ROOT,OUT

def main():
    p=ROOT/'Elliot/Content/Paks/Elliot-Windows.pak';dest=OUT/'pak-fisico';dest.mkdir(exist_ok=True)
    dec=Ooz(OUT/'tools/ooz.exe',OUT/'work')
    with p.open('rb') as f:
        f.seek(-512,2);tail=f.read();a=tail.index(struct.pack('<I',0x5a6f12e1));end=struct.unpack_from('<Q',tail,a+8)[0]
        methods=['None']+[tail[a+44+i*32:a+44+(i+1)*32].split(b'\0')[0].decode() for i in range(5)]
        print('Metodos',methods,flush=True)
        pos=0;entries=[];found=[];errors=[]
        while pos<end:
            f.seek(pos);base=f.read(48)
            if len(base)!=48:raise ValueError('Cabecalho truncado')
            if base==b'\0'*48:
                print('Padding/fronteira desconhecida: cadeia interrompida',pos,flush=True);break
            offset,compressed,length,method=struct.unpack_from('<QQQI',base)
            if offset not in (0,pos) or method>=len(methods) or compressed>p.stat().st_size or length>10*1024**3:
                print('Fim da cadeia fisica',pos,base[:20].hex(),flush=True);break
            blocks=[]
            if method:
                n=struct.unpack('<I',f.read(4))[0]
                if n>200000:raise ValueError('Blocos excessivos')
                blocks=[struct.unpack('<QQ',f.read(16)) for _ in range(n)]
            flags,blocksize=struct.unpack('<BI',f.read(5));hs=f.tell()-pos
            if flags&1:
                nextpos=pos+hs+((compressed+15)//16*16 if not blocks else sum((b-a+15)//16*16 for a,b in blocks))
            else:nextpos=pos+hs+compressed
            record=dict(offset=pos,length=length,compressed=compressed,method=methods[method],encrypted=bool(flags&1),header_size=hs,blocks=len(blocks))
            entries.append(record)
            if not flags&1 and 16<=length<=8*1024*1024:
                try:
                    parts=[];comp_parts=[]
                    for i,(lo,hi) in enumerate(blocks if method else [(hs,hs+length)]):
                        if lo<hs or hi<lo or hi>hs+compressed:raise ValueError('Intervalo de bloco inconsistente')
                        f.seek(pos+lo);raw=f.read(hi-lo);comp_parts.append(raw)
                        size=min(blocksize,length-i*blocksize) if method else length
                        if method:
                            if methods[method]=='Zlib':raw=zlib.decompress(raw)
                            elif methods[method]=='Oodle':raw=dec(raw,size)
                            else:raise ValueError('Metodo nao habilitado')
                        if len(raw)!=size:raise ValueError('Tamanho do bloco divergente')
                        parts.append(raw)
                    data=b''.join(parts)
                    if len(data)!=length:raise ValueError('Comprimento divergente')
                    if hashlib.sha1(b''.join(comp_parts)).digest()!=base[28:48]:raise ValueError('SHA1 payload divergente')
                    if data.startswith(MAGIC):
                        loc=LocRes(data);name=f'{pos:016x}.locres';atomic_write(dest/name,data)
                        found.append(dict(**record,file=name,sha256=hashlib.sha256(data).hexdigest(),version=loc.version,entries=len(loc.records),samples=[r['original'] for r in loc.records[:5]],roundtrip=True))
                        print('LocRes',name,len(loc.records),flush=True)
                    elif data[:16]==struct.pack('<4I',0xA14CEE4F,0x83554868,0xBD464C6C,0x7C50DA70):
                        atomic_write(dest/f'{pos:016x}.locmeta',data)
                    elif b'LocalizationPaths' in data or b'ProjectVersion=' in data or b'NativeCulture' in data or b'"CulturesToGenerate"' in data:
                        atomic_write(dest/f'{pos:016x}.config',data)
                except Exception as exc:errors.append(dict(offset=pos,error=type(exc).__name__+': '+str(exc)))
            if nextpos<=pos:raise ValueError('Offset sem avanco')
            pos=nextpos
            if len(entries)%500==0:print('Arquivos',len(entries),'offset',pos,'locres',len(found),'erros',len(errors),flush=True)
        atomic_write(dest/'indice-fisico.json',json.dumps(entries,indent=2).encode())
        atomic_write(dest/'locres-encontrados.json',json.dumps(found,ensure_ascii=False,indent=2).encode())
        atomic_write(dest/'erros.json',json.dumps(errors,ensure_ascii=False,indent=2).encode())
        print('Concluido',len(entries),len(found),len(errors),'ultimo',pos,'indice',end,flush=True)

if __name__=='__main__':main()
