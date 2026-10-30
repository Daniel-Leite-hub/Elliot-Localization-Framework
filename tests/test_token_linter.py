"""
Unit tests for the Deterministic Token & Tag Linter
"""

import unittest
import sys
from pathlib import Path

# Adiciona o diretório do projeto e curatorship_pipeline ao sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from curatorship_pipeline.scripts.validate_tokens_and_tags import validate_translation_syntax

class TestTokenLinter(unittest.TestCase):
    def test_exact_token_preservation(self):
        orig = "Restores {0} HP and grants {1} MP."
        trans = "Restaura {0} PV e concede {1} PM."
        valid, errors = validate_translation_syntax(orig, trans)
        self.assertTrue(valid)
        self.assertEqual(errors, [])

    def test_missing_parameter_detection(self):
        orig = "Restores {0} HP and grants {1} MP."
        trans = "Restaura {0} PV."
        valid, errors = validate_translation_syntax(orig, trans)
        self.assertFalse(valid)
        self.assertTrue(any("Divergência de parâmetros" in e for e in errors))

    def test_rich_text_tag_preservation(self):
        orig = "Notice: <span color=\"#FFD700\">Legendary Sword</span> equipped."
        trans = "Aviso: <span color=\"#FFD700\">Espada Lendária</span> equipada."
        valid, errors = validate_translation_syntax(orig, trans)
        self.assertTrue(valid)

    def test_corrupted_tag_detection(self):
        orig = "Notice: <span color=\"#FFD700\">Legendary</span>."
        trans = "Aviso: <span color=\"#FFD700\">Lendária."
        valid, errors = validate_translation_syntax(orig, trans)
        self.assertFalse(valid)

    def test_line_break_preservation(self):
        orig = "Line 1\\nLine 2\\nLine 3"
        trans = "Linha 1\\nLinha 2\\nLinha 3"
        valid, errors = validate_translation_syntax(orig, trans)
        self.assertTrue(valid)

    def test_mismatched_line_breaks(self):
        orig = "Line 1\\nLine 2"
        trans = "Linha 1 Linha 2"
        valid, errors = validate_translation_syntax(orig, trans)
        self.assertFalse(valid)

if __name__ == "__main__":
    unittest.main()
