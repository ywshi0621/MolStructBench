import importlib.util,json,pathlib,unittest
from benchmark_core.io import load_public
ROOT=pathlib.Path(__file__).resolve().parents[1]
class EditionTests(unittest.TestCase):
    def test_independent_data_contract(self):
        rows,info=load_public(ROOT/'data/benchmark_288_public.jsonl')
        self.assertEqual(len(rows),288);self.assertEqual(info['task_units'],48)
    def test_edition_boundary(self):
        edition=json.loads((ROOT/'EDITION.json').read_text())
        if edition['harness_included']:
            self.assertTrue((ROOT/'runner').is_dir())
        else:
            for name in ('runner','opencode','tools','vendor'):
                self.assertFalse((ROOT/name).exists())
            self.assertIsNone(importlib.util.find_spec('runner'))
            self.assertIsNone(importlib.util.find_spec('runner.gateway') if importlib.util.find_spec('runner') else None)
