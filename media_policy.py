"""User-selected YouTube exclusion, shared across Kora entry points."""
from urllib.parse import urlsplit

YOUTUBE_HOSTS=('youtube.com','youtu.be','youtube-nocookie.com','youtubeeducation.com','googlevideo.com','youtube.googleapis.com','youtubei.googleapis.com')

def reject_youtube(url):
    if not isinstance(url,str):raise ValueError('Expected a URL')
    host=(urlsplit(url).hostname or '').lower().rstrip('.')
    if any(host==domain or host.endswith('.'+domain) for domain in YOUTUBE_HOSTS):
        raise ValueError('YouTube videos are excluded from Kora')

def check_info(info):
    if not isinstance(info,dict):raise ValueError('No video information was returned')
    extractor=str(info.get('extractor_key') or info.get('extractor') or '').lower()
    if extractor.startswith('youtube'):raise ValueError('Embedded YouTube videos are excluded from Kora')
    for key in ('webpage_url','original_url','url'):
        value=info.get(key)
        if isinstance(value,str) and value.startswith(('http://','https://')):reject_youtube(value)
    if info.get('has_drm') or info.get('is_drm'):raise ValueError('This video is DRM-protected and cannot be downloaded by Kora')
