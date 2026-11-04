"""Export only reviewed source and an extension-only Chrome Web Store upload ZIP."""
import argparse,hashlib,json,re,shutil,zipfile
from pathlib import Path
from install_support import VERSION,SERVICE_FILES
ROOT=Path(__file__).resolve().parent
SOURCE_FILES=set(SERVICE_FILES)|{
 'setup_installer.py','install_native_host.py','install_antigravity.py','uninstall.py',
 'build_release.py','build_publication.py','requirements-lock.txt','requirements.txt','requirements-dev.txt',
 '安装与修复.command','安装Antigravity.command','启动翻译器.command','安装Chrome插件.command',
 '卸载后台（保留可恢复备份）.command','快速开始.txt','LICENSE','PRIVACY.md','SECURITY.md','THIRD_PARTY_NOTICES.md','STORE_LISTING.md','.gitignore'}
FORBIDDEN_NAMES={'connection.json','auth.json','credentials.json','native-config.json','install-receipt.json','service-process.json','extension-connected.json','cache.sqlite'}
TEXT_SUFFIXES={'.py','.js','.json','.html','.css','.md','.txt','.svg','.command'}

def audit(files):
 errors=[]
 for name,raw in files.items():
  p=Path(name)
  if p.name in FORBIDDEN_NAMES or p.suffix in {'.pem','.key','.sqlite','.db','.log','.pyc'} or any(x in p.parts for x in {'__pycache__','.git','antigravity-profile','backups'}):errors.append(name+': private path')
  if p.suffix in TEXT_SUFFIXES:
   s=raw.decode('utf-8')
   # Test fixtures may use fake values but real token-shaped literals must never ship.
   for label,pattern in [
    ('private user path',r'/'+'Users/'+r'[^/\s]+/'),('private key',r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    ('OpenAI key',r'\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{30,}'),('Google key',r'\bAIza[0-9A-Za-z_-]{30,}'),
    ('GitHub token',r'\b(?:ghp_|github_pat_)[A-Za-z0-9_]{30,}'),('Google OAuth token',r'\bya29\.[A-Za-z0-9_-]{30,}')]:
    if re.search(pattern,s):errors.append(name+': '+label)
 if errors:raise ValueError('Publication blocked: '+', '.join(errors))

def build(out):
 out=Path(out).resolve();out.mkdir(parents=True,exist_ok=True)
 source=out/'github';source.mkdir(exist_ok=True)
 # Refuse to erase an existing clone or overwrite unrelated staged content.
 if (source/'.git').exists():raise ValueError('Use a fresh export directory; existing Git history is preserved.')
 files={name:(ROOT/name).read_bytes() for name in SOURCE_FILES}
 readme=ROOT/'发布资料/README.md'
 files['README.md']=(readme if readme.is_file() else ROOT/'README.md').read_bytes()
 for directory in ('extension','packaging','tests'):
  for p in (ROOT/directory).rglob('*'):
   if p.is_file() and p.name!='.DS_Store' and '__pycache__' not in p.parts and p.suffix!='.pyc':
    if directory=='tests' and p.suffix not in {'.py','.js'}:continue
    files[str(p.relative_to(ROOT))]=p.read_bytes()
 audit(files)
 for name,raw in files.items():
  p=source/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
  if p.suffix=='.command':p.chmod(0o755)
 extension={name.removeprefix('extension/'):raw for name,raw in files.items() if name.startswith('extension/')}
 manifest=json.loads(extension['manifest.json']);manifest.pop('key',None)
 manifest['homepage_url']='https://github.com/a719386471-stack/bilingual-translator'
 extension['manifest.json']=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode()
 extension['PRIVACY.md']=files['PRIVACY.md'];extension['LICENSE']=files['LICENSE']
 audit(extension)
 store=out/('双语翻译器-'+VERSION+'-Chrome商店上传.zip')
 with zipfile.ZipFile(store,'w',zipfile.ZIP_DEFLATED) as z:
  for name,raw in sorted(extension.items()):z.writestr(name,raw)
 source_zip=out/('双语翻译器-'+VERSION+'-源码.zip')
 with zipfile.ZipFile(source_zip,'w',zipfile.ZIP_DEFLATED) as z:
  for name,raw in sorted(files.items()):z.writestr('bilingual-translator/'+name,raw)
 report={'version':VERSION,'source_files':len(files),'store_files':len(extension),'account_files':0,'credential_files':0,
  'source_sha256':hashlib.sha256(source_zip.read_bytes()).hexdigest(),'store_sha256':hashlib.sha256(store.read_bytes()).hexdigest(),
  'note':'Public extension key is an identifier, not authentication. Store-assigned ID must be synchronized with the companion before submission.'}
 (out/'publication-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'source':str(source),'source_zip':str(source_zip),'store_zip':str(store),'audit':report},ensure_ascii=False))
 return source

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,default=ROOT/'publication');a=p.parse_args();build(a.out)
