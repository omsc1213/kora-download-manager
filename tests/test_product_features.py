import io,json,os,sys,tempfile,threading,time,unittest,zipfile,hashlib
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import preferences
from product_features import parse_links
from speed_control import AdaptiveTransport
from engine import Control,Interrupted,download
from tool_updates import snapshot,restore,rollback_tools
from queue_store import Store
ROOT=Path(__file__).resolve().parents[1]

class ProductTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'test-work');self.folder=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def test_preferences_round_trip(self):
        path=self.folder/'settings.json';value={**preferences.defaults(),'connections':12,'quality':'720','video_folder':str(self.folder/'videos')}
        preferences.save(value,path);self.assertEqual(preferences.load(path),value)
    def test_bad_preferences_do_not_replace_valid_file(self):
        path=self.folder/'settings.json';preferences.save(preferences.defaults(),path);original=path.read_bytes()
        with self.assertRaises(ValueError):preferences.save({'connections':99},path)
        self.assertEqual(path.read_bytes(),original)
    def test_corrupt_preferences_fall_back(self):
        path=self.folder/'settings.json';path.write_text('broken');self.assertEqual(preferences.load(path),preferences.defaults())
    def test_batch_validates_and_deduplicates(self):
        self.assertEqual(parse_links('https://example.test/1\n\nhttps://example.test/1\nhttps://example.test/2'),['https://example.test/1','https://example.test/2'])
        with self.assertRaises(ValueError):parse_links('https://youtu.be/123')
        with self.assertRaises(ValueError):parse_links('not a url')
        with self.assertRaises(ValueError):parse_links('\n')
    def test_batch_limit(self):
        with self.assertRaises(ValueError):parse_links('\n'.join(f'https://example.test/{n}' for n in range(101)))
    def test_clear_completed_keeps_files_and_active_rows(self):
        store=Store(self.folder/'queue.db');target=self.folder/'movie.mp4';target.write_bytes(b'movie')
        done=store.add('https://example.test/a',str(target),8);store.update(done,status='Completed')
        pending=store.add('https://example.test/b','other.mp4',8);store.remove_completed()
        self.assertEqual([r[0] for r in store.rows()],[pending]);self.assertEqual(target.read_bytes(),b'movie');store.close()
    def test_adaptive_reduces_and_releases_slots(self):
        class Response:
            status=429;headers={}
            def close(self):pass
        gate=AdaptiveTransport(lambda *_:Response(),8,Control());response=gate('https://example.test',{})
        self.assertEqual(gate.limit,4);self.assertEqual(gate.active,1);response.close();response.close();self.assertEqual(gate.active,0)
    def test_adaptive_failure_releases_slot(self):
        def fail(*_):raise OSError('network')
        gate=AdaptiveTransport(fail,8,Control())
        with self.assertRaises(OSError):gate('https://example.test',{})
        self.assertEqual(gate.active,0)
    def test_waiting_adaptive_request_cancels(self):
        control=Control();gate=AdaptiveTransport(None,1,control);gate.until=time.monotonic()+30
        control.stop()
        with self.assertRaises(Interrupted):gate('https://example.test',{})
    def test_tool_rollback_and_redo(self):
        (self.folder/'vendor').mkdir();(self.folder/'vendor/version').write_text('old')
        old=snapshot(self.folder);(self.folder/'vendor/version').write_text('new')
        (self.folder/'data/tool-backup.json').write_text(json.dumps({'directory':old.name}))
        with patch('tool_updates.validate_tools'):
            rollback_tools(self.folder);self.assertEqual((self.folder/'vendor/version').read_text(),'old')
            rollback_tools(self.folder);self.assertEqual((self.folder/'vendor/version').read_text(),'new')
    def test_bad_rollback_restores_current(self):
        (self.folder/'vendor').mkdir();(self.folder/'vendor/version').write_text('old')
        old=snapshot(self.folder);(self.folder/'vendor/version').write_text('current')
        (self.folder/'data/tool-backup.json').write_text(json.dumps({'directory':old.name}))
        with patch('tool_updates.validate_tools',side_effect=RuntimeError('bad')):
            with self.assertRaises(RuntimeError):rollback_tools(self.folder)
        self.assertEqual((self.folder/'vendor/version').read_text(),'current')
    def test_video_reduces_fragments_after_rate_limit(self):
        import video
        target=self.folder/'movie.mp4';counts=[]
        def run(args,control=None,timeout=None,on_line=None):
            counts.append(args[args.index('--concurrent-fragments')+1])
            if len(counts)==1:raise RuntimeError('HTTP Error 429')
            media=Path(str(target)+'.kora-video')/'media.mp4';media.write_bytes(b'video')
            on_line('KORA_DONE:'+json.dumps(str(media)))
        with patch('video.inspect_video',return_value={'title':'Video','formats':[]}),patch('video.tools',return_value=(['tool'],'ffmpeg.exe')),patch('video.run',side_effect=run):
            video.download_video('https://example.test/video',target,{'mode':'best','connections':8})
        self.assertEqual(counts,['8','4']);self.assertEqual(target.read_bytes(),b'video')
    def test_browser_jobs_use_preferred_folder_and_quality(self):
        from browser_host import enqueue
        folder=self.folder/'preferred'
        enqueue({'action':'queue','kind':'video','url':'https://example.test/video'},self.folder/'queue.db',self.folder/'files',folder,6,'720')
        store=Store(self.folder/'queue.db');row=store.rows()[0];store.close()
        self.assertEqual(Path(row[2]).parent,folder);self.assertEqual(row[3],6);self.assertEqual(json.loads(row[9])['height'],720)
    def exercise_update(self,fail=False):
        import setup_video_tools
        root=self.folder;cache=root/'data/video-cache';cache.mkdir(parents=True)
        (root/'vendor').mkdir();(root/'vendor/old.txt').write_text('old')
        (root/'tools/ffmpeg').mkdir(parents=True);(root/'tools/ffmpeg/ffmpeg.exe').write_bytes(b'old ffmpeg')
        yt=cache/'yt.whl';ff=cache/'imageio_win_amd64.whl'
        with zipfile.ZipFile(yt,'w') as archive:archive.writestr('yt_dlp/__init__.py','new')
        with zipfile.ZipFile(ff,'w') as archive:archive.writestr('imageio_ffmpeg/binaries/ffmpeg.exe',b'new ffmpeg')
        def meta(name):
            path=yt if name=='yt-dlp' else ff
            return {'info':{'version':'2'},'urls':[{'filename':path.name,'url':'https://example.test/'+path.name,'digests':{'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}}]}
        with patch('setup_video_tools.ROOT',root),patch('setup_video_tools.metadata',side_effect=meta),patch('tool_updates.validate_tools',side_effect=RuntimeError('invalid tool') if fail else None):
            if fail:
                with self.assertRaises(RuntimeError):setup_video_tools.install()
                self.assertEqual((root/'vendor/old.txt').read_text(),'old');self.assertEqual((root/'tools/ffmpeg/ffmpeg.exe').read_bytes(),b'old ffmpeg')
            else:
                setup_video_tools.install();self.assertEqual((root/'vendor/yt_dlp/__init__.py').read_text(),'new')
                self.assertEqual(json.loads((root/'tools/dependency-manifest.json').read_text())['yt_dlp']['version'],'2')
                self.assertTrue((root/'data/tool-backup.json').exists())
    def test_hash_verified_tool_update_transaction(self):self.exercise_update()
    def test_tool_update_failure_restores_previous_tools(self):self.exercise_update(True)
    def test_desktop_batch_preferences_and_layout(self):
        import tkinter as tk
        from desktop import App
        root=tk.Tk();root.withdraw();app=App(root,self.folder/'queue.db',auto_start=False)
        def cleanup():
            for callback in root.tk.call('after','info'):root.after_cancel(callback)
            app.store.close();root.destroy()
        try:
            folder=self.folder/'videos';app.pref_video.set(str(folder));app.pref_files.set(str(self.folder/'files'));app.pref_quality.set('720');app.connections.set(6);app.save_preferences()
            self.assertEqual(preferences.load(app.settings_path)['connections'],6)
            app.batch_text.insert('1.0','https://example.test/1\nhttps://example.test/2')
            with patch('product_features.inspect_video',return_value={'title':'Example','duration':5,'formats':[]}):
                app.queue_batch();deadline=time.monotonic()+5
                while app.batch_control and time.monotonic()<deadline:root.update();time.sleep(.01)
            rows=app.store.rows();self.assertEqual(len(rows),2);self.assertNotEqual(rows[0][2],rows[1][2]);self.assertEqual(Path(rows[0][2]).parent,folder)
            self.assertEqual(json.loads(rows[0][9])['height'],720)
            app.tree.selection_set(str(rows[0][0]));app.resume()
            root.deiconify();root.update();self.assertGreater(app.tree.winfo_height(),40)
        finally:cleanup()

class ControlledSpeedTests(unittest.TestCase):
    def test_parallelism_on_latency_fixture(self):
        payload=b'x'*(4*1024*1024)
        class Response(io.BytesIO):
            status=206
            def __init__(self,a,b):super().__init__(payload[a:b+1]);self.headers={'ETag':'"test"','Content-Range':f'bytes {a}-{b}/{len(payload)}','Content-Length':str(b-a+1)}
            def geturl(self):return 'https://example.test/file'
        def transport(url,headers):
            time.sleep(.025);a,b=map(int,headers['Range'][6:].split('-'));return Response(a,b)
        with tempfile.TemporaryDirectory(dir=ROOT/'test-work') as work:
            times=[]
            for count in (1,8):
                started=time.monotonic();target=Path(work)/str(count)
                download('https://example.test/file',target,count,chunk_size=256*1024,transport=transport)
                times.append(time.monotonic()-started);self.assertEqual(target.read_bytes(),payload)
            print(f'Controlled latency fixture, 1 connection: {times[0]:.3f}s; 8 connections: {times[1]:.3f}s. Not a network benchmark.')
            self.assertLess(times[1],times[0])

if __name__=='__main__':unittest.main()
