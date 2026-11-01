"""Shared installation metadata; contains no account data."""
import base64,hashlib,json,os,re,shutil
from pathlib import Path

VERSION='0.7.0'
NAME='local.chatgpt_web_translator'
DEFAULT_DATA=Path.home()/'Library/Application Support/NewsBridge'
DEFAULT_HOSTS=Path.home()/'Library/Application Support/Google/Chrome/NativeMessagingHosts'
SERVICE_FILES=('helper.py','translation_policy.py','local_engine.py','antigravity_engine.py','youtube_captions.py','usage_store.py','translation_errors.py',
               'dashboard.html','dashboard.js','dashboard.css','logo.svg','native_host.py','install_support.py','diagnostics.py')

def read_json(path,default=None):
    try:return json.loads(Path(path).read_text())
    except (OSError,ValueError):return {} if default is None else default

def write_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');temp.chmod(0o600);temp.replace(path)

def extension_id(key):
    raw=base64.b64decode(key,validate=True)
    if len(raw)<100:raise ValueError('插件公钥格式不完整。')
    return ''.join(chr(97+int(c,16)) for c in hashlib.sha256(raw).digest()[:16].hex())

def valid_id(value):return isinstance(value,str) and bool(re.fullmatch('[a-p]{32}',value))

def codex_executable():
    return next((Path(p) for p in (shutil.which('codex'),'/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex',
                '/Applications/Codex.app/Contents/Resources/codex') if p and Path(p).is_file()),None)
