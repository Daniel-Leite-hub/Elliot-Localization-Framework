import unittest
from core import TOKENS, prepare, restore, validate


class PercentageMarkers(unittest.TestCase):
    def test_percent_is_not_a_printf_placeholder_after_number_or_field(self):
        for source in ['{Num:1}% chance', '{Num:1}% or greater', '50% damage', '{Num:1}% for a while']:
            self.assertFalse(any(t.startswith('%') for t in TOKENS.findall(source)))
            xml, markers = prepare(source)
            self.assertEqual(restore(xml, markers), source)

    def test_real_printf_stays_protected(self):
        self.assertEqual(TOKENS.findall('value %d %s %04d %1$s % d %%'), ['%d','%s','%04d','%1$s','% d','%%'])
        self.assertTrue(validate('value %d', 'valor %s')[0])

    def test_natural_percentage_translation(self):
        self.assertEqual(validate('Creates a {Num:1}% chance', 'Concede {Num:1}% de chance')[0], [])


if __name__ == '__main__':
    unittest.main()
