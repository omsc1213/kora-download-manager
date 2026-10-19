"""Validated preferences persisted atomically."""
import json
import os
from pathlib import Path
from engine import atomic_json
ROOT=Path(__file__).resolve().parent
def data_dir():return Path(os.environ.get('KORA_DATA_DIR') or ROOT/'data')
def defaults():
    return {'video_folder':str(Path.home()/'Downloads/Kora/Videos'),'file_folder':str(Path.home()/'Downloads/Kora'),'connections':8,'quality':'best','adaptive':True}
def validate(value):
    if not isinstance(value,dict):raise ValueError('Settings must be an object')
    clean=defaults()
    for key in ('video_folder','file_folder'):
        if key in value:
            path=Path(value[key]).expanduser()
            if not path.is_absolute():raise ValueError('Choose an absolute download folder')
            clean[key]=str(path)
    count=value.get('connections',8)
    if type(count) is not int or not 1<=count<=16:raise ValueError('Connections must be 1 to 16')
    clean['connections']=count
    if value.get('quality','best') not in ('best','2160','1440','1080','720','480','360'):raise ValueError('Invalid quality')
    clean['quality']=value.get('quality','best')
    if type(value.get('adaptive',True)) is not bool:raise ValueError('Invalid speed setting')
    clean['adaptive']=value.get('adaptive',True)
    return clean
def load(path=None):
    try:return validate(json.loads((Path(path) if path else data_dir()/'settings.json').read_text(encoding='utf-8')))
    except (OSError,ValueError,TypeError):return defaults()
def save(value,path=None):
    clean=validate(value);path=Path(path) if path else data_dir()/'settings.json'
    path.parent.mkdir(parents=True,exist_ok=True);atomic_json(path,clean);return clean
