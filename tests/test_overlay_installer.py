import json
import sys
import uuid
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from elliot_overlay_installer import action,verify
from build_translation_patch import read_pak,OUT
from core import file_hash

class OverlayTests(unittest.TestCase):
    def test_install_restore_and_conflicts(self):
        workspace=Path(__file__).resolve().parents[1]/'validacao-local'
        tmp=workspace/('overlay-test-'+uuid.uuid4().hex)
        tmp.mkdir(parents=True, exist_ok=True)
        archive_path = OUT/'payload/Elliot_PTBR_P.pak'
        manifest_path = OUT/'manifest.json'
        if not archive_path.exists() or not manifest_path.exists():
            self.skipTest("Binários do instalador de overlay legados não empacotados no git (ver Aplicador v2)")
        root=Path(tmp)/'game';home=Path(tmp)/'bundle';root.mkdir();home.mkdir()
        (root/'Elliot/Content/Paks').mkdir(parents=True)
        (root/'Elliot.exe').write_bytes(b'fixture base')
        (home/'payload').mkdir();payload=home/'payload/Elliot_PTBR_P.pak';payload.write_bytes(archive_path.read_bytes())
        m=json.loads(manifest_path.read_text(encoding='utf-8'));m['base_checks']=[dict(target='Elliot.exe',sha256=file_hash(root/'Elliot.exe'))]
        (home/'manifest.json').write_text(json.dumps(m),encoding='utf-8')
        action(root,'install',home,False);target=root/m['target'];self.assertEqual(file_hash(target),m['sha256'])
        self.assertIn('já está instalada',action(root,'install',home,False))
        action(root,'restore',home,False);self.assertFalse(target.exists());self.assertEqual((root/'Elliot.exe').read_bytes(),b'fixture base')
        target.write_bytes(b'foreign');self.assertRaises(ValueError,verify,root,home);self.assertEqual(target.read_bytes(),b'foreign')
        target.unlink();(root/'Elliot.exe').write_bytes(b'wrong base');self.assertRaises(ValueError,verify,root,home)
        (root/'Elliot.exe').write_bytes(b'fixture base');payload.write_bytes(b'corrupt');self.assertRaises(ValueError,verify,root,home)

    def test_real_archive_integrity(self):
        archive_path = OUT/'payload/Elliot_PTBR_P.pak'
        if not archive_path.exists():
            self.skipTest("Arquivo de overlay local não distribuído no repositório público (ver Aplicador v2 atômico)")
        path,payload=read_pak(archive_path.read_bytes())
        self.assertEqual(path,'../../../Elliot/Content/Localization/Game/es/Game.locres')
        from locres import LocRes
        self.assertEqual(len(LocRes(payload).records),16914)

if __name__=='__main__':unittest.main()
