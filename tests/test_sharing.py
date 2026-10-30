import hashlib
import json
import sqlite3
import sys
import unittest
import uuid
import zipfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from core import Store
from sharing import JoinedReader, current_locres, export_manual


class SharingTests(unittest.TestCase):
    def test_stream_zip_and_existing_destination(self):
        root = Path(__file__).resolve().parents[1] / "validacao-local" / ("sharing-" + uuid.uuid4().hex)
        root.mkdir(parents=True, exist_ok=True)
        base = root / "original.pak"
        base.write_bytes(b"BASE")
        suffix = b"SUFFIX"
        m = dict(
            base_sha256=hashlib.sha256(b"BASE").hexdigest(),
            output_sha256=hashlib.sha256(b"BASESUFFIX").hexdigest(),
            output_size=10,
        )
        with JoinedReader(base, suffix) as f:
            f.seek(-4, 2)
            self.assertEqual(f.read(), b"FFIX")
            f.seek(2)
            self.assertEqual(f.read(5), b"SESUF")
        dest = root / "manual.zip"
        with patch("sharing.prepare", return_value=(root, base, suffix, m, [])):
            export_manual(None, dest)
            self.assertRaises(ValueError, export_manual, None, dest)
        with zipfile.ZipFile(dest) as z:
            self.assertEqual(z.read("Elliot/Content/Paks/Elliot-Windows.pak"), b"BASESUFFIX")
            self.assertIn("backup", z.read("LEIA-ME.txt").decode())
            self.assertFalse(any("key.local" in p for p in z.namelist()))

    def test_current_draft_and_approval_selection(self):
        project = Path(__file__).resolve().parents[1]
        root = project / "validacao-local" / ("sharing-db-" + uuid.uuid4().hex)
        root.mkdir(parents=True, exist_ok=True)
        db = root / "fixture.sqlite"

        # Procura o banco demo ou o banco real
        db_source = project / "data" / "demo_project.sqlite"
        if not db_source.exists():
            db_source = project.parent / "FerramentaTraducao" / "projetos" / "Elliot.sqlite"
        if not db_source.exists():
            self.skipTest("Banco SQLite de referência não encontrado")

        es_source = project / "Textos_para_leitura/originais/es/Game.locres"
        if not es_source.exists():
            self.skipTest("Arquivo original Game.locres para exportação não distribuído no repositório git")

        source = sqlite3.connect("file:" + db_source.as_posix() + "?mode=ro", uri=True)
        copy = sqlite3.connect(db)
        source.backup(copy)
        copy.close()
        source.close()
        fixture = Store(db)
        try:
            row = fixture.db.execute(
                "SELECT * FROM entries WHERE active=1 AND language='EN' AND original NOT LIKE '%None%' AND instr(original,char(10))=0 AND draft IS NOT NULL LIMIT 1"
            ).fetchone()
            if row is None:
                self.skipTest("Nenhuma entrada elegível na fixture")
            fixture.edit(row["id"], "Texto de teste do compartilhamento")
            meta_data = json.loads(row["meta"])
            if "external_id" in meta_data:
                key = json.loads(meta_data["external_id"])
            else:
                self.skipTest("Entrada sem external_id")
            _, audit = current_locres(fixture, project, "reviewed")
            item = next(a for a in audit if [a["namespace"], a["key"]] == key)
            self.assertEqual(item["translation"], "Texto de teste do compartilhamento")
            self.assertEqual(item["selection"], "rascunho")
            _, audit = current_locres(fixture, project, "approved")
            item = next(a for a in audit if [a["namespace"], a["key"]] == key)
            self.assertNotEqual(item["selection"], "rascunho")
        finally:
            fixture.close()


if __name__ == "__main__":
    unittest.main()
