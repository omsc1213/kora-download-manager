"""REA discovery and cancellable, recorded read-only investigations."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

from engine import Control, Interrupted, atomic_json, digest

ROOT=Path(__file__).resolve().parent
def discovery():
    config_path=ROOT/'settings.json'
    try: config=json.loads(config_path.read_text(encoding='utf-8'))
    except (OSError,ValueError): config={}
    home=Path.home()
    node=os.environ.get('KORA_NODE') or config.get('node')
    if not node:node=shutil.which('node')
    entry=os.environ.get('KORA_REA_ENTRY') or config.get('rea_entry')
    candidates=[ROOT/'node_modules/rea-agents/scripts/rea.mjs',home/'AppData/Roaming/npm/node_modules/rea-agents/scripts/rea.mjs']
    found=shutil.which('rea')
    if found:candidates.append(Path(found).parent/'node_modules/rea-agents/scripts/rea.mjs')
    if not entry: entry=next((str(p) for p in candidates if p.is_file()),None)
    if not node or not Path(node).is_file(): raise RuntimeError('Node.js was not found. Set KORA_NODE or node in settings.json.')
    if not entry or not Path(entry).is_file(): raise RuntimeError('REA was not found. Set KORA_REA_ENTRY or rea_entry in settings.json.')
    return node,entry

def stop_process(process):
    if process.poll() is not None: return
    if os.name=='nt':
        try:
            subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        except (OSError,subprocess.TimeoutExpired):pass
    else: process.terminate()
    if process.poll() is None: process.kill()
    process.communicate(timeout=10)

def capture(args, control=None, timeout=180):
    control=control or Control();control.check();node,entry=discovery()
    process=subprocess.Popen([node,entry,*args],stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    started=time.monotonic()
    try:
        while True:
            control.check()
            if time.monotonic()-started>timeout: raise TimeoutError(f'REA exceeded {timeout:g} seconds')
            try:
                out,err=process.communicate(timeout=.15)
                return process.returncode,out,err
            except subprocess.TimeoutExpired: pass
    finally:
        if process.poll() is None: stop_process(process)

def validate_evidence(data, operation, expected_sha256):
    if not isinstance(data,dict): raise ValueError('Evidence must be an object')
    if not re.fullmatch(r'ev_[0-9a-f]{64}',str(data.get('evidence_id',''))): raise ValueError('Invalid evidence ID format')
    if data.get('operation')!=operation.replace('-','_'): raise ValueError('Evidence operation mismatch')
    if data.get('predicate_type')!='rea.analysis': raise ValueError('Unexpected evidence predicate')
    provider=data.get('provider')
    if not isinstance(provider,dict) or not provider.get('id'): raise ValueError('Missing provider identity')
    subject=data.get('subject',{})
    if subject.get('digest',{}).get('sha256','').lower()!=expected_sha256.lower(): raise ValueError('Evidence does not describe the selected file bytes')
    if not isinstance(data.get('normalized_result'),dict): raise ValueError('Missing structured result')
    if not isinstance(data.get('limitations'),list): raise ValueError('Missing limitations list')
    return data['evidence_id']

def workflow(target, out, control=None, progress=None, timeout=180):
    target=Path(target).resolve(strict=True);out=Path(out).absolute();out.mkdir(parents=True,exist_ok=True)
    control=control or Control();sha=digest(target)
    report={'version':2,'target':str(target),'sha256':sha,'steps':[],
            'validation_scope':'Structure, operation and subject digest checks; not cryptographic evidence-ID authentication.',
            'native_analysis':'Not automatically run; previous Ghidra attempt failed.'}
    try:
        for index,command in enumerate(('inspect-artifact','inspect-managed-artifact','inspect-pe-resources')):
            control.check();started=time.monotonic();step={'command':command,'status':'running'}
            report['steps'].append(step)
            if progress: progress({'step':index+1,'count':3,'command':command})
            atomic_json(out/'workflow-summary.json',report)
            try:
                code,raw,err=capture([command,str(target),'--format','json'],control,timeout)
                (out/f'{command}.json').write_bytes(raw);(out/f'{command}.stderr.txt').write_bytes(err)
                step['exit_code']=code
                if code: raise RuntimeError(f'REA returned exit code {code}; see the stderr record')
                data=json.loads(raw.decode('utf-8-sig'))
                step['evidence_id']=validate_evidence(data,command,sha)
                if digest(target)!=sha: raise ValueError('The selected file changed during inspection')
                step['status']='passed'
            except Interrupted:
                step['status']='cancelled';raise
            except Exception as exc:
                step['status']='failed';step['error']=str(exc)
            finally:
                step['elapsed_seconds']=round(time.monotonic()-started,3)
                atomic_json(out/'workflow-summary.json',report)
    finally:
        report['status']='passed' if len(report['steps'])==3 and all(s['status']=='passed' for s in report['steps']) else 'incomplete'
        atomic_json(out/'workflow-summary.json',report)
    return report
