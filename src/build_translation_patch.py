"""Build a separate localization overlay; never modifies the editorial database."""
import collections, hashlib, json, sqlite3, struct
from pathlib import Path
from core import atomic_write, validate, file_hash
from locres import LocRes, fstring
from deep_search import Reader

PROJECT=Path(__file__).resolve().parents[1]
OUT=PROJECT/'AplicadorPTBR'

def pak(payload):
    # Uncompressed PAK v3 entry and legacy full index. No encryption or signing.
    entry=struct.pack('<QQQI',0,len(payload),len(payload),0)+hashlib.sha1(payload).digest()+struct.pack('<BI',0,0)
    index=fstring('../../../Elliot/Content/')+struct.pack('<I',1)+fstring('Localization/Game/es/Game.locres')+entry
    offset=len(entry)+len(payload)
    return entry+payload+index+struct.pack('<IIQQ',0x5a6f12e1,3,offset,len(index))+hashlib.sha1(index).digest()

def read_pak(data):
    magic,version,off,size=struct.unpack_from('<IIQQ',data,len(data)-44)
    assert magic==0x5a6f12e1 and version==3 and off+size==len(data)-44
    index=data[off:off+size];assert hashlib.sha1(index).digest()==data[-20:]
    r=Reader(index);mount=r.string();assert r.number()==1;path=r.string()
    start,length,unc,method=struct.unpack_from('<QQQI',index,r.pos)
    header=index[r.pos:r.pos+53];assert r.pos+53==len(index) and method==0 and length==unc and data[start:start+53]==header
    payload=data[start+53:start+53+length];assert hashlib.sha1(payload).digest()==header[28:48] and start+53+length==off
    return mount+path,payload

def main():
    OUT.mkdir(exist_ok=True);(OUT/'payload').mkdir(exist_ok=True)
    es=LocRes((PROJECT/'Textos_para_leitura/originais/es/Game.locres').read_bytes())
    en=LocRes((PROJECT/'Textos_para_leitura/originais/en/Game.locres').read_bytes())
    db=sqlite3.connect(f'file:{(PROJECT/"projetos/Elliot.sqlite").as_posix()}?mode=ro',uri=True);db.row_factory=sqlite3.Row
    entries={tuple(json.loads(json.loads(r['meta'])['external_id'])):dict(r) for r in db.execute("SELECT * FROM entries WHERE active=1 AND language='EN'")};db.close()
    source={(r['namespace'],r['key']):r for r in en.records};replacements={};audit=[]
    for record in es.records:
        key=(record['namespace'],record['key']);s=source[key];r=entries[key]
        assert record['source_crc']==s['source_crc'] and s['original']==r['original']
        orig=r['original'];preserve=orig=='None' or any('\u3040'<=c<='\u30ff' or '\u4e00'<=c<='\u9fff' for c in orig) or r['kind']!='traduzivel'
        text=orig if preserve else r['draft'] if r['draft'] is not None else r['approved'] if r['approved'] is not None else r['machine'] if r['machine'] is not None else orig
        errors,warnings=validate(orig,text,json.loads(r['meta']).get('restrictions'))
        if errors:raise ValueError((key,errors))
        replacements[key]=text
        audit.append(dict(namespace=key[0],key=key[1],source_crc=s['source_crc'],selection='original_preservado' if preserve else 'rascunho_revisado' if r['draft'] is not None else 'outra_selecao',translation=text))
    payload=es.build(replacements);parsed=LocRes(payload)
    assert [(r['namespace'],r['key'],r['source_crc']) for r in parsed.records]==[(r['namespace'],r['key'],r['source_crc']) for r in es.records]
    assert all(r['original']==replacements[r['namespace'],r['key']] for r in parsed.records)
    archive=pak(payload);path,extracted=read_pak(archive)
    assert path=='../../../Elliot/Content/Localization/Game/es/Game.locres' and extracted==payload
    name='Elliot_PTBR_P.pak';atomic_write(OUT/'payload'/name,archive)
    inventory=json.loads((PROJECT/'relatorios/inventario.json').read_text(encoding='utf-8'))
    checks=[dict(target=r['path'],sha256=r['sha256']) for r in inventory['files'] if r['path'].endswith('.exe') or r['path'].endswith('Elliot-Windows.pak')]
    for c in checks:assert file_hash(PROJECT.parent/c['target'])==c['sha256']
    manifest=dict(format='elliot-overlay-v1',name='Elliot PT-BR — localização sobre espanhol',game_validated=False,base_checks=checks,target='Elliot/Content/Paks/'+name,payload='payload/'+name,sha256=hashlib.sha256(archive).hexdigest(),entries=len(audit),selections=dict(collections.Counter(a['selection'] for a in audit)),language='es',structural_validation=True)
    for name,obj in [('manifest.json',manifest),('selecao-textos.json',audit)]:atomic_write(OUT/name,json.dumps(obj,ensure_ascii=False,indent=2).encode())
    print(json.dumps(manifest,ensure_ascii=False))

if __name__=='__main__':main()
