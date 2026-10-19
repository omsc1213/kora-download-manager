"""Integration checks against the compiled Rust coordinator and real backend."""
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_v02 import Handler,DATA

ROOT=Path(__file__).resolve().parents[1]
EXE=Path(os.environ.get('KORA_EXE',str(ROOT/'kora.exe')))

@unittest.skipUnless(EXE.is_file(),'Build kora.exe before running Rust binary integration tests')
class RustBinaryTests(unittest.TestCase):
    def setUp(self):
        folder=ROOT/'test-work';folder.mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=folder);self.addCleanup(self.temp.cleanup);self.work=Path(self.temp.name)
    def test_version_without_python(self):
        env={**os.environ,'KORA_PYTHON':str(self.work/'missing.exe')}
        result=subprocess.run([str(EXE),'--version'],capture_output=True,env=env,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr);self.assertIn(b'Rust coordinator',result.stdout)
    def test_missing_python_error(self):
        env={**os.environ,'KORA_PYTHON':str(self.work/'missing.exe')}
        result=subprocess.run([str(EXE),'--help'],capture_output=True,env=env,timeout=15)
        self.assertNotEqual(result.returncode,0);self.assertIn(b'KORA_PYTHON',result.stderr)
    def test_spaces_unicode_and_literal_arguments(self):
        folder=self.work/'Kora caf\u00e9 with spaces';folder.mkdir();exe=folder/'kora.exe';shutil.copyfile(EXE,exe)
        (folder/'kora.py').write_text('import json,sys\nprint(json.dumps(sys.argv[1:]))\n',encoding='utf-8')
        args=['download','https://example.test/a?x=1&y=two words','C:\\a b\\caf\u00e9.zip']
        result=subprocess.run([str(exe),*args],capture_output=True,env={**os.environ,'KORA_PYTHON':sys.executable},timeout=15)
        self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(json.loads(result.stdout),args)
    def test_rea_passthrough(self):
        result=subprocess.run([str(EXE),'rea','--version'],capture_output=True,timeout=60)
        self.assertEqual(result.returncode,0,result.stderr);self.assertRegex(result.stdout.decode().strip(),r'^\d+\.\d+\.\d+$')
    def test_real_download_through_executable(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.daemon_threads=True
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            target=self.work/'download.bin'
            result=subprocess.run([str(EXE),'download',f'http://127.0.0.1:{server.server_port}/range',str(target),'4'],capture_output=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(target.read_bytes(),DATA)
        finally:server.shutdown();server.server_close();thread.join(timeout=2)

if __name__=='__main__':unittest.main(verbosity=2)
