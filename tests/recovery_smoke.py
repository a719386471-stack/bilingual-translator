"""Real extension/browser + disposable HTTP faults; no real accounts or network changes."""
import sys,tempfile,threading,shutil,json,time,socket,subprocess,base64
from pathlib import Path
from http.server import ThreadingHTTPServer
from playwright.sync_api import sync_playwright,expect
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
import helper
helper.PORT=19489;helper.BASE='http://127.0.0.1:19489'
class FaultHandler(helper.Handler):
 dropped_post=False;dropped_poll=False;forgotten=False
 def do_POST(self):
  if self.path=='/api/jobs' and not FaultHandler.dropped_post:
   self.guard();data=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
   self.app.start_job(data);FaultHandler.dropped_post=True
   self.close_connection=True;self.connection.shutdown(socket.SHUT_RDWR);return
  super().do_POST()
 def do_GET(self):
  if self.path.startswith('/api/jobs/') and not FaultHandler.dropped_poll:
   FaultHandler.dropped_poll=True;self.close_connection=True;self.connection.shutdown(socket.SHUT_RDWR);return
  if self.path.startswith('/api/jobs/') and not FaultHandler.forgotten:
   id=self.path.rsplit('/',1)[-1]
   with self.app.jobs_lock:
    j=self.app.jobs.get(id)
    if j and j['status']=='done':self.app.jobs.pop(id);FaultHandler.forgotten=True
  super().do_GET()
