"""Install the pinned official Google ACP archive with registry SHA-256."""
import hashlib
import json
import os
from pathlib import Path
import platform
import urllib.request
import zipfile

VERSION='1.4.5'
ARCHIVES={
 'arm64':('darwin-arm64','886fff7767d08994ca39eb02c3d01a7532c7325a94aa33aaf52d52068733284f'),
 'x86_64':('darwin-x86_64','b39f3573c03b9acb9df028853f647527f1f3133f32bd77e78b796e48a205114a')}

def main():
 os.umask(0o077)
 if platform.system()!='Darwin' or platform.machine() not in ARCHIVES:raise SystemExit('此安装脚本支持 macOS Apple 芯片及 Intel。')
 suffix,expected=ARCHIVES[platform.machine()]
 root=globals().get('ROOT',Path.home()/'Library/Application Support/NewsBridge')/'antigravity-acp'/VERSION
 root.mkdir(parents=True,exist_ok=True,mode=0o700)
 archive=root/'distribution.zip'
 url='https://dl.google.com/agy-extensions/releases/macos/agy-acp-server-'+VERSION+'-'+suffix+'.zip'
 if not archive.exists() or hashlib.sha256(archive.read_bytes()).hexdigest()!=expected:
  part=root/'distribution.part'
  print('正在下载 Google 官方 ACP 运行组件…',flush=True)
  with urllib.request.urlopen(url,timeout=60) as response,part.open('wb') as output:
   while True:
    chunk=response.read(1024*1024)
    if not chunk:break
    output.write(chunk)
  if hashlib.sha256(part.read_bytes()).hexdigest()!=expected:raise SystemExit('校验未通过，未安装组件。')
  part.replace(archive)
 with zipfile.ZipFile(archive) as z:
  for name in z.namelist():
   if not (root/name).resolve().is_relative_to(root.resolve()):raise SystemExit('压缩包路径无效。')
  z.extractall(root)
 for name in ('agy_acp_server.par','localharness_external'):(root/name).chmod(0o700)
 (root/'install-receipt.json').write_text(json.dumps({'version':VERSION,'sha256':expected,'source':url}))
 print('Antigravity 官方 ACP 组件已安装。打开插件，选择 Antigravity 并连接 Google 账号。')

if __name__=='__main__':main()
