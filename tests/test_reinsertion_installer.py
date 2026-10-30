import hashlib
import json
import sys
import unittest
import uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from elliot_reinsertion_installer import action,verify

class ReinsertionTests(unittest.TestCase):
 def test_backup_install_restore_and_rejections(self):
  workspace=Path(__file__).resolve().parents[1]/'validacao-local'
  root=workspace/('reinsercao-teste-'+uuid.uuid4().hex);home=root/'bundle';home.mkdir(parents=True)
  (root/'Elliot/Content/Paks').mkdir(parents=True);(home/'payload').mkdir()
  base=b'original-pak-fixture';suffix=b'new-entry-and-index-fixture';digest=lambda data:hashlib.sha256(data).hexdigest()
  target=root/'Elliot/Content/Paks/Elliot-Windows.pak';target.write_bytes(base)
  payload=home/'payload/reinsercao.bin';payload.write_bytes(suffix)
  overlay=root/'Elliot/Content/Paks/Elliot_PTBR_P.pak';overlay.write_bytes(b'old overlay')
  m=dict(format='elliot-reinsertion-v2',target='Elliot/Content/Paks/Elliot-Windows.pak',base_sha256=digest(base),output_sha256=digest(base+suffix),output_size=len(base+suffix),payload='payload/reinsercao.bin',payload_sha256=digest(suffix),old_overlay_sha256=digest(b'old overlay'))
  (home/'manifest.json').write_text(json.dumps(m),encoding='utf-8')
  action(root,'install',home,False);self.assertEqual(target.read_bytes(),base+suffix);self.assertFalse(overlay.exists())
  backups=list((root/'TraducaoBackups').glob('reinsercao-*/original.pak'));self.assertEqual(len(backups),1);self.assertEqual(backups[0].read_bytes(),base)
  self.assertIn('já instalada',action(root,'install',home,False))
  action(root,'restore',home,False);self.assertEqual(target.read_bytes(),base)
  payload.write_bytes(b'broken');self.assertRaises(ValueError,verify,root,home);self.assertEqual(target.read_bytes(),base)
  payload.write_bytes(suffix);target.write_bytes(b'foreign');self.assertRaises(ValueError,verify,root,home);self.assertEqual(target.read_bytes(),b'foreign')

if __name__=='__main__':unittest.main()
