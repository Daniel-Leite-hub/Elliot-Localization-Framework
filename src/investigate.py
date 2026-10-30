"""Inventário integral do jogo, somente leitura e sem duplicar os contêineres."""
import json, struct, time
from pathlib import Path
from core import Store, file_hash, atomic_write

def inventory(root,store,notify=print):
    root=Path(root).resolve(); items=[]
    paths=[root/'Elliot.exe',root/'Elliot/Binaries/Win64/Elliot-Win64-Shipping.exe']
    paths+=sorted((root/'Elliot/Content/Paks').glob('*'))
    for p in paths:
        if not p.is_file():continue
        notify('Hash integral: '+p.name); detail={}
        with p.open('rb') as f:
            h=f.read(144)
            if p.suffix=='.utoc':
                detail=dict(version=h[16],entries=struct.unpack_from('<I',h,24)[0],flags=h[80],encrypted=bool(h[80]&2))
            if p.suffix=='.pak':
                f.seek(-512,2); tail=f.read(); at=tail.find(struct.pack('<I',0x5a6f12e1))
                if at>=17:detail=dict(version=struct.unpack_from('<I',tail,at+4)[0],encrypted_index=bool(tail[at-1]))
        item=dict(path=str(p.relative_to(root)),size=p.stat().st_size,sha256=file_hash(p),details=json.dumps(detail))
        items.append(item)
        with store.lock,store.db:store.db.execute('INSERT OR REPLACE INTO inventory VALUES (:path,:size,:sha256,:details)',item)
    report=dict(base=str(root),platform='Windows/Win64',engine='Unreal Engine; versão em pesquisa/probe.json',commercial_version='Não comprovada',region='Não comprovada',files=items,inspected_at=time.time(),originals_modified=False)
    store.set_setting('game_root',str(root));store.set_setting('investigation',report)
    return report

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('root');p.add_argument('database');p.add_argument('report');a=p.parse_args()
    s=Store(a.database)
    try:atomic_write(a.report,json.dumps(inventory(a.root,s),ensure_ascii=False,indent=2).encode())
    finally:s.close()
