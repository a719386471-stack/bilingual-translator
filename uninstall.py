"""Recoverable uninstall: move this app's files to a backup; never purge accounts."""
import argparse,os,shutil,uuid
from datetime import datetime
from pathlib import Path
from install_support import DEFAULT_DATA,DEFAULT_HOSTS,NAME,read_json

def uninstall(data=DEFAULT_DATA,hosts=DEFAULT_HOSTS,backup=None):
    data=Path(data).resolve();hosts=Path(hosts).resolve()
    if data==Path.home() or data==Path('/'):raise ValueError('卸载目录无效。')
    receipt=read_json(data/'install-receipt.json')
    if not receipt.get('version'):raise ValueError('该目录没有本程序安装记录，未改动文件。')
    from native_host import control
    control('stop',data)
    target=Path(backup or Path.home()/'.Trash')/('双语翻译器备份-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6])
    target.mkdir(parents=True,exist_ok=False,mode=0o700)
    manifest=hosts/(NAME+'.json');m=read_json(manifest)
    if m and Path(m.get('path','/not-owned')).parent==data/'service':manifest.replace(target/'native-host-manifest.json')
    shutil.move(str(data),str(target/'NewsBridge'))
    return target

def main():
    p=argparse.ArgumentParser();p.add_argument('--data-dir',type=Path,default=DEFAULT_DATA);p.add_argument('--hosts-dir',type=Path,default=DEFAULT_HOSTS);p.add_argument('--backup-dir',type=Path)
    p.add_argument('--execute',action='store_true');a=p.parse_args()
    if not a.execute:print('预览：将停止本机服务，并把程序、账号及缓存移入可恢复备份；Chrome 插件请在扩展管理页移除。');return
    target=uninstall(a.data_dir,a.hosts_dir,a.backup_dir);print('已停止并移出本机组件。账号和缓存未销毁，备份位于：'+str(target))

if __name__=='__main__':main()
