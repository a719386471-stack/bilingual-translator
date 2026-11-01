"""Fresh offline install + real Native Messaging in isolated Chrome for Testing."""
import argparse,hashlib,json,os,shutil,sqlite3,subprocess,sys,tempfile,time
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from install_support import NAME,VERSION,read_json
from native_host import control
from uninstall import uninstall
p=argparse.ArgumentParser();p.add_argument('bundle',type=Path);a=p.parse_args();bundle=a.bundle.resolve()
with tempfile.TemporaryDirectory(prefix='distribution-test-') as tmp:
 base=Path(tmp);data=base/'新用户 空白数据';profile=base/'profile one';hosts=profile/'NativeMessagingHosts';hosts.mkdir(parents=True);hostfile=hosts/(NAME+'.json')
 env=dict(os.environ);env['TRANSLATOR_DATA_DIR']=str(data)
 started=time.perf_counter();installed=False
 try:
  run=subprocess.run(['/bin/zsh',str(bundle/'安装与修复.command'),'--hosts-dir',str(hosts),'--port','19493','--no-open'],env=env,capture_output=True,text=True,timeout=120)
  assert run.returncode==0,run.stdout+run.stderr;installed=True;print('Fresh install OK',flush=True)
  install_seconds=round(time.perf_counter()-started,2)
  receipt=read_json(data/'install-receipt.json');extension=data/'extension';expected_id=receipt['extension_id']
  assert not read_json(data/'connection.json').get('accounts')
  assert not (data/'antigravity-profile/translator-connected').exists()
  original_key=read_json(data/'connection.json')['pairing_key']
  with sqlite3.connect(data/'cache.sqlite') as db:db.execute('INSERT INTO translations VALUES (?,?,?)',('fixture-cache','保留的测试译文',time.time()))
  # Only the test profile routes to the isolated helper; production Chrome is not touched.
  bg=extension/'background.js';bg.write_text(bg.read_text().replace('19487','19493'))
  with sync_playwright() as playwright:
   ctx=playwright.chromium.launch_persistent_context(str(profile),channel='chromium',headless=True,args=['--disable-extensions-except='+str(extension),'--load-extension='+str(extension)],viewport={'width':1200,'height':1000})
   worker=ctx.service_workers[0] if ctx.service_workers else ctx.wait_for_event('serviceworker')
   actual_id=worker.url.split('/')[2];assert actual_id==expected_id,(actual_id,expected_id)
   popup=ctx.new_page();popup.goto('chrome-extension://'+actual_id+'/popup.html')
   probe=worker.evaluate('async()=>{try{const r=await chrome.runtime.sendNativeMessage("local.chatgpt_web_translator",{action:"status"});return {ok:r.ok,error:r.error}}catch(e){return {error:e.message}}}')
   assert probe.get('ok'),probe
   expect(popup.locator('#service-state')).to_have_text('已开启',timeout=20000)
   assert worker.evaluate('()=>chrome.storage.local.get("pairingKey")')['pairingKey']==original_key
   expect(popup.locator('#pairing')).to_be_hidden();expect(popup.locator('#translate')).to_be_disabled()
   popup.locator('#diagnose').click();expect(popup.locator('#diagnostic-results')).to_contain_text('独立运行环境',timeout=10000)
   assert '安装版本：'+VERSION in popup.locator('#diagnostic-results').inner_text()
   worker.evaluate('()=>chrome.storage.local.set({pairingKey:"damaged-test-code"})')
   popup.locator('#reconnect').click();expect(popup.locator('#message')).to_contain_text('无需复制连接码',timeout=10000)
   assert worker.evaluate('()=>chrome.storage.local.get("pairingKey")')['pairingKey']==original_key
   popup.locator('#service-toggle').click();expect(popup.locator('#service-toggle')).to_have_attribute('aria-checked','false',timeout=15000)
   popup.locator('#service-toggle').click();expect(popup.locator('#service-toggle')).to_have_attribute('aria-checked','true',timeout=15000)
   page=ctx.new_page();page.goto('http://127.0.0.1:19493/')
   expect(page.locator('#installed-version')).to_have_text('v'+VERSION,timeout=10000)
   expect(page.locator('#extension-status')).to_contain_text('已自动连接')
   assert '连接本机' in page.locator('#status').inner_text()
   assert read_json(data/'connection.json')['pairing_key']==original_key
   control('stop',data)
   print('Closing isolated browser after stopping its disposable helper',flush=True)
   for open_page in list(ctx.pages):open_page.close()
   ctx.close()
   # Re-run from a different extraction folder. ID, accounts and cache stay put.
   moved=base/'安装包换了位置';shutil.copytree(bundle,moved)
   repair_start=time.perf_counter()
   repair=subprocess.run(['/bin/zsh',str(moved/'安装与修复.command'),'--hosts-dir',str(hosts),'--port','19493','--no-open'],env=env,capture_output=True,text=True,timeout=60)
   assert repair.returncode==0,repair.stdout+repair.stderr
   repair_seconds=round(time.perf_counter()-repair_start,2)
   # Replace the runtime too: must retain the helper identity, local key and cache.
   renewed=subprocess.run(['/bin/zsh',str(moved/'安装与修复.command'),'--hosts-dir',str(hosts),'--port','19493','--no-open','--refresh-runtime'],env=env,capture_output=True,text=True,timeout=60)
   assert renewed.returncode==0,renewed.stdout+renewed.stderr
   assert read_json(data/'install-receipt.json')['extension_id']==actual_id
   assert read_json(data/'connection.json')['pairing_key']==original_key
   with sqlite3.connect(data/'cache.sqlite') as db:assert db.execute('SELECT value FROM translations WHERE key="fixture-cache"').fetchone()[0]=='保留的测试译文'
   # Simulate a missing standard SSL module in this disposable runtime only.
   control('stop',data)
   ssl_path=Path(subprocess.check_output([str(data/'runtime/bin/python3'),'-I','-c','import ssl;print(ssl.__file__)'],text=True).strip())
   assert ssl_path.resolve().is_relative_to(data.resolve())
   ssl_path.replace(ssl_path.with_suffix('.test-hidden'))
   broken=subprocess.run([str(data/'runtime/bin/python3'),'-I','-c','import ssl'],capture_output=True)
   assert broken.returncode!=0,'fixture did not damage the disposable runtime'
   repaired=subprocess.run(['/bin/zsh',str(moved/'安装与修复.command'),'--hosts-dir',str(hosts),'--port','19493','--no-open'],env=env,capture_output=True,text=True,timeout=60)
   assert repaired.returncode==0,repaired.stdout+repaired.stderr
   subprocess.run([str(data/'runtime/bin/python3'),'-I','-c','import ssl,jwt,cryptography,youtube_transcript_api'],check=True)
   assert read_json(data/'connection.json')['pairing_key']==original_key
   # Load the same extension from another directory in another empty profile.
   relocated=base/'插件路径变更';shutil.copytree(data/'extension',relocated)
   bg=relocated/'background.js';bg.write_text(bg.read_text().replace('19487','19493'))
   second_profile=base/'profile two';(second_profile/'NativeMessagingHosts').mkdir(parents=True)
   shutil.copy2(hostfile,second_profile/'NativeMessagingHosts'/hostfile.name)
   ctx=playwright.chromium.launch_persistent_context(str(second_profile),channel='chromium',headless=True,args=['--disable-extensions-except='+str(relocated),'--load-extension='+str(relocated)])
   worker=ctx.service_workers[0] if ctx.service_workers else ctx.wait_for_event('serviceworker')
   assert worker.url.split('/')[2]==actual_id
   popup=ctx.new_page();popup.goto('chrome-extension://'+actual_id+'/popup.html');expect(popup.locator('#service-state')).to_have_text('已开启',timeout=15000)
   assert worker.evaluate('()=>chrome.storage.local.get("pairingKey")')['pairingKey']==original_key
   control('stop',data)
   print('Closing isolated browser after stopping its disposable helper',flush=True)
   for open_page in list(ctx.pages):open_page.close()
   ctx.close()
  backup=uninstall(data,hosts,base/'可恢复卸载备份');installed=False
  assert not hostfile.exists() and not data.exists()
  assert read_json(backup/'NewsBridge/connection.json')['pairing_key']==original_key
  with sqlite3.connect(backup/'NewsBridge/cache.sqlite') as db:assert db.execute('SELECT COUNT(*) FROM translations WHERE key="fixture-cache"').fetchone()[0]==1
  print('PASS: offline first install; real Native Messaging auto-pair; no inherited accounts; reconnect; service restart; wizard; relocated installer/extension stable ID; cache preservation; damaged-runtime repair; recoverable uninstall')
  print(json.dumps({'first_install_seconds':install_seconds,'repair_seconds':repair_seconds,'runtime':'standalone Python 3.12.16','system_python_used':False,'network_dependency_install':False}))
 finally:
  if installed:
   try:uninstall(data,hosts,base/'failed-test-backup')
   except Exception:
    try:control('stop',data)
    except Exception:pass
    if hostfile.exists() and str(data) in hostfile.read_text():hostfile.unlink()
