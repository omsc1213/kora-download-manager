import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import browser_host
import rea_bridge
from engine import Control,Interrupted
from queue_store import Store

class BridgeTests(unittest.TestCase):
    def setUp(self):
        work=Path(__file__).resolve().parents[1]/'test-work/bridge';work.mkdir(parents=True,exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=work);self.addCleanup(self.tmp.cleanup);self.folder=Path(self.tmp.name)
    def test_native_framing_unicode(self):
        stream=io.BytesIO();message={'message':'café'};browser_host.write_message(stream,message);stream.seek(0)
        self.assertEqual(browser_host.read_message(stream),message)
    def test_native_oversized_message(self):
        with self.assertRaises(ValueError):browser_host.read_message(io.BytesIO(struct.pack('<I',1024*1024+1)))
    def test_native_truncated_message(self):
        with self.assertRaises(ValueError):browser_host.read_message(io.BytesIO(struct.pack('<I',20)+b'{}'))
    def test_browser_queue_safe_filename(self):
        path=self.folder/'queue.db';result=browser_host.enqueue({'action':'queue','url':'https://example.test/%2F..%2FCON.exe'},path,self.folder/'downloads')
        self.assertTrue(result['ok']);store=Store(path,recover=False);row=store.rows()[0];store.close()
        self.assertEqual(Path(row[2]).parent,self.folder/'downloads');self.assertNotIn('..',Path(row[2]).name)
    def test_browser_rejects_file_url(self):
        with self.assertRaises(ValueError):browser_host.enqueue({'action':'queue','url':'file:///private'},self.folder/'q.db',self.folder)
    def test_rea_timeout_kills_process(self):
        script=self.folder/'sleep.py';script.write_text('import time\ntime.sleep(30)\n')
        with patch.object(rea_bridge,'discovery',return_value=(sys.executable,str(script))):
            started=time.monotonic()
            with self.assertRaises(TimeoutError):rea_bridge.capture([],timeout=.2)
            self.assertLess(time.monotonic()-started,15)
    def test_rea_cancel(self):
        control=Control();control.stop('Cancelled')
        with self.assertRaises(Interrupted):rea_bridge.capture([],control)
    def test_timeout_writes_workflow_summary(self):
        target=self.folder/'target.exe';target.write_bytes(b'fixture')
        with patch.object(rea_bridge,'capture',side_effect=TimeoutError('test timeout')):
            result=rea_bridge.workflow(target,self.folder/'evidence')
        self.assertEqual(result['status'],'incomplete');self.assertEqual(len(result['steps']),3)
        self.assertTrue(all(step['status']=='failed' for step in result['steps']))
        self.assertEqual(json.loads((self.folder/'evidence/workflow-summary.json').read_text())['status'],'incomplete')

if __name__=='__main__':unittest.main(verbosity=2)
