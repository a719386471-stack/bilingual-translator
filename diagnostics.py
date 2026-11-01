"""Local checks only: no tokens, emails, article contents, or credential exports."""
import importlib,platform,ssl,sys,hashlib
from pathlib import Path
from install_support import VERSION,DEFAULT_DATA,DEFAULT_HOSTS,NAME,read_json,codex_executable

def collect(data=DEFAULT_DATA,running=False,hosts=None):
    data=Path(data);config=read_json(data/'service/native-config.json');receipt=read_json(data/'install-receipt.json')
    hosts=Path(hosts or config.get('hosts_dir') or DEFAULT_HOSTS)
    checks=[]
    def add(id,label,ok,detail,optional=False):checks.append({'id':id,'label':label,'state':'ok' if ok else ('info' if optional else 'error'),'detail':detail})
    add('platform','系统',platform.system()=='Darwin',('macOS' if platform.system()=='Darwin' else platform.system())+' · '+('Apple 芯片' if platform.machine()=='arm64' else platform.machine()))
    add('python','独立运行环境',sys.version_info>=(3,9),'已就绪 · Python '+platform.python_version())
    missing=[]
    for package in ('jwt','cryptography','youtube_transcript_api','requests'):
        try:importlib.import_module(package)
        except Exception:missing.append(package)
    add('dependencies','翻译组件',not missing,'已就绪' if not missing else '缺少或损坏：'+', '.join(missing)+'；请运行安装与修复。')
    manifest=read_json(hosts/(NAME+'.json'));allowed=config.get('origins') or [config.get('origin')]
    native_ok=bool(manifest) and manifest.get('allowed_origins')==allowed and Path(manifest.get('path','/not-installed')).is_file()
    add('native','Chrome 本机连接',native_ok,'已注册' if native_ok else '尚未正确注册；请运行安装与修复。')
    add('version','安装版本',receipt.get('version')==VERSION,receipt.get('version','未完成安装')+'；当前程序 '+VERSION)
    hashes=receipt.get('service_hashes') or {}
    intact=bool(hashes) and all((data/'service'/name).is_file() and hashlib.sha256((data/'service'/name).read_bytes()).hexdigest()==digest for name,digest in hashes.items())
    add('files','程序文件',intact,'完整' if intact else '文件缺失或发生变化，请运行安装与修复。')
    add('service','翻译服务',running,'已开启' if running else '已关闭，可在面板打开。',optional=True)
    add('chatgpt','ChatGPT 官方组件',bool(codex_executable()),'已找到；登录状态请在账号设置中检查。' if codex_executable() else '尚未找到。若使用 ChatGPT，请先安装并登录官方 ChatGPT/Codex 组件。',optional=True)
    agy=data/'antigravity-acp/1.4.5/agy_acp_server.par'
    add('antigravity','Antigravity 官方组件',agy.is_file(),'已安装；登录状态请在账号设置中检查。' if agy.is_file() else '未安装；使用此来源时运行安装Antigravity。',optional=True)
    add('startup','启动方式',True,'仅按需启动，未设置开机自启。')
    return {'version':VERSION,'ready':not any(c['state']=='error' for c in checks),'checks':checks,
            'note':'检查在本机完成，不含账号令牌、邮箱或网页内容。'}
