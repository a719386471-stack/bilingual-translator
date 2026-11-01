"""Isolated MV3 checks for sessions, alerts, popup layout and offline recovery."""
import os,sys,tempfile,threading,shutil,time
from pathlib import Path
from http.server import ThreadingHTTPServer
from playwright.sync_api import sync_playwright,expect
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
import helper
helper.PORT=19489;helper.BASE='http://127.0.0.1:19489'

class Handler(helper.Handler):
 def do_GET(self):
  if self.path in ('/first','/second','/offline'):
   name=self.path[1:]
   self.send('<!doctype html><html><title>'+name+' test</title><body><main><article><h1>Independent '+name+' article headline</h1><p>This is an English article about '+name+' and it has enough words to translate correctly.</p></article></main></body></html>',kind='text/html; charset=utf-8')
  else:super().do_GET()

with tempfile.TemporaryDirectory(prefix='translator-experience-') as tmp:
 app=helper.App(Path(tmp)/'data')
 app.status=lambda *args:{'connected':True,'email':'fixture@example.invalid','provider':'chatgpt','providerName':'ChatGPT'}
 app.models=lambda *args:[{'slug':'fixture','display_name':'Fixture model'}]
 app.local_engine.quota=lambda:{'available':False,'scope':'fixture','message':'No official quota in fixture'}
 calls=[]
 def infer(title,paras,previous,model,**kw):
  calls.append(title)
  if 'offline' in title:time.sleep(1.5)
  kw['on_usage']({'input':90,'output':30,'total':120,'cached':0,'reasoning':0})
  return ['中文：'+p for p in paras]
 app.infer=infer
 server=ThreadingHTTPServer(('127.0.0.1',19489),Handler);server.app=app
 threading.Thread(target=server.serve_forever,daemon=True).start()
 ext=Path(tmp)/'extension';shutil.copytree(root/'extension',ext)
 bg=ext/'background.js';bg.write_text(bg.read_text().replace('19487','19489'))
 try:
  with sync_playwright() as p:
   ctx=p.chromium.launch_persistent_context(str(Path(tmp)/'profile'),channel='chromium',headless=True,args=['--disable-extensions-except='+str(ext),'--load-extension='+str(ext)],viewport={'width':1000,'height':800})
   worker=ctx.service_workers[0] if ctx.service_workers else ctx.wait_for_event('serviceworker')
   worker.evaluate('key=>chrome.storage.local.set({pairingKey:key,modelsByProvider:{chatgpt:"fixture"},dailyAlert:100})',app.config['pairing_key'])
   worker.evaluate('()=>{chrome.runtime.sendNativeMessage=async()=>({ok:true,data:{running:true}})}')
   first=ctx.new_page();first.goto(helper.BASE+'/first')
   second=ctx.new_page();second.goto(helper.BASE+'/second')
   ids=worker.evaluate('async()=>Object.fromEntries((await chrome.tabs.query({})).filter(t=>/\/(first|second)$/.test(t.url||"")).map(t=>[t.url.split("/").pop(),t.id]))')
   start='async items=>Promise.all(items.map(({id,url})=>pageAction("translate",{id,url},false)))'
   results=worker.evaluate(start,[{'id':ids['first'],'url':helper.BASE+'/first'},{'id':ids['second'],'url':helper.BASE+'/second'}])
   assert all(r['ok'] for r in results)
   expect(first.locator('.nb-translation')).to_have_count(2,timeout=15000)
   expect(second.locator('.nb-translation')).to_have_count(2,timeout=15000)
   usage='async a=>helper("usage",null,null,a.url,a.id)'
   a=worker.evaluate(usage,{'id':ids['first'],'url':helper.BASE+'/first'})
   b=worker.evaluate(usage,{'id':ids['second'],'url':helper.BASE+'/second'})
   assert a['hasSession'] and b['hasSession'] and a['session']['total']==120 and b['session']['total']==120,(a,b)
   assert a['page']['total']==120 and b['page']['total']==120 and a['today']['total']==240
   # Warning appears without blocking work and does not expose source text.
   for _ in range(60):
    if any('达到提醒值' in page.locator('#cgpt-command-message').all_text_contents()[0] for page in (first,second) if page.locator('#cgpt-command-message').count()):break
    time.sleep(.1)
   else:raise AssertionError('No visible daily alert after threshold was reached')
   assert len(calls)==2,calls
   worker.evaluate('async a=>pageAction("translate",a,false)',{'id':ids['first'],'url':helper.BASE+'/first'})
   expect(first.locator('.nb-translation')).to_have_count(2,timeout=15000)
   again=worker.evaluate(usage,{'id':ids['first'],'url':helper.BASE+'/first'})
   assert again['session']['total']==0 and again['page']['total']==120 and len(calls)==2,again
   # New navigation within a tab does not inherit the old session's counts.
   assert not worker.evaluate(usage,{'id':ids['first'],'url':helper.BASE+'/different'})['hasSession']
   offline=ctx.new_page();offline.goto(helper.BASE+'/offline')
   oid=worker.evaluate('async()=> (await chrome.tabs.query({})).find(t=>t.url?.endsWith("/offline")).id')
   worker.evaluate('async a=>pageAction("translate",a,false)',{'id':oid,'url':helper.BASE+'/offline'})
   ctx.set_offline(True);time.sleep(2.5);ctx.set_offline(False)
   expect(offline.locator('.nb-translation')).to_have_count(2,timeout=20000)
   assert calls.count('offline test')==1,calls
   # Mock account values and graphics never touch the live user's data.
   extid=worker.url.split('/')[2];popup=ctx.new_page();popup.set_viewport_size({'width':370,'height':592})
   popup.goto('chrome-extension://'+extid+'/popup.html');expect(popup.locator('#translate')).to_be_enabled(timeout=10000)
   popup.evaluate("()=>renderPage({url:'https://www.youtube.com/watch?v=fixture',title:'A clear example video title for an accessibility check'})")
   expect(popup.locator('#caption-control')).to_be_visible()
   popup.locator('#open-settings').click();popup.locator('#daily-alert').fill('250')
   popup.locator('#save-alert').click();expect(popup.locator('#alert-setting-note')).to_contain_text('250')
   assert worker.evaluate('()=>chrome.storage.local.get("dailyAlert")')['dailyAlert']==250
   popup.locator('#settings-view .back').click();popup.locator('#open-usage').click()
   expect(popup.locator('#usage-details')).to_contain_text('本页累计')
   popup.locator('#usage-view .back').click()
   popup.evaluate("()=>renderPage({url:'https://www.wsj.com/example',title:'A clear example of a news article'})")
   expect(popup.locator('#caption-control')).to_be_hidden()
   out=os.environ.get('TRANSLATOR_TEST_SCREENSHOTS')
   if out:
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    for theme in ('light','dark'):
     popup.emulate_media(color_scheme=theme);popup.screenshot(path=str(out/('插件面板-'+theme+'.png')))
    popup.evaluate("()=>renderPage({url:'https://www.youtube.com/watch?v=fixture',title:'A clear example of an English video'})")
    popup.emulate_media(color_scheme='light');popup.screenshot(path=str(out/'插件面板-视频.png'))
   metrics=popup.evaluate('''()=>({height:document.documentElement.scrollHeight,body:document.body.scrollHeight,main:document.querySelector('#main').scrollHeight,visible:document.querySelector('#main').clientHeight})''')
   assert metrics['height']<=600 and metrics['body']<=600 and metrics['main']<=metrics['visible']+1,metrics
   ctx.close()
 finally:
  server.shutdown();app.pool.shutdown();app.local_engine.close(cleanup=True);app.antigravity.close(cleanup=True)
print('PASS: two simultaneous tabs; session and page ledger isolation; visible threshold alert; cached new session; offline and recovery; popup settings, daily limit and responsive layouts')
