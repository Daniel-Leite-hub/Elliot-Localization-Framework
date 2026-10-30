"""DeepL exclusivo. Não faz rede ao importar e nunca persiste a chave."""
import json
import threading
import time
import requests
import math
from email.utils import parsedate_to_datetime
from core import canonical, restore, validate, estimated_characters


class Provider:
    def __init__(self, key, plan='Free', session=None):
        if not key.strip():
            raise ValueError('Informe a chave da API DeepL.')
        self.session = session or requests.Session()
        self.session.headers.update({'Authorization': 'DeepL-Auth-Key ' + key.strip()})
        self.url = 'https://api-free.deepl.com/v2' if plan == 'Free' else 'https://api.deepl.com/v2'

    def usage(self):
        response = self.session.get(self.url + '/usage', timeout=(10, 30))
        if response.status_code != 200:
            raise ValueError(f'Consulta de cota: HTTP {response.status_code}.')
        obj = response.json()
        if not all(isinstance(obj.get(k), int) for k in ['character_count', 'character_limit']):
            raise ValueError('Cota de caracteres não confirmada pela API.')
        return dict(used=obj['character_count'], limit=obj['character_limit'], remaining=max(0, obj['character_limit']-obj['character_count']))

    def close(self):
        self.session.close()

    def check_glossary(self, glossary_id, source):
        try:response=self.session.get(self.url+'/v3/glossaries/'+glossary_id,timeout=(10,30))
        except requests.RequestException:raise ValueError('Consulta do glossário indisponível; nenhuma tradução enviada.') from None
        if response.status_code!=200: raise ValueError('Glossário indisponível: HTTP '+str(response.status_code))
        obj=response.json()
        dictionaries=obj.get('dictionaries',[])
        if not any(x.get('source_lang','').upper()==source.upper() and x.get('target_lang','').upper() in ('PT','PT-BR') for x in dictionaries):
            raise ValueError('Glossário incompatível com '+source+' → PT-BR.')


