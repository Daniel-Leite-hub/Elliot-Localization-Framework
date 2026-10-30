"""Recursos soltos LocRes padrão v0–v3. Não lê/reempacota PAK/IoStore.

Mantém namespace, chaves e hashes opacos. Rejeita variantes e bytes não interpretados.
"""
import hashlib
import json
import struct
from pathlib import Path
from core import atomic_write, canonical, digest

MAGIC = struct.pack('<4I', 0x7574140E, 0xFC034A67, 0x9D90154A, 0x1B7F37C3)


def fstring(text):
    if not text:
        return struct.pack('<i', 0)
    if '\x00' in text:
        raise ValueError('NUL dentro de FString.')
    try:
        raw = text.encode('ascii') + b'\0'
        return struct.pack('<i', len(raw)) + raw
    except UnicodeEncodeError:
        raw = text.encode('utf-16-le') + b'\0\0'
        return struct.pack('<i', -(len(raw)//2)) + raw


class LocRes:
    def __init__(self, data):
        self.data, self.pos = data, 0
        self.version = 0
        self.explicit_magic = data.startswith(MAGIC)
        if self.explicit_magic:
            self.pos = 16
            self.version = self.number('B')
        if self.version not in range(4):
            raise ValueError('Versão LocRes não suportada.')
        self.lut, self.records = [], []
        if self.version >= 1:
            self.lut_offset = self.number('q')
            if not self.pos <= self.lut_offset < len(data):
                raise ValueError('Offset da tabela de strings inválido.')
            cursor = self.pos
            self.pos = self.lut_offset
            for _ in range(self.count()):
                text, raw, _, _ = self.string()
                refs = self.number('i') if self.version >= 2 else None
                self.lut.append((text, raw, refs))
            if self.pos != len(data):
                raise ValueError('Dados adicionais após strings: variante não habilitada.')
            self.pos = cursor
        total = self.number('I') if self.version >= 2 else None
        namespaces = self.count()
        seen = set()
        for _ in range(namespaces):
            if self.version >= 2:
                self.number('I')  # hash de namespace opaco
            namespace = self.string()[0]
            for _ in range(self.count()):
                if self.version >= 2:
                    self.number('I')  # hash de chave opaco
                key = self.string()[0]
                source_crc = self.number('I')
                if (namespace, key) in seen:
                    raise ValueError('Chave duplicada: associação ambígua.')
                seen.add((namespace, key))
                if self.version >= 1:
                    at = self.pos
                    index = self.number('i')
                    if not 0 <= index < len(self.lut):
                        raise ValueError('Índice de string fora da tabela.')
                    text = self.lut[index][0]
                    span = (at, self.pos)
                else:
                    text, _, start, end = self.string()
                    index, span = None, (start, end)
                self.records.append(dict(namespace=namespace, key=key, source_crc=source_crc,
                                         original=text, index=index, span=span))
        if total is not None and total != len(self.records):
            raise ValueError('Contagem total de entradas incompatível.')
        if self.pos != (self.lut_offset if self.version >= 1 else len(data)):
            raise ValueError('Bytes adicionais/offsets incompatíveis entre índices e textos.')
        # Prova da reconstrução deste recurso, sem alterações.
        if self.build({}) != data:
            raise ValueError('Reconstrução sem alterações divergiu da base.')

    def number(self, fmt):
        size = struct.calcsize('<'+fmt)
        if self.pos+size > len(self.data):
            raise ValueError('LocRes truncado.')
        value = struct.unpack_from('<'+fmt, self.data, self.pos)[0]
        self.pos += size
        return value

    def count(self):
        value = self.number('I')
        if value > 2_000_000 or value > len(self.data):
            raise ValueError('Contagem de tabela excessiva.')
        return value

    def string(self):
        start = self.pos
        length = self.number('i')
        if abs(length) > 2_000_000:
            raise ValueError('FString excessiva.')
        size = length if length >= 0 else -length*2
        end = self.pos+size
        if end > len(self.data):
            raise ValueError('FString truncada.')
        raw = self.data[self.pos:end]
        self.pos = end
        if length == 0:
            text = ''
        elif length > 0:
            if raw[-1:] != b'\0':
                raise ValueError('FString ANSI sem terminador.')
            text = raw[:-1].decode('utf-8', errors='strict')
        else:
            if raw[-2:] != b'\0\0':
                raise ValueError('FString Unicode sem terminador.')
            text = raw[:-2].decode('utf-16-le', errors='strict')
        return text, self.data[start:end], start, end

    def build(self, replacements):
        if self.version == 0:
            chunks, cursor = [], 0
            for record in self.records:
                a, b = record['span']
                text = replacements.get((record['namespace'], record['key']), record['original'])
                chunks.extend([self.data[cursor:a], self.data[a:b] if text == record['original'] else fstring(text)])
                cursor = b
            chunks.append(self.data[cursor:])
            return b''.join(chunks)
        prefix = bytearray(self.data[:self.lut_offset])
        lut = list(self.lut)
        refs = [0]*len(lut)
        changed = False
        new_indices = {}
        for record in self.records:
            text = replacements.get((record['namespace'], record['key']), record['original'])
            index = record['index']
            if text != record['original']:
                changed = True
                if text not in new_indices:
                    new_indices[text] = len(lut)
                    lut.append((text, fstring(text), 0))
                    refs.append(0)
                index = new_indices[text]
            struct.pack_into('<i', prefix, record['span'][0], index)
            refs[index] += 1
        chunks = [bytes(prefix), struct.pack('<I', len(lut))]
        for i, (_, raw, original_refs) in enumerate(lut):
            chunks.append(raw)
            if self.version >= 2:
                chunks.append(struct.pack('<i', refs[i] if changed else original_refs))
        return b''.join(chunks)


def import_locres(store, path, language):
    path = Path(path).resolve()
    data = path.read_bytes()
    parsed = LocRes(data)
    resource = str(path)
    catalog = dict(format='studio-catalog-v1', entries=[dict(id=canonical([r['namespace'], r['key']]), original=r['original'],
                   resource=resource, language=language.upper(), category='locres',
                   context='Namespace: '+r['namespace'], restrictions={'encoding': 'utf-16-le'}) for r in parsed.records])
    # O catálogo temporário fica dentro do projeto e é excluído depois de importado.
    temp = store.path.parent / ('import-' + str(__import__('time').time_ns()) + '.json')
    atomic_write(temp, canonical(catalog).encode('utf-8'))
    try:
        count = store.import_catalog(temp)
        with store.lock, store.db:
            store.db.execute('DELETE FROM resources WHERE path=?', (str(temp),))
            store.db.execute('INSERT OR REPLACE INTO resources VALUES (?,?,?,?)', (resource, hashlib.sha256(data).hexdigest(), 'locres-standard', data))
    finally:
        temp.unlink(missing_ok=True)
    return count, parsed.version


def generate_locres(store, directory, approved_only=False):
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    with store.lock:
        resources = [dict(r) for r in store.db.execute("SELECT * FROM resources WHERE adapter='locres-standard'")]
    if not resources:
        raise ValueError('Nenhum LocRes solto importado e reconstruído. Geração de PAK/IoStore bloqueada.')
    prepared, report, selections = [], [], []
    for resource in resources:
        parsed = LocRes(resource['base'])
        replacements, fallback = {}, []
        for row in store.rows():
            if row['resource'] != resource['path']:
                continue
            text, kind, reason = store.select(row, approved_only)
            ns, key = json.loads(json.loads(row['meta'])['external_id'])
            if (ns, key) in replacements and replacements[(ns, key)] != text:
                raise ValueError('Múltiplos idiomas importados no mesmo recurso: geração ambígua.')
            replacements[(ns, key)] = text
            selections.append((text, kind, row['id']))
            if reason:
                fallback.append(dict(namespace=ns, key=key, reason=reason))
        output = parsed.build(replacements)
        reread = LocRes(output)
        for record in reread.records:
            expected = replacements.get((record['namespace'], record['key']), record['original'])
            if record['original'] != expected:
                raise ValueError('Texto gerado diverge da seleção.')
        name = digest(resource['path'])[:12] + '-' + Path(resource['path']).name
        target = directory / name
        if target.exists():
            raise ValueError('Saída já existe; escolha uma pasta nova para preservar artefatos.')
        prepared.append((target, output))
        report.append(dict(file=name, source=resource['path'], source_sha256=resource['source_hash'], sha256=hashlib.sha256(output).hexdigest(),
                           version=parsed.version, entries=len(parsed.records), fallback=fallback, roundtrip=True, reread=True))
    for target, output in prepared:
        atomic_write(target, output)
        if target.read_bytes() != output:
            raise ValueError('Verificação do arquivo gravado falhou.')
    result = dict(format='studio-locres-report-v1', resources=report, package_reinsertion=False, game_tested=False, font_tested=False,
                  warning='Recursos soltos gerados. Não são patch Elliot; montagem do contêiner e teste no jogo pendentes.')
    atomic_write(directory/'relatorio.json', json.dumps(result, ensure_ascii=False, indent=2).encode('utf-8'))
    with store.lock, store.db:
        store.db.executemany('UPDATE entries SET selected=?,selected_kind=? WHERE id=?', selections)
    return result
