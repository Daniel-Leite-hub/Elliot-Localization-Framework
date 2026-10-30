"""
Seed Demo Database Generator
Creates a fully functional SQLite demo database for the Elliot Localization Framework.
Enables local testing, UI exploration, and unit tests without needing proprietary game files.
"""

import hashlib
import json
import sqlite3
import time
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "demo_project.sqlite"
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

SAMPLE_ENTRIES = [
    {
        "resource": "Elliot/Content/Localization/Game/en/Game.locres",
        "category": "Story/MainQuest_M01",
        "language": "EN",
        "original": "Elliot, wake up! Today is the day of the Millennium Trial!",
        "draft": "Elliot, acorde! Hoje é o dia da Prova do Milênio!",
        "approved": "Elliot, acorde! Hoje é o dia da Prova do Milênio!",
        "position": 1,
        "kind": "traduzivel",
        "meta": {
            "external_id": '["StoryText","M01_Prologue_001"]',
            "speaker": "Faie",
            "sequence": "M01_Prologue_ElliotRoom",
            "sequence_proof": "StoryTable_M01",
            "ordinal": 1,
            "auxiliary": {
                "JA": {"text": "エリオット、起きて！今日は千年試練の日だよ！", "source_crc": 1001},
                "ES": {"text": "¡Elliot, despierta! ¡Hoy es el día de la Prueba del Milenio!", "source_crc": 1001},
            },
        },
    },
    {
        "resource": "Elliot/Content/Localization/Game/en/Game.locres",
        "category": "Story/MainQuest_M01",
        "language": "EN",
        "original": "……Five more minutes, Faie. Just five more……",
        "draft": "……Só mais cinco minutos, Faie. Só mais cinco……",
        "approved": "……Só mais cinco minutos, Faie. Só mais cinco……",
        "position": 2,
        "kind": "traduzivel",
        "meta": {
            "external_id": '["StoryText","M01_Prologue_002"]',
            "speaker": "Elliot",
            "sequence": "M01_Prologue_ElliotRoom",
            "sequence_proof": "StoryTable_M01",
            "ordinal": 2,
            "auxiliary": {
                "JA": {"text": "……あと５分、ファイエ。あと５分だけ……", "source_crc": 1002},
                "ES": {"text": "……Cinco minutos más, Faie. Solo cinco más……", "source_crc": 1002},
            },
        },
    },
    {
        "resource": "Elliot/Content/Localization/Game/en/Game.locres",
        "category": "Items/Consumables",
        "language": "EN",
        "original": 'Restores {0} HP to an ally and cures <span color="#00FF00">Poison</span>.',
        "draft": 'Restaura {0} PV de um aliado e cura <span color="#00FF00">Veneno</span>.',
        "approved": 'Restaura {0} PV de um aliado e cura <span color="#00FF00">Veneno</span>.',
        "position": 10,
        "kind": "traduzivel",
        "meta": {
            "external_id": '["ItemDescription","ITEM_HEAL_POTION_01"]',
            "auxiliary": {
                "JA": {"text": '味方一人のHPを{0}回復し、<span color="#00FF00">毒</span>を治癒する。', "source_crc": 2001},
                "ES": {"text": 'Restaura {0} PV a un aliado y cura el <span color="#00FF00">Veneno</span>.', "source_crc": 2001},
            },
        },
    },
    {
        "resource": "Elliot/Content/Localization/Game/en/Game.locres",
        "category": "Tutorial/Combat",
        "language": "EN",
        "original": "Input guard right before receiving an enemy attack to succeed in a perfect guard.",
        "draft": "Pressione a guarda no instante exato do golpe inimigo para executar um Bloqueio Perfeito.",
        "approved": "Pressione a guarda no instante exato do golpe inimigo para executar um Bloqueio Perfeito.",
        "position": 25,
        "kind": "traduzivel",
        "meta": {
            "external_id": '["TutorialText","TUT_PARRY_EXPLAIN"]',
            "auxiliary": {
                "JA": {"text": "敵の攻撃を受ける直前にガードを入力すると、ジャストガードが成功します。", "source_crc": 3001},
                "ES": {"text": "Pulsa guardia justo antes de recibir un ataque enemigo para lograr una guardia perfecta.", "source_crc": 3001},
            },
        },
    },
    {
        "resource": "Elliot/Content/Localization/Game/en/Game.locres",
        "category": "Support/Combat",
        "language": "EN",
        "original": "Elliot... Watch out! A big move is coming...!",
        "draft": "Elliot…… Cuidado! Ele vai usar o ataque supremo……!",
        "approved": "Elliot…… Cuidado! Ele vai usar o ataque supremo……!",
        "position": 40,
        "kind": "traduzivel",
        "meta": {
            "external_id": '["SupMsgText","SUP_FAIE_BOSS_DANGER"]',
            "speaker": "Faie",
            "auxiliary": {
                "JA": {"text": "エリオット……危ないっ！大技が来るよ……！", "source_crc": 4001},
                "ES": {"text": "¡Elliot... cuidado! ¡Se acerca un gran ataque...!", "source_crc": 4001},
            },
        },
    },
    {
        "resource": "Elliot/Content/Localization/Game/en/Game.locres",
        "category": "System/Actions",
        "language": "EN",
        "original": "Play with cat",
        "draft": "Brincar com o gato",
        "approved": "Brincar com o gato",
        "position": 55,
        "kind": "traduzivel",
        "meta": {
            "external_id": '["SystemText","SYS_CAT_PLAY_ACTION"]',
            "auxiliary": {
                "JA": {"text": "ネコとあそぶ", "source_crc": 5001},
                "ES": {"text": "Jugar con el gato", "source_crc": 5001},
            },
        },
    },
]


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def create_demo_database():
    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(DB_PATH)
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        conn.executescript(f.read())

    # Inserir configurações do projeto usando JSON válido (compatível com Store.setting)
    settings = [
        ("name", canonical_json("The Adventures of Elliot - PT-BR Localization")),
        ("project_name", canonical_json("The Adventures of Elliot - PT-BR Localization")),
        ("source_language", canonical_json("EN")),
        ("target_language", canonical_json("PT-BR")),
        ("dramatic_authority_language", canonical_json("JA")),
        ("unreal_version", canonical_json("4.27/5.x")),
        ("encryption_mode", canonical_json("AES-ECB")),
        ("target_replacement_slot", canonical_json("es")),
        ("lqa_curatorship_pass", canonical_json("2nd Pass (Editorial & Dramatic)")),
        ("general_context", canonical_json("")),
        ("before", canonical_json(2)),
        ("after", canonical_json(0)),
        ("glossary_id", canonical_json("")),
        ("glossary_revision", canonical_json("")),
        ("plan", canonical_json("Free")),
        ("formality", canonical_json("default")),
        ("notes", canonical_json("Projeto de demonstração homologado em PT-BR.")),
    ]
    conn.executemany("INSERT INTO settings (key, value) VALUES (?, ?)", settings)

    # Inserir falas de exemplo
    now = time.time()
    for entry in SAMPLE_ENTRIES:
        eid = hash_text(canonical_json([entry["resource"], entry["language"], entry["meta"]["external_id"]]))
        source_hash = hash_text(entry["original"])
        meta_json = canonical_json(entry["meta"])

        conn.execute(
            """
            INSERT INTO entries (
                id, resource, category, language, original, source_hash,
                position, kind, exclusion, meta, machine, machine_hash, draft, approved,
                approved_hash, stale, active, selected, selected_kind
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, '', ?, ?, ?, ?, ?, ?, 0, 1, ?, 'aprovada')
        """,
            (
                eid,
                entry["resource"],
                entry["category"],
                entry["language"],
                entry["original"],
                source_hash,
                entry["position"],
                entry["kind"],
                meta_json,
                entry["draft"],
                source_hash,
                entry["draft"],
                entry["approved"],
                source_hash,
                entry["approved"],
            ),
        )

        conn.execute(
            """
            INSERT INTO history (entry_id, event, text, at)
            VALUES (?, 'aprovada', ?, ?)
        """,
            (eid, entry["approved"], now),
        )

    conn.commit()
    conn.close()
    print(f"Banco de dados de demonstração gerado com sucesso: {DB_PATH}")


if __name__ == "__main__":
    create_demo_database()
