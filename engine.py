"""Kora 0.2 transport, durable range state and managed cancellation."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
import hashlib
import http.client
import errno
import json
import os
from pathlib import Path
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from media_policy import reject_youtube

BLOCK = 256 * 1024
CHUNK = 4 * 1024 * 1024

class Interrupted(Exception): pass
class ProtocolError(Exception): pass
class Retryable(Exception): pass

class Control:
    def __init__(self):
        self.event = threading.Event()
        self.reason = 'Paused'
        self.responses = set()
        self.lock = threading.Lock()
    def stop(self, reason='Paused'):
        if not self.event.is_set(): self.reason = reason
        self.event.set()
    def check(self):
        if self.event.is_set(): raise Interrupted(self.reason)
    @contextmanager
    def response(self, response):
        with self.lock: self.responses.add(response)
        try: yield response
        finally:
            with self.lock: self.responses.discard(response)
            response.close()

class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        reject_youtube(newurl)
        before, after = urllib.parse.urlsplit(req.full_url), urllib.parse.urlsplit(newurl)
        if after.scheme not in ('http', 'https') or (before.scheme=='https' and after.scheme!='https'):
            raise ProtocolError('Refused an unsafe redirect')
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected and (before.scheme,before.netloc)!=(after.scheme,after.netloc):
            for key in ('Authorization','Cookie','If-match'):
                redirected.remove_header(key)
        return redirected

def open_http(url, headers):
    opener = urllib.request.build_opener(SafeRedirect())
    request = urllib.request.Request(url, headers={'Accept-Encoding':'identity','User-Agent':'Kora/0.2',**headers})
    try: return opener.open(request, timeout=8)
    except urllib.error.HTTPError as response: return response

def validate_url(url):
    reject_youtube(url)
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password or any(c in url for c in '\r\n'):
        raise ValueError('Enter an HTTP/HTTPS URL without embedded login credentials')

@contextmanager
def job_lock(work):
    """OS lock is automatically released after crashes. Its file is never unlinked."""
    path = work/'owner.lock'
    handle = path.open('a+b')
    try:
        handle.seek(0,2)
        if handle.tell()==0: handle.write(b'0'); handle.flush()
        handle.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError as exc: raise RuntimeError('This destination already has an active job') from exc
        try: yield
        finally:
            handle.seek(0)
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl
                fcntl.flock(handle,fcntl.LOCK_UN)
    finally: handle.close()

def atomic_json(path, data):
    temp = path.with_suffix('.new')
    with temp.open('w',encoding='utf-8') as handle:
        json.dump(data,handle);handle.flush();os.fsync(handle.fileno())
    os.replace(temp,path)

def digest(path):
    hasher=hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda:handle.read(BLOCK),b''): hasher.update(block)
    return hasher.hexdigest()

def publish(source, target):
    if os.name=='nt': os.rename(source,target) # refuses an existing destination
    else: os.link(source,target);source.unlink()

def partition(size, chunk_size=CHUNK):
    return [(start,min(size-1,start+chunk_size-1)) for start in range(0,size,chunk_size)]

def download(url, output, connections=8, control=None, progress=None, chunk_size=CHUNK, transport=open_http, adaptive=True):
    validate_url(url)
    if not 1<=connections<=16 or chunk_size<1: raise ValueError('Connections must be 1 to 16')
    control=control or Control();control.check()
    if adaptive:
        from speed_control import AdaptiveTransport
        transport=AdaptiveTransport(transport,connections,control)
    target=Path(output).absolute()
    if target.exists(): raise FileExistsError('Destination exists; choose a different filename')
    target.parent.mkdir(parents=True,exist_ok=True)
    work=Path(str(target)+'.kora-parts');work.mkdir(exist_ok=True)
    count_lock=threading.Lock();done=0;baseline=0;total=None;started=time.monotonic()
    def tick(delta=0, initial=None):
        nonlocal done,baseline
        with count_lock:
            done=initial if initial is not None else done+delta
            if initial is not None:baseline=initial
            elapsed=max(.01,time.monotonic()-started)
            speed=(done-baseline)/elapsed
            if progress: progress({'bytes':done,'total':total,'speed':speed,'eta':((total-done)/speed) if total and speed else None})
    def obtain(headers):
        for attempt in range(4):
            control.check()
            try:
                response=transport(url,headers)
                if response.status in (408,429,500,502,503,504):response.close();raise Retryable('Temporary server error')
                return response
            except (OSError,http.client.HTTPException,Retryable):
                if attempt==3:raise
                if control.event.wait(min(4,.25*2**attempt)):control.check()
    def check_response(response):
        if response.status in (408,429,500,502,503,504): raise Retryable(f'HTTP {response.status}; retrying')
        if response.status>=400: raise ProtocolError(f'HTTP {response.status}')
        if response.headers.get('Content-Encoding','identity').lower()!='identity': raise ProtocolError('Unexpected encoded response')
    def cleanup():
        # The caller owns the OS lock throughout cleanup; its file stays stable.
        for path in work.iterdir():
            if path.name!='owner.lock' and path.is_file():path.unlink()
    def single(response):
        nonlocal total
        check_response(response)
        if response.status!=200: raise ProtocolError('Expected a full-file response')
        length=response.headers.get('Content-Length');total=int(length) if length is not None else None
        temp=work/'single.partial';tick(initial=0)
        with temp.open('wb') as handle:
            while True:
                control.check();block=response.read(BLOCK)
                if not block: break
                handle.write(block);tick(len(block))
            handle.flush();os.fsync(handle.fileno())
        control.check()
        if total is not None and temp.stat().st_size!=total: raise ProtocolError('Incomplete response')
        publish(temp,target)
        cleanup()
    with job_lock(work):
        control.check()
        with control.response(obtain({'Range':'bytes=0-0'})) as probe:
            if probe.status==416 and probe.headers.get('Content-Range')=='bytes */0':
                empty=work/'empty.tmp';empty.write_bytes(b'');publish(empty,target);cleanup();return {'bytes':0,'sha256':digest(target)}
            if probe.status==200:
                single(probe) # reuse the full response; never download it twice
                return {'bytes':target.stat().st_size,'sha256':digest(target)}
            check_response(probe)
            match=re.fullmatch(r'bytes 0-0/(\d+)',probe.headers.get('Content-Range',''))
            if probe.status!=206 or not match or int(match[1])<1:
                raise ProtocolError('Invalid range probe')
            payload=probe.read(2)
            if len(payload)!=1: raise ProtocolError('Range probe returned an invalid body length')
            total=int(match[1]);etag=probe.headers.get('ETag','')
            strong=etag.startswith('"') and etag.endswith('"')
            final_url=probe.geturl()
        if not strong:
            # Without a stable validator, use one response to avoid mixing file versions.
            with control.response(obtain({})) as response: single(response)
            return {'bytes':target.stat().st_size,'sha256':digest(target)}
        chunk_size=max(chunk_size,(total+4095)//4096)
        plan=partition(total,chunk_size)
        identity={'version':2,'url_sha256':hashlib.sha256(url.encode()).hexdigest(),'length':total,'etag':etag,'chunk_size':chunk_size,'resolved_url_sha256':hashlib.sha256(final_url.encode()).hexdigest()}
        state_path=work/'state.json'
        try: old=json.loads(state_path.read_text(encoding='utf-8'))
        except (OSError,ValueError): old={}
        reuse=old==identity
        if not reuse:
            for path in work.glob('part-*'):
                if path.is_file(): path.unlink()
        atomic_json(state_path,identity)
        initial=0
        for index,(a,b) in enumerate(plan):
            part=work/f'part-{index}.bin';hash_path=work/f'part-{index}.sha256'
            if part.exists():
                size=part.stat().st_size
                if size>b-a+1 or not hash_path.exists() or hash_path.read_text()!=digest(part):
                    part.unlink();hash_path.unlink(missing_ok=True)
                else: initial+=size
        tick(initial=initial)
        def worker(index,a,b):
            part=work/f'part-{index}.bin';expected=b-a+1
            for attempt in range(4):
                control.check()
                have=part.stat().st_size if part.exists() else 0
                if have==expected: return
                response=None
                try:
                    response=transport(url,{'Range':f'bytes={a+have}-{b}','If-Match':etag})
                    with control.response(response):
                        check_response(response)
                        if response.status!=206 or response.headers.get('Content-Range')!=f'bytes {a+have}-{b}/{total}':
                            raise ProtocolError('Server did not honor the requested byte range')
                        if response.headers.get('ETag')!=etag: raise ProtocolError('Remote file identity changed')
                        remaining=expected-have
                        length=response.headers.get('Content-Length')
                        if length is not None and int(length)!=remaining: raise ProtocolError('Invalid range Content-Length')
                        with part.open('ab') as handle:
                            try:
                                while remaining:
                                    control.check();block=response.read(min(BLOCK,remaining))
                                    if not block: raise Retryable('Connection ended before the range completed')
                                    handle.write(block);remaining-=len(block);tick(len(block))
                                if response.read(1): raise ProtocolError('Range response was larger than requested')
                            finally:
                                handle.flush();os.fsync(handle.fileno())
                                (work/f'part-{index}.sha256').write_text(digest(part))
                        (work/f'part-{index}.sha256').write_text(digest(part))
                    return
                except (OSError,http.client.HTTPException,Retryable) as exc:
                    if isinstance(exc,OSError) and exc.errno in (errno.ENOSPC,errno.EACCES,errno.EROFS):
                        raise RuntimeError('Cannot write download data; check free space and file permissions') from exc
                    if attempt==3: raise RuntimeError('Connection failed after four attempts') from exc
                    if control.event.wait(min(4,.25*2**attempt)): control.check()
            raise RuntimeError('Worker could not finish')
        failure=None
        with ThreadPoolExecutor(max_workers=connections) as pool:
            pending=[pool.submit(worker,i,a,b) for i,(a,b) in enumerate(plan)]
            for future in as_completed(pending):
                try: future.result()
                except Exception as exc:
                    if failure is None: failure=exc
                    control.stop('Stopped after a worker failed')
            if failure: raise failure
        control.check()
        assembled=work/'assembled.tmp'
        with assembled.open('wb') as dest:
            for i,(a,b) in enumerate(plan):
                control.check();part=work/f'part-{i}.bin'
                if part.stat().st_size!=b-a+1: raise ProtocolError('Part length changed during assembly')
                if digest(part)!=(work/f'part-{i}.sha256').read_text(): raise ProtocolError('Part checksum changed during assembly')
                with part.open('rb') as src:
                    for block in iter(lambda:src.read(BLOCK),b''): control.check();dest.write(block)
            dest.flush();os.fsync(dest.fileno())
        if assembled.stat().st_size!=total: raise ProtocolError('Assembly length mismatch')
        checksum=digest(assembled);control.check();publish(assembled,target)
        # Cleanup stays inside the OS lock. Keep owner.lock and its directory stable.
        cleanup()
        return {'bytes':total,'sha256':checksum}
