"""Video-page inspection and downloads using verified, external yt-dlp/FFmpeg."""
from collections import deque
import json
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit

from engine import Control,Interrupted,atomic_json,digest,job_lock,publish,validate_url
from media_policy import check_info,reject_youtube

ROOT=Path(__file__).resolve().parent

def tools():
    yt=os.environ.get('KORA_YTDLP') or str(ROOT/'tools/yt-dlp.exe')
    ff=os.environ.get('KORA_FFMPEG') or str(ROOT/'tools/ffmpeg/ffmpeg.exe')
    if os.environ.get('KORA_YTDLP') and not Path(yt).is_file():
        raise RuntimeError('KORA_YTDLP does not point to a video tool.')
    if not Path(yt).is_file() and not (ROOT/'vendor/yt_dlp/__main__.py').is_file():yt=shutil.which('yt-dlp.exe') or ''
    if not Path(ff).is_file():ff=shutil.which('ffmpeg.exe') or ''
    if yt and Path(yt).is_file():command=[yt]
    elif (ROOT/'vendor/yt_dlp/__main__.py').is_file():command=[sys.executable,str(ROOT/'video_tool.py')]
    else:raise RuntimeError('Video tools are missing. Run Setup-Video-Tools.cmd.')
    return command,ff

def base_args(context=None):
    yt,ff=tools()
    args=[*yt,'--ignore-config','--no-plugin-dirs','--no-colors','--no-cache-dir','--no-playlist',
          '--use-extractors','default,-.*youtube.*','--socket-timeout','20','--retries','10','--extractor-retries','3','--http-chunk-size','10M']
    if ff:args+=['--ffmpeg-location',str(Path(ff).parent)]
    context=context or {}
    if context.get('twitter_api'):
        if context['twitter_api'] not in ('graphql','syndication'):raise ValueError('Invalid Twitter extraction method')
        args+=['--extractor-args','twitter:api='+context['twitter_api']]
    if context.get('referer'):
        validate_url(context['referer']);args+=['--referer',context['referer']]
    if context.get('user_agent'):
        agent=context['user_agent']
        if not isinstance(agent,str) or len(agent)>512 or agent.startswith('-') or any(c in agent for c in '\r\n'):raise ValueError('Invalid browser user agent')
        args+=['--user-agent',agent]
    return args

def stop_tree(process):
    if process.poll() is not None:return
    if os.name=='nt':
        try:subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        except (OSError,subprocess.TimeoutExpired):pass
    if process.poll() is None:process.kill()
    process.wait(timeout=10)

def run(args,control=None,timeout=180,on_line=None):
    control=control or Control();control.check()
    process=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',errors='replace',env={**os.environ,'PYTHONUTF8':'1'},creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    events=queue.Queue();threads=[]
    def reader(stream,kind):
        try:
            while True:
                line=stream.readline(32*1024*1024+1)
                if not line:break
                if len(line)>32*1024*1024:events.put(('error','Video tool returned an oversized record'));break
                events.put((kind,line))
        finally:stream.close();events.put(('closed',kind))
    for stream,kind in ((process.stdout,'out'),(process.stderr,'err')):
        thread=threading.Thread(target=reader,args=(stream,kind),daemon=True);thread.start();threads.append(thread)
    out=[];errors=deque(maxlen=20);closed=0;started=time.monotonic();size=0
    try:
        while closed<2 or process.poll() is None:
            control.check()
            if time.monotonic()-started>timeout:raise TimeoutError('Video operation timed out')
            try:kind,line=events.get(timeout=.1)
            except queue.Empty:continue
            if kind=='closed':closed+=1
            elif kind=='error':raise RuntimeError(line)
            elif kind=='err':errors.append(line[-2000:])
            else:
                size+=len(line)
                if not on_line and size>64*1024*1024:raise RuntimeError('Video tool returned too much output')
                if on_line:on_line(line.rstrip('\r\n'))
                else:out.append(line)
        code=process.wait()
        if code:
            detail=''.join(errors).strip()
            detail=re.sub(r'https?://\S+','[video URL]',detail)
            if re.search(r'(?:login required|sign in to|requires? (?:a )?login|private (?:video|tweet|post)|only available (?:for|to) registered)',detail,re.I):
                raise RuntimeError('This video requires login or is private. Kora has not imported a browser session.')
            if 'drm' in detail.lower():raise RuntimeError('This video is DRM-protected and is not supported')
            raise RuntimeError(detail[-1500:] or f'Video tool exited with code {code}')
        return ''.join(out)
    finally:
        if process.poll() is None:stop_tree(process)
        for thread in threads:thread.join(timeout=3)

