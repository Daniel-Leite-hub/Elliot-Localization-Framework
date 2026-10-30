"""Verificações locais executáveis também no EXE. Nenhuma chamada real ao DeepL."""
import json
import sqlite3
import struct
import contextlib
import uuid
import requests
from pathlib import Path
from core import Store, VERSION, canonical, prepare, restore, validate, atomic_write
from locres import LocRes, MAGIC, fstring, import_locres, generate_locres
from provider import Provider, TranslationJob


def fixture(version):
    prefix = (MAGIC + bytes([version])) if version else b''
    if version:
        prefix += b'\0'*8
    if version >= 2:
        prefix += struct.pack('<I', 2)
    prefix += struct.pack('<I', 1)
    if version >= 2:
        prefix += struct.pack('<I', 456)
    prefix += fstring('Test') + struct.pack('<I', 2)
    for i in range(2):
        if version >= 2: prefix += struct.pack('<I', 100+i)
        prefix += fstring('key'+str(i)) + struct.pack('<I', 321+i)
        prefix += struct.pack('<i', 0) if version else fstring('Hello {name}!\nYes.')
    if version:
        prefix=bytearray(prefix)
        struct.pack_into('<q',prefix,17,len(prefix))
        prefix=bytes(prefix)+struct.pack('<I',1)+fstring('Hello {name}!\nYes.')
        if version>=2: prefix+=struct.pack('<i',2)
    return prefix


class FakeResponse:
    def __init__(self, status, text, headers=None):
        self.status_code,self.text,self.headers=status,text,headers or {}


class FakeSession:
    def __init__(self, responses):
        self.responses=list(responses); self.headers={}; self.calls=0
    def post(self,*args,**kwargs):
        self.calls+=1
        response=self.responses.pop(0)
        if isinstance(response,Exception): raise response
        return response
    def close(self): pass


@contextlib.contextmanager
def test_directory():
    directory = Path.cwd() / 'validacao-local' / ('teste-' + uuid.uuid4().hex)
    directory.mkdir(parents=True, exist_ok=False)
    # Conserva fixtures/resultados para auditoria. Evita ACL especial de tempfile no Windows.
    yield str(directory)


