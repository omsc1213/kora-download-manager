"""Local readiness checks. Does not access browser sessions or the network."""
import sys
import tempfile

def report():
    from preferences import data_dir
    checks={}
    try:
        import tkinter as tk
        root=tk.Tk();root.withdraw();root.update_idletasks();root.destroy()
        checks['desktop']='OK'
    except Exception as exc:checks['desktop']=str(exc)
    try:
        folder=data_dir();folder.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryFile(dir=folder) as handle:handle.write(b'Kora readiness check')
        checks['data_folder']='OK'
    except OSError as exc:checks['data_folder']=str(exc)
    try:
        from video import tools
        extractor,ffmpeg=tools()
        checks['video_extractor']='Found'
        checks['ffmpeg']='Found' if ffmpeg else 'Missing: run Setup-Video-Tools.cmd'
    except RuntimeError as exc:checks['video_extractor']=str(exc)
    return {'version':'0.4.2','python':sys.version.split()[0],
            'startup_ready':checks['desktop']=='OK' and checks['data_folder']=='OK',
            'checks':checks,'startup_log':str(data_dir()/'startup.log'),
            'help':'If video tools are missing, close Kora and run Setup-Video-Tools.cmd.'}
