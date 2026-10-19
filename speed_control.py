"""Bound concurrency and back off when servers reject parallel requests."""
import threading
import time
from contextlib import contextmanager

class AdaptiveTransport:
    def __init__(self,transport,connections,control):
        self.transport=transport;self.limit=connections;self.control=control
        self.condition=threading.Condition();self.active=0;self.until=0
    def release(self):
        with self.condition:self.active-=1;self.condition.notify_all()
    def __call__(self,url,headers):
        with self.condition:
            while self.active>=self.limit or time.monotonic()<self.until:
                self.control.check();self.condition.wait(.1)
            self.control.check();self.active+=1
        try:
            response=self.transport(url,headers)
            if response.status in (429,500,502,503,504):
                with self.condition:
                    self.limit=max(1,self.limit//2)
                    try:delay=min(30,max(0,float(response.headers.get('Retry-After','0'))))
                    except ValueError:delay=0
                    self.until=max(self.until,time.monotonic()+delay)
            return LeasedResponse(response,self.release)
        except BaseException:self.release();raise

class LeasedResponse:
    def __init__(self,response,release):self.response=response;self.release=release;self.closed=False
    def __getattr__(self,key):return getattr(self.response,key)
    def close(self):
        if not self.closed:
            self.closed=True
            try:self.response.close()
            finally:self.release()
