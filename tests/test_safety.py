import json
import sys
import threading
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from core import Store,canonical,prepare,restore,validate
from provider import TranslationJob,Provider
from selfcheck import FakeSession
from elliot_tables import StringTable

class SafetyTests(unittest.TestCase):
    def setUp(self):
        self.root=Path(__file__).resolve().parents[1]/'validacao-local'/('safety-'+uuid.uuid4().hex)
        self.root.mkdir(parents=True);self.path=self.root/'project.sqlite';self.store=Store(self.path)
        self.catalog=self.root/'catalog.json'
    def tearDown(self):self.store.close()
    def load(self,entries):
        self.catalog.write_text(canonical(dict(format='studio-catalog-v1',entries=entries)),encoding='utf-8')
        self.store.import_catalog(self.catalog)
    def test_source_english_never_sends_native_japanese(self):
        self.load([dict(id='k',original='こんにちは',language='JA',resource='r')])
        self.store.set_setting('source_language','EN')
        self.assertEqual(self.store.estimate()['network'],0)
    def test_printf_types_and_positional_order_preserved(self):
        text='Value %2$*3$.*4$lld / %zu / %1$s / %%'
        xml,markers=prepare(text)
        self.assertEqual(markers,['%2$*3$.*4$lld','%zu','%1$s','%%'])
        self.assertEqual(restore(xml,markers),text)
        self.assertTrue(validate(text,text.replace('%zu','%d'))[0])
    def test_invalid_xml_isolated_before_spending(self):
        self.load([dict(id=str(i),original=t,language='EN',resource='r') for i,t in enumerate(['Bad\x01','Valid'])])
        estimate=self.store.estimate();self.assertEqual(estimate['entries'],1)
        self.assertIn('XML',self.store.rows()[0]['exclusion'])
    def test_preparation_pause_no_payloads(self):
        self.load([dict(id='k',original='Valid',language='EN',resource='r')]);stop=threading.Event();stop.set()
        self.assertEqual(self.store.estimate(stop=stop)['network'],0)
    def test_raw_200_recovered_after_interruption_without_network(self):
        self.load([dict(id='k',original='Hello {x}',language='EN',resource='r')]);row=self.store.rows()[0];payload,_,key,_=self.store.payload(row)
        raw=json.dumps(dict(translations=[dict(text='<r>Olá <ph id="0">T0</ph></r>')]))
        with self.store.db:self.store.db.execute('INSERT INTO requests(cache_key,entry_id,state,payload,raw,http_status) VALUES (?,?,?,?,?,?)',(key,row['id'],'enviando',canonical(payload),raw,200))
        self.store.close();self.store=Store(self.path)
        self.assertEqual(self.store.rows()[0]['machine'],'Olá {x}')
        self.assertEqual(self.store.db.execute('SELECT state FROM requests').fetchone()[0],'concluida')
    def test_persistent_429_wait_paused_before_send(self):
        self.load([dict(id='k',original='Hello',language='EN',resource='r')]);estimate=self.store.estimate()
        self.store.set_setting('deepl_retry_deadline',__import__('time').time()+3600)
        session=FakeSession([]);job=TranslationJob(self.store,Provider('FAKE',session=session),estimate['groups'],members=estimate['members'])
        with patch.object(job,'wait',return_value=True):job.run()
        self.assertEqual(session.calls,0)
    def test_actual_native_tables_roundtrip_and_unicode(self):
        base=Path(__file__).resolve().parents[1]/'pesquisa/extraidos/Elliot/Content/Data/MessageText'
        if not base.exists():self.skipTest('Bases locais não distribuídas')
        count=0
        for p in base.glob('ST_*.uasset'):
            data=p.read_bytes();table=StringTable(data);self.assertEqual(table.build({}),data)
            row=next((r for r in table.records if r['original']),None)
            if row:
                output=StringTable(table.build({row['key']:'AÇÃO: çãõáéíóúâêô'}))
                self.assertEqual(next(r['original'] for r in output.records if r['key']==row['key']),'AÇÃO: çãõáéíóúâêô')
            count+=1
        self.assertEqual(count,22)

if __name__=='__main__':unittest.main()
