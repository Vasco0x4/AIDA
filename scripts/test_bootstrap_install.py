import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from bootstrap_install import bootstrap

class BootstrapTest(unittest.TestCase):
    def test_preserves_existing_configuration(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            self.assertTrue(bootstrap(p))
            original=(p/'.env').read_bytes()
            self.assertFalse(bootstrap(p))
            self.assertEqual(original,(p/'.env').read_bytes())

    def test_independent_secrets(self):
        with tempfile.TemporaryDirectory() as a,tempfile.TemporaryDirectory() as b:
            bootstrap(Path(a));bootstrap(Path(b))
            def values(d):return dict(x.split('=',1) for x in (Path(d)/'.env').read_text().splitlines() if '=' in x)
            for key in ('POSTGRES_PASSWORD','SECRET_KEY'):
                self.assertNotEqual(values(a)[key],values(b)[key])

    def test_isolated_project(self):
        with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'AIDA_PROJECT_NAME':'aida-test','FRONTEND_PORT':'32338'}):
            bootstrap(Path(d))
            text=(Path(d)/'.env').read_text()
            self.assertIn('AIDA_VOLUME_PREFIX=aida_test',text)
            self.assertIn('FRONTEND_PORT=32338',text)
            self.assertIn('DEFAULT_CONTAINER_NAME=aida-test-pentest',text)

    def test_rejects_invalid_configuration(self):
        for values in ({'AIDA_PROJECT_NAME':'bad\nname'},{'BACKEND_PORT':'65536'}):
            with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,values):
                with self.assertRaises(ValueError):bootstrap(Path(d))
                self.assertFalse((Path(d)/'.env').exists())

if __name__=='__main__':unittest.main()
