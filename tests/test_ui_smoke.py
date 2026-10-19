"""Owned-app smoke harness. Keeps its window open briefly for visual QA."""
from pathlib import Path
import sys
import json
import threading
import time
import tkinter as tk

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from desktop import App
from test_v02 import Handler,ThreadingHTTPServer,DATA

work=Path(__file__).resolve().parents[3]/'work/kora-ui-smoke';work.mkdir(parents=True,exist_ok=True)
stamp=str(time.time_ns());db=work/f'queue-{stamp}.db';output=work/f'fixture-{stamp}.bin'
server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.daemon_threads=True
threading.Thread(target=server.serve_forever,daemon=True).start()
root=tk.Tk();app=App(root,db,auto_start=False)
def callback_error(kind,error,traceback):
    import traceback as tb
    tb.print_exception(kind,error,traceback);app.closing=True
    if app.active:app.active[1].stop('Paused')
    root.after(100,app.close)
    result_path.write_text(json.dumps({'error':str(error)}))
root.report_callback_exception=callback_error
identity=app.store.add(f'http://127.0.0.1:{server.server_port}/range',str(output),4)
app.start_job(app.store.rows()[0]);started=time.monotonic()
result_path=work/'result.json'
def verify():
    rows=app.store.rows()
    if rows[0][4]=='Completed':
        assert output.read_bytes()==DATA
        app.store.add('https://example.test/next.zip',str(work/'next.zip'),4)
        app.refresh();app.message.set('Local HTTP download verified. Ready for another download.')
        root.update_idletasks()
        assert app.tree.winfo_width()>500 and app.tree.winfo_height()>100
        assert app.progress.winfo_width()>500
        result_path.write_text(json.dumps({'ui_download':'passed','queue_visible':True,'tree_size':[app.tree.winfo_width(),app.tree.winfo_height()],'visual_capture':'not available: Computer Use app-server missing'}))
        root.after(250,app.close)
        return
    if rows[0][4]=='Failed' or time.monotonic()-started>30:raise RuntimeError(str(rows))
    root.after(100,verify)
root.after(100,verify)
try:
    root.mainloop()
    reopened=tk.Tk();second=App(reopened,db,auto_start=False);reopened.update_idletasks()
    assert 'error' not in json.loads(result_path.read_text())
    assert second.store.rows()[0][4]=='Completed'
    assert second.tree.item(str(identity),'values')[1]=='Completed'
    result=json.loads(result_path.read_text());result['gui_queue_reopened']='passed';result_path.write_text(json.dumps(result))
    reopened.after(100,second.close);reopened.mainloop()
finally:server.shutdown();server.server_close()
