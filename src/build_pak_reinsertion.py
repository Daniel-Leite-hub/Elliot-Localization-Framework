"""Append one encrypted Spanish resource and a relocated primary index."""
import hashlib,json,struct,shutil,time
from pathlib import Path
from Crypto.Cipher import AES
from deep_search import Pak,Reader
from locres import LocRes
from build_translation_patch import read_pak
from core import atomic_write,file_hash

P=Path(__file__).resolve().parents[1];ROOT=P.parent;OUT=P/'AplicadorPTBR-v2'
def main():
 OUT.mkdir(exist_ok=True);(OUT/'payload').mkdir(exist_ok=True)
 base=ROOT/'Elliot/Content/Paks/Elliot-Windows.pak'
 key=(P/'pesquisa/archive-key.local').read_text().strip()
 old=Pak(base,key);entry=next(e for e in old.files if e['path']=='../../../Elliot/Content/Localization/Game/es/Game.locres')
 _,payload=read_pak((P/'AplicadorPTBR/payload/Elliot_PTBR_P.pak').read_bytes());loc=LocRes(payload)
 inventory=json.loads((P/'relatorios/inventario.json').read_text(encoding='utf-8'));expected=next(e['sha256'] for e in inventory['files'] if e['path'].endswith('Elliot-Windows.pak'))
 assert file_hash(base)==expected
 with base.open('rb') as f:
  f.seek(-221,2);footer=bytearray(f.read());assert struct.unpack_from('<II',footer,17)==(0x5a6f12e1,11)
  off,size=struct.unpack_from('<QQ',footer,25);f.seek(off);raw=f.read(size)
 aes=AES.new(bytes.fromhex(key.removeprefix('0x')),AES.MODE_ECB)
 index=bytearray(aes.decrypt(raw) if footer[16] else raw)
 r=Reader(index);r.string();r.number();r.number('Q')
 for _ in range(2):assert r.number()==1;r.pos+=36
 blobsize=r.number();blobstart=r.pos
 offset=base.stat().st_size;pad=b'\0'*((-offset)%16);offset+=len(pad)
 assert offset<2**32 and len(payload)<2**32
 pos=blobstart+entry['entry_offset'];assert entry['entry_offset']+12<=blobsize
 # Keep all other encoded entry offsets and both secondary indices unchanged.
 index[pos:pos+12]=struct.pack('<III',(1<<31)|(1<<30)|(1<<29)|(1<<22),offset,len(payload))
 header=struct.pack('<QQQI',0,len(payload),len(payload),0)+hashlib.sha1(payload).digest()+struct.pack('<BI',1,0)
 encrypted=aes.encrypt(payload+b'\0'*((-len(payload))%16))
 index_offset=offset+len(header)+len(encrypted)
 index_bytes=aes.encrypt(bytes(index)) if footer[16] else bytes(index)
 struct.pack_into('<QQ',footer,25,index_offset,len(index_bytes));footer[41:61]=hashlib.sha1(index).digest()
 suffix=pad+header+encrypted+index_bytes+footer
 atomic_write(OUT/'payload/reinsercao.bin',suffix)
 stage=P/'validacao-local'/('pak-reinsercao-'+str(time.time_ns())+'.pak')
 assert stage.resolve().is_relative_to((P/'validacao-local').resolve())
 try:
  with base.open('rb') as source,stage.open('xb') as target:shutil.copyfileobj(source,target,8*1024*1024);target.write(suffix)
  new=Pak(stage,key);assert len(new.files)==len(old.files)
  differences=[]
  for a,b in zip(old.files,new.files):
   if a!=b:
    # Container name differs for the temporary staging file only.
    ca={k:v for k,v in a.items() if k!='container'};cb={k:v for k,v in b.items() if k!='container'}
    if ca!=cb:differences.append(a['path'])
  assert differences==[entry['path']],differences
  rebuilt=next(e for e in new.files if e['path']==entry['path']);assert new.read_file(rebuilt)==payload
  result_hash=file_hash(stage)
  manifest=dict(format='elliot-reinsertion-v2',game_validated=False,target='Elliot/Content/Paks/Elliot-Windows.pak',base_sha256=expected,base_size=base.stat().st_size,output_sha256=result_hash,output_size=stage.stat().st_size,payload='payload/reinsercao.bin',payload_sha256=hashlib.sha256(suffix).hexdigest(),old_overlay_sha256='1210fe485a19503d439f0a53de4451235f79a5ea90c835801e6e23c1dfe2732b',entries=len(loc.records),index_hashes_verified=True,only_changed_archive_entry=entry['path'])
  atomic_write(OUT/'manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2).encode())
  print(json.dumps(manifest,ensure_ascii=False))
 finally:stage.unlink(missing_ok=True)

if __name__=='__main__':main()
