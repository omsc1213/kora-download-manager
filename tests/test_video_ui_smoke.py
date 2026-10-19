"""Exercise the actual Video links tab and download worker against local media."""
from pathlib import Path
import json,sys,time,tkinter as tk,subprocess
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from desktop import App
from test_video import VideoIntegrationTests
ROOT=Path(__file__).resolve().parents[1]
VideoIntegrationTests.setUpClass()
work=ROOT/'test-work';stamp=str(time.time_ns());db=work/('video-ui-'+stamp+'.db');target=work/('video-ui-'+stamp+'.mp4')
root=tk.Tk();app=App(root,db,auto_start=False);started=time.monotonic();phase='inspect';failed=[]
result_path=work/'video-ui-result.json'
def failure(kind,error,tb):
    import traceback
    failed.append(''.join(traceback.format_exception(kind,error,tb)));app.close()
root.report_callback_exception=failure
app.tabs.select(1)
def popup_failure(*args,**kwargs):raise AssertionError(str(args))
popup=patch('desktop.messagebox.showerror',side_effect=popup_failure);popup.start()
app.video_url.set(VideoIntegrationTests.base+'/watch.html');app.find_video()
def tick():
    global phase
    if time.monotonic()-started>90:raise AssertionError('Video UI timed out')
    if phase=='inspect' and app.video_info:
        assert app.video_source==app.video_url.get()
        assert app.video_choices
        root.update_idletasks();assert app.quality_box.winfo_width()>500
        app.video_destination.set(str(target));app.add_video()
        row=app.store.rows()[0];assert row[8]=='video'
        app.start_job(row);phase='download'
    elif phase=='download':
        row=app.store.rows()[0]
        if row[4]=='Failed':raise AssertionError(row[7])
        if row[4]=='Completed':
            result=subprocess.run([VideoIntegrationTests.ffmpeg,'-v','error','-i',str(target),'-f','null','-'],capture_output=True,timeout=30)
            assert result.returncode==0,result.stderr
            result_path.write_text(json.dumps({'video_inspection':'passed','quality_selection':'passed','video_queue_download':'passed','media_decode':'passed','visual_capture':'not verified'}))
            app.close();return
    root.after(100,tick)
root.after(100,tick)
try:
    root.mainloop()
    if failed:raise AssertionError(failed)
    reopened=tk.Tk();second=App(reopened,db,auto_start=False)
    assert second.store.rows()[0][4]=='Completed'
    assert second.store.rows()[0][8]=='video'
    data=json.loads(result_path.read_text());data['video_queue_reopen']='passed';result_path.write_text(json.dumps(data))
    reopened.after(100,second.close);reopened.mainloop()
finally:
    popup.stop();VideoIntegrationTests.tearDownClass()
print(result_path.read_text())