def twitter_url(url):
    """Canonicalize official post links, preserving a selected video number."""
    parts=urlsplit(url)
    if parts.hostname not in ('x.com','www.x.com','mobile.x.com','twitter.com','www.twitter.com','mobile.twitter.com','m.twitter.com'):return url,False
    match=re.fullmatch(r'/(?:[^/]+/status|i/web/status|i/status|statuses)/(\d+)(/video/[1-9]\d*)?/?',parts.path)
    if not match:return url,False
    return 'https://twitter.com/i/web/status/'+match[1]+(match[2] or ''),True

def inspect_video(url,control=None,context=None):
    validate_url(url)
    url,is_twitter=twitter_url(url)
    context=dict(context or {})
    try:
        raw=run([*base_args(context),'--dump-single-json','--skip-download','--',url],control,timeout=180)
    except RuntimeError as first:
        if not is_twitter or 'drm' in str(first).lower():raise
        if control:control.check()
        context['twitter_api']='syndication'
        try:raw=run([*base_args(context),'--dump-single-json','--skip-download','--',url],control,timeout=180)
        except RuntimeError as exc:
            raise RuntimeError('Twitter/X could not provide this video. Update video tools and retry. The post may be unavailable or require login. Details: '+str(exc)) from exc
    try:info=json.loads(raw)
    except ValueError as exc:raise RuntimeError('Video information was not valid JSON') from exc
    check_info(info)
    if info.get('_type') in ('playlist','multi_video') or info.get('entries') is not None:
        entries=[entry for entry in info.get('entries',[]) if entry]
        if len(entries)!=1:raise ValueError('This page contains multiple videos. Open an individual video and paste its link.')
        info=entries[0];check_info(info)
    formats=[]
    for entry in info.get('formats') or [info]:
        if entry.get('has_drm') or entry.get('vcodec')=='none' or entry.get('protocol') in ('mhtml','images'):continue
        media=entry.get('url')
        try:
            if media:reject_youtube(media)
        except ValueError:continue
        identity=str(entry.get('format_id') or '')
        if not identity:continue
        formats.append({'id':identity,'height':entry.get('height'),'width':entry.get('width'),
                        'ext':entry.get('ext'),'audio':entry.get('acodec')!='none',
                        'size':entry.get('filesize') or entry.get('filesize_approx'),'note':entry.get('format_note') or ''})
    if not formats:raise ValueError('No downloadable, unprotected video formats were found')
    return {'title':str(info.get('title') or 'Video')[:400],'duration':info.get('duration'),'thumbnail':info.get('thumbnail'),
            'extractor':info.get('extractor_key') or info.get('extractor'),'formats':formats,
            'extraction_context':context,'source_url':url}

def selector_for(selection,info):
    selection=selection or {'mode':'best'}
    if selection.get('mode')=='format':
        identity=selection.get('id','')
        item=next((f for f in info['formats'] if f['id']==identity),None)
        if not item or not re.fullmatch(r'[A-Za-z0-9_.-]+',identity):raise ValueError('The selected format is no longer available; inspect the video again')
        return identity if item['audio'] else identity+'+bestaudio/'+identity
    height=selection.get('height')
    if height is not None:
        if type(height) is not int or height not in (2160,1440,1080,720,480,360):raise ValueError('Unsupported quality selection')
        return f'bestvideo*[height<={height}]+bestaudio/best[height<={height}]/bestvideo[height<={height}]'
    if selection.get('mode')!='best':raise ValueError('Invalid video selection')
    return 'bestvideo*+bestaudio/best/bestvideo'

