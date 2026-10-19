"""Video integration tests use actual yt-dlp, FFmpeg and a local HTTP server."""
from functools import partial
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
import io,json,os
from pathlib import Path
import sqlite3,subprocess,sys,tempfile,threading,time,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from engine import Control,Interrupted,validate_url
from media_policy import check_info,reject_youtube
from video import inspect_video,download_video,selector_for,tools,run,base_args
from queue_store import Store
from browser_host import enqueue

ROOT=Path(__file__).resolve().parents[1]

class PolicyTests(unittest.TestCase):
    def test_youtube_hosts_and_subdomains(self):
        for url in ('https://youtube.com/watch?v=x','https://m.youtube.com/shorts/x','https://youtu.be/x','https://www.youtube-nocookie.com/embed/x','https://r1.googlevideo.com/videoplayback','https://youtube.com./x'):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):validate_url(url)
    def test_domain_boundaries(self):
        for url in ('https://notyoutube.com/video','https://youtube.com.example.test/video','https://vimeo.com/123'):
            reject_youtube(url)
    def test_embedded_youtube_rejected(self):
        with self.assertRaises(ValueError):check_info({'extractor_key':'Youtube','webpage_url':'https://example.test/embed'})
    def test_youtube_media_metadata_rejected(self):
        with self.assertRaises(ValueError):check_info({'extractor_key':'Generic','url':'https://r1.googlevideo.com/videoplayback'})
    def test_drm_rejected(self):
        with self.assertRaises(ValueError):check_info({'has_drm':True})
    def test_format_selector_revalidates_ids(self):
        info={'formats':[{'id':'safe','audio':False}]}
        self.assertEqual(selector_for({'mode':'format','id':'safe'},info),'safe+bestaudio/safe')
        with self.assertRaises(ValueError):selector_for({'mode':'format','id':'missing'},info)
    def test_queue_video_options_persist(self):
        work=ROOT/'test-work';work.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=work) as d:
            path=Path(d)/'queue.db';store=Store(path);store.add('https://example.test/a','a.mp4',4,'video',{'mode':'best','height':720});store.close()
            store=Store(path);row=store.rows()[0];self.assertEqual(row[8],'video');self.assertEqual(json.loads(row[9])['height'],720);store.close()
    def test_old_queue_schema_migrates(self):
        work=ROOT/'test-work';work.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=work) as d:
            path=Path(d)/'old.db';db=sqlite3.connect(path)
            db.execute("CREATE TABLE jobs(id INTEGER PRIMARY KEY,url TEXT,path TEXT,connections INTEGER,status TEXT,bytes INTEGER DEFAULT 0,total INTEGER,note TEXT DEFAULT '',created REAL)")
            db.execute("INSERT INTO jobs(url,path,connections,status,created) VALUES('https://example.test/a','a.bin',4,'Queued',0)");db.commit();db.close()
            store=Store(path);self.assertEqual(store.rows()[0][8:10],('file','{}'));store.close()
    def test_browser_video_queue(self):
        work=ROOT/'test-work';work.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=work) as d:
            path=Path(d)/'queue.db'
            enqueue({'action':'queue','kind':'video','url':'https://example.test/stream.m3u8','referer':'https://example.test/watch','user_agent':'BrowserTest'},path,Path(d)/'downloads')
            store=Store(path,recover=False);row=store.rows()[0];self.assertEqual(row[8],'video');self.assertTrue(row[2].endswith('.mp4'));self.assertEqual(json.loads(row[9])['context']['referer'],'https://example.test/watch');store.close()
    def test_cancellation_stops_video_child(self):
        control=Control();timer=threading.Timer(.3,lambda:control.stop('Paused'));timer.start()
        started=time.monotonic()
        try:
            with self.assertRaises(Interrupted):run([sys.executable,'-c','import time;time.sleep(30)'],control)
        finally:timer.cancel()
        self.assertLess(time.monotonic()-started,15)

class Handler(SimpleHTTPRequestHandler):
    def log_message(self,*args):pass

class VideoIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _,cls.ffmpeg=tools()
        if not cls.ffmpeg:raise RuntimeError('FFmpeg must be installed to run video integration tests')
        work=ROOT/'test-work';work.mkdir(exist_ok=True);cls.temp=tempfile.TemporaryDirectory(dir=work);cls.folder=Path(cls.temp.name)
        def ff(args):
            result=subprocess.run([cls.ffmpeg,'-hide_banner','-loglevel','error','-y',*args],capture_output=True,timeout=60,cwd=cls.folder)
            if result.returncode:raise RuntimeError(result.stderr.decode(errors='replace'))
        ff(['-f','lavfi','-i','testsrc=size=160x90:rate=10','-f','lavfi','-i','sine=frequency=440:sample_rate=44100','-t','2','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-shortest','-movflags','+faststart',str(cls.folder/'fixture.mp4')])
        ff(['-i',str(cls.folder/'fixture.mp4'),'-c','copy','-f','hls','-hls_time','1','-hls_list_size','0',str(cls.folder/'stream.m3u8')])
        ff(['-i',str(cls.folder/'fixture.mp4'),'-map','0:v','-map','0:a','-c','copy','-f','dash',str(cls.folder/'manifest.mpd')])
        (cls.folder/'watch.html').write_text('<html><head><title>Kora test video</title></head><body><video controls src="/fixture.mp4"></video></body></html>')
        (cls.folder/'master.m3u8').write_text('#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=180000,RESOLUTION=160x90\nstream.m3u8\n')
        handler=partial(Handler,directory=str(cls.folder))
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),handler);cls.server.daemon_threads=True
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start();cls.base=f'http://127.0.0.1:{cls.server.server_port}'
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join(timeout=2);cls.temp.cleanup()
    def setUp(self):
        self.job=tempfile.TemporaryDirectory(dir=self.folder);self.addCleanup(self.job.cleanup);self.output=Path(self.job.name)/'result.mp4'
    def validate_media(self,path):
        result=subprocess.run([self.ffmpeg,'-hide_banner','-i',str(path),'-f','null','-'],capture_output=True,timeout=30)
        text=result.stderr.decode(errors='replace')
        self.assertEqual(result.returncode,0,text);self.assertIn('Video:',text);self.assertIn('Audio:',text)
    def test_video_pause_then_resume(self):
        control=Control()
        def progress(value):
            if value.get('bytes',0)>0:control.stop('Paused')
        with self.assertRaises(Interrupted):download_video(self.base+'/fixture.mp4',self.output,control=control,progress=progress)
        self.assertFalse(self.output.exists())
        download_video(self.base+'/fixture.mp4',self.output);self.validate_media(self.output)
    def test_direct_video_info_and_download(self):
        info=inspect_video(self.base+'/fixture.mp4');self.assertTrue(info['formats'])
        result=download_video(self.base+'/fixture.mp4',self.output);self.assertGreater(result['bytes'],1000);self.validate_media(self.output)
    def test_generic_embedded_player(self):
        info=inspect_video(self.base+'/watch.html');self.assertIn('video',info['title'].lower())
        download_video(self.base+'/watch.html',self.output);self.validate_media(self.output)
    def test_hls_master_quality(self):
        info=inspect_video(self.base+'/master.m3u8');self.assertTrue(any(f['height']==90 for f in info['formats']))
        download_video(self.base+'/master.m3u8',self.output,{'mode':'best','height':360});self.validate_media(self.output)
    def test_dash_separate_audio_and_video_merge(self):
        info=inspect_video(self.base+'/manifest.mpd');self.assertTrue(any(not f['audio'] for f in info['formats']))
        download_video(self.base+'/manifest.mpd',self.output);self.validate_media(self.output)
    def test_specific_format_download(self):
        info=inspect_video(self.base+'/fixture.mp4');identity=info['formats'][0]['id']
        download_video(self.base+'/fixture.mp4',self.output,{'mode':'format','id':identity});self.validate_media(self.output)
    def test_destination_not_overwritten(self):
        self.output.write_bytes(b'keep')
        with self.assertRaises(FileExistsError):download_video(self.base+'/fixture.mp4',self.output)
        self.assertEqual(self.output.read_bytes(),b'keep')
    def test_extractors_exclude_youtube(self):
        args=base_args()
        pattern=args[args.index('--use-extractors')+1]
        code="import sys;sys.path.insert(0,sys.argv[1]);from yt_dlp import YoutubeDL;d=YoutubeDL({'allowed_extractors':sys.argv[2].split(','),'quiet':True});assert len(d._ies)>1000;assert not any('youtube' in k.lower() for k in d._ies),[k for k in d._ies if 'youtube' in k.lower()]"
        run([sys.executable,'-c',code,str(ROOT/'vendor'),pattern])

if __name__=='__main__':unittest.main(verbosity=2)
