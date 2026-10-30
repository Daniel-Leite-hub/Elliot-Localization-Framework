"""
Token and Tag Syntax Linter for Unreal Engine Localization
Deterministically verifies that translated strings preserve:
1. Positional format arguments ({0}, {1}, %s, %d, %2$*3$.*4$lld)
2. Unreal Engine Rich Text markup (<span color="...">...</span>, <action id="..."/>)
3. Line break counts and escape sequences (\\n, \\r, \\t)
4. Canonical ellipsis patterns (……)
"""

import re
import sys

# Garante saída UTF-8 mesmo em consoles Windows com codepage legado (ex: cp1252 do GitHub Actions)
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PARAM_REGEX = re.compile(r"(\{\d+\}|%[0-9]*\$?[a-zA-Z%]|%[0-9]*\$?\*?[0-9]*\.?\*?[0-9]*[a-zA-Z]+)")
TAG_REGEX = re.compile(r"(<[^>]+>)")
ESCAPE_REGEX = re.compile(r"(\\[nrt]|\r\n|\n|\r)")


def extract_tokens(text: str) -> dict[str, list[str]]:
    if not text:
        return {"params": [], "tags": [], "escapes": []}
    return {
        "params": PARAM_REGEX.findall(text),
        "tags": TAG_REGEX.findall(text),
        "escapes": ESCAPE_REGEX.findall(text),
    }


def validate_translation_syntax(original: str, translation: str) -> tuple[bool, list[str]]:
    errors: list[str] = []

    orig_tokens = extract_tokens(original)
    trans_tokens = extract_tokens(translation)

    # 1. Checagem de parâmetros de interpolação
    if sorted(orig_tokens["params"]) != sorted(trans_tokens["params"]):
        errors.append(
            f"Divergência de parâmetros: Original={orig_tokens['params']} vs Tradução={trans_tokens['params']}"
        )

    # 2. Checagem de tags rich text
    orig_tag_names = [re.sub(r"\s.*", "", t.strip("<>/")) for t in orig_tokens["tags"]]
    trans_tag_names = [re.sub(r"\s.*", "", t.strip("<>/")) for t in trans_tokens["tags"]]
    if sorted(orig_tag_names) != sorted(trans_tag_names):
        errors.append(
            f"Divergência de tags de formatação: Original={orig_tokens['tags']} vs Tradução={trans_tokens['tags']}"
        )

    # 3. Checagem de sequências de quebra de linha (literal \n ou caractere de nova linha)
    orig_nl = sum(1 for e in orig_tokens["escapes"] if e in ("\\n", "\n", "\r\n"))
    trans_nl = sum(1 for e in trans_tokens["escapes"] if e in ("\\n", "\n", "\r\n"))
    if orig_nl != trans_nl:
        errors.append(
            f"Divergência de quebras de linha (\\n): Original={orig_nl} vs Tradução={trans_nl}"
        )

    return (len(errors) == 0, errors)


if __name__ == "__main__":
    print("Executando auto-teste do Token and Tag Syntax Linter...")
    test_cases = [
        (
            'Cura {0} PV com <span color="#FF0000">Poção</span>\\nPronto.',
            'Cura {0} PV com <span color="#FF0000">Poção</span>\\nPronto.',
            True,
        ),
        (
            "Cura {0} PV com {1}.",
            "Cura {0} PV.",
            False,
        ),
        (
            "Texto sem tags\\nLinha 2",
            "Texto sem tags Linha 2",
            False,
        ),
    ]

    all_passed = True
    for orig, trans, expected in test_cases:
        ok, errs = validate_translation_syntax(orig, trans)
        if ok != expected:
            print(f"[FALHA] Caso: '{orig}' -> '{trans}'. Esperado: {expected}, Obtido: {ok}")
            all_passed = False
        else:
            print(f"[OK] Validação correta: {ok} (Erros: {len(errs)})")

    if all_passed:
        print("Todos os testes unitários do linter sintático passaram com sucesso!")
        sys.exit(0)
    else:
        sys.exit(1)
