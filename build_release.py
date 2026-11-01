"""Build an allowlisted distributable; never walks runtime/account directories."""
import argparse,hashlib,json,shutil,zipfile
from pathlib import Path
from install_support import VERSION,SERVICE_FILES,extension_id
ROOT=Path(__file__).resolve().parent

def build(assets,out=None):
    assets=Path(assets);out=Path(out or ROOT/'dist');out.mkdir(parents=True,exist_ok=True)
    folder=out/('双语翻译器-'+VERSION+'-Mac-Apple芯片')
    if folder.exists():shutil.rmtree(folder)
    folder.mkdir()
    sources=set(SERVICE_FILES)|{'setup_installer.py','install_native_host.py','install_antigravity.py','uninstall.py','requirements-lock.txt','requirements.txt','LICENSE','PRIVACY.md','THIRD_PARTY_NOTICES.md'}
    sources|={'安装与修复.command','启动翻译器.command','安装Antigravity.command','卸载后台（保留可恢复备份）.command','快速开始.txt'}
    for name in sorted(sources):shutil.copy2(ROOT/name,folder/name)
    shutil.copytree(ROOT/'extension',folder/'extension',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    shutil.copytree(ROOT/'packaging',folder/'packaging')
    shutil.copy2(ROOT/'快速开始.txt',folder/'README.txt')
    public=(ROOT/'packaging/release-public-key.txt').read_text().strip()
    m=json.loads((folder/'extension/manifest.json').read_text());m['key']=public;(folder/'extension/manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
    target=folder/'assets';target.mkdir();shutil.copy2(assets/'python-arm64.tar.gz',target/'python-arm64.tar.gz');shutil.copytree(assets/'wheels',target/'wheels')
    expected=json.loads((ROOT/'packaging/runtime.json').read_text())['sha256']
    if hashlib.sha256((target/'python-arm64.tar.gz').read_bytes()).hexdigest()!=expected:raise ValueError('运行环境摘要不匹配。')
    hashes={str(p.relative_to(folder)):hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.rglob('*') if p.is_file()}
    (target/'hashes.json').write_text(json.dumps(hashes,ensure_ascii=False,indent=2)+'\n')
    # A generated private signing key is deliberately not kept; this is only a public identifier.
    assert not any(p.name in ('connection.json','cache.sqlite') or p.suffix in ('.pem','.key') for p in folder.rglob('*'))
    archive=out/(folder.name+'.zip')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(folder.rglob('*')):
            if p.is_file():z.write(p,Path(folder.name)/p.relative_to(folder),compress_type=zipfile.ZIP_STORED if p.suffix in ('.gz','.whl') else zipfile.ZIP_DEFLATED)
    with zipfile.ZipFile(archive) as z:assert z.testzip() is None
    print(json.dumps({'folder':str(folder),'archive':str(archive),'size':archive.stat().st_size,'extensionId':extension_id(public)},ensure_ascii=False))
    return folder,archive

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--assets',type=Path,required=True);p.add_argument('--out',type=Path);a=p.parse_args();build(a.assets,a.out)
