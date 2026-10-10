import json
import tempfile
import threading
import sys
import unittest
from pathlib import Path
from runner.sandbox import execute

class NamespaceConcurrencyTests(unittest.TestCase):
    def test_host_uid_threads_do_not_prevent_namespace_creation(self):
        venv=sys.prefix
        if not Path(venv).exists():self.skipTest('Pinned Linux runtime unavailable')
        event=threading.Event()
        threads=[threading.Thread(target=event.wait) for _ in range(270)]
        for t in threads:t.start()
        try:
            with tempfile.TemporaryDirectory(dir='/dev/shm') as tmp:
                root=Path(tmp)
                for name in ('input','output','tmp'):(root/name).mkdir()
                result=execute(root,venv,'echo NAMESPACE_OK')
                self.assertEqual(result['status'],'ok',result)
                self.assertEqual(result['output'].strip(),'NAMESPACE_OK')
        finally:
            event.set()
            for t in threads:t.join()