class TranslationJob:
    def __init__(self, store, provider, groups, notify=None, char_cap=None, members=None, progress=None, baseline=0, total=None):
        self.store, self.provider, self.groups = store, provider, groups
        self.notify = notify or (lambda message: None)
        self.stop = threading.Event()
        self.char_cap = char_cap
        self.used_estimate = 0
        self.done = 0
        self.members = members
        self.uncertain = 0
        self.reason = 'Fila concluída.'
        self.progress = progress or (lambda data: None)
        self.baseline, self.total = baseline, total
        self.completed_entries = 0
        self.failed_entries = 0
        self.session_total = 0

    def emit_progress(self):
        session_total = self.session_total
        total = self.total if self.total is not None else session_total
        completed = self.baseline + self.completed_entries
        self.progress(dict(completed=completed, total=total, percent=100*completed/total if total else 0,
                           session_completed=self.completed_entries, session_total=session_total,
                           unresolved=self.failed_entries))

    def wait(self, seconds, message):
        # Aguarda em trechos curtos, mantém a pausa responsiva e mostra atividade.
        while seconds > 0 and not self.stop.is_set():
            self.notify(f'{message} Retomada automática em {seconds:.0f}s.')
            step = min(10, seconds)
            if self.stop.wait(step):
                break
            seconds -= step
        return self.stop.is_set()

    def recover_connection(self):
        while not self.stop.is_set():
            if self.wait(30, 'Conexão instável; aguardando recuperação sem enviar traduções.'):
                return False
            try:
                usage = self.provider.usage()  # Leitura: não repete chamadas possivelmente cobradas.
                if usage['remaining'] <= 0:
                    self.reason = 'Cota DeepL esgotada.'
                    return False
                self.notify('Conexão recuperada; continuando os pendentes independentes.')
                return True
            except Exception:
                continue
        return False

    def pause(self):
        self.stop.set()

    def update_request(self, rid, state, error=None, translation=None, elapsed=None):
        with self.store.lock, self.store.db:
            self.store.db.execute('UPDATE requests SET state=?,error=?,translation=?,finished=?,elapsed=? WHERE id=?',
                (state, error, translation, time.time(), elapsed, rid))

    def run(self):
        try:
            # Índice único da fila: nunca recalcule 40 mil payloads por resposta.
            if self.members is None:
                self.members = {}
                for member, _, member_key in self.store.prepared_pending():
                    if member_key in self.groups:
                        self.members.setdefault(member_key, []).append(member['id'])
            consecutive_failures = 0
            self.session_total = sum(len(ids) for ids in self.members.values())
            self.emit_progress()
            for key, (representative, payload) in self.groups.items():
                if self.stop.is_set():
                    self.reason = 'Pausada pelo usuário.'
                    break
                row = self.store.entry(representative['id'])
                live_payload, markers, live_key, _ = self.store.payload(row)
                if live_key != key:
                    self.reason = 'Origem/contexto mudou; estime uma nova fila.'
                    self.notify('Origem/contexto mudou. Pare e estime uma nova fila.')
                    break
                if not self.store.eligibility(row):
                    continue
                with self.store.lock:
                    cached = self.store.db.execute('SELECT translation,request_id FROM cache WHERE cache_key=?', (key,)).fetchone()
                    blocked = self.store.db.execute("SELECT 1 FROM requests WHERE (cache_key=? OR entry_id=?) AND state IN ('enviando','incerta','recusada')", (key, row['id'])).fetchone()
                if blocked:
                    continue
                if cached:
                    text, rid = cached
                else:
                    cost = estimated_characters(row['original'])
                    if self.char_cap is not None and self.used_estimate + cost > self.char_cap:
                        self.reason = 'Teto de caracteres alcançado.'
                        self.notify('Teto de caracteres alcançado; progresso preservado.')
                        break
                    body = canonical(payload).encode('utf-8')
                    if len(body) > 128 * 1024:
                        self.notify('Unidade excede 128 KiB; envio bloqueado: ' + row['id'][:12])
                        continue
                    with self.store.lock, self.store.db:
                        rid = self.store.db.execute('INSERT INTO requests(cache_key,entry_id,state,payload,started) VALUES (?,?,?,?,?)',
                            (key, row['id'], 'enviando', canonical(payload), time.time())).lastrowid
                    self.used_estimate += cost
                    started = time.monotonic()
                    response = None
                    # Só HTTP 429 explícito permite repetição automática; transporte/5xx são incertos.
                    attempt = 0
                    deadline=self.store.setting('deepl_retry_deadline',0)
                    if deadline>time.time() and self.wait(deadline-time.time(),'Espera HTTP 429 persistida.'):
                        self.update_request(rid,'erro','Pausada durante espera persistida.')
                        self.reason='Pausada pelo usuário.'
                        return
                    while not self.stop.is_set():
                        try:
                            response = self.provider.session.post(self.provider.url + '/translate', data=body,
                                headers={'Content-Type': 'application/json'}, timeout=(20, 90))
                        except requests.RequestException as exc:
                            self.update_request(rid, 'incerta', 'Comunicação sem resposta recuperável (' + type(exc).__name__ + '); cobrança possível.', elapsed=time.monotonic()-started)
                            response = None
                            break
                        # Checkpoint de toda resposta antes de interpretar ou chamar novamente.
                        with self.store.lock, self.store.db:
                            self.store.db.execute('INSERT INTO request_responses(request_id,status,raw,at) VALUES (?,?,?,?)',(rid,response.status_code,response.text,time.time()))
                            self.store.db.execute('UPDATE requests SET raw=?,http_status=? WHERE id=?', (response.text,response.status_code, rid))
                        if response.status_code != 429:
                            break
                        try:
                            delay = float(response.headers.get('Retry-After', min(60, 2 ** min(attempt+1, 6))))
                        except ValueError:
                            try: delay=max(1,parsedate_to_datetime(response.headers['Retry-After']).timestamp()-time.time())
                            except (ValueError,KeyError,TypeError): delay = 60
                        if not math.isfinite(delay) or delay < 0:
                            delay = 60
                        attempt += 1
                        self.store.set_setting('deepl_retry_deadline',time.time()+max(1,delay))
                        if self.wait(max(1, delay), 'HTTP 429: limite temporário de frequência.'):
                            self.update_request(rid, 'erro', 'Pausada após resposta HTTP 429.')
                            self.reason = 'Pausada durante espera por limite de frequência.'
                            return
                        if attempt>=8:
                            self.update_request(rid,'erro','Limite de oito tentativas HTTP 429; espera preservada.')
                            self.reason='Limite de tentativas HTTP 429; retome posteriormente.'
                            return
                    if self.stop.is_set() and (response is None or response.status_code == 429):
                        self.update_request(rid, 'erro', 'Pausada antes de novo envio.')
                        self.reason = 'Pausada pelo usuário.'
                        return
                    elapsed = time.monotonic()-started
                    if response is None or response.status_code >= 500:
                        if response is not None:
                            self.update_request(rid, 'incerta', f'HTTP {response.status_code}: processamento não confirmado.', elapsed=elapsed)
                        self.uncertain += 1
                        self.failed_entries += len(self.members.get(key, [row['id']]))
                        self.emit_progress()
                        self.reason='Comunicação incerta; progresso salvo. Autorize deliberadamente qualquer repetição.'
                        return
                    consecutive_failures = 0
                    status = response.status_code
                    if status != 200:
                        self.update_request(rid, 'erro', f'HTTP {status}', elapsed=elapsed)
                        self.reason = f'DeepL HTTP {status}: verifique cota, credencial ou configuração.'
                        self.notify(f'DeepL HTTP {status}. Fila parada; traduções concluídas preservadas.')
                        return
                    try:
                        obj = json.loads(response.text)
                        translations = obj['translations']
                        if not isinstance(translations, list) or len(translations) != 1:
                            raise ValueError('Associação entre resposta e alvo inválida.')
                        text = restore(translations[0]['text'], markers)
                        errors, _ = validate(row['original'], text, json.loads(row['meta']).get('restrictions'))
                        if errors:
                            raise ValueError('; '.join(errors))
                    except (ValueError, KeyError, TypeError, IndexError) as exc:
                        self.update_request(rid, 'recusada', str(exc), elapsed=elapsed)
                        self.notify('Resposta recusada; demais unidades continuam: ' + row['id'][:12])
                        self.failed_entries += len(self.members.get(key, [row['id']]))
                        self.emit_progress()
                        continue
                    except Exception:
                        self.update_request(rid, 'recusada', 'Estrutura XML inválida.', elapsed=elapsed)
                        self.notify('XML recusado; demais unidades continuam.')
                        self.failed_entries += len(self.members.get(key, [row['id']]))
                        self.emit_progress()
                        continue
                    self.update_request(rid, 'recebida', translation=text, elapsed=elapsed)
                    self.store.receive_machine(row['id'], text, key, rid)
                    self.update_request(rid, 'concluida', translation=text, elapsed=elapsed)
                # Reutilização validada por chave completa; cada ocorrência mantém histórico próprio.
                for member_id in self.members.get(key, [row['id']]):
                    other = self.store.entry(member_id)
                    if not self.store.eligibility(other) or (other['approved'] and not other['stale']):
                        continue
                    if other['machine'] is not None and other['machine_hash'] == other['source_hash'] and not other['stale']:
                        self.completed_entries += 1
                        continue
                    _, _, other_key, _ = self.store.payload(other)
                    if other_key == key:
                        self.store.receive_machine(other['id'], text, key, rid)
                        self.completed_entries += 1
                self.done += 1
                self.emit_progress()
                self.notify(f'Unidades concluídas/reutilizadas: {self.done}. Última: {row["id"][:12]}')
        except Exception as exc:
            self.reason = 'Erro local: ' + type(exc).__name__ + '.'
            # Nunca mostra texto de exceção de HTTP com cabeçalhos/credenciais.
            self.notify('Fila interrompida por erro local: ' + type(exc).__name__ + '. Consulte as requisições salvas.')
        finally:
            if self.failed_entries and self.reason == 'Fila concluída.':
                self.reason = 'Pendentes elegíveis processados; há entradas incertas/recusadas aguardando revisão.'
            if self.members is not None: self.emit_progress()
            self.provider.close()
            self.notify(f'{self.reason} {self.done} unidades concluídas/reutilizadas; {self.uncertain} chamadas incertas nesta execução. Progresso salvo; incertas/recusadas não são reenviadas automaticamente.')
