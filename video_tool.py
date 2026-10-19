"""Run the unmodified, vendored yt-dlp release without changing system Python."""
from pathlib import Path
import runpy
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent/'vendor'))
runpy.run_module('yt_dlp',run_name='__main__')
