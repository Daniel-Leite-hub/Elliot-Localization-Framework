"""Importa a fonte inglesa no projeto editorial, preservando referências e histórico."""
import json
import time
from pathlib import Path
from core import Store, canonical


def main():
    project = Path(__file__).resolve().parents[1]
    rows = json.loads((project / 'Textos_para_leitura/ingles-espanhol.json').read_text(encoding='utf-8'))
    resource = 'Elliot/Content/Localization/Game/en/Game.locres'
    entries = []
    for r in rows:
        entries.append(dict(id=canonical([r['namespace'], r['key']]), resource=resource,
            language='EN', original=r['english'], category='locres-ingles',
            restrictions={'encoding': 'utf-16-le'},
            context='Namespace: '+r['namespace']+'; chave: '+r['key']+'; CRC origem: '+str(r['source_crc'])+'. Sequência narrativa não comprovada.',
            auxiliary={'ES': {'text': r['spanish'], 'resource': r['target_resource'], 'source_crc': r['source_crc']},
                       'JA': {'text': r['japanese_reference'], 'role': 'consulta futura apenas', 'source_crc': r['source_crc']}}))
    catalog = project / 'Textos_para_leitura/catalogo-studio-ingles.json'
    catalog.write_text(canonical({'format': 'studio-catalog-v1', 'entries': entries}), encoding='utf-8')
    store = Store(project / 'projetos/Elliot.sqlite')
    try:
        backup = project / 'backups' / ('Elliot-pre-importacao-ingles-'+str(time.time_ns())+'.sqlite')
        store.backup(backup)
        imported = store.import_catalog(catalog)
        store.set_setting('source_language', 'EN')
        store.set_setting('original_language', 'JA')
        store.set_setting('reference_only_languages', ['JA'])
        store.set_setting('future_replacement_language', 'es')
        store.set_setting('notes', 'Inglês importado como fonte de tradução. Japonês original: somente consultas futuras. Espanhol: base da futura substituição por PT-BR. Reinserção, fontes e layout no jogo pendentes.')
        en = [r for r in store.rows() if r['language']=='EN']
        eligible = sum(bool(store.eligibility(r)) for r in en)
        assert len(en)==len(entries)
        assert not any(store.eligibility(r) for r in store.rows() if r['language']=='JA')
        assert store.db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        report = dict(imported=imported, english_entries=len(en), eligible=eligible,
                      excluded=len(en)-eligible, backup=str(backup), integrity='ok')
        (project / 'relatorios/importacao-ingles-studio.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report))
    finally:
        store.close()


if __name__ == '__main__':
    main()
