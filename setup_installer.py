"""One installer for first install and repair; standard library bootstrap only."""
import argparse,json,os,platform,shutil,subprocess,sys,uuid,webbrowser
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from install_support import VERSION,DEFAULT_DATA,DEFAULT_HOSTS,write_json,read_json

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))

def healthy(python):
    if not python.is_file():return False
    try:
        r=subprocess.run([str(python),'-I','-c','import sys;assert sys.version_info>=(3,9);import ssl,jwt,cryptography,youtube_transcript_api,requests;from cryptography.hazmat.primitives.asymmetric import rsa'],capture_output=True,timeout=20)
        return r.returncode==0
    except (OSError,subprocess.TimeoutExpired):return False

def verify_assets(root):
    import hashlib,re
    manifest=read_json(root/'assets/hashes.json')
    if (root/'assets').exists() and (not isinstance(manifest,dict) or not manifest):raise ValueError('安装资源校验清单缺失或损坏，请重新解压原始安装包。')
    for rel,digest in manifest.items():
        if not isinstance(rel,str) or not isinstance(digest,str) or not re.fullmatch('[a-f0-9]{64}',digest):raise ValueError('安装资源校验清单格式错误。')
        path=root/rel
        if not path.resolve().is_relative_to(root.resolve()) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
            raise ValueError('安装资源校验未通过：'+rel)
    return bool(manifest)

def prepare_runtime(data,source=ROOT,force=False):
    data=Path(data);data.mkdir(parents=True,exist_ok=True,mode=0o700)
    runtime=data/'runtime'
    if not force and healthy(runtime/'bin/python3'):return {'kind':'existing'}
    verify_assets(source)
    target=data/'venvs'/('runtime-'+VERSION+'-'+uuid.uuid4().hex[:8]);target.parent.mkdir(parents=True,exist_ok=True)
    print('正在准备独立运行环境…',flush=True)
    subprocess.run([sys.executable,'-I','-m','venv',str(target)],check=True)
    pip=[str(target/'bin/python3'),'-I','-m','pip','--isolated','--disable-pip-version-check','install','--only-binary=:all:']
    if (source/'assets/wheels').is_dir():pip+=['--no-index','--find-links',str(source/'assets/wheels')]
    subprocess.run(pip+['-r',str(source/'requirements-lock.txt')],check=True)
    if not healthy(target/'bin/python3'):raise ValueError('独立运行环境未能通过检查。')
    from native_host import helper_request,control
    running=helper_request(data=data)
    old=None
    link=data/('runtime.next-'+uuid.uuid4().hex[:8]);link.symlink_to(target,target_is_directory=True)
    try:
        if running:control('stop',data)
        if runtime.exists() or runtime.is_symlink():
            old=data/('runtime.previous-'+uuid.uuid4().hex[:8]);runtime.replace(old)
        link.replace(runtime)
    except Exception:
        if old and (old.exists() or old.is_symlink()):old.replace(runtime)
        if link.is_symlink():link.unlink()
        if running:control('start',data)
        raise
    return {'kind':'new','previous':old,'was_running':running}

def rollback_runtime(data,state):
    if not state or state.get('kind')!='new':return
    runtime=Path(data)/'runtime';old=state.get('previous')
    if old and (old.exists() or old.is_symlink()):
        if runtime.is_symlink():runtime.unlink()
        old.replace(runtime)
        if state.get('was_running'):
            from native_host import control
            control('start',data)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--data-dir',type=Path,default=Path(os.environ.get('TRANSLATOR_DATA_DIR',str(DEFAULT_DATA))))
    parser.add_argument('--hosts-dir',type=Path,default=DEFAULT_HOSTS)
    parser.add_argument('--port',type=int,default=19487)
    parser.add_argument('--extension-id')
    parser.add_argument('--extension-dir',type=Path)
    parser.add_argument('--no-open',action='store_true')
    parser.add_argument('--no-start',action='store_true')
    parser.add_argument('--with-antigravity',action='store_true')
    parser.add_argument('--refresh-runtime',action='store_true')
    args=parser.parse_args();os.umask(0o077)
    if platform.system()!='Darwin':raise SystemExit('当前安装版仅支持 macOS。')
    runtime=None;core_done=False
    try:
        verify_assets(ROOT)
        runtime=prepare_runtime(args.data_dir,force=args.refresh_runtime)
        from install_native_host import install
        result=install(ROOT,args.data_dir,args.hosts_dir,args.extension_id,args.port,not args.no_start,extension_dir=args.extension_dir)
        core_done=True
        if args.with_antigravity:
            import install_antigravity
            install_antigravity.ROOT=args.data_dir
            install_antigravity.main()
        result['runtime']=runtime['kind']
        print('安装与检查完成。账号、缓存和用量记录已保留。',flush=True)
        print('插件目录：'+result['extensionDir'],flush=True)
        if not args.no_open and not args.no_start:webbrowser.open('http://127.0.0.1:%d/'%args.port)
    except Exception as exc:
        if not core_done:rollback_runtime(args.data_dir,runtime)
        print('安装未完成：'+str(exc),file=sys.stderr)
        print('已有账号和译文记录未被清除；修复后可重新运行本安装器。',file=sys.stderr)
        raise SystemExit(1)

if __name__=='__main__':main()
