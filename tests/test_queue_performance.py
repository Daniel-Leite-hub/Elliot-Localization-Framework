import json
import sys
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from core import Store, canonical
from provider import Provider, TranslationJob
from selfcheck import FakeSession, FakeResponse


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[1] / 'validacao-local' / ('queue-' + uuid.uuid4().hex)
        self.root.mkdir(parents=True)
        self.store = Store(self.root / 'test.sqlite')

    def tearDown(self):
        self.store.close()

    def load(self, texts):
        p = self.root / 'catalog.json'
        p.write_text(canonical(dict(format='studio-catalog-v1', entries=[dict(id=str(i), resource='scene', language='EN', original=t) for i, t in enumerate(texts)])), encoding='utf-8')
        self.store.import_catalog(p)
        return self.store.estimate()

    def test_indexed_duplicate_reuse_no_catalog_scan_per_response(self):
        estimate = self.load(['Hello {x}', 'Hello {x}', 'Goodbye {x}'])
        session = FakeSession([FakeResponse(200, json.dumps({'translations':[{'text':'<r>Olá <ph id="0">T0</ph></r>'}]})), FakeResponse(200, json.dumps({'translations':[{'text':'<r>Tchau <ph id="0">T0</ph></r>'}]}))])
        job = TranslationJob(self.store, Provider('FAKE', session=session), estimate['groups'], members=estimate['members'])
        with patch.object(self.store, 'pending', side_effect=AssertionError('full scan')), patch.object(self.store, 'prepared_pending', side_effect=AssertionError('full scan')):
            job.run()
        self.assertEqual(session.calls, 2)
        self.assertEqual(job.done, 2)
        self.assertTrue(all(r['machine'] for r in self.store.rows()))
        self.assertEqual(self.store.db.execute("select count(*) from history where event='automatica_validada'").fetchone()[0], 3)

    def test_uncertainty_stops_and_blocks_resend(self):
        estimate = self.load(['First', 'Second'])
        session = FakeSession([requests.ReadTimeout(), FakeResponse(200, '{"translations":[{"text":"<r>Segundo</r>"}]}')])
        job = TranslationJob(self.store, Provider('FAKE', session=session), estimate['groups'], members=estimate['members'])
        with patch.object(job.stop, 'wait', return_value=False): job.run()
        self.assertEqual(session.calls, 1)
        self.assertEqual([r[0] for r in self.store.db.execute('select state from requests order by id')], ['incerta'])
        self.assertEqual(len(self.store.pending()),1)

    def test_global_uncertainty_never_reaches_second_call(self):
        estimate = self.load(['First', 'Second', 'Third', 'Fourth'])
        session = FakeSession([requests.Timeout()] * 3 + [FakeResponse(200, '{"translations":[{"text":"<r>Quarto</r>"}]}')])
        job = TranslationJob(self.store, Provider('FAKE', session=session), estimate['groups'], members=estimate['members'])
        with patch.object(job.stop, 'wait', return_value=False), patch.object(job.provider, 'usage', return_value={'remaining':1000}): job.run()
        self.assertEqual(session.calls, 1)
        self.assertEqual(len(self.store.pending()), 3)
        self.assertEqual(job.completed_entries, 0)
        self.assertEqual(job.failed_entries, 1)

    def test_429_long_retry_after_and_final_status(self):
        estimate = self.load(['First'])
        session = FakeSession([FakeResponse(429, '{}', {'Retry-After':'75'})]*3 + [FakeResponse(200, '{"translations":[{"text":"<r>Primeiro</r>"}]}')])
        messages = []
        job = TranslationJob(self.store, Provider('FAKE', session=session), estimate['groups'], members=estimate['members'], notify=messages.append)
        with patch.object(job.stop, 'wait', return_value=False) as wait: job.run()
        self.assertEqual(session.calls, 4)
        self.assertGreaterEqual(wait.call_count, 3)
        self.assertEqual(self.store.db.execute('select state from requests').fetchone()[0], 'concluida')
        self.assertIn('1 unidades', messages[-1])

    def test_quota_and_character_cap_stop_without_extra_send(self):
        estimate = self.load(['First', 'Second'])
        session = FakeSession([FakeResponse(456, '{}')])
        job = TranslationJob(self.store, Provider('FAKE', session=session), estimate['groups'], members=estimate['members'])
        job.run()
        self.assertEqual(session.calls, 1)
        self.assertIn('456', job.reason)
        session2 = FakeSession([])
        job2 = TranslationJob(self.store, Provider('FAKE', session=session2), estimate['groups'], members=estimate['members'], char_cap=0)
        job2.run()
        self.assertEqual(session2.calls, 0)

    def test_snapshot_payload_preserves_existing_cache_key(self):
        estimate = self.load(['First', 'Second'])
        for key, (row, payload) in estimate['groups'].items():
            live, _, livekey, _ = self.store.payload(row)
            self.assertEqual(payload, live)
            self.assertEqual(key, livekey)

    def test_preparation_upgrade_does_not_resend_rejected_entry(self):
        estimate=self.load(['Creates a {Num:1}% chance'])
        row=self.store.rows()[0]
        with self.store.db:
            self.store.db.execute("INSERT INTO requests(cache_key,entry_id,state,payload) VALUES (?,?,?,?)",
                                  ('old-preparation-key',row['id'],'recusada','{}'))
        self.assertEqual(self.store.pending(),[])
        session=FakeSession([])
        TranslationJob(self.store,Provider('FAKE',session=session),estimate['groups'],members=estimate['members']).run()
        self.assertEqual(session.calls,0)
        rid=self.store.db.execute('SELECT id FROM requests').fetchone()[0]
        self.store.retry(rid)
        self.assertEqual(len(self.store.pending()),1)

    def test_429_bounded_preserves_every_response(self):
        estimate = self.load(['First'])
        session = FakeSession([FakeResponse(429, '{}')]*8 + [FakeResponse(200, '{"translations":[{"text":"<r>Primeiro</r>"}]}')])
        progress=[]
        job=TranslationJob(self.store,Provider('FAKE',session=session),estimate['groups'],members=estimate['members'],progress=progress.append,baseline=9,total=10)
        with patch.object(job.stop,'wait',return_value=False): job.run()
        self.assertEqual(session.calls,8)
        self.assertEqual(progress[0]['percent'],90)
        self.assertEqual(progress[-1]['percent'],90)
        self.assertEqual(self.store.db.execute('select count(*) from request_responses').fetchone()[0],8)
        self.assertGreater(self.store.setting('deepl_retry_deadline'),0)
        self.assertEqual(self.store.db.execute('select count(*) from requests').fetchone()[0],1)

    def test_uncertainty_never_counts_as_completed(self):
        estimate=self.load(['First','Second'])
        session=FakeSession([requests.Timeout(),FakeResponse(200,'{"translations":[{"text":"<r>Segundo</r>"}]}')])
        progress=[]
        job=TranslationJob(self.store,Provider('FAKE',session=session),estimate['groups'],members=estimate['members'],progress=progress.append)
        with patch.object(job.stop,'wait',return_value=False):job.run()
        self.assertEqual(progress[-1]['percent'],0)
        self.assertEqual(progress[-1]['unresolved'],1)

    def test_pause_during_429_is_responsive(self):
        estimate=self.load(['First'])
        session=FakeSession([FakeResponse(429,'{}',{'Retry-After':'3600'})])
        job=TranslationJob(self.store,Provider('FAKE',session=session),estimate['groups'],members=estimate['members'])
        def pause(seconds):
            job.pause()
            return True
        with patch.object(job.stop,'wait',side_effect=pause):job.run()
        self.assertEqual(session.calls,1)
        self.assertEqual(job.completed_entries,0)
        self.assertEqual(self.store.db.execute('select state from requests').fetchone()[0],'erro')


if __name__ == '__main__': unittest.main()