def run():
    checks=[]
    def check(name, condition):
        if not condition: raise AssertionError(name)
        checks.append(name)
    # Diretório dentro da pasta de execução para funcionar também em sandbox e pacote portátil.
    with test_directory() as directory:
        root=Path(directory)
        source='Hello {name}!\n<color=red>Yes</color> %02d \\n'
        xml,markers=prepare(source)
        check('XML: roundtrip de comandos e quebras',restore(xml,markers)==source)
        icon_source='Use \ue0c1 to walk.'
        icon_xml,icon_markers=prepare(icon_source)
        check('Ícones PUA: proteção e roundtrip',icon_markers==['\ue0c1'] and restore(icon_xml,icon_markers)==icon_source)
        check('Ícones PUA: perda bloqueia',bool(validate(icon_source,'Use to walk.')[0]))
        try: restore(xml.replace('id="0"','id="9"'),markers)
        except ValueError: rejected=True
        else: rejected=False
        check('XML: alteração de marcador recusada',rejected)
        check('Validação: marcador faltante bloqueia',bool(validate(source,'Olá!')[0]))
        check('Acentos: UTF-8 aceito',not validate('Hello','Ação, coração, ÓTIMO!')[0])
        check('Capacidade: limite em bytes bloqueia',bool(validate('x','ação',{'max_bytes':3})[0]))
        for version in range(4):
            base=fixture(version)
            parsed=LocRes(base)
            check(f'LocRes v{version}: reconstrução byte a byte',parsed.build({})==base)
            output=parsed.build({('Test','key0'):'Olá {name}!\nSim. çãõáéíóúâêô'})
            records=LocRes(output).records
            check(f'LocRes v{version}: expansão/acentos e chave independente',records[0]['original'].startswith('Olá') and records[1]['original']=='Hello {name}!\nYes.')
        path=root/'catalog.json'
        items=[dict(id=str(i),resource='scene',language='EN',original='Hello {name}!',speaker='Alice',sequence='s',sequence_proof='fixture confirmada',ordinal=i) for i in range(3)]
        items.append(dict(id='tech',resource='scene',language='EN',original='{name}'))
        atomic_write(path,canonical(dict(format='studio-catalog-v1',entries=items)).encode())
        store=Store(root/'test.sqlite')
        try:
            check('Importação transacional e classificação',store.import_catalog(path)==4 and len(store.pending())==3)
            row=store.rows()[1]
            store.set_setting('before',1); store.set_setting('after',1)
            context,evidence=store.context(row)
            check('Contexto: vizinhos comprovados',context.count('Hello')==2 and len(evidence)==2)
            key=store.payload(row)[2]
            store.set_setting('general_context','Verified fact')
            check('Cache: contexto altera chave',key!=store.payload(row)[2])
            store.edit(row['id'],'Olá {name}!',approve=True)
            store.edit(row['id'],'RASCUNHO {name}!')
            check('Prioridade: rascunho excluído da geração',store.select(store.entry(row['id']))[0]=='Olá {name}!')
            store.export(root/'export.json')
            check('Exportação: relida e seleção persistente',store.entry(row['id'])['selected_kind']=='aprovada')
            store.backup(root/'backup.sqlite')
            backup=sqlite3.connect(root/'backup.sqlite')
            check('Backup WAL: dados e integridade',backup.execute('PRAGMA integrity_check').fetchone()[0]=='ok' and backup.execute('SELECT count(*) FROM entries').fetchone()[0]==4)
            backup.close()
            items[1]['original']='Goodbye {name}!'
            atomic_write(path,canonical(dict(format='studio-catalog-v1',entries=items)).encode())
            store.import_catalog(path)
            try: store.select(store.entry(row['id']))
            except ValueError: blocked=True
            else: blocked=False
            check('Nova base: aprovação afetada bloqueia',blocked)
            # Recurso real de teste é gerado, importado, aprovado e relido pelo mesmo código distribuído.
            loc=root/'test.locres'; loc.write_bytes(fixture(3))
            count,_=import_locres(store,loc,'EN')
            locrow=next(r for r in store.rows() if r['category']=='locres')
            store.edit(locrow['id'],'Olá {name}!\nSim.',approve=True)
            # Aprovação antiga afetada em outro recurso não interfere nesta geração de recurso.
            report=generate_locres(store,root/'generated')
            check('Gerador: arquivo gravado/reaberto e hashes',count==2 and report['resources'][0]['reread'])
            check('Projeto: segundo processo bloqueado',lock_check(store.path))
        finally: store.close()
        # Fila isolada e determinística, sem contexto: três textos = três unidades.
        queue_path=root/'queue.json'
        entries=[dict(id=str(i),resource='queue',language='EN',original=t) for i,t in enumerate(['One {x}','Two {x}','Three {x}'])]
        atomic_write(queue_path,canonical(dict(format='studio-catalog-v1',entries=entries)).encode())
        queue_store=Store(root/'queue.sqlite')
        try:
            queue_store.import_catalog(queue_path)
            response=lambda xml: FakeResponse(200,json.dumps({'translations':[{'text':xml}]}))
            session=FakeSession([response('<r>Um</r>'),response('<r>Dois <ph id="0">T0</ph></r>'),FakeResponse(456,'{"message":"Quota exceeded"}')])
            estimate=queue_store.estimate()
            progress=[]
            job=TranslationJob(queue_store,Provider('FAKE-KEY-NOT-REAL',session=session),estimate['groups'],members=estimate['members'],progress=progress.append)
            original_pending=queue_store.pending
            queue_store.pending=lambda *args: (_ for _ in ()).throw(AssertionError('Varredura integral por resposta'))
            job.run()
            queue_store.pending=original_pending
            check('Fila otimizada: nenhuma varredura integral por resposta',job.done==1)
            check('Percentual: só entradas concluídas, sem contar resposta recusada',progress[-1]['session_completed']==1 and progress[-1]['session_total']==3 and progress[-1]['unresolved']==1 and 33 < progress[-1]['percent'] < 34)
            states=[r[0] for r in queue_store.db.execute('SELECT state FROM requests ORDER BY id')]
            check('DeepL simulado: recusa isolada, checkpoint e 456',states==['recusada','concluida','erro'] and session.calls==3)
            check('DeepL simulado: resposta inválida fora do cache',queue_store.db.execute('SELECT count(*) FROM cache').fetchone()[0]==1)
            check('DeepL simulado: credencial não persistida','FAKE-KEY' not in ''.join(queue_store.db.iterdump()))
            # O grupo com 456 permanece elegível; transporte sem resposta fica incerto.
            session2=FakeSession([requests.Timeout()])
            TranslationJob(queue_store,Provider('FAKE',session=session2),queue_store.estimate()['groups']).run()
            check('DeepL simulado: timeout incerto sem repetição',session2.calls==1 and queue_store.db.execute("SELECT count(*) FROM requests WHERE state='incerta'").fetchone()[0]==1)
            check('DeepL simulado: incerta bloqueia nova fila',not queue_store.pending())
        finally: queue_store.close()
    return dict(version=VERSION,passed=len(checks),checks=checks,real_deepl_call=False,game_validation=False,visual_ui_validation=False)


def lock_check(path):
    try:
        another=Store(path)
    except ValueError:
        return True
    another.close()
    return False


if __name__=='__main__': print(json.dumps(run(),ensure_ascii=True,indent=2))
