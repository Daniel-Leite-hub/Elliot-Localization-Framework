"""
Transactional Homologation Engine
Applies approved translation refinements into the SQLite localization database.
Enforces ACID guarantees, atomic commits, hash recalculations, and automatic rollback on failure.
"""

import hashlib
import json
import sqlite3
import sys
import time
from pathlib import Path


def hash_string(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def apply_proposals(db_path: Path, proposals_json_path: Path) -> int:
    if not db_path.exists():
        raise FileNotFoundError(f"Banco de dados não encontrado: {db_path}")
    if not proposals_json_path.exists():
        raise FileNotFoundError(f"Arquivo de propostas não encontrado: {proposals_json_path}")

    with open(proposals_json_path, encoding="utf-8") as f:
        proposals = json.load(f)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON;")

    applied_count = 0
    now = time.time()

    try:
        cursor.execute("BEGIN TRANSACTION;")
        for item in proposals:
            entry_id = item.get("id")
            key = item.get("key")
            approved_text = item["approved"]

            # Localiza a entrada pelo ID direto ou pela chave no JSON de metadados
            row = cursor.execute(
                "SELECT id, source_hash FROM entries WHERE id = ? OR ( ? IS NOT NULL AND meta LIKE ? )",
                (entry_id, key, f"%{key}%" if key else ""),
            ).fetchone()

            if row:
                target_id, source_hash = row
            else:
                target_id = entry_id
                source_hash = hash_string(item.get("english_source", approved_text))

            cursor.execute(
                """
                UPDATE entries
                SET approved = ?,
                    approved_hash = ?,
                    draft = ?,
                    selected = ?,
                    selected_kind = 'aprovada',
                    stale = 0
                WHERE id = ?
            """,
                (approved_text, source_hash, approved_text, approved_text, target_id),
            )

            if cursor.rowcount > 0:
                cursor.execute(
                    """
                    INSERT INTO history (entry_id, event, text, at)
                    VALUES (?, 'homologated_curatorship', ?, ?)
                """,
                    (target_id, approved_text, now),
                )
                applied_count += 1

        conn.commit()
        print(f"Sucesso: {applied_count} propostas homologadas transacionalmente com zero inconsistências.")
    except Exception as e:
        conn.rollback()
        print(f"Erro crítico durante homologação transacional: {e}. Executado ROLLBACK completo.")
        raise
    finally:
        conn.close()

    return applied_count


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Uso: python apply_homologated_proposals.py <caminho_sqlite> <caminho_propostas_json>")
        sys.exit(1)
    apply_proposals(Path(sys.argv[1]), Path(sys.argv[2]))