def download_video(url,output,selection=None,control=None,progress=None):
    validate_url(url);control=control or Control();control.check()
    connections=(selection or {}).get('connections',8)
    if type(connections) is not int or not 1<=connections<=16:raise ValueError('Connections must be 1 to 16')
    target=Path(output).absolute()
    if target.suffix.lower() not in ('.mp4','.mkv','.webm','.mov'):raise ValueError('Choose an MP4, MKV, WebM or MOV output filename')
    if target.exists():raise FileExistsError('Destination exists; choose another filename')
    _,ff=tools()
    if not ff:raise RuntimeError('FFmpeg is missing. Run Setup-Video-Tools.cmd.')
    context=(selection or {}).get('context') or {}
    info=inspect_video(url,control,context);selector=selector_for(selection,info)
    context=info.get('extraction_context',context)
    url=info.get('source_url',url)
    target.parent.mkdir(parents=True,exist_ok=True);work=Path(str(target)+'.kora-video');work.mkdir(exist_ok=True)
    with job_lock(work):
        import hashlib
        identity={'url_sha256':hashlib.sha256(url.encode()).hexdigest(),'selector':selector,'container':target.suffix.lower()}
        state=work/'state.json'
        try:old=json.loads(state.read_text(encoding='utf-8'))
        except (OSError,ValueError):old={}
        if old!=identity:
            for path in work.iterdir():
                if path.name!='owner.lock' and path.is_file():path.unlink()
        atomic_json(state,identity)
        complete=[]
        def line(text):
            if text.startswith('KORA_PROGRESS:') and progress:
                try:
                    data=json.loads(text[len('KORA_PROGRESS:'):])
                    for key in ('bytes','total','speed','eta'):
                        if not isinstance(data.get(key),(int,float)):data[key]=None if key in ('total','eta') else 0
                    progress(data)
                except (ValueError,TypeError):pass
            elif text.startswith('KORA_DONE:'):
                value=json.loads(text[len('KORA_DONE:'):]);path=Path(value).resolve()
                if path.parent!=work.resolve():raise RuntimeError('Video tool returned an unexpected output path')
                complete.append(path)
        template=str(work/'media.%(ext)s')
        # Escape literal percent characters in the destination folder only.
        template=str(work).replace('%','%%')+os.sep+'media.%(ext)s'
        progress_template='download:KORA_PROGRESS:{"bytes":%(progress.downloaded_bytes|0)j,"total":%(progress.total_bytes,progress.total_bytes_estimate|0)j,"speed":%(progress.speed|0)j,"eta":%(progress.eta|0)j}'
        args=[*base_args(context),'--concurrent-fragments',str(connections),'--buffer-size','256K','--resize-buffer',
              '--fragment-retries','10','--abort-on-unavailable-fragments',
              '--no-simulate','--no-overwrites','--continue','--newline','--progress','--progress-delta','.2',
              '--progress-template',progress_template,'--print','after_move:KORA_DONE:%(filepath)j',
              '--format',selector,'--merge-output-format',target.suffix[1:].lower(),'--remux-video',target.suffix[1:].lower(),
              '--output',template,'--',url]
        while True:
            try:run(args,control,timeout=24*60*60,on_line=line);break
            except RuntimeError as exc:
                if not (selection or {}).get('adaptive',True) or connections<=1 or not any(code in str(exc) for code in ('429','503','502')):raise
                connections=max(1,connections//2)
                args[args.index('--concurrent-fragments')+1]=str(connections)
                complete.clear()
        control.check()
        if len(complete)!=1 or not complete[0].is_file():raise RuntimeError('Video tool did not produce one complete video')
        video=complete[0]
        if video.suffix.lower()!=target.suffix.lower():raise RuntimeError('The output container did not match the requested format')
        with video.open('r+b') as handle:handle.flush();os.fsync(handle.fileno())
        result={'bytes':video.stat().st_size,'sha256':digest(video),'title':info['title']}
        publish(video,target)
        for path in work.iterdir():
            if path.name!='owner.lock' and path.is_file():path.unlink()
        return result
