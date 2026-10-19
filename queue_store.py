"""Small durable queue. Running jobs reopen paused, never restart silently."""
import sqlite3
import time
import json

class Store:
    def __init__(self,path,recover=True):
        self.db=sqlite3.connect(path,timeout=10)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('CREATE TABLE IF NOT EXISTS jobs(id INTEGER PRIMARY KEY,url TEXT NOT NULL,path TEXT NOT NULL,connections INTEGER NOT NULL,status TEXT NOT NULL,bytes INTEGER NOT NULL DEFAULT 0,total INTEGER,note TEXT NOT NULL DEFAULT \'\',created REAL NOT NULL)')
        columns={row[1] for row in self.db.execute('PRAGMA table_info(jobs)')}
        if 'kind' not in columns:self.db.execute("ALTER TABLE jobs ADD COLUMN kind TEXT NOT NULL DEFAULT 'file'")
        if 'params' not in columns:self.db.execute("ALTER TABLE jobs ADD COLUMN params TEXT NOT NULL DEFAULT '{}'")
        if recover:self.db.execute("UPDATE jobs SET status='Paused',note='Recovered after application restart' WHERE status IN ('Downloading','Pausing','Cancelling')")
        self.db.commit()
    def add(self,url,path,connections,kind='file',params=None):
        if kind not in ('file','video'):raise ValueError('Invalid download kind')
        if params is not None and not isinstance(params,dict):raise ValueError('Invalid job settings')
        cur=self.db.execute("INSERT INTO jobs(url,path,connections,status,created,kind,params) VALUES(?,?,?,'Queued',?,?,?)",(url,path,connections,time.time(),kind,json.dumps(params or {})));self.db.commit();return cur.lastrowid
    def rows(self): return self.db.execute('SELECT id,url,path,connections,status,bytes,total,note,kind,params FROM jobs ORDER BY id').fetchall()
    def update(self,identity,**values):
        allowed={'status','bytes','total','note'}
        if not values or not set(values)<=allowed: raise ValueError('Invalid queue update')
        self.db.execute('UPDATE jobs SET '+','.join(k+'=?' for k in values)+' WHERE id=?',(*values.values(),identity));self.db.commit()
    def remove_completed(self):
        self.db.execute("DELETE FROM jobs WHERE status='Completed'");self.db.commit()
    def close(self): self.db.close()
