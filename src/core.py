"""Banco e validação conservadora do Studio. Sem dependência do jogo ou do provedor."""
import hashlib
import json
import os
import re
import sqlite3
import threading
import time
from pathlib import Path
from xml.etree import ElementTree as ET

VERSION = '0.1.2'
PREPARATION = 'xml-conservative-v4-percent'
TOKENS = re.compile(r'[\ue000-\uf8ff\U000f0000-\U000ffffd\U00100000-\U0010fffd]|\r\n|\r|\n|<[^<>\n]+>|\{[^{}\n]+\}|\[[A-Za-z_][^\[\]\n]*\]|(?<![\d}])%(?:\d+\$)?[-+0 #]*(?:\d+|\*(?:\d+\$)?)?(?:\.(?:\d+|\*(?:\d+\$)?))?(?:hh|h|ll|l|j|z|t|L)?[diuoxXfFeEgGaAcspn%]|\\[nrt]|\\[A-Za-z]+(?:\[[^\]\n]*\])?')


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.tmp-' + str(time.time_ns()))
    try:
        with temp.open('xb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def classify(text):
    if not text.strip():
        return 'vazia', 'Entrada vazia; posição preservada.'
    if not TOKENS.sub('', text).strip():
        return 'tecnica', 'Somente marcadores/comandos.'
    return 'traduzivel', ''


def prepare(text):
    if any(ord(c)<32 and c not in '\t\r\n' or 0xD800<=ord(c)<=0xDFFF or ord(c) in (0xfffe,0xffff) for c in text):
        raise ValueError('Fonte contém caracteres incompatíveis com XML.')
    pieces, markers, start = ['<r>'], [], 0
    for match in TOKENS.finditer(text):
        pieces.append(escape(text[start:match.start()]))
        markers.append(match.group())
        pieces.append(f'<ph id="{len(markers)-1}">T{len(markers)-1}</ph>')
        start = match.end()
    pieces.extend([escape(text[start:]), '</r>'])
    return ''.join(pieces), markers


def estimated_characters(text):
    # Limite conservador: texto original mais conteúdo dos placeholders enviados.
    # Evita subestimar quebras curtas que passam a ser T0, T1 etc. no XML.
    return len(text) + sum(len(f'T{i}') for i, _ in enumerate(TOKENS.finditer(text)))


def escape(text):
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def restore(xml, markers):
    if len(xml) > 2_000_000 or '<!DOCTYPE' in xml.upper() or '<!ENTITY' in xml.upper():
        raise ValueError('XML inseguro ou excessivo.')
    root = ET.fromstring(xml)
    if root.tag != 'r' or root.attrib:
        raise ValueError('Raiz XML modificada.')
    children = list(root)
    if len(children) != len(markers):
        raise ValueError('Quantidade de marcadores alterada.')
    result = [root.text or '']
    for index, child in enumerate(children):
        if child.tag != 'ph' or child.attrib != {'id': str(index)} or list(child) or child.text != f'T{index}':
            raise ValueError('Identidade, ordem ou conteúdo de marcador alterado.')
        result.extend([markers[index], child.tail or ''])
    return ''.join(result)


def validate(source, target, restrictions=None):
    errors, warnings = [], []
    restrictions = restrictions or {}
    original = [m.group() for m in TOKENS.finditer(source)]
    translated = [m.group() for m in TOKENS.finditer(target)]
    if original != translated:
        errors.append('Quantidade, identidade ou ordem de comandos/quebras mudou.')
    if source.strip() and not target.strip():
        errors.append('Texto traduzido vazio.')
    encoding = restrictions.get('encoding', 'utf-8')
    try:
        size = len(target.encode(encoding, errors='strict'))
        if restrictions.get('max_bytes') is not None and size > int(restrictions['max_bytes']):
            errors.append(f'{size} bytes excedem capacidade {restrictions["max_bytes"]}.')
    except (UnicodeError, LookupError):
        errors.append(f'Texto não representável em {encoding}.')
    if restrictions.get('max_lines') and len(target.splitlines()) > int(restrictions['max_lines']):
        warnings.append('Quantidade de linhas excede limite informado.')
    if restrictions.get('max_chars') and len(target) > int(restrictions['max_chars']):
        warnings.append('Quantidade de caracteres excede limite editorial informado.')
    if re.search(r'[^\S\n]{2,}|\s+[,.!?;:]', target):
        warnings.append('Espaçamento/pontuação merece revisão.')
    if source == target and classify(source)[0] == 'traduzivel':
        warnings.append('Texto igual ao original; pode ser nome ou termo intencional.')
    if '\x00' in target:
        errors.append('Caractere NUL não permitido no catálogo.')
    for quote in ['"', '“', '”']:
        if quote == '"' and target.count(quote) % 2:
            warnings.append('Aspa possivelmente órfã.')
    if target.count('“') != target.count('”'):
        warnings.append('Aspas curvas sem par.')
    # Não presume a semântica dos comandos: alerta quando o contato com palavras muda.
    for sm, tm in zip(TOKENS.finditer(source), TOKENS.finditer(target)):
        for side in ['left', 'right']:
            s = source[sm.start()-1:sm.start()] if side == 'left' else source[sm.end():sm.end()+1]
            t = target[tm.start()-1:tm.start()] if side == 'left' else target[tm.end():tm.end()+1]
            if bool(s and s.isalnum()) != bool(t and t.isalnum()):
                warnings.append('Contato entre marcador e palavra mudou; conferir espaços.')
                break
    warnings.append('Largura em pixels, fonte e renderização no jogo ainda não verificadas.')
    return errors, list(dict.fromkeys(warnings))


class Store:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.process_lock = open(str(self.path) + '.lock', 'a+b')
        self.process_lock.seek(0)
        self.process_lock.write(b'0')
        self.process_lock.flush()
        self.process_lock.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.process_lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.process_lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.process_lock.close()
            raise ValueError('Projeto já aberto em outro processo. Feche-o antes de continuar.')
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.path, check_same_thread=False, timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.execute('PRAGMA busy_timeout=30000')
        self.migrate()
        saved=self.db.execute("SELECT * FROM requests WHERE state IN ('enviando','incerta') AND http_status=200 AND raw IS NOT NULL").fetchall()
        for request in saved:
            try:
                row=self.entry(request['entry_id']); _,markers,key,_=self.payload(row)
                if key!=request['cache_key']: continue
                obj=json.loads(request['raw'])
                if len(obj['translations'])!=1:continue
                text=restore(obj['translations'][0]['text'],markers)
                self.receive_machine(row['id'],text,key,request['id'])
                with self.db:self.db.execute("UPDATE requests SET state='concluida',translation=? WHERE id=?",(text,request['id']))
            except (ValueError,KeyError,TypeError,IndexError,ET.ParseError):
                with self.db:self.db.execute("UPDATE requests SET state='recusada',error='Resposta bruta recuperada inválida' WHERE id=?",(request['id'],))
        # Uma chamada interrompida não é tratada como pendente comum.
        with self.lock, self.db:
            self.db.execute("UPDATE requests SET state='incerta',error='Programa encerrado durante envio' WHERE state='enviando'")
        received = self.db.execute("SELECT * FROM requests WHERE state='recebida'").fetchall()
        for request in received:
            try:
                self.receive_machine(request['entry_id'], request['translation'], request['cache_key'], request['id'])
                with self.lock, self.db:
                    self.db.execute("UPDATE requests SET state='concluida' WHERE id=?", (request['id'],))
            except ValueError:
                with self.lock, self.db:
                    self.db.execute("UPDATE requests SET state='recusada',error='Resposta salva incompatível com a base atual' WHERE id=?", (request['id'],))

    def migrate(self):
        version = self.db.execute('PRAGMA user_version').fetchone()[0]
        if version > 2:
            raise ValueError('Projeto criado por uma versão mais nova do Studio.')
        if version == 0:
            self.db.executescript('''
            BEGIN;
            CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE entries(
              id TEXT PRIMARY KEY, resource TEXT NOT NULL, category TEXT NOT NULL,
              language TEXT NOT NULL, original TEXT NOT NULL, source_hash TEXT NOT NULL,
              position INTEGER NOT NULL, kind TEXT NOT NULL, exclusion TEXT NOT NULL,
              meta TEXT NOT NULL, machine TEXT, machine_hash TEXT, draft TEXT,
              approved TEXT, approved_hash TEXT, stale INTEGER NOT NULL DEFAULT 0,
              active INTEGER NOT NULL DEFAULT 1, selected TEXT, selected_kind TEXT);
            CREATE TABLE history(seq INTEGER PRIMARY KEY,entry_id TEXT,event TEXT,text TEXT,at REAL);
            CREATE TABLE requests(
              id INTEGER PRIMARY KEY, cache_key TEXT NOT NULL, entry_id TEXT NOT NULL,
              state TEXT NOT NULL, payload TEXT NOT NULL, raw TEXT, error TEXT,
              translation TEXT, started REAL, finished REAL, elapsed REAL);
            CREATE INDEX request_key ON requests(cache_key,state);
            CREATE TABLE cache(cache_key TEXT PRIMARY KEY,translation TEXT NOT NULL,request_id INTEGER);
            CREATE TABLE resources(path TEXT PRIMARY KEY,source_hash TEXT NOT NULL,adapter TEXT NOT NULL,base BLOB NOT NULL);
            CREATE TABLE inventory(path TEXT PRIMARY KEY,size INTEGER,sha256 TEXT,details TEXT);
            PRAGMA user_version=1;
            COMMIT;
            ''')
            self.set_setting('name', self.path.stem)
            self.set_setting('general_context', '')
            self.set_setting('before', 2)
            self.set_setting('after', 0)
            self.set_setting('glossary_id', '')
            self.set_setting('glossary_revision', '')
            self.set_setting('plan', 'Free')
            self.set_setting('formality', 'default')
            self.set_setting('notes', '')
        if version<2:
            self.db.executescript('''
            BEGIN;
            ALTER TABLE requests ADD COLUMN http_status INTEGER;
            CREATE TABLE request_responses(seq INTEGER PRIMARY KEY,request_id INTEGER NOT NULL,status INTEGER,raw TEXT NOT NULL,at REAL NOT NULL);
            CREATE INDEX entry_resource ON entries(resource,position);
            CREATE INDEX entry_state ON entries(active,kind);
            PRAGMA user_version=2;
            COMMIT;
            ''')

    def close(self):
        with self.lock:
            self.db.close()
            self.process_lock.close()

    def worker_connection(self):
        """Conexão da thread worker; bloqueio de processo permanece com o Studio."""
        worker=object.__new__(Store)
        worker.path=self.path
        worker.lock=threading.RLock()
        worker.db=sqlite3.connect(self.path,timeout=30)
        worker.db.row_factory=sqlite3.Row
        worker.db.execute('PRAGMA foreign_keys=ON')
        worker.db.execute('PRAGMA busy_timeout=30000')
        return worker

    def set_setting(self, key, value):
        with self.lock, self.db:
            self.db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', (key, canonical(value)))

    def setting(self, key, default=None):
        with self.lock:
            row = self.db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def rows(self):
        with self.lock:
            return [dict(r) for r in self.db.execute('SELECT * FROM entries WHERE active=1 ORDER BY resource,position,id')]

    def entry(self, entry_id):
        with self.lock:
            row = self.db.execute('SELECT * FROM entries WHERE id=?', (entry_id,)).fetchone()
            if not row:
                raise ValueError('Entrada não encontrada.')
            return dict(row)

    def log(self, entry_id, event, text):
        self.db.execute('INSERT INTO history(entry_id,event,text,at) VALUES (?,?,?,?)', (entry_id, event, text, time.time()))

    def history(self, entry_id):
        with self.lock:
            return [dict(r) for r in self.db.execute('SELECT * FROM history WHERE entry_id=? ORDER BY seq DESC', (entry_id,))]

    def import_catalog(self, path):
        """Formato editorial explícito. Nunca presume ser extração de pacote Unreal."""
        raw = Path(path).read_bytes()
        obj = json.loads(raw.decode('utf-8-sig'))
        if obj.get('format') != 'studio-catalog-v1' or not isinstance(obj.get('entries'), list):
            raise ValueError('Esperado catálogo studio-catalog-v1. Consulte o exemplo.')
        prepared, seen = [], set()
        for index, item in enumerate(obj['entries']):
            if not isinstance(item, dict) or not all(isinstance(item.get(k), str) for k in ['id', 'original', 'resource', 'language']):
                raise ValueError(f'Entrada {index}: id, original, resource e language são obrigatórios.')
            entry_id = digest(canonical([item['resource'], item['language'], item['id']]))
            if entry_id in seen:
                raise ValueError('ID duplicado no mesmo recurso/idioma.')
            seen.add(entry_id)
            meta = {k: item[k] for k in ['speaker', 'sequence', 'sequence_proof', 'ordinal', 'barrier', 'restrictions', 'context', 'auxiliary'] if k in item}
            meta['external_id'] = item['id']
            if 'ordinal' in meta and (type(meta['ordinal']) is not int):
                raise ValueError('ordinal deve ser inteiro.')
            if meta.get('sequence') and not meta.get('sequence_proof'):
                raise ValueError('Uma sequência exige sequence_proof com procedência verificável.')
            restrictions = meta.get('restrictions', {})
            if not isinstance(restrictions, dict):
                raise ValueError('restrictions deve ser objeto.')
            for k in ['max_bytes', 'max_lines', 'max_chars']:
                if k in restrictions and (type(restrictions[k]) is not int or restrictions[k] < 0):
                    raise ValueError(f'{k} deve ser inteiro não negativo.')
            kind, reason = classify(item['original'])
            prepared.append((entry_id, item, meta, kind, reason, index))
        with self.lock, self.db:
            for entry_id, item, meta, kind, reason, index in prepared:
                sh = digest(item['original'])
                previous = self.db.execute('SELECT * FROM entries WHERE id=?', (entry_id,)).fetchone()
                if previous:
                    changed = previous['source_hash'] != sh or previous['meta'] != canonical(meta)
                    if changed:
                        self.log(entry_id, 'base_alterada', canonical(dict(previous)))
                    self.db.execute('''UPDATE entries SET original=?,source_hash=?,position=?,category=?,meta=?,
                        stale=CASE WHEN ? THEN 1 ELSE stale END,active=1 WHERE id=?''',
                        (item['original'], sh, index, item.get('category', 'geral'), canonical(meta), changed, entry_id))
                else:
                    self.db.execute('''INSERT INTO entries(id,resource,category,language,original,source_hash,position,kind,exclusion,meta)
                        VALUES (?,?,?,?,?,?,?,?,?,?)''', (entry_id, item['resource'], item.get('category', 'geral'), item['language'], item['original'], sh, index, kind, reason, canonical(meta)))
                    self.log(entry_id, 'importada', item['original'])
            self.db.execute('INSERT OR REPLACE INTO resources VALUES (?,?,?,?)', (str(Path(path).resolve()), hashlib.sha256(raw).hexdigest(), 'catalog-editorial', raw))
        return len(prepared)

    def edit(self, entry_id, text, approve=False):
        row = self.entry(entry_id)
        errors, warnings = validate(row['original'], text, json.loads(row['meta']).get('restrictions'))
        if approve and errors:
            raise ValueError('\n'.join(errors))
        with self.lock, self.db:
            self.db.execute('UPDATE entries SET draft=? WHERE id=?', (text, entry_id))
            self.log(entry_id, 'rascunho', text)
            if approve:
                self.db.execute('UPDATE entries SET approved=?,approved_hash=?,stale=0 WHERE id=?', (text, row['source_hash'], entry_id))
                self.log(entry_id, 'aprovada', text)
        return warnings

    def revoke(self, entry_id):
        with self.lock, self.db:
            self.log(entry_id, 'aprovacao_revogada', self.entry(entry_id)['approved'])
            self.db.execute('UPDATE entries SET approved=NULL,approved_hash=NULL WHERE id=?', (entry_id,))

    def eligibility(self, row):
        source=self.setting('source_language',None)
        return row['active'] and row['kind'] == 'traduzivel' and (not source or row['language'].upper()==source.upper())

    def classify_entry(self, entry_id, kind, reason):
        if kind not in ['traduzivel', 'tecnica', 'vazia'] or (kind != 'traduzivel' and not reason.strip()):
            raise ValueError('Informe o motivo da exclusão.')
        with self.lock, self.db:
            self.db.execute('UPDATE entries SET kind=?,exclusion=? WHERE id=?', (kind, reason, entry_id))
            self.log(entry_id, 'classificacao', canonical([kind, reason]))

    def context(self, row, snapshot=None):
        meta = json.loads(row['meta'])
        setting = self.setting if snapshot is None else lambda key, default=None: snapshot['settings'].get(key, default)
        general = setting('general_context', '')
        context = [general] if general else []
        evidence = []
        if meta.get('context'):
            context.append(str(meta['context']))
        if not meta.get('sequence') or not meta.get('sequence_proof') or 'ordinal' not in meta or meta.get('barrier'):
            return '\n'.join(context), ['Sem sequência comprovada ou alvo com barreira; sem vizinhos.']
        candidates = {} if snapshot is None else snapshot.get('sequence_index',{}).get((row['resource'],row['language'],meta['sequence'],meta['sequence_proof']),{})
        for other in (self.rows() if snapshot is None else []):
            om = json.loads(other['meta'])
            if other['resource'] == row['resource'] and other['language'] == row['language'] and om.get('sequence') == meta['sequence'] and om.get('sequence_proof') == meta['sequence_proof']:
                ordinal = om.get('ordinal')
                if ordinal is not None:
                    candidates.setdefault(ordinal, []).append((other, om))
        neighbors = []
        for direction, number in [(-1, setting('before', 2)), (1, setting('after', 0))]:
            for offset in range(1, max(0, min(10, int(number))) + 1):
                found = candidates.get(meta['ordinal'] + direction * offset, [])
                if len(found) != 1:
                    evidence.append(f'Interrupção {direction:+}: lacuna ou ramificação no ordinal {meta["ordinal"] + direction*offset}.')
                    break
                other, om = found[0]
                if om.get('barrier') or other['kind'] != 'traduzivel':
                    evidence.append(f'Interrupção em {om["external_id"]}: barreira/controle técnico.')
                    break
                neighbors.append((om['ordinal'], f'{om.get("speaker", "Falante não identificado")}: {other["original"]}'))
                evidence.append(f'{om["external_id"]} | falante={om.get("speaker", "?")} | método=sequência explícita | {om["sequence_proof"]}')
        context.extend(text for _, text in sorted(neighbors))
        return '\n'.join(context), evidence

    def payload(self, row, snapshot=None):
        text, markers = prepare(row['original'])
        setting = self.setting if snapshot is None else lambda key, default=None: snapshot['settings'].get(key, default)
        context, evidence = self.context(row, snapshot)
        payload = dict(text=[text], source_lang=row['language'].upper(), target_lang='PT-BR',
                       context=context, tag_handling='xml', ignore_tags=['ph'],
                       split_sentences='nonewlines', preserve_formatting=True, formality=setting('formality', 'default'))
        if setting('glossary_id', ''):
            payload['glossary_id'] = setting('glossary_id')
        meta = json.loads(row['meta'])
        conditions = dict(payload=payload, preparation=PREPARATION, speaker=meta.get('speaker'),
                          restrictions=meta.get('restrictions'), endpoint_plan=setting('plan', 'Free'),
                          glossary_revision=setting('glossary_revision', ''))
        return payload, markers, digest(canonical(conditions)), evidence

    def prepared_pending(self, only_id=None, stop=None):
        with self.lock:
            snapshot = dict(rows=self.rows(), settings={r[0]: json.loads(r[1]) for r in self.db.execute('SELECT key,value FROM settings')})
            blocked = {r[0] for r in self.db.execute("SELECT cache_key FROM requests WHERE state IN ('enviando','incerta','recusada')")}
            blocked_entries = {r[0] for r in self.db.execute("SELECT entry_id FROM requests WHERE state IN ('enviando','incerta','recusada')")}
        snapshot['sequence_index']={}
        for item in snapshot['rows']:
            meta=json.loads(item['meta'])
            if meta.get('sequence') and meta.get('sequence_proof') and 'ordinal' in meta:
                group=(item['resource'],item['language'],meta['sequence'],meta['sequence_proof'])
                snapshot['sequence_index'].setdefault(group,{}).setdefault(meta['ordinal'],[]).append((item,meta))
        for row in snapshot['rows']:
            if stop and stop.is_set(): return
            if row['id'] in blocked_entries: continue
            if only_id and row['id'] != only_id:
                continue
            if self.eligibility(row) and (not row['approved'] or row['stale']) and (not row['machine'] or row['machine_hash'] != row['source_hash'] or row['stale']):
                try: payload, _, key, _ = self.payload(row, snapshot)
                except ValueError as exc:
                    self.classify_entry(row['id'],'tecnica','Envio isolado por XML incompatível: '+str(exc))
                    continue
                if key not in blocked:
                    yield row, payload, key

    def pending(self, only_id=None):
        return [row for row, _, _ in self.prepared_pending(only_id)]

    def estimate(self, only_id=None, stop=None):
        unique, members, count = {}, {}, 0
        for row, payload, key in self.prepared_pending(only_id,stop):
            count += 1
            unique.setdefault(key, (row, payload))
            members.setdefault(key, []).append(row['id'])
        with self.lock:
            cached = {r[0] for r in self.db.execute('SELECT cache_key FROM cache')}
        network = {k: v for k, v in unique.items() if k not in cached}
        chars = sum(estimated_characters(r['original']) for r, _ in network.values())
        return dict(entries=count, unique=len(unique), network=len(network), characters=chars,
                    avoided=count-len(network), groups=unique, members=members)

    def receive_machine(self, entry_id, text, key, request_id):
        row = self.entry(entry_id)
        errors, _ = validate(row['original'], text, json.loads(row['meta']).get('restrictions'))
        if errors:
            raise ValueError('; '.join(errors))
        with self.lock, self.db:
            self.db.execute('UPDATE entries SET machine=?,machine_hash=?,stale=CASE WHEN approved IS NULL THEN 0 ELSE stale END WHERE id=?', (text, row['source_hash'], entry_id))
            self.log(entry_id, 'automatica_validada', text)
            self.db.execute('INSERT OR REPLACE INTO cache VALUES (?,?,?)', (key, text, request_id))

    def select(self, row, approved_only=False):
        restrictions = json.loads(row['meta']).get('restrictions')
        if row['approved'] is not None:
            errors, _ = validate(row['original'], row['approved'], restrictions)
            if row['stale'] or row['approved_hash'] != row['source_hash']:
                errors.append('Aprovação afetada por mudança de origem/contexto; revisar e aprovar novamente.')
            if errors:
                raise ValueError(f'{json.loads(row["meta"])["external_id"]}: ' + '; '.join(errors))
            return row['approved'], 'aprovada', ''
        if not approved_only and row['machine'] is not None and row['machine_hash'] == row['source_hash'] and not row['stale']:
            errors, _ = validate(row['original'], row['machine'], restrictions)
            if not errors:
                return row['machine'], 'automatica', ''
            return row['original'], 'original', '; '.join(errors)
        return row['original'], 'original', 'Sem revisão aprovada.' if approved_only else 'Sem tradução automática válida.'

    def export(self, path, approved_only=False):
        entries, fallback, selections = [], [], []
        for row in self.rows():
            text, kind, reason = self.select(row, approved_only)
            meta = json.loads(row['meta'])
            item = dict(id=meta.pop('external_id'), resource=row['resource'], category=row['category'], language=row['language'],
                        original=row['original'], translation=text, selected_kind=kind, source_hash=row['source_hash'], **meta)
            entries.append(item)
            selections.append((text, kind, row['id']))
            if reason:
                fallback.append(dict(id=item['id'], reason=reason))
        obj = dict(format='studio-catalog-v1', version=VERSION, target='PT-BR', editorial_only=True, entries=entries,
                   generation_report=dict(fallback=fallback, game_reinsertion=False, font_validation=False))
        data = json.dumps(obj, ensure_ascii=False, indent=2).encode('utf-8')
        # Verifica o conteúdo efetivamente gravado antes de registrar seleção.
        atomic_write(path, data)
        if Path(path).read_bytes() != data or json.loads(data)['entries'] != entries:
            raise ValueError('Falha de leitura da exportação.')
        with self.lock, self.db:
            self.db.executemany('UPDATE entries SET selected=?,selected_kind=? WHERE id=?', selections)
        return len(entries)

    def import_reviews(self, path):
        obj = json.loads(Path(path).read_text(encoding='utf-8-sig'))
        if obj.get('format') != 'studio-reviews-v1':
            raise ValueError('Esperado studio-reviews-v1, com entry_id, source_hash e draft. Importação nunca aprova.')
        prepared = []
        for item in obj['entries']:
            row = self.entry(item['entry_id'])
            if item['source_hash'] != row['source_hash']:
                raise ValueError('Revisão pertence a uma origem diferente: ' + item['entry_id'])
            if not isinstance(item['draft'], str):
                raise ValueError('Rascunho deve ser texto.')
            prepared.append(item)
        with self.lock, self.db:
            for item in prepared:
                self.db.execute('UPDATE entries SET draft=? WHERE id=?', (item['draft'], item['entry_id']))
                self.log(item['entry_id'], 'rascunho_importado', item['draft'])
        return len(prepared)

    def export_reviews(self, path):
        entries = [dict(entry_id=r['id'], source_hash=r['source_hash'], draft=r['draft'] if r['draft'] is not None else (r['approved'] or r['machine'] or r['original'])) for r in self.rows()]
        atomic_write(path, json.dumps(dict(format='studio-reviews-v1', entries=entries), ensure_ascii=False, indent=2).encode('utf-8'))

    def backup(self, path):
        path = Path(path).resolve()
        if path == self.path or path.exists():
            raise ValueError('Escolha um arquivo novo para backup.')
        with self.lock:
            destination = sqlite3.connect(path)
            try:
                self.db.backup(destination)
                if destination.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise ValueError('Backup não passou na verificação de integridade.')
            finally:
                destination.close()

    def retry(self, request_id, allow_uncertain=False):
        with self.lock, self.db:
            row = self.db.execute('SELECT * FROM requests WHERE id=?', (request_id,)).fetchone()
            if not row or row['state'] not in ['incerta', 'recusada', 'erro']:
                raise ValueError('Operação não pode ser reaberta.')
            if row['state'] == 'incerta' and not allow_uncertain:
                raise ValueError('Reenvio incerto exige autorização explícita; pode consumir cota novamente.')
            self.log(row['entry_id'], 'reenvio_autorizado', f'Requisição {request_id}; estado {row["state"]}')
            self.db.execute("UPDATE requests SET state='reenvio_autorizado' WHERE id=?", (request_id,))

    def report(self):
        rows = self.rows()
        with self.lock:
            states = dict(self.db.execute('SELECT state,count(*) FROM requests GROUP BY state').fetchall())
            inventory = [dict(r) for r in self.db.execute('SELECT * FROM inventory')]
        return dict(version=VERSION, project=str(self.path), name=self.setting('name'), entries=len(rows),
                    eligible=sum(bool(self.eligibility(r)) for r in rows), approved=sum(r['approved'] is not None for r in rows),
                    stale=sum(r['stale'] for r in rows), requests=states, inventory=inventory,
                    coverage='Catálogo importado; cobertura total do jogo não comprovada.',
                    generation='Patch Elliot bloqueado: reinserção de contêineres e fontes/layout ainda não comprovados.',
                    notes=self.setting('notes', ''), deep_search=self.setting('deep_search', None),
                    source_language=self.setting('source_language',None),
                    progress=dict(valid_translation=sum(self.eligibility(r) and ((r['approved'] is not None and not r['stale'] and not validate(r['original'],r['approved'],json.loads(r['meta']).get('restrictions'))[0]) or (r['machine'] is not None and r['machine_hash']==r['source_hash'] and not r['stale'] and not validate(r['original'],r['machine'],json.loads(r['meta']).get('restrictions'))[0])) for r in rows),
                        eligible_denominator=sum(bool(self.eligibility(r)) for r in rows),
                        reference_excluded=sum(not self.eligibility(r) for r in rows),
                        editorial_read=self.setting('editorial_read_count',0),
                        approved=sum(bool(self.eligibility(r) and r['approved'] is not None and not r['stale']) for r in rows),
                        selected=sum(r['selected_kind'] in ('aprovada','automatica') for r in rows),
                        inserted=self.setting('inserted_count',0),installed=self.setting('installed_count',0),game_tested_scenes=self.setting('game_tested_scenes',[])))
