"""Adaptador estreito das StringTables Zen de Elliot desta base.

Lê o export único, pares namespace/chave/FString e metadata. Conserva o restante.
Não habilita reinserção em IoStore: dependências/container ainda não comprovados.
"""
import struct,json,hashlib,collections
from pathlib import Path
from locres import fstring
from core import atomic_write,Store,canonical

class StringTable:
    def __init__(self,data):
        self.data=data;self.records=[]
        if len(data)<88 or struct.unpack_from('<I',data)[0]!=0:raise ValueError('Resumo Zen não habilitado')
        self.header=struct.unpack_from('<I',data,4)[0]
        self.export_at,self.bundle_at=struct.unpack_from('<II',data,32)
        if self.bundle_at-self.export_at!=72:raise ValueError('Exigido export único')
        serial_offset,self.serial_size=struct.unpack_from('<QQ',data,self.export_at)
        if serial_offset!=0 or self.header+self.serial_size+4!=len(data):raise ValueError('Comprimentos não comprovados')
        if data[self.header:self.header+6]!=b'\0\1\0\0\0\0' or data[-4:]!=b'\xc1\x83\x2a\x9e':raise ValueError('Propriedades/trailer não habilitados')
        self.pos=self.header+6
        self.namespace=self.string()[0]
        seen=set()
        for i in range(self.count()):
            key,_,_=self.string();text,start,end=self.string()
            if key in seen:raise ValueError('Chave duplicada')
            seen.add(key);self.records.append(dict(key=key,original=text,offset=start,span=(start,end),position=i))
        self.metadata_at=self.pos;metadata=[]
        for _ in range(self.count()):
            key,_,_=self.string();values=[]
            for _ in range(self.count()):
                name=self.data[self.pos:self.pos+8];self.pos+=8
                value,_,_=self.string();values.append(dict(name_raw=name.hex(),value=value))
            metadata.append(dict(key=key,values=values))
        self.metadata=metadata
        if self.pos!=len(data)-4:raise ValueError('Dados adicionais não interpretados')
        if self.build({})!=data:raise ValueError('Roundtrip divergente')

    def count(self):
        if self.pos+4>len(self.data):raise ValueError('Contagem truncada')
        n=struct.unpack_from('<I',self.data,self.pos)[0];self.pos+=4
        if n>200000:raise ValueError('Contagem excessiva')
        return n

    def string(self):
        start=self.pos
        if self.pos+4>len(self.data):raise ValueError('FString truncada')
        n=struct.unpack_from('<i',self.data,self.pos)[0];self.pos+=4
        size=n if n>=0 else -n*2
        if size>len(self.data)-self.pos:raise ValueError('FString excede arquivo')
        raw=self.data[self.pos:self.pos+size];self.pos+=size
        if not n:return '',start,self.pos
        terminator=b'\0' if n>0 else b'\0\0'
        if not raw.endswith(terminator):raise ValueError('FString sem terminador')
        text=raw[:-len(terminator)].decode('utf-8' if n>0 else 'utf-16-le')
        if '\0' in text:raise ValueError('NUL interno')
        return text,start,self.pos

    def build(self,replacements):
        if set(replacements)-{r['key'] for r in self.records}:raise ValueError('Chave desconhecida')
        result=[];cursor=0
        for r in self.records:
            a,b=r['span'];result.append(self.data[cursor:a])
            text=replacements.get(r['key'],r['original'])
            result.append(self.data[a:b] if text==r['original'] else fstring(text));cursor=b
        result.append(self.data[cursor:]);out=bytearray(b''.join(result))
        struct.pack_into('<Q',out,self.export_at+8,self.serial_size+len(out)-len(self.data))
        return bytes(out)

def audit(root,database):
    root=Path(root);project=Path(database);entries=[];files=[];errors=[];proofs=[]
    for p in sorted(root.rglob('ST_*.uasset')):
        if '/MessageText' not in p.as_posix():continue
        try:
            data=p.read_bytes();table=StringTable(data);trial='MessageTextTrial' in p.parts
            resource=p.relative_to(root).as_posix();sha=hashlib.sha256(data).hexdigest()
            files.append(dict(resource=resource,namespace=table.namespace,entries=len(table.records),sha256=sha,roundtrip=True,trial=trial,metadata=table.metadata))
            for r in table.records:
                entries.append(dict(id=canonical([table.namespace,r['key']]),resource=resource,language='JA',original=r['original'],category=('ensaio-trial/' if trial else 'nativo/')+table.namespace,
                    restrictions={'encoding':'utf-16-le'},context=f"Referência nativa japonesa; namespace {table.namespace}; chave {r['key']}; offset {r['offset']}; SHA256 {sha}. Não usar como fonte inglesa. Sequência narrativa não comprovada."))
            r=next((r for r in table.records if r['original']),None)
            if r:
                text='Ação, coração, bênção. ÇÃÕÁÉÍÓÚÂÊÔ — teste de armazenamento.'
                modified=table.build({r['key']:text});reread=StringTable(modified)
                assert next(x['original'] for x in reread.records if x['key']==r['key'])==text
                proofs.append(dict(resource=resource,key=r['key'],roundtrip_sha256=sha,modified_reread=True,unicode_storage=True,game_reinsertion=False,font_rendering=False))
        except Exception as exc:errors.append(dict(resource=str(p),error=str(exc)))
    catalog=project.parent/'catalogo-nativo-auditoria.json'
    atomic_write(catalog,canonical(dict(format='studio-catalog-v1',entries=entries)).encode())
    store=Store(project)
    try:
        store.import_catalog(catalog)
        with store.lock,store.db:
            store.db.execute("UPDATE entries SET kind='tecnica',exclusion='Referência japonesa. Fonte principal autorizada: inglês, ainda cifrado no PAK.'")
        store.set_setting('name','Elliot — referência nativa (envios bloqueados)')
        store.set_setting('source_language','EN')
        store.set_setting('notes','Catálogo de auditoria japonesa. Não substitui a fonte inglesa; nenhuma tradução/ aprovação realizada.')
    finally:store.close()
    report=dict(files=files,entries=len(entries),errors=errors,modified_proofs=proofs,counts=dict(collections.Counter(e['category'] for e in entries)),english_entries=0,deepl_calls=0,game_modified=False)
    atomic_write(project.parent.parent/'relatorios'/'tabelas-nativas.json',json.dumps(report,ensure_ascii=False,indent=2).encode())
    return report

if __name__=='__main__':
    import sys
    result=audit(sys.argv[1],sys.argv[2]);print(json.dumps({k:v for k,v in result.items() if k not in ('files','modified_proofs','counts')},ensure_ascii=True))
