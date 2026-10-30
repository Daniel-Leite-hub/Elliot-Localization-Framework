"""Exporta textos para leitura e alinha a base espanhola, sem alterar o jogo."""
import hashlib
import json
from pathlib import Path
from deep_search import Pak, Ooz
from locres import LocRes


def main():
    root = Path(__file__).resolve().parents[2]
    project = root / 'FerramentaTraducao'
    out = project / 'Textos_para_leitura'
    out.mkdir(exist_ok=True)
    pak = Pak(root / 'Elliot/Content/Paks/Elliot-Windows.pak',
              (project / 'pesquisa/archive-key.local').read_text().strip())
    decoder = Ooz(project / 'pesquisa/tools/ooz.exe', out / 'work')
    parsed, report = {}, {'index_hashes_verified': True, 'game_modified': False, 'resources': {}}
    for language, label in [('en', 'ingles'), ('es', 'espanhol'), ('ja', 'japones_consulta')]:
        path = f'../../../Elliot/Content/Localization/Game/{language}/Game.locres'
        entry = next(x for x in pak.files if x['path'] == path)
        data = pak.read_file(entry, decoder)
        loc = LocRes(data)
        parsed[language] = loc.records
        target = out / 'originais' / language / 'Game.locres'
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        (out / f'{label}.json').write_text(json.dumps(loc.records, ensure_ascii=False, indent=2), encoding='utf-8')
        text = '\n\n'.join(f'[{i}] {r["namespace"]} | {r["key"]}\n{r["original"]}' for i, r in enumerate(loc.records, 1))
        (out / f'{label}.txt').write_text(text, encoding='utf-8-sig')
        report['resources'][language] = {'path': path, 'entries': len(loc.records),
            'sha256': hashlib.sha256(data).hexdigest(), 'roundtrip_identical': loc.build({}) == data}
    def identity(r):
        return r['namespace'], r['key'], r['source_crc']
    es = {identity(r): r for r in parsed['es']}
    en = {identity(r): r for r in parsed['en']}
    ja = {identity(r): r for r in parsed['ja']}
    aligned = [dict(namespace=r['namespace'], key=r['key'], source_crc=r['source_crc'],
                    english=r['original'], spanish=es.get(identity(r), {}).get('original'),
                    japanese_reference=ja.get(identity(r), {}).get('original'), pt_br='',
                    target_resource='Elliot/Content/Localization/Game/es/Game.locres') for r in parsed['en']]
    report.update(aligned_entries=sum(r['spanish'] is not None for r in aligned),
                  english_without_spanish=sum(r['spanish'] is None for r in aligned),
                  spanish_without_english=sum(identity(r) not in en for r in parsed['es']),
                  source_language='en', original_language='ja', reference_only_languages=['ja'],
                  japanese_reference_matches=sum(r['japanese_reference'] is not None for r in aligned),
                  future_replacement_language='es')
    (out / 'ingles-espanhol.json').write_text(json.dumps(aligned, ensure_ascii=False, indent=2), encoding='utf-8')
    (out / 'validacao.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    (out / 'LEIA-ME.txt').write_text(
        'Textos extraídos para leitura\n\n'
        'ingles.txt: texto inglês com namespace e chave.\n'
        'espanhol.txt: base espanhola preservada.\n'
        'japones_consulta.txt: texto original japonês, reservado apenas para futuras consultas.\n'
        'ingles-espanhol.json: alinhamento por namespace, chave e CRC da fonte; campo pt_br vazio.\n'
        'originais/: recursos LocRes extraídos sem mudanças.\n'
        'validacao.json: contagens, hashes e verificações.\n\n'
        'Fonte da tradução: inglês. Substituição futura: slot espanhol (es).\n'
        'Idioma original da obra: japonês. Uso do japonês: somente referência para consultas futuras.\n'
        'A ordem é a do recurso e não comprova sequência narrativa.\n'
        'Cobertura: Game.locres; textos em imagens, vídeos ou outros recursos não foram auditados aqui.\n'
        'Nenhum patch foi criado ou instalado.\n', encoding='utf-8-sig')
    print(json.dumps(report, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
