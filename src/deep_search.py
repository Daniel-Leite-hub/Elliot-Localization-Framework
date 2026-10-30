"""Pesquisa somente leitura em PAK v11 e IoStore v3/v8; sem geração de patch."""
import collections
import hashlib
import json
import re
import struct
import subprocess
import uuid
from pathlib import Path
from core import atomic_write

class Ooz:
    def __init__(self,path,work):
        self.path=Path(path).resolve();self.work=Path(work).resolve();self.work.mkdir(parents=True,exist_ok=True)
        self.calls=0
    def __call__(self,data,size):
        name=uuid.uuid4().hex; source=self.work/(name+'.ooz');target=self.work/(name+'.raw')
        source.write_bytes(struct.pack('<Q',size)+data)
        try:
            result=subprocess.run([str(self.path),'-d',str(source),str(target)],capture_output=True,timeout=60,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            if result.returncode or not target.exists(): raise ValueError('Falha ooz: '+result.stderr.decode(errors='replace')[:200])
            output=target.read_bytes()
            if len(output)!=size: raise ValueError('ooz: tamanho divergente')
            self.calls+=1
            return output
        finally:
            source.unlink(missing_ok=True);target.unlink(missing_ok=True)

class Pak:
    def __init__(self,path,key):
        from Crypto.Cipher import AES
        self.path=path if hasattr(path,'open') and not isinstance(path,(str,Path)) else Path(path);self.key=bytes.fromhex(key.removeprefix('0x'))
        with self.path.open('rb') as stream:
            stream.seek(-512,2);tail=stream.read();at=tail.index(struct.pack('<I',0x5A6F12E1))
            version=struct.unpack_from('<I',tail,at+4)[0]
            if version!=11: raise ValueError('Somente PAK v11')
            off,size=struct.unpack_from('<QQ',tail,at+8);expected=tail[at+24:at+44]
            self.methods=['None']+[tail[at+44+i*32:at+44+(i+1)*32].split(b'\0')[0].decode() for i in range(5)]
            stream.seek(off);raw=stream.read(size)
            data=AES.new(self.key,AES.MODE_ECB).decrypt(raw) if tail[at-1] else raw
            if hashlib.sha1(data).digest()!=expected: raise ValueError('Hash do índice principal inválido')
            reader=Reader(data);mount=reader.string();count=reader.number();reader.number('Q')
            for kind in ['pathhash','directory']:
                if not reader.number(): raise ValueError('Índice secundário ausente')
                off,size=reader.number('q'),reader.number('q');expected=data[reader.pos:reader.pos+20];reader.pos+=20
                stream.seek(off);raw=stream.read(size)
                secondary=AES.new(self.key,AES.MODE_ECB).decrypt(raw) if tail[at-1] else raw
                if hashlib.sha1(secondary).digest()!=expected: raise ValueError('Hash do índice '+kind+' inválido')
                if kind=='directory': directory=secondary
            blobsize=reader.number();self.blob=data[reader.pos:reader.pos+blobsize];reader.pos+=blobsize
            if reader.number()!=0: raise ValueError('Entradas não compactas ainda não habilitadas')
        directory=Reader(directory);self.files=[]
        for _ in range(directory.number()):
            prefix=directory.string()
            for _ in range(directory.number()):
                name=directory.string();offset=directory.number('i')
                if offset<0: raise ValueError('Índice negativo não habilitado')
                self.files.append(dict(path=mount+prefix+name,entry_offset=offset,container=self.path.name,**self.entry(offset)))
        if count!=len(self.files): raise ValueError('Contagem de arquivos PAK divergente')
        self.index_hashes_verified=True

    def entry(self,offset):
        reader=Reader(self.blob);reader.pos=offset;bits=reader.number()
        blocksize=reader.number() if bits&63==63 else (bits&63)<<11
        method=(bits>>23)&63
        offset=reader.number('I' if bits&(1<<31) else 'q')
        uncompressed=reader.number('I' if bits&(1<<30) else 'q')
        compressed=reader.number('I' if bits&(1<<29) else 'q') if method else uncompressed
        encrypted=bool(bits&(1<<22));blocks=(bits>>6)&65535
        header_size=53+(4+blocks*16 if method else 0)
        blocksize=uncompressed if blocks==1 else blocksize
        cursor=offset+header_size;table=[]
        if blocks==1 and not encrypted: table=[(cursor,compressed)]
        else:
            for _ in range(blocks):
                size=reader.number();table.append((cursor,size));cursor+=(size+15)//16*16 if encrypted else size
        return dict(offset=offset,length=uncompressed,compressed_size=compressed,encrypted=encrypted,method=method,
                    compression=self.methods[method],block_size=blocksize,blocks=table,header_size=header_size)

    def read_file(self,entry,decoder=None):
        from Crypto.Cipher import AES
        output=[]
        with self.path.open('rb') as stream:
            stream.seek(entry['offset']);header=stream.read(entry['header_size'])
            size,unc,method=struct.unpack_from('<QQI',header,8)
            if (size,unc,method)!=(entry['compressed_size'],entry['length'],entry['method']): raise ValueError('Cabeçalho não confere com índice')
            blocks=entry['blocks'] if method else [(entry['offset']+entry['header_size'],entry['length'])]
            for offset,size in blocks:
                stream.seek(offset);raw=stream.read((size+15)//16*16 if entry['encrypted'] else size)
                if entry['encrypted']: raw=AES.new(self.key,AES.MODE_ECB).decrypt(raw)
                raw=raw[:size]
                if method:
                    expected=min(entry['block_size'],entry['length']-sum(len(x) for x in output))
                    if entry['compression']=='Zlib':raw=__import__('zlib').decompress(raw)
                    elif entry['compression']=='Oodle' and decoder:raw=decoder(raw,expected)
                    else:raise ValueError('Descompressor necessário: '+entry['compression'])
                    if len(raw)!=expected:raise ValueError('Bloco PAK com tamanho divergente')
                output.append(raw)
        result=b''.join(output)
        if len(result)!=entry['length']: raise ValueError('Arquivo PAK com tamanho divergente')
        return result

class Reader:
    def __init__(self,data): self.data,self.pos=data,0
    def number(self,fmt='I'):
        n=struct.calcsize('<'+fmt)
        if self.pos+n>len(self.data): raise ValueError('Índice truncado')
        value=struct.unpack_from('<'+fmt,self.data,self.pos)[0]; self.pos+=n
        return value
    def string(self):
        n=self.number('i'); size=n if n>=0 else -n*2
        if size>len(self.data)-self.pos: raise ValueError('FString truncada')
        raw=self.data[self.pos:self.pos+size]; self.pos+=size
        return (raw[:-1].decode('utf-8') if n>0 else raw[:-2].decode('utf-16-le')) if n else ''

class Toc:
    def __init__(self,path):
        self.path=Path(path); self.data=self.path.read_bytes(); d=self.data
        if d[:16]!=b'-==--==--==--==-' or d[16] not in (3,8): raise ValueError('Somente IoStore v3/v8 comprovados')
        hs,n,b,bs,mc,ml,self.block_size,ds,parts=struct.unpack_from('<9I',d,20)
        self.flags=d[80]
        if self.flags&2 or self.flags&4 or parts!=1 or bs!=12: raise ValueError('Contêiner cifrado/assinado/particionado não habilitado')
        self.chunks=[]
        for i in range(n):
            at=hs+n*12+i*10
            offset=int.from_bytes(d[at:at+5],'big'); length=int.from_bytes(d[at+5:at+10],'big')
            self.chunks.append(dict(index=i,id=d[hs+i*12:hs+(i+1)*12].hex(),offset=offset,length=length))
        at=hs+n*22
        if d[16]>=4: at+=struct.unpack_from('<I',d,84)[0]*4
        if d[16]>=5: at+=struct.unpack_from('<I',d,96)[0]*4
        self.blocks=[]
        for i in range(b):
            raw=d[at+i*12:at+(i+1)*12]
            self.blocks.append((int.from_bytes(raw[:5],'little'),int.from_bytes(raw[5:8],'little'),int.from_bytes(raw[8:11],'little'),raw[11]))
        at+=b*12
        self.methods=['None']+[d[at+i*ml:at+(i+1)*ml].split(b'\0')[0].decode() for i in range(mc)]
        at+=mc*ml; self.files=[]; self.cache=collections.OrderedDict()
        if ds:
            reader=Reader(d[at:at+ds]); mount=reader.string()
            directories=[tuple(reader.number() for _ in range(4)) for _ in range(reader.number())]
            files=[tuple(reader.number() for _ in range(3)) for _ in range(reader.number())]
            strings=[reader.string() for _ in range(reader.number())]
            if reader.pos!=ds: raise ValueError('Índice não interpretado integralmente')
            stack=[(0,mount)]; visited=set()
            while stack:
                index,parent=stack.pop()
                if index in visited: raise ValueError('Ciclo de diretórios')
                visited.add(index)
                name,child,sibling,file=directories[index]
                prefix=parent+(strings[name]+'/' if name!=0xffffffff else '')
                if sibling!=0xffffffff: stack.append((sibling,parent))
                if child!=0xffffffff: stack.append((child,prefix))
                seen=set()
                while file!=0xffffffff:
                    if file in seen: raise ValueError('Ciclo de arquivos')
                    seen.add(file)
                    name,nxt,user=files[file]
                    item=dict(self.chunks[user],path=prefix+strings[name],container=self.path.name)
                    self.files.append(item); file=nxt
            if len(self.files)!=len(files): raise ValueError('Arquivos não alcançados pelo índice')
        self.meta_offset=at+ds

    def read_chunk(self,index,decoder=None):
        chunk=self.chunks[index]; start=chunk['offset']; end=start+chunk['length']; output=[]
        with self.path.with_suffix('.ucas').open('rb') as stream:
            for block_index in range(start//self.block_size,(end+self.block_size-1)//self.block_size):
                offset,compressed,uncompressed,method=self.blocks[block_index]
                data=self.cache.get(block_index)
                if data is None:
                    stream.seek(offset); data=stream.read(compressed)
                    if len(data)!=compressed: raise ValueError('Bloco truncado')
                    if method:
                        if decoder is None: raise ValueError('Decodificador '+self.methods[method]+' necessário')
                        data=decoder(data,uncompressed)
                    self.cache[block_index]=data
                    if len(self.cache)>32:self.cache.popitem(last=False)
                else:self.cache.move_to_end(block_index)
                if len(data)!=uncompressed: raise ValueError('Tamanho descomprimido divergente')
                low=max(0,start-block_index*self.block_size)
                high=min(len(data),end-block_index*self.block_size)
                output.append(data[low:high])
        result=b''.join(output)
        if len(result)!=chunk['length']: raise ValueError('Chunk reconstruído com tamanho divergente')
        return result

def main():
    import argparse
    parser=argparse.ArgumentParser(); parser.add_argument('--root',default='Elliot/Content/Paks'); parser.add_argument('--output',default='FerramentaTraducao/pesquisa')
    args=parser.parse_args(); output=Path(args.output); output.mkdir(parents=True,exist_ok=True)
    all_files=[]; reports=[]
    for path in sorted(Path(args.root).glob('*.utoc')):
        toc=Toc(path); all_files.extend(toc.files)
        types=collections.Counter(Path(f['path']).suffix for f in toc.files)
        interesting=[f for f in toc.files if re.search(r'local|locres|locmeta|string|dialog|talk|message|text|scenario|subtitle|font|tutorial|quest|item|skill|ability',f['path'],re.I)]
        reports.append(dict(container=path.name,chunks=len(toc.chunks),files=len(toc.files),methods=toc.methods,
                            types=dict(types),interesting_count=len(interesting)))
        print(json.dumps(reports[-1]))
    atomic_write(output/'indice-completo.json',json.dumps(all_files,ensure_ascii=False,indent=2).encode())
    atomic_write(output/'candidatos.json',json.dumps([f for f in all_files if re.search(r'local|locres|locmeta|string|dialog|talk|message|text|scenario|subtitle|font|tutorial|quest|item|skill|ability',f['path'],re.I)],ensure_ascii=False,indent=2).encode())
    atomic_write(output/'resumo-indices.json',json.dumps(reports,ensure_ascii=False,indent=2).encode())

if __name__=='__main__': main()
