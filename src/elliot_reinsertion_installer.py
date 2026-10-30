"""Stream a verified appendix onto the original PAK; retain original for restore."""
import json,os,shutil,sys,time,uuid
from pathlib import Path
from core import atomic_write,file_hash
from applicator import inside
from elliot_overlay_installer import running

HOME=Path(sys.executable).resolve().parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[1]/'AplicadorPTBR-v2'

def load(home=HOME):
 m=json.loads((home/'manifest.json').read_text(encoding='utf-8'))
 if m['format']!='elliot-reinsertion-v2' or m['target']!='Elliot/Content/Paks/Elliot-Windows.pak':raise ValueError('Manifesto incompatível.')
 p=inside(home,m['payload'])
 if file_hash(p)!=m['payload_sha256']:raise ValueError('Pacote de reinserção alterado.')
 return m,p

def verify(root,home=HOME):
 m,p=load(home);target=inside(root,m['target'])
 if not target.is_file():raise ValueError('PAK original ausente. Confira a pasta selecionada.')
 h=file_hash(target)
 if h not in [m['base_sha256'],m['output_sha256']]:raise ValueError('PAK incompatível ou alterado; preservado sem mudanças.')
 overlay=inside(root,'Elliot/Content/Paks/Elliot_PTBR_P.pak')
 if overlay.exists() and file_hash(overlay)!=m['old_overlay_sha256']:raise ValueError('Pacote separado desconhecido; preservado. Resolva o conflito antes de instalar.')
 return m,p,target,h

def action(root,mode,home=HOME,check_running=True):
 root=Path(root).resolve()
 if check_running and running():raise ValueError('Feche o jogo antes de instalar ou restaurar.')
 m,p,target,h=verify(root,home)
 if mode=='verify':return 'PAK compatível. Reinserção v2 substitui o texto espanhol diretamente.'
 if mode=='restore':
  if h==m['base_sha256']:return 'O PAK original já está restaurado.'
  backups=inside(root,'TraducaoBackups');candidates=[]
  for j in backups.glob('reinsercao-*/operacao.json'):
   if j.is_symlink() or j.parent.is_symlink() or j.parent.is_junction():continue
   obj=json.loads(j.read_text(encoding='utf-8'));b=inside(j.parent,'original.pak')
   if obj.get('format')=='elliot-reinsertion-operation-v2' and obj.get('base_sha256')==m['base_sha256'] and b.is_file():candidates.append((j,b,obj))
  if not candidates:raise ValueError('Backup original não localizado. Nenhum arquivo alterado.')
  j,b,obj=sorted(candidates,key=lambda t:str(t[0]))[-1]
  if file_hash(b)!=m['base_sha256']:raise ValueError('Backup original alterado; restauração bloqueada.')
  translated=inside(j.parent,'traduzido-'+str(time.time_ns())+'.pak')
  os.replace(target,translated)
  try:os.replace(b,target)
  except Exception:os.replace(translated,target);raise
  obj['state']='restaurada';atomic_write(j,json.dumps(obj,ensure_ascii=False,indent=2).encode())
  return 'PAK original restaurado. Cópia traduzida preservada em '+str(translated)
 if mode!='install':raise ValueError('Operação inválida.')
 if h==m['output_sha256']:return 'Reinserção v2 já instalada. Selecione Espanhol no jogo.'
 required=m['output_size']+64*1024*1024
 if shutil.disk_usage(target.parent).free<required:raise ValueError('Espaço insuficiente: reserve aproximadamente 4 GB livres para a preparação.')
 stage=inside(root,'Elliot/Content/Paks/.ptbr-v2-'+uuid.uuid4().hex+'.tmp')
 backup=inside(root,'TraducaoBackups/reinsercao-'+str(time.time_ns()));backup.mkdir(parents=True)
 j=backup/'operacao.json';obj=dict(format='elliot-reinsertion-operation-v2',state='preparando',base_sha256=m['base_sha256'],output_sha256=m['output_sha256'],target=m['target'])
 def log():atomic_write(j,json.dumps(obj,ensure_ascii=False,indent=2).encode())
 log()
 try:
  with target.open('rb') as source,stage.open('xb') as dest:
   shutil.copyfileobj(source,dest,8*1024*1024)
   with p.open('rb') as suffix:shutil.copyfileobj(suffix,dest,8*1024*1024)
   dest.flush();os.fsync(dest.fileno())
  if stage.stat().st_size!=m['output_size'] or file_hash(stage)!=m['output_sha256']:raise ValueError('Reconstrução divergiu do pacote; original preservado.')
  if file_hash(target)!=m['base_sha256']:raise ValueError('PAK mudou durante a preparação; original preservado.')
  if check_running and running():raise ValueError('O jogo abriu durante a preparação. Feche-o e tente novamente.')
  obj['state']='substituindo';log();original=backup/'original.pak'
  os.replace(target,original)
  try:os.replace(stage,target)
  except Exception:os.replace(original,target);raise
  overlay=inside(root,'Elliot/Content/Paks/Elliot_PTBR_P.pak')
  if overlay.exists() and file_hash(overlay)==m['old_overlay_sha256']:os.replace(overlay,backup/'overlay-antigo.pak')
  obj['state']='instalada';log()
  return 'Reinserção v2 instalada. Abra o jogo e selecione Espanhol. Backup: '+str(original)
 finally:stage.unlink(missing_ok=True)

def main():
 # Reuse the tested responsive GUI; replace its operations with v2 reinsertion.
 import elliot_overlay_installer as ui
 ui.HOME=HOME;ui.action=action;ui.verify=verify
 ui.main(reinsertion=True)

if __name__=='__main__':
 if len(sys.argv)==4 and sys.argv[1]=='--verify-report':
  m,p,target,h=verify(Path(sys.argv[2]));atomic_write(Path(sys.argv[3]),json.dumps(dict(verified=True,mode='reinsercao-v2',target=str(target),installed=h==m['output_sha256'],game_validated=False)).encode())
 else:main()
