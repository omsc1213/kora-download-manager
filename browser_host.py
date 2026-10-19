"""Length-framed native messaging host. No cookies or browsing history captured."""
import json
import os
from pathlib import Path
import re
import struct
import sys
import urllib.parse
import uuid

from engine import validate_url
from queue_store import Store

ROOT=Path(__file__).resolve().parent
def read_exact(source,size):
    data=b''
    while len(data)<size:
        block=source.read(size-len(data))
        if not block:raise ValueError('Incomplete native message')
        data+=block
    return data
def read_message(source):
    size=struct.unpack('<I',read_exact(source,4))[0]
    if not 1<=size<=1024*1024:raise ValueError('Native message size exceeds the supported limit')
    return json.loads(read_exact(source,size).decode('utf-8'))
def write_message(dest,message):
    data=json.dumps(message).encode('utf-8');dest.write(struct.pack('<I',len(data))+data);dest.flush()
def enqueue(message,queue_path,download_dir,video_dir=None,connections=8,quality='best'):
    if not isinstance(message,dict) or message.get('action')!='queue':raise ValueError('Unsupported native action')
    url=message.get('url')
    if not isinstance(url,str) or len(url)>16384:raise ValueError('Invalid download URL')
    validate_url(url)
    kind=message.get('kind','file')
    if kind not in ('file','video'):raise ValueError('Invalid download kind')
    context={}
    if kind=='video':
        referer=message.get('referer')
        if referer:validate_url(referer);context['referer']=referer
        agent=message.get('user_agent')
        if agent:
            if not isinstance(agent,str) or len(agent)>512 or agent.startswith('-') or any(c in agent for c in '\r\n'):raise ValueError('Invalid browser user agent')
            context['user_agent']=agent
    name=urllib.parse.unquote(urllib.parse.urlsplit(url).path.rsplit('/',1)[-1])
    name=re.sub(r'[^\w.() -]','_',name).strip(' .')[:120] or 'download.bin'
    name=re.sub(r'\.{2,}','_',name)
    if name.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(1,10)),*(f'LPT{i}' for i in range(1,10))}:name='download-'+name
    if kind=='video':name=Path(name).stem+'.mp4'
    folder=(Path(video_dir) if video_dir else Path(download_dir)/'Videos') if kind=='video' else Path(download_dir)
    output=folder/(uuid.uuid4().hex[:8]+'-'+name)
    queue_path=Path(queue_path);queue_path.parent.mkdir(parents=True,exist_ok=True)
    store=Store(queue_path,recover=False)
    params={'mode':'best','context':context,'connections':connections} if kind=='video' else {}
    if kind=='video' and quality!='best':params['height']=int(quality)
    try:identity=store.add(url,str(output.absolute()),connections,kind=kind,params=params)
    finally:store.close()
    return {'ok':True,'job_id':identity}
def run(origin):
    if os.name=='nt':
        import msvcrt
        msvcrt.setmode(sys.stdin.fileno(),os.O_BINARY);msvcrt.setmode(sys.stdout.fileno(),os.O_BINARY)
    try:
        config=json.loads((ROOT/'browser-host.json').read_text(encoding='utf-8-sig'))
        if origin not in config.get('allowed_origins',[]):raise ValueError('Caller origin is not registered')
        import preferences
        settings=preferences.load()
        response=enqueue(read_message(sys.stdin.buffer),preferences.data_dir()/'jobs.db',settings['file_folder'],settings['video_folder'],settings['connections'],settings['quality'])
    except Exception as exc:response={'ok':False,'error':str(exc)}
    write_message(sys.stdout.buffer,response)
