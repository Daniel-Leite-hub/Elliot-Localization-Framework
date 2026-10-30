import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from selfcheck import run


class Integration(unittest.TestCase):
    def test_local_workflows(self):
        result=run()
        self.assertGreaterEqual(result['passed'],25)


if __name__=='__main__': unittest.main()
