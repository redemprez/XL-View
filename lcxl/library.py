"""Local, versioned SysEx presets. No application database or cloud dependency."""
from pathlib import Path
from datetime import datetime
import os, re, sys, uuid
from .protocol import encode_mode, parse_mode, same_mode

MAX_VERSIONS=5

def data_root():
    # Installed builds keep user data outside the replaceable application folder.
    # Portable builds and source launches retain their existing library location.
    exe=Path(sys.executable).parent
    if getattr(sys,'frozen',False):
        if (exe/'installed-mode.txt').is_file():
            local=Path(os.environ.get('LOCALAPPDATA') or Path.home()/'AppData'/'Local')
            return local/'XL View'/'presets'
        return exe.parent.parent/'presets' if exe.parent.name=='dist' else exe/'presets'
    return Path(__file__).resolve().parent.parent/'presets'

def atomic_write(path,data):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        with temp.open('xb') as f: f.write(data); f.flush(); os.fsync(f.fileno())
        os.replace(temp,path)
    finally:
        if temp.exists(): temp.unlink()

def save_preset(mode,root=None,category='library'):
    return store_preset(mode,root,category)[0]

def store_preset(mode,root=None,category='library'):
    """Return (path, created). Identical latest versions do not consume history."""
    root=Path(root) if root else data_root()
    if category=='library':
        matches=[p for p,name,error in list_presets(root) if not error and name==mode.name]
        if matches:
            previous=parse_mode(matches[0].read_bytes())
            if same_mode(previous,mode) and previous.extras==mode.extras:
                trim_versions(root,mode.name);return matches[0],False
    safe=re.sub(r'[^A-Za-z0-9 _-]','_',mode.name).strip()[:48] or 'Custom Mode'
    stamp=datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    path=root/category/f'{safe}_{stamp}_{uuid.uuid4().hex[:6]}.syx'
    atomic_write(path,encode_mode(mode))
    if category=='library':trim_versions(root,mode.name)
    return path,True

def trim_versions(root=None,name=None):
    """Keep five active versions; preserve overflow outside the active library.

    Backups and damaged files are never pruned. Moves are individual, contained
    in the library root, and occur only after any new file was written atomically.
    """
    root=(Path(root) if root else data_root()).resolve();groups={}
    for path,title,error in list_presets(root):
        if not error and (name is None or title==name):groups.setdefault(title,[]).append(path)
    for paths in groups.values():
        for path in paths[MAX_VERSIONS:]:
            destination=root/'archive'/'library'/path.name
            if not path.resolve().is_relative_to(root) or not destination.resolve().is_relative_to(root):
                raise ValueError('Preset archive must stay inside the library folder.')
            destination.parent.mkdir(parents=True,exist_ok=True)
            if destination.exists():destination=destination.with_name(destination.stem+'_'+uuid.uuid4().hex[:8]+'.syx')
            path.replace(destination)

def grouped_presets(root=None,category='library'):
    groups={};invalid=[]
    for path,name,error in list_presets(root,category):
        if error:invalid.append({'name':name,'versions':[path],'error':error});continue
        groups.setdefault(name,{'name':name,'versions':[],'error':None})['versions'].append(path)
    result=list(groups.values())+invalid
    if category=='library':
        for group in result:group['versions']=group['versions'][:MAX_VERSIONS]
    return sorted(result,key=lambda g:(g['name'].casefold(),g['name']))

def backup_mode(mode,root=None):
    path=save_preset(mode,root,'backups')
    # Exact response is available separately for forensic restoration/comparison.
    if mode.raw: atomic_write(path.with_suffix('.readback'),mode.raw)
    return path

def list_presets(root=None,category='library'):
    root=Path(root) if root else data_root()
    result=[]
    for path in sorted((root/category).glob('*.syx'),key=lambda p:(p.stat().st_mtime_ns,p.name),reverse=True):
        try: result.append((path,parse_mode(path.read_bytes()).name,None))
        except (ValueError,OSError) as ex: result.append((path,path.stem,str(ex)))
    return result
