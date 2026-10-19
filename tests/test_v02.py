"""Real loopback HTTP integration tests plus queue/evidence regression tests."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import hashlib
import json
import os
from pathlib import Path
import socket
import ssl
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from engine import Control,Interrupted,ProtocolError,download,digest,job_lock
from queue_store import Store
from rea_bridge import validate_evidence
from engine import SafeRedirect

DATA=bytes(range(256))*2048

class Handler(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    calls=[];tag='"v1"';dropped=False;retry=False;lock=threading.Lock()
    def log_message(self,*args):pass
    def do_GET(self):
        path=self.path;interval=self.headers.get('Range');tag=type(self).tag
        with self.lock:self.calls.append((path,interval))
        if path=='/redirect':
            self.send_response(302);self.send_header('Location','/range');self.send_header('Content-Length','0');self.end_headers();return
        if path=='/missing':
            self.send_response(404);self.send_header('Content-Length','0');self.end_headers();return
        if path=='/empty':
            self.send_response(416 if interval else 200);self.send_header('Content-Range','bytes */0');self.send_header('Content-Length','0');self.end_headers();return
        if path=='/retry' and interval!='bytes=0-0':
            with self.lock:
                if not type(self).retry:
                    type(self).retry=True;self.send_response(503);self.send_header('Content-Length','0');self.end_headers();return
        if self.headers.get('If-Match') and self.headers['If-Match']!=tag:
            self.send_response(412);self.send_header('Content-Length','0');self.end_headers();return
        ranged=interval and path not in ('/single','/chunked')
        if ranged:
            a,b=map(int,interval.removeprefix('bytes=').split('-'));content=DATA[a:b+1]
            self.send_response(206)
            cr=f'bytes {a}-{b}/{len(DATA)}'
            if path=='/bad' and interval!='bytes=0-0':cr='bytes 0-0/1'
            self.send_header('Content-Range',cr)
        else:a,b=0,len(DATA)-1;content=DATA;self.send_response(200)
        if path!='/no-etag':self.send_header('ETag',tag)
        chunked=path=='/chunked' and not ranged
        self.send_header('Transfer-Encoding','chunked') if chunked else self.send_header('Content-Length',str(len(content)))
        self.end_headers()
        try:
            with self.lock:
                drop=path=='/drop' and interval!='bytes=0-0' and not type(self).dropped
                if drop:type(self).dropped=True
            if drop:
                self.wfile.write(content[:65536]);self.wfile.flush();self.close_connection=True
                self.connection.shutdown(socket.SHUT_RDWR);self.connection.close();return
            if chunked:
                for start in range(0,len(content),65536):
                    block=content[start:start+65536];self.wfile.write(f'{len(block):x}\r\n'.encode()+block+b'\r\n')
                self.wfile.write(b'0\r\n\r\n')
            else:self.wfile.write(content)
        except (BrokenPipeError,ConnectionResetError,OSError):pass

class LiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);cls.server.daemon_threads=True
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.base=f'http://127.0.0.1:{cls.server.server_port}'
    @classmethod
    def tearDownClass(cls):cls.server.shutdown();cls.server.server_close();cls.thread.join(timeout=2)
    def setUp(self):
        work=Path(__file__).resolve().parents[3]/'work/kora-v02-tests';work.mkdir(parents=True,exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=work);self.addCleanup(self.tmp.cleanup);self.output=Path(self.tmp.name)/'result.bin'
        Handler.calls=[];Handler.tag='"v1"';Handler.dropped=False;Handler.retry=False
    def get(self,path,**kwargs):return download(self.base+path,self.output,connections=kwargs.pop('connections',2),chunk_size=131072,**kwargs)
    def assert_data(self):self.assertEqual(self.output.read_bytes(),DATA)
    def test_parallel_hash(self):
        result=self.get('/range');self.assert_data();self.assertEqual(result['sha256'],hashlib.sha256(DATA).hexdigest())
    def test_range_ignored_downloads_once(self):
        self.get('/single');self.assert_data();self.assertEqual(Handler.calls,[('/single','bytes=0-0')])
    def test_empty_416(self):self.get('/empty');self.assertEqual(self.output.read_bytes(),b'')
    def test_redirect(self):self.get('/redirect');self.assert_data()
    def test_missing(self):
        with self.assertRaises(ProtocolError):self.get('/missing')
        self.assertFalse(self.output.exists())
    def test_bad_range_rejected(self):
        with self.assertRaises(ProtocolError):self.get('/bad')
        self.assertFalse(self.output.exists())
    def test_no_validator_single_stream(self):
        self.get('/no-etag');self.assert_data();self.assertEqual(len(Handler.calls),2)
    def test_chunked_full_response(self):self.get('/chunked');self.assert_data();self.assertEqual(len(Handler.calls),1)
    def test_drop_resumes_partial_bytes(self):
        self.get('/drop',connections=1);self.assert_data()
        self.assertTrue(any(r and r.startswith('bytes=65536-') for _,r in Handler.calls))
    def test_transient_retry(self):self.get('/retry',connections=1);self.assert_data();self.assertTrue(Handler.retry)
    def pause(self):
        ctrl=Control()
        def progress(p):
            if p['bytes']>=65536:ctrl.stop('Paused')
        with self.assertRaises(Interrupted):self.get('/range',connections=1,control=ctrl,progress=progress)
        self.assertFalse(self.output.exists());return Path(str(self.output)+'.kora-parts')
    def test_pause_resume_mid_part(self):
        work=self.pause();self.assertEqual((work/'part-0.bin').stat().st_size,65536)
        Handler.calls=[];self.get('/range');self.assert_data()
        self.assertIn(('/range','bytes=65536-131071'),Handler.calls)
    def test_changed_validator_restarts(self):
        self.pause();Handler.tag='"v2"';Handler.calls=[];self.get('/range');self.assert_data()
        self.assertIn(('/range','bytes=0-131071'),Handler.calls)
    def test_corrupt_checkpoint_restarts(self):
        work=self.pause();(work/'part-0.bin').write_bytes(b'X'*65536);Handler.calls=[]
        self.get('/range');self.assert_data();self.assertIn(('/range','bytes=0-131071'),Handler.calls)
    def test_existing_output_preserved(self):
        self.output.write_bytes(b'keep')
        with self.assertRaises(FileExistsError):self.get('/range')
        self.assertEqual(self.output.read_bytes(),b'keep')
    def test_lock_released_after_error(self):
        with self.assertRaises(ProtocolError):self.get('/bad')
        self.get('/range');self.assert_data()
    def test_lock_exclusive(self):
        work=Path(str(self.output)+'.kora-parts');work.mkdir()
        with job_lock(work):
            with self.assertRaises(RuntimeError):self.get('/range')
        self.get('/range');self.assert_data()
    def test_cancel_before_start(self):
        ctrl=Control();ctrl.stop('Cancelled')
        with self.assertRaises(Interrupted):self.get('/range',control=ctrl)
        self.assertEqual(Handler.calls,[])
    def test_queue_recovers_running(self):
        path=Path(self.tmp.name)/'queue.db';store=Store(path);identity=store.add('https://example.test/a','a.bin',4);store.update(identity,status='Downloading',bytes=64);store.close()
        store=Store(path);self.assertEqual(store.rows()[0][4:6],('Paused',64));store.close()
    def test_queue_external_add_does_not_reset_active(self):
        path=Path(self.tmp.name)/'queue.db';store=Store(path);identity=store.add('https://example.test/a','a.bin',4);store.update(identity,status='Downloading')
        second=Store(path,recover=False);second.add('https://example.test/b','b.bin',4);second.close()
        self.assertEqual(store.rows()[0][4],'Downloading');store.close()
    def test_tls_with_trusted_local_certificate(self):
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes,serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
        import datetime,ipaddress
        key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'localhost')])
        now=datetime.datetime.now(datetime.timezone.utc)
        cert=(x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-datetime.timedelta(minutes=5)).not_valid_after(now+datetime.timedelta(days=1)).add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]),False).add_extension(x509.BasicConstraints(ca=True,path_length=None),True).sign(key,hashes.SHA256()))
        folder=Path(self.tmp.name);certpath=folder/'cert.pem';keypath=folder/'key.pem'
        certpath.write_bytes(cert.public_bytes(serialization.Encoding.PEM));keypath.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.daemon_threads=True
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(certpath,keypath);server.socket=context.wrap_socket(server.socket,server_side=True)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        previous=os.environ.get('SSL_CERT_FILE');os.environ['SSL_CERT_FILE']=str(certpath)
        try:
            download(f'https://127.0.0.1:{server.server_port}/range',self.output,chunk_size=131072);self.assert_data()
        finally:
            if previous is None:os.environ.pop('SSL_CERT_FILE',None)
            else:os.environ['SSL_CERT_FILE']=previous
            server.shutdown();server.server_close();thread.join(timeout=2)

class EvidenceTests(unittest.TestCase):
    def valid(self):return {'evidence_id':'ev_'+'a'*64,'operation':'inspect_artifact','predicate_type':'rea.analysis','provider':{'id':'test'},'subject':{'digest':{'sha256':'b'*64}},'normalized_result':{},'limitations':[]}
    def test_structure_and_subject(self):self.assertEqual(validate_evidence(self.valid(),'inspect-artifact','b'*64),'ev_'+'a'*64)
    def test_wrong_subject(self):
        with self.assertRaises(ValueError):validate_evidence(self.valid(),'inspect-artifact','c'*64)
    def test_wrong_operation(self):
        with self.assertRaises(ValueError):validate_evidence(self.valid(),'inspect-pe-resources','b'*64)
    def test_bare_id_is_insufficient(self):
        with self.assertRaises(ValueError):validate_evidence({'evidence_id':'ev_'+'a'*64},'inspect-artifact','b'*64)
    def test_redirect_downgrade_refused(self):
        import urllib.request
        with self.assertRaises(ProtocolError):SafeRedirect().redirect_request(urllib.request.Request('https://example.test/a'),None,302,'',{},'http://example.test/a')

if __name__=='__main__':unittest.main(verbosity=2)
