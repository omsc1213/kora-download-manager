"""Kora desktop/CLI entry point. Python implementation; not a Rust binary."""
import argparse
import json
from pathlib import Path
import signal
import sys

from engine import Control, Interrupted, download
from rea_bridge import capture, workflow, discovery

ROOT=Path(__file__).resolve().parent

def main(args=None):
    args=list(sys.argv[1:] if args is None else args)
    if args and args[0]=='native-host':
        from browser_host import run
        run(args[1] if len(args)>1 else '');return 0
    if args and args[0]=='rea-paths':
        for value in discovery():
            if '\n' in value or '\r' in value:raise ValueError('Invalid dependency path')
            print(value)
        return 0
    if args and args[0]=='setup-video-tools':
        from setup_video_tools import install
        install();return 0
    if not args or args[0]=='gui':
        from desktop import launch
        launch();return 0
    if args[0]=='rea':
        code,out,err=capture(args[1:],timeout=3600)
        sys.stdout.buffer.write(out);sys.stderr.buffer.write(err);return code
    parser=argparse.ArgumentParser(description='Kora Download Manager 0.3')
    sub=parser.add_subparsers(dest='command',required=True)
    get=sub.add_parser('download');get.add_argument('url');get.add_argument('output');get.add_argument('connections',nargs='?',type=int,default=8)
    inspect=sub.add_parser('idm-workflow');inspect.add_argument('out',nargs='?',default=str(ROOT/'evidence/latest-v02'));inspect.add_argument('--target',default=r'')
    video_info=sub.add_parser('video-info');video_info.add_argument('url')
    video_get=sub.add_parser('video-download');video_get.add_argument('url');video_get.add_argument('output');video_get.add_argument('--quality',choices=['best','2160','1440','1080','720','480','360'],default='best');video_get.add_argument('--format-id')
    parsed=parser.parse_args(args)
    control=Control();signal.signal(signal.SIGINT,lambda *_:control.stop('Paused by Ctrl+C'))
    if parsed.command=='video-info':
        from video import inspect_video
        print(json.dumps(inspect_video(parsed.url,control),indent=2,ensure_ascii=False));return 0
    if parsed.command=='video-download':
        from video import download_video
        selection={'mode':'format','id':parsed.format_id} if parsed.format_id else {'mode':'best'}
        if parsed.quality!='best':selection['height']=int(parsed.quality)
        result=download_video(parsed.url,parsed.output,selection,control,lambda p:print(f"\r{p['bytes'] or 0:,} / {p['total'] or '?'} bytes",end='',flush=True))
        print('\n'+json.dumps(result,indent=2));return 0
    if parsed.command=='download':
        result=download(parsed.url,parsed.output,parsed.connections,control,lambda p:print(f"\r{p['bytes']:,} / {p['total'] or '?'} bytes",end='',flush=True))
        print('\n'+json.dumps(result,indent=2));return 0
    result=workflow(parsed.target,parsed.out,control,lambda p:print(f"{p['step']}/3 {p['command']}",flush=True))
    print(json.dumps(result,indent=2));return 0 if result['status']=='passed' else 1

if __name__=='__main__':
    try:sys.exit(main())
    except Interrupted as exc:print(f'Kora: {exc}. Run the same command to resume.',file=sys.stderr);sys.exit(130)
    except Exception as exc:print(f'Kora: {exc}',file=sys.stderr);sys.exit(1)
