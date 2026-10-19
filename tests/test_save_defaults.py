import json
import io
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from save_paths import suggested_path,safe_name
from engine import download
import video


class DefaultsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'test-work')
        self.home=Path(self.temp.name)
        self.mock=patch('pathlib.Path.home',return_value=self.home);self.mock.start()
    def tearDown(self):
        self.mock.stop();self.temp.cleanup()
    def test_url_name_without_query(self):
        path=suggested_path('https://example.test/media/My%20holiday.mp4?token=secret')
        self.assertEqual(path,self.home/'Downloads/Kora/Videos/My holiday.mp4')
        self.assertTrue(path.parent.is_dir())
    def test_title_replaces_opaque_url(self):
        self.assertEqual(suggested_path('https://example.test/123','A lovely day').name,'A lovely day.mp4')
    def test_safe_windows_names(self):
        self.assertEqual(safe_name('CON'),'_CON')
        self.assertEqual(safe_name('../../x:*?'),'_.._x___')
        self.assertEqual(safe_name(' ... '),'Video')
    def test_collisions_include_queue_and_partial(self):
        first=suggested_path('https://example.test/a.mp4');first.touch()
        second=first.with_name('a (2).mp4')
        third=suggested_path('https://example.test/a.mp4',reserved=[second])
        self.assertEqual(third.name,'a (3).mp4')
        Path(str(third)+'.kora-video').mkdir()
        self.assertEqual(suggested_path('https://example.test/a.mp4',reserved=[second]).name,'a (4).mp4')
    def test_empty_and_incomplete_urls(self):
        self.assertEqual(suggested_path('https://[').name,'Video.mp4')
        self.assertEqual(suggested_path('https://example.test').name,'example.test.mp4')
    def test_file_name_keeps_extension(self):
        self.assertEqual(suggested_path('https://example.test/a.zip?x=y',video=False).name,'a.zip')
    def test_video_parallelism_used_and_final_bytes(self):
        target=self.home/'result.mp4';captured=[]
        def fake_run(args,control=None,timeout=None,on_line=None):
            captured.extend(args)
            media=Path(str(target)+'.kora-video')/'media.mp4';media.write_bytes(b'video')
            on_line('KORA_DONE:'+json.dumps(str(media)))
        with patch('video.inspect_video',return_value={'title':'Test','formats':[]}),patch('video.tools',return_value=(['tool'],'ffmpeg.exe')),patch('video.run',side_effect=fake_run):
            result=video.download_video('https://example.test/clip',target,{'mode':'best','connections':12})
        self.assertEqual(captured[captured.index('--concurrent-fragments')+1],'12')
        self.assertIn('--abort-on-unavailable-fragments',captured)
        self.assertEqual(result['bytes'],5);self.assertEqual(target.read_bytes(),b'video')
    def test_bad_parallelism(self):
        for count in (0,17,True,'8'):
            with self.assertRaises(ValueError):
                video.download_video('https://example.test/v',self.home/'out.mp4',{'connections':count})
    def test_parallel_file_download_assembles_exact_bytes(self):
        payload=bytes(range(256))*10000
        class Response(io.BytesIO):
            status=206
            def __init__(self,a,b):
                super().__init__(payload[a:b+1])
                self.headers={'ETag':'"stable"','Content-Length':str(b-a+1),'Content-Range':f'bytes {a}-{b}/{len(payload)}'}
            def geturl(self):return 'https://example.test/file'
        def transport(url,headers):
            a,b=map(int,headers['Range'].removeprefix('bytes=').split('-'))
            return Response(a,b)
        target=self.home/'large.bin'
        result=download('https://example.test/file',target,8,chunk_size=512*1024,transport=transport)
        self.assertEqual(target.read_bytes(),payload)
        self.assertEqual(result['sha256'],hashlib.sha256(payload).hexdigest())
    def test_ui_defaults_and_preserve_custom_name(self):
        import tkinter as tk
        from desktop import App
        root=tk.Tk();root.withdraw();app=App(root,self.home/'queue.db',auto_start=False)
        try:
            app.video_url.set('https://example.test/123')
            self.assertEqual(Path(app.video_destination.get()).name,'123.mp4')
            app.events.put(('video-info',app.video_url.get(),{'title':'Real title','formats':[]}));app.pump()
            self.assertEqual(Path(app.video_destination.get()).name,'Real title.mp4')
            custom=self.home/'Custom.mp4';app.video_destination.set(str(custom))
            app.video_url.set('https://example.test/456')
            app.events.put(('video-info',app.video_url.get(),{'title':'Other title','formats':[]}));app.pump()
            self.assertEqual(app.video_destination.get(),str(custom))
            app.connections.set(12);app.add_video()
            self.assertEqual(json.loads(app.store.rows()[0][9])['connections'],12)
        finally:
            app.store.close();root.destroy()

if __name__=='__main__':unittest.main()