with tempfile.TemporaryDirectory() as tmp:
 app=helper.App(Path(tmp)/'data');app.models=lambda *args:[{'slug':'fixture'}]
 app.retry_wait=lambda job,seconds:job['cancel'].is_set()
 def no_captions(video):raise helper.CaptionsError('Fixture: no public transcript; use DOM transcript.')
 app.caption_store.fetch=no_captions
 calls=[];quota=False;slow=False;cancelled=[]
 def infer(title,paras,previous,model,**kw):
  calls.append(list(paras))
  if quota and paras[0].startswith('Recovery paragraph number 6 '):raise helper.AppError('额度暂不可用','quota')
  if slow:
   for _ in range(20):
    if kw['cancel'].wait(.05):cancelled.append(paras);return ['被取消']*len(paras)
  return ['中文：'+p for p in paras]
 app.infer=infer
 server=ThreadingHTTPServer(('127.0.0.1',19489),FaultHandler);server.app=app
 threading.Thread(target=server.serve_forever,daemon=True).start()
 ext=Path(tmp)/'extension';shutil.copytree(root/'extension',ext)
 for name in ('youtube.js','content.js'):
  f=ext/name;f.write_text(f.read_text().replace("mode:'closed'","mode:'open'"))
 f=ext/'background.js';f.write_text(f.read_text().replace('19487','19489'))
 m=json.loads((ext/'manifest.json').read_text());m['host_permissions']+=['https://www.reuters.com/*','https://www.youtube.com/*'];(ext/'manifest.json').write_text(json.dumps(m))
 with sync_playwright() as p:
  ctx=p.chromium.launch_persistent_context(str(Path(tmp)/'profile'),channel='chromium',headless=True,args=['--disable-extensions-except='+str(ext),'--load-extension='+str(ext)])
  worker=ctx.service_workers[0] if ctx.service_workers else ctx.wait_for_event('serviceworker')
  worker.evaluate('key=>chrome.storage.local.set({pairingKey:key})',app.config['pairing_key'])
  page=ctx.new_page()
  def start():
   id=worker.evaluate('async()=> (await chrome.tabs.query({})).find(t=>/^https:\/\/www\.(reuters|youtube)\.com/.test(t.url||"")).id')
   result=worker.evaluate('async id=>{await chrome.scripting.executeScript({target:{tabId:id},files:["recovery.js","youtube.js","content.js"]});return chrome.tabs.sendMessage(id,{action:"translate",provider:"chatgpt",model:"fixture"});}',id)
   assert result['ok'],result
   return id
  url='https://www.reuters.com/recovery-test/'
  body='<h1>Recovery article for network testing</h1><div data-testid="ArticleBody">'+''.join('<p>'+('Recovery paragraph number %d has several complete English sentences for testing.'%i).ljust(1400,'x')+'</p>' for i in range(18))+'</div>'
  page.route(url,lambda r:r.fulfill(content_type='text/html',body=body));page.goto(url);tab=start()
  expect(page.locator('.nb-translation')).to_have_count(19,timeout=25000)
  assert FaultHandler.dropped_post and FaultHandler.dropped_poll and FaultHandler.forgotten
  assert len(calls)==4,calls  # 19 blocks, no repeated model work after lost POST or lost task.
  worker.evaluate('id=>chrome.tabs.sendMessage(id,{action:"restore"})',tab)
  # A hard quota error pauses once; the visible Continue button retries only missing paragraphs.
  calls.clear();quota=True
  page.route('https://www.reuters.com/quota-test/',lambda r:r.fulfill(content_type='text/html',body='<div data-testid="ArticleBody">'+''.join('<p>'+('Recovery paragraph number %d has different content for a quota test.'%i).ljust(1300,'x')+'</p>' for i in range(14))+'</div>'))
  page.goto('https://www.reuters.com/quota-test/');tab=start()
  expect(page.locator('.nb-translation')).to_have_count(6,timeout=10000)
  again=page.get_by_role('button',name='继续翻译');expect(again).to_be_visible(timeout=10000)
  assert len(calls)==2,calls
  quota=False;again.click();expect(page.locator('.nb-translation')).to_have_count(14,timeout=10000)
  assert len(calls)==4,calls
  assert sum(p[0].startswith('Recovery paragraph number 0 ') for p in calls)==1
  worker.evaluate('id=>chrome.tabs.sendMessage(id,{action:"restore"})',tab)
  calls.clear()
  cues=''.join('<ytd-transcript-segment-renderer><div class="segment-timestamp">%d:%02d</div><div class="segment-text">English caption number %d is aligned with this video.</div></ytd-transcript-segment-renderer>'%(i*2//60,i*2%60,i) for i in range(600))
  media=Path(tmp)/'silent.webm'
  subprocess.run([shutil.which('ffmpeg'),'-hide_banner','-loglevel','error','-f','lavfi','-i','color=c=black:s=32x32:r=1','-t','1250','-an','-c:v','libvpx-vp9','-b:v','10k','-g','1',str(media)],check=True)
  page.route('https://www.youtube.com/fixture.webm',lambda r:r.fulfill(content_type='video/webm',body=media.read_bytes()))
  video='https://www.youtube.com/watch?v=fixturelong'
  page.route(video,lambda r:r.fulfill(content_type='text/html',body='<style>#movie_player{position:relative;width:900px;height:500px}video{width:100%;height:100%}</style><div id="movie_player"><video muted src="data:video/webm;base64,'+base64.b64encode(media.read_bytes()).decode()+'"></video></div>'+cues));page.goto(video)
  tab=start();expect(page.locator('.cgpt-transcript-translation')).to_have_count(35,timeout=10000)
  assert len(calls)==2 and len(calls[0])==3 and len(calls[1])==32,calls
  # Playback starts: fetch about a minute in one request, rather than fixed six-cue calls.
  page.evaluate('async()=>{const v=document.querySelector("video");v.currentTime=4;await v.play()}')
  page.wait_for_timeout(1700)
  assert len(calls)==2 and 20<=len(calls[-1])<=32,[len(x) for x in calls]
  # A far seek interrupts the old slow prefetch and prioritizes the new location.
  slow=True
  page.evaluate('document.querySelector("video").currentTime=60');page.wait_for_timeout(450)
  page.evaluate('()=>{const v=document.querySelector("video");v.currentTime=600;v.pause()}');page.wait_for_function('Math.abs(document.querySelector("video").currentTime-600)<1')
  expect(page.locator('#caption-box .translated')).to_contain_text('number 300',timeout=10000)
  assert cancelled,'far seek left obsolete request running'
  assert any('number 300 ' in p[0] for p in calls),calls
  worker.evaluate('id=>chrome.tabs.sendMessage(id,{action:"restore"})',tab)
  expect(page.locator('#cgpt-youtube-subtitles')).to_have_count(0)
  # A stable public transcript wins over differently split webpage fragments.
  slow=False;canonical=[{'text':'Canonical English caption number %d for stable segmentation.'%i,'start':i*2,'duration':2} for i in range(20)]
  app.caption_store.fetch=lambda video:{'cues':canonical,'language':'en'}
  page.evaluate('document.querySelector("video").pause();document.querySelector("video").currentTime=0')
  start();expect(page.locator('#caption-box .translated')).to_contain_text('Canonical English caption number 0',timeout=10000)
  used=len(calls)
  page.reload();start();expect(page.locator('#caption-box .translated')).to_contain_text('Canonical English caption number 0',timeout=10000)
  assert len(calls)==used,'refresh with different webpage segmentation billed the canonical transcript twice'
  worker.evaluate('id=>chrome.tabs.sendMessage(id,{action:"restore"})',tab)
  ctx.close()
 server.shutdown();app.pool.shutdown();app.local_engine.close(cleanup=True);app.antigravity.close(cleanup=True)
 print('PASS: lost POST dedup; interrupted poll recovery; helper task loss/cache resume; quota pause/manual continue; adaptive time buffer; far-seek cancellation; canonical segmentation/cache after reload; restore')
