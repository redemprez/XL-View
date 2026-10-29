"""Exercise the real installer, reinstallation and uninstall in an isolated folder."""
import hashlib,json,os,subprocess,sys,tempfile,uuid,winreg
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'release';SETUP=OUT/'XL-View-Setup-0.7.0-x64.exe'
KEY=r'Software\Microsoft\Windows\CurrentVersion\Uninstall\{65A650D9-AB05-4D38-8E26-1080E1416CF1}_is1'
def registered():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,KEY) as k:return winreg.QueryValueEx(k,'InstallLocation')[0]
    except FileNotFoundError:return None
def main():
    if registered():raise SystemExit('Existing installed edition found; refusing to replace it during testing.')
    base=Path(tempfile.mkdtemp(prefix='XLView-InstallerTest-'));target=base/'app';token=uuid.uuid4().hex
    report={'tests':{},'directory':str(base),'hardware_writes':False,'setup_sha256':hashlib.sha256(SETUP.read_bytes()).hexdigest()}
    canary=None
    try:
        args=[str(SETUP),'/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/SP-','/NOCLOSEAPPLICATIONS',f'/DIR={target}',f'/GROUP=XL View Install Test {token}',f'/LOG={OUT / "install-test.log"}']
        subprocess.run(args,check=True,timeout=120)
        assert target.joinpath('XL View.exe').exists() and target.joinpath('installed-mode.txt').exists()
        assert Path(registered()).resolve()==target.resolve()
        report['tests']['install']=True
        check=OUT/'installed-app-check.json'
        subprocess.run([str(target/'XL View.exe'),'--check-install',str(check)],check=True,timeout=60)
        data=json.loads(check.read_text(encoding='utf-8'));assert data['ok'] and not data['midi_opened']
        assert Path(data['data_root'])==Path(os.environ['LOCALAPPDATA'])/'XL View'/'presets'
        report['tests']['offline_app_launch_and_preset_write']=True
        report['application_check']=data
        canary=Path(data['data_root'])/('installer-test-'+token+'.txt');canary.write_text(token)
        subprocess.run(args,check=True,timeout=120)
        assert canary.read_text()==token
        report['tests']['reinstall_preserves_data']=True
        subprocess.run([str(target/'unins000.exe'),'/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART',f'/LOG={OUT / "uninstall-test.log"}'],check=True,timeout=120)
        assert not (target/'XL View.exe').exists() and registered() is None
        assert canary.read_text()==token
        report['tests']['uninstall_preserves_data']=True
        report['ok']=True
    finally:
        if canary and canary.exists():canary.unlink()  # Only this test's unique marker.
        (OUT/'installer-verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))

if __name__=='__main__': main()
