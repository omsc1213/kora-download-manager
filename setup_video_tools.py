"""Install/update local video tools from published, hash-verified PyPI wheels."""
from contextlib import ExitStack,nullcontext
import hashlib,json,os
from pathlib import Path,PurePosixPath
import shutil,sys,tempfile,time,urllib.error,urllib.request,zipfile
from engine import SafeRedirect,download,digest,job_lock
ROOT=Path(__file__).resolve().parent
def transport(url,headers):
    request=urllib.request.Request(url,headers={'Accept-Encoding':'identity','User-Agent':'Kora-setup',**headers})
    try:return urllib.request.build_opener(SafeRedirect()).open(request,timeout=45)
    except urllib.error.HTTPError as response:return response
def metadata(name):
    with urllib.request.urlopen('https://pypi.org/pypi/'+name+'/json',timeout=45) as response:return json.load(response)
def install(lock_app=True):
    state=ROOT/'data';state.mkdir(exist_ok=True)
    guard=state/'app-lock';guard.mkdir(exist_ok=True)
    tools=ROOT/'tools';tools.mkdir(exist_ok=True)
    with (job_lock(guard) if lock_app else nullcontext()):
        yt=metadata('yt-dlp');ff=metadata('imageio-ffmpeg')
        assets=[next(a for a in yt['urls'] if a['filename'].endswith('.whl')),next(a for a in ff['urls'] if 'win_amd64' in a['filename'])]
        cache=state/'video-cache';cache.mkdir(exist_ok=True)
        archives=[]
        for asset in assets:
            path=cache/asset['filename'];expected=asset['digests']['sha256']
            print('Obtaining '+asset['filename'],flush=True)
            if path.exists() and digest(path)!=expected:path.unlink()
            if not path.exists():
                last=0
                def progress(p):
                    nonlocal last
                    if time.monotonic()-last>3:
                        print(str(p['bytes'])+' / '+str(p['total'])+' bytes',flush=True);last=time.monotonic()
                download(asset['url'],path,2,progress=progress,transport=transport)
            if digest(path)!=expected:raise RuntimeError('Published SHA-256 did not match '+asset['filename'])
            archives.append(path)
        with tempfile.TemporaryDirectory(dir=cache,prefix='install-') as temporary:
            stage=Path(temporary);new_vendor=stage/'vendor';new_vendor.mkdir()
            with zipfile.ZipFile(archives[0]) as archive:
                for name in archive.namelist():
                    parts=PurePosixPath(name)
                    if parts.is_absolute() or '..' in parts.parts or '\\' in name or ':' in name:raise RuntimeError('Unsafe archive path')
                archive.extractall(new_vendor)
            with zipfile.ZipFile(archives[1]) as archive:
                binary=next(n for n in archive.namelist() if n.endswith('.exe'))
                new_ff=stage/'ffmpeg.exe';new_ff.write_bytes(archive.read(binary))
                notices=stage/'licenses';notices.mkdir()
                for name in archive.namelist():
                    if 'license' in Path(name).name.lower() or 'copying' in Path(name).name.lower():
                        (notices/Path(name).name).write_bytes(archive.read(name))
            from tool_updates import snapshot,finish,restore
            rollback=snapshot(ROOT)
            vendor=ROOT/'vendor';backup=ROOT/('vendor-backup-'+str(time.time_ns()))
            if vendor.exists():vendor.rename(backup)
            try:new_vendor.rename(vendor)
            except Exception:
                if backup.exists() and not vendor.exists():backup.rename(vendor)
                raise
            try:
                ffdir=tools/'ffmpeg';ffdir.mkdir(exist_ok=True)
                os.replace(new_ff,ffdir/'ffmpeg.exe')
                dest=ffdir/'licenses';dest.mkdir(exist_ok=True)
                for path in notices.iterdir():shutil.copyfile(path,dest/path.name)
            except BaseException:restore(ROOT,rollback);raise
        manifest={'installed_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'yt_dlp':{'version':yt['info']['version'],'url':assets[0]['url'],'sha256':assets[0]['digests']['sha256']},'ffmpeg':{'provider':'imageio-ffmpeg','version':ff['info']['version'],'url':assets[1]['url'],'sha256':assets[1]['digests']['sha256'],'binary_sha256':digest(tools/'ffmpeg/ffmpeg.exe')},'sources':['https://github.com/yt-dlp/yt-dlp','https://github.com/imageio/imageio-ffmpeg','https://ffmpeg.org/']}
        try:
            from engine import atomic_json
            atomic_json(tools/'dependency-manifest.json',manifest)
            finish(ROOT,rollback)
        except BaseException:restore(ROOT,rollback);raise
        print('Video tools installed and checksums verified.',flush=True)
if __name__=='__main__':install()
