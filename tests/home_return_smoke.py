"""Real MV3 navigation, SPA return, remount and opt-out without helper/model calls."""
import tempfile,shutil,json
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
root=Path(__file__).resolve().parents[1]
home='''<html><body><main><h3><a href="/finance/one" data-testid="flexcard-headline">Markets react to a new policy announcement</a></h3><p data-testid="flexcard-text">Investors reconsider the risks of the latest technology.</p><h3><a href="/finance/two" data-testid="flexcard-headline">A second story with a different headline</a></h3></main></body></html>'''
with tempfile.TemporaryDirectory() as tmp,sync_playwright() as p:
 ext=Path(tmp)/'extension';shutil.copytree(root/'extension',ext)
 manifest=json.loads((ext/'manifest.json').read_text());manifest['host_permissions']+=['https://www.wsj.com/*'];(ext/'manifest.json').write_text(json.dumps(manifest))
 ctx=p.chromium.launch_persistent_context(str(Path(tmp)/'profile'),headless=True,channel='chromium',args=['--disable-extensions-except='+str(ext),'--load-extension='+str(ext)])
 sw=ctx.service_workers[0] if ctx.service_workers else ctx.wait_for_event('serviceworker')
 helper_requests=[];ctx.on('request',lambda r:helper_requests.append(r.url) if '127.0.0.1' in r.url else None)
 page=ctx.new_page();page.route('https://www.wsj.com/**',lambda r:r.fulfill(content_type='text/html',body=home if r.request.url=='https://www.wsj.com/' else '<article><h1>Article page</h1></article>'))
 page.goto('https://www.wsj.com/')
 tab=sw.evaluate('async()=> (await chrome.tabs.query({})).find(t=>t.url==="https://www.wsj.com/").id')
 sw.evaluate('''async id=>{
  await chrome.scripting.executeScript({target:{tabId:id},func:()=>{
   globalThis.__cgptBridge={raw:async()=>({}),run:async(payload,h)=>{
    document.documentElement.dataset.fixtureCalls=String(Number(document.documentElement.dataset.fixtureCalls||0)+1);
    h.update({results:Object.fromEntries(payload.paragraphs.map((v,i)=>[i,'模拟中文 '+v])),status:'done'});
   }};
  }});
  await chrome.scripting.executeScript({target:{tabId:id},files:['content.js']});
  return chrome.tabs.sendMessage(id,{action:'translate',model:'fixture',provider:'chatgpt',sessionId:'a'.repeat(32)});
 }''',tab)
 expect(page.locator('.nb-translation')).to_have_count(3)
 assert page.locator('html').get_attribute('data-fixture-calls')=='1'
 # Ensure the async snapshot has committed before leaving.
 page.wait_for_timeout(250)
 assert len(sw.evaluate('async()=> (await chrome.storage.session.get(HOME_SNAPSHOTS))[HOME_SNAPSHOTS]'))==1
 page.get_by_role('link',name='Markets react to a new policy announcement').click()
 expect(page.locator('.nb-translation')).to_have_count(0)
 page.go_back();expect(page.locator('.nb-translation')).to_have_count(3,timeout=10000)
 page.reload();expect(page.locator('.nb-translation')).to_have_count(3,timeout=10000)
 # Replace the whole framework-rendered body and alter one story. Only exact originals return.
 page.evaluate('(html)=>{document.body.innerHTML=new DOMParser().parseFromString(html,"text/html").body.innerHTML;document.querySelectorAll("h3 a")[1].textContent="A materially changed headline without a cached translation";}',home)
 expect(page.locator('.nb-translation')).to_have_count(2,timeout=10000)
 # Simulate same-document routing away and back.
 page.evaluate('()=>{history.pushState({},"","/finance/one");document.body.innerHTML="<article>Another page</article>"}')
 page.wait_for_timeout(650)
 page.evaluate('(html)=>{history.pushState({},"","/");document.body.innerHTML=new DOMParser().parseFromString(html,"text/html").body.innerHTML;}',home)
 expect(page.locator('.nb-translation')).to_have_count(3,timeout=10000)
 assert helper_requests==[],helper_requests
 sw.evaluate('id=>chrome.tabs.sendMessage(id,{action:"restore"})',tab)
 expect(page.locator('.nb-translation')).to_have_count(0)
 page.reload();page.wait_for_timeout(800);expect(page.locator('.nb-translation')).to_have_count(0)
 assert helper_requests==[],helper_requests
 ctx.close()
print('PASS: WSJ back/reload/SPA return; framework remount; changed text skipped; explicit restore respected; one translation invocation only')
