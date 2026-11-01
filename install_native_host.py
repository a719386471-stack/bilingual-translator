"""Transactional per-user installation; never modifies account/cache files."""
import argparse,hashlib,json,os,shlex,shutil,uuid
from datetime import datetime
from pathlib import Path
from install_support import VERSION,NAME,SERVICE_FILES,DEFAULT_DATA,DEFAULT_HOSTS,read_json,write_json,extension_id,valid_id

ROOT=Path(__file__).resolve().parent

def install(source=ROOT,data=DEFAULT_DATA,hosts=DEFAULT_HOSTS,extension=None,port=19487,start=True,extension_dir=None):
    from native_host import control,helper_request
    source=Path(source).resolve();data=Path(data).resolve();hosts=Path(hosts).resolve()
    if not 1024<=port<=65535:raise ValueError('端口无效。')
    for name in SERVICE_FILES:
        if not (source/name).is_file():raise ValueError('安装文件不完整：'+name)
    old_cfg=read_json(data/'service/native-config.json');old_receipt=read_json(data/'install-receipt.json')
    old_origin=old_cfg.get('origin','');old_id=old_origin.removeprefix('chrome-extension://').rstrip('/') if hasattr(str,'removeprefix') else old_origin[len('chrome-extension://'):].rstrip('/')
    public=(source/'packaging/release-public-key.txt').read_text().strip();release_id=extension_id(public)
    selected=extension or (old_id if valid_id(old_id) else release_id)
    if not valid_id(selected):raise ValueError('插件编号无效。')
    managed=selected==release_id
    ext_dir=data/'extension' if managed else Path(extension_dir or old_cfg.get('extension_dir') or source/'extension')
    if not managed:
        legacy_manifest=read_json(ext_dir/'manifest.json')
        if not legacy_manifest:raise ValueError('旧版插件目录无效，请指定原有 extension 文件夹。')
        if legacy_manifest.get('key') and extension_id(legacy_manifest['key'])!=selected:
            raise ValueError('安装包与旧插件编号不同，请指定原有插件目录，以保留现有安装。')
    manifest=read_json(source/'extension/manifest.json')
    if manifest.get('version')!=VERSION:raise ValueError('安装器与插件版本不一致。')
    existing_host=read_json(hosts/(NAME+'.json'))
    if existing_host and Path(existing_host.get('path','/unknown')).parent!=data/'service':
        raise ValueError('现有 Chrome 连接指向另一个安装目录，未覆盖；请使用原安装目录修复。')
    if tuple(int(x) for x in old_receipt.get('version','0.0.0').split('.'))>tuple(int(x) for x in VERSION.split('.')):raise ValueError('已安装较新版本，未执行降级。')
    data.mkdir(parents=True,exist_ok=True,mode=0o700);data.chmod(0o700)
    origin='chrome-extension://'+selected+'/'
    backup=data/'backups'/(datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]);backup.mkdir(parents=True,mode=0o700)
    service=data/'service';stage=data/('service.next-'+uuid.uuid4().hex);stage.mkdir(mode=0o700)
    hpath=hosts/(NAME+'.json');hosts.mkdir(parents=True,exist_ok=True)
    old_host=hpath.read_bytes() if hpath.exists() else None
    old_r=(data/'install-receipt.json').read_bytes() if (data/'install-receipt.json').exists() else None
    was_running=helper_request(data=data);had_service=service.exists();had_extension=(data/'extension').exists()
    deployed=False;old_moved=False
    try:
        for name in SERVICE_FILES:shutil.copyfile(source/name,stage/name)
        write_json(stage/'native-config.json',{'origin':origin,'origins':[origin],'port':port,'hosts_dir':str(hosts),'extension_dir':str(ext_dir)})
        launcher=stage/'native-host'
        launcher.write_text('#!/bin/sh\nexec '+shlex.quote(str(data/'runtime/bin/python3'))+' '+shlex.quote(str(service/'native_host.py'))+' "$@"\n');launcher.chmod(0o700)
        if was_running:control('stop',data)
        if had_service:service.replace(backup/'service');old_moved=True
        stage.replace(service);deployed=True
        if managed:
            if had_extension:(data/'extension').replace(backup/'extension')
            shutil.copytree(source/'extension',data/'extension')
            manifest['key']=public;write_json(data/'extension/manifest.json',manifest)
        write_json(hpath,{'name':NAME,'description':'双语翻译器 本机连接','path':str(service/'native-host'),'type':'stdio','allowed_origins':[origin]})
        write_json(data/'install-receipt.json',{'version':VERSION,'extension_id':selected,'extension_dir':str(ext_dir),'managed_extension':managed,
                   'port':port,'source':str(source),'service_hashes':{n:hashlib.sha256((source/n).read_bytes()).hexdigest() for n in SERVICE_FILES}})
        if start:control('start',data)
        return {'version':VERSION,'extensionId':selected,'extensionDir':str(ext_dir),'running':start,'backup':str(backup)}
    except Exception:
        if deployed or old_moved:
            if helper_request(data=data):control('stop',data)
            failed=backup/'failed-service'
            if service.exists():service.replace(failed)
            if old_moved and (backup/'service').exists():(backup/'service').replace(service)
            if managed:
                if (data/'extension').exists():shutil.move(str(data/'extension'),str(backup/'failed-extension'))
                if had_extension and (backup/'extension').exists():(backup/'extension').replace(data/'extension')
        if old_host is not None:hpath.write_bytes(old_host);hpath.chmod(0o600)
        elif hpath.exists():hpath.replace(backup/'new-host-manifest.json')
        if old_r is not None:(data/'install-receipt.json').write_bytes(old_r)
        elif (data/'install-receipt.json').exists():(data/'install-receipt.json').replace(backup/'new-install-receipt.json')
        if was_running and had_service:control('start',data)
        raise

def main():
    from setup_installer import main as setup
    setup()

if __name__=='__main__':main()
