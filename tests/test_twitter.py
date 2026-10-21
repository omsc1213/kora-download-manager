import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import video
from engine import Interrupted

INFO={'title':'Public post','extractor_key':'Twitter','formats':[{'format_id':'http-720','vcodec':'h264','acodec':'aac','ext':'mp4'}]}

class TwitterTests(unittest.TestCase):
    def test_official_urls_preserve_video_index(self):
        for host in ('x.com','www.x.com','mobile.twitter.com','twitter.com'):
            self.assertEqual(video.twitter_url(f'https://{host}/author/status/123/video/2?s=20'),('https://twitter.com/i/web/status/123/video/2',True))
        self.assertEqual(video.twitter_url('https://x.com.evil.test/a/status/123')[1],False)

    def test_fallback_and_download_use_same_api(self):
        calls=[]
        def run(args,*a,**kw):
            calls.append(args)
            if '--skip-download' in args:
                if len(calls)==1:raise RuntimeError('Unable to extract GraphQL response')
                return json.dumps(INFO)
            template=args[args.index('--output')+1]
            path=Path(template.replace('%(ext)s','mp4'));path.write_bytes(b'complete video fixture')
            kw['on_line']('KORA_DONE:'+json.dumps(str(path)))
            return ''
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'test-work') as folder,patch.object(video,'tools',return_value=(['yt-dlp'],'ffmpeg.exe')),patch.object(video,'run',side_effect=run):
            output=Path(folder)/'video.mp4'
            video.download_video('https://x.com/author/status/123?s=20',output)
            self.assertEqual(output.read_bytes(),b'complete video fixture')
        self.assertEqual(len(calls),3)
        for args in calls[1:]:
            self.assertIn('twitter:api=syndication',args)
            self.assertEqual(args[-1],'https://twitter.com/i/web/status/123')

    def test_other_sites_and_cancellation_do_not_retry(self):
        for url,error in (('https://example.test/video',RuntimeError('failure')),('https://x.com/a/status/123',Interrupted('Paused'))):
            with patch.object(video,'base_args',return_value=[]),patch.object(video,'run',side_effect=error) as runner:
                with self.assertRaises(type(error)):video.inspect_video(url)
                self.assertEqual(runner.call_count,1)

    def test_youtube_stays_blocked(self):
        with patch.object(video,'run') as runner:
            with self.assertRaises(ValueError):video.inspect_video('https://youtube.com/watch?v=123')
            runner.assert_not_called()

    def test_vendor_precedes_path_tool(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'test-work') as folder:
            root=Path(folder);(root/'vendor/yt_dlp').mkdir(parents=True)
            (root/'vendor/yt_dlp/__main__.py').write_text('')
            with patch.object(video,'ROOT',root),patch.dict('os.environ',{},clear=True),patch.object(video.shutil,'which',return_value='old.exe'):
                self.assertEqual(video.tools()[0],[sys.executable,str(root/'video_tool.py')])

if __name__=='__main__':unittest.main()

