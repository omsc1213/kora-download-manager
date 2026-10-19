"""Safe default destinations for downloads, including queued-name collisions."""
from pathlib import Path
from urllib.parse import urlsplit, unquote
import re


def video_folder():
    folder = Path.home() / 'Downloads' / 'Kora' / 'Videos'
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def safe_name(value):
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f]', '_', value)
    value = re.sub(r'\s+', ' ', value).strip(' .')[:120].rstrip(' .')
    if not value:
        value = 'Video'
    if value.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL', *('COM'+str(i) for i in range(1,10)), *('LPT'+str(i) for i in range(1,10))}:
        value = '_' + value
    return value


def suggested_path(url, title=None, reserved=(), video=True, folder=None):
    try:
        source = urlsplit(url)
    except ValueError:
        source = urlsplit('')
    leaf = unquote(source.path.rstrip('/').rsplit('/', 1)[-1])
    name = safe_name(title or leaf or source.hostname or 'Video')
    folder = Path(folder) if folder else (video_folder() if video else Path.home() / 'Downloads' / 'Kora')
    folder.mkdir(parents=True, exist_ok=True)
    if video:
        if Path(name).suffix.lower() in ('.mp4','.mkv','.webm','.mov','.m3u8','.mpd'):
            name = Path(name).stem
        name += '.mp4'
    reserved = {str(Path(p).absolute()).casefold() for p in reserved}
    target = folder / name
    index = 2
    while target.exists() or str(target.absolute()).casefold() in reserved or Path(str(target)+'.kora-video').exists():
        target = folder / f'{Path(name).stem} ({index}){Path(name).suffix}'
        index += 1
    return target
