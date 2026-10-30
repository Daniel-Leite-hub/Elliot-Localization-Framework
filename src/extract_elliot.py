"""Retoma a pesquisa PAK com uma chave local validada; não altera o jogo."""
import argparse,hashlib,json,re
from pathlib import Path
from core import Store,atomic_write,canonical
from deep_search import Pak,Ooz
from locres import LocRes

def extract(root,database,key_file,output,notify=print,stop=None):
    root=Path(root).resolve();output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    key=Path(key_file).read_text().strip()
    if not re.fullmatch(r'(?:0x)?[0-9a-fA-F]{64}',key):raise ValueError('Exigida chave AES de 32 bytes hexadecimal.')
    pak=Pak(root/'Elliot/Content/Paks/Elliot-Windows.pak',key)
    atomic_write(output/'indice-pak.json',json.dumps(pak.files,ensure_ascii=False,indent=2).encode())
    dec=Ooz(output.parent/'pesquisa/tools/ooz.exe',output/'work')
    records=[];resources=[];files=[];errors=[]
    selected=[x for x in pak.files if '/Localization/' in x['path'] or '/Fonts/' in x['path'] or '/Font/' in x['path'] or x['path'].lower().endswith(('.ini','.uproject','.locres','.locmeta'))]
    for i,item in enumerate(selected,1):
        if stop and stop.is_set():break
        relative=item['path'].removeprefix('../../../');target=output/'extraidos'/relative
        if not target.resolve().is_relative_to((output/'extraidos').resolve()):raise ValueError('Caminho inseguro')
        try:
            data=pak.read_file(item,dec);sha=hashlib.sha256(data).hexdigest();atomic_write(target,data)
            record=dict(path=relative,sha256=sha,size=len(data),offset=item['offset']);files.append(record)
            if not relative.endswith('.locres'):continue
            loc=LocRes(data);language=target.parent.name
            if language.lower() in ('en','en-us','en-gb'):language='EN'
            resources.append(dict(path=relative,language=language,parsed=loc,data=data,sha256=sha))
            record.update(locres_version=loc.version,entries=len(loc.records),roundtrip=True)
        except Exception as exc:errors.append(dict(path=relative,error=type(exc).__name__+': '+str(exc)))
        if i%100==0:notify(f'Extração: {i}/{len(selected)}; {len(resources)} LocRes; {len(errors)} erros.')
    auxiliaries={}
    for resource in resources:
        if resource['language']=='EN':continue
        scope=Path(resource['path']).parent.parent.as_posix()+'/'+Path(resource['path']).name
        for r in resource['parsed'].records:
            auxiliaries.setdefault((scope,r['namespace'],r['key'],r['source_crc']),{})[resource['language']]=dict(text=r['original'],resource=resource['path'],source_crc=r['source_crc'])
    english=[r for r in resources if r['language']=='EN']
    for resource in english:
        scope=Path(resource['path']).parent.parent.as_posix()+'/'+Path(resource['path']).name
        for r in resource['parsed'].records:
            records.append(dict(id=canonical([r['namespace'],r['key']]),resource=resource['path'],language='EN',original=r['original'],category='locres-ingles',restrictions={'encoding':'utf-16-le'},
                context='Namespace: '+r['namespace']+'; chave: '+r['key']+'; CRC origem: '+str(r['source_crc'])+'; sequência narrativa não comprovada.',auxiliary=auxiliaries.get((scope,r['namespace'],r['key'],r['source_crc']),{})))
    catalog=output/'catalogo-ingles.json';atomic_write(catalog,canonical(dict(format='studio-catalog-v1',entries=records)).encode())
    store=Store(database)
    try:
        store.backup(store.path.parent/('backup-pre-extracao-'+str(__import__('time').time_ns())+'.sqlite'))
        store.import_catalog(catalog);store.set_setting('source_language','EN')
        with store.lock,store.db:
            for r in english:store.db.execute('INSERT OR REPLACE INTO resources VALUES (?,?,?,?)',(r['path'],r['sha256'],'locres-standard',r['data']))
        report=dict(format='elliot-extraction-v1',files=files,errors=errors,english_entries=len(records),english_resources=len(english),selected=len(selected),completed=len(files)+len(errors),game_modified=False,coverage='Recursos LocRes ingleses extraídos; texto em imagens, vídeos e categorias adicionais não comprova cobertura completa.')
        store.set_setting('extraction',report)
    finally:store.close()
    atomic_write(output/'resumo.json',json.dumps(report,ensure_ascii=False,indent=2).encode());return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--database',required=True);p.add_argument('--key-file',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    extract(a.root,a.database,a.key_file,a.output)
