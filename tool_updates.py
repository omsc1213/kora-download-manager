"""Transactional replacement of the video-tool set with explicit rollback."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ARTIFACTS=('vendor','tools/ffmpeg','tools/dependency-manifest.json')

def validate_tools(root):
    env={**os.environ,'PYTHONUTF8':'1'}
    commands=([sys.executable,str(root/'video_tool.py'),'--version'],[str(root/'tools/ffmpeg/ffmpeg.exe'),'-version'])
    for command in commands:
        result=subprocess.run(command,capture_output=True,timeout=30,env=env,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if result.returncode:raise RuntimeError('Updated video tools failed the startup check')

def restore(root,backup):
    for name in ARTIFACTS:
        dest=root/name;old=backup/name
        if dest.is_dir():shutil.rmtree(dest)
        elif dest.exists():dest.unlink()
        if old.exists():
            dest.parent.mkdir(parents=True,exist_ok=True)
            if old.is_dir():shutil.copytree(old,dest)
            else:shutil.copy2(old,dest)

def snapshot(root):
    backups=root/'data/tool-backups';backups.mkdir(parents=True,exist_ok=True)
    backup=backups/str(time.time_ns());backup.mkdir()
    for name in ARTIFACTS:
        source=root/name;dest=backup/name
        if source.exists():
            dest.parent.mkdir(parents=True,exist_ok=True)
            if source.is_dir():shutil.copytree(source,dest,ignore=shutil.ignore_patterns('__pycache__'))
            else:shutil.copy2(source,dest)
    return backup

def finish(root,backup):
    validate_tools(root)
    pointer=root/'data/tool-backup.json';pointer.write_text(json.dumps({'directory':backup.name}),encoding='utf-8')

def rollback_tools(root):
    pointer=json.loads((root/'data/tool-backup.json').read_text(encoding='utf-8'))
    name=pointer.get('directory','')
    if not name.isdigit():raise RuntimeError('No valid rollback snapshot is available')
    backup=root/'data/tool-backups'/name
    if not backup.is_dir():raise RuntimeError('The rollback copy is missing')
    current=snapshot(root)
    try:restore(root,backup);validate_tools(root)
    except BaseException:restore(root,current);raise
    (root/'data/tool-backup.json').write_text(json.dumps({'directory':current.name}),encoding='utf-8')
