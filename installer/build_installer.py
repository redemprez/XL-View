"""Build an isolated Windows payload and installer; never replace the running portable app."""
from pathlib import Path
import hashlib,json,shutil,subprocess,sys,zipfile
from importlib.metadata import distribution
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'release';PAYLOAD=OUT/'payload'/'XL View'
ISCC=Path('C:/Program Files (x86)/Inno Setup 6/ISCC.exe')
VERSION='0.7.0'
def run(*args):subprocess.run(list(map(str,args)),cwd=ROOT,check=True)
if __name__=='__main__':
    if not ISCC.is_file():raise SystemExit('Inno Setup 6 compiler was not found.')
    run(sys.executable,'-m','PyInstaller','--noconfirm','--distpath',OUT/'payload','--workpath',OUT/'build','XL View.spec')
    shutil.copy2(ROOT/'INSTRUKCJA.txt',PAYLOAD/'INSTRUKCJA.txt')
    shutil.copy2(ROOT/'installer/THIRD_PARTY_NOTICES.txt',PAYLOAD/'THIRD_PARTY_NOTICES.txt')
    shutil.copytree(ROOT/'installer/licenses',PAYLOAD/'licenses',dirs_exist_ok=True)
    shutil.copy2(Path(sys.base_prefix)/'LICENSE.txt',PAYLOAD/'licenses/Python-LICENSE.txt')
    d=distribution('pyinstaller')
    for f in d.files:
        if str(f).endswith('licenses/COPYING.txt'):shutil.copy2(d.locate_file(f),PAYLOAD/'licenses/PyInstaller-COPYING.txt')
    # Rebuildable application sources, with no user presets or review data.
    source=OUT/f'XL-View-{VERSION}-source.zip'
    with zipfile.ZipFile(source,'w',zipfile.ZIP_DEFLATED) as z:
        files=[ROOT/n for n in ('main.py','requirements.txt','XL View.spec','INSTRUKCJA.txt','build_icon.py')]
        files += [p for folder in ('lcxl','installer') for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts]
        for p in sorted(set(files)):z.write(p,str(p.relative_to(ROOT)))
    shutil.copy2(source,PAYLOAD/source.name)
    run(ISCC,'/Qp',ROOT/'installer/XLView.iss')
    setup=OUT/f'XL-View-Setup-{VERSION}-x64.exe'
    lines=[hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name for p in (setup,source)]
    (OUT/'SHA256SUMS.txt').write_text('\n'.join(lines)+'\n',encoding='ascii')
    print('Installer:',setup,'Size MiB:',round(setup.stat().st_size/1024**2,1))
