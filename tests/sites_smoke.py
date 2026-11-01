# -*- coding: utf-8 -*-
import sys,tempfile,threading,shutil,json,time
from pathlib import Path
from http.server import ThreadingHTTPServer
from playwright.sync_api import sync_playwright,expect
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
import helper
helper.PORT=19489;helper.BASE='http://127.0.0.1:19489'
with tempfile.TemporaryDirectory() as tmp:
 app=helper.App(Path(tmp)/'data');app.models=lambda *args:[{'slug':'test-model'}]
 app.local_engine.quota=lambda:{'available':False,'scope':'fixture','message':'No real account in fixture'}
 def no_captions(video):raise helper.CaptionsError('此视频没有英文字幕，请尝试打开网页转录文稿。')
 app.caption_store.fetch=no_captions
 app.infer=lambda title,paras,previous,model,**kwargs:['这是第 '+p.split('number ')[1].split()[0]+' 条字幕的中文演示。' if 'caption number ' in p else '这是一段用于检查排版的中文模拟译文。' for p in paras]
 server=ThreadingHTTPServer(('127.0.0.1',19489),helper.Handler);server.app=app
 threading.Thread(target=server.serve_forever,daemon=True).start()
 ext=Path(tmp)/'extension';shutil.copytree(root/'extension',ext)
 yt=ext/'youtube.js';yt.write_text(yt.read_text().replace("mode:'closed'","mode:'open'"))
 f=ext/'background.js';f.write_text(f.read_text().replace('19487','19489'))
 manifest=json.loads((ext/'manifest.json').read_text());manifest['host_permissions']+=['https://www.youtube.com/*','https://www.wsj.com/*','https://www.reuters.com/*'];(ext/'manifest.json').write_text(json.dumps(manifest))
 with sync_playwright() as p:
  ctx=p.chromium.launch_persistent_context(str(Path(tmp)/'profile'),channel='chromium',headless=True,args=['--disable-extensions-except='+str(ext),'--load-extension='+str(ext)],viewport={'width':1100,'height':850})
  worker=ctx.service_workers[0] if ctx.service_workers else ctx.wait_for_event('serviceworker')
  worker.evaluate('(key)=>chrome.storage.local.set({pairingKey:key})',app.config['pairing_key'])
  page=ctx.new_page()
  def inject_translate():
   tab=worker.evaluate('async()=>{const tabs=await chrome.tabs.query({});return tabs.find(t=>/www\.(youtube|wsj|reuters)\.com/.test(t.url||"")).id}')
   r=worker.evaluate('async id=>{await chrome.scripting.executeScript({target:{tabId:id},files:["recovery.js","youtube.js","content.js"]});return chrome.tabs.sendMessage(id,{action:"translate",model:"test-model"});}',tab)
   return tab,r
  for host,body in [('www.wsj.com','<article><h1 style="color:rgb(240,240,240);background:black">Markets react to policy announcement</h1><div class="paywall"><p>Stocks moved higher after the announcement on Tuesday.</p><p>The forecast remains uncertain, analysts said.</p></div></article><aside><p>Subscribe to receive every latest news update</p></aside>'),('www.reuters.com','<h1>Markets react to policy announcement</h1><div data-testid="ArticleBody"><div data-testid="paragraph-0">Stocks moved higher after the announcement on Tuesday.</div><div data-testid="paragraph-1">The forecast remains uncertain, analysts said.</div></div><p>Newsletter content should not translate.</p>')]:
   url='https://'+host+'/test-article';page.route(url,lambda r,request,body=body:r.fulfill(content_type='text/html',body='<html><body>'+body+'</body></html>'))
   page.goto(url)
   page.evaluate('()=>{const n=document.createElement("div");n.className="nb-translation";n.lang="zh-CN";n.translate=false;n.textContent="旧扩展残留译文";document.body.append(n)}')
   page.evaluate('()=>{const n=document.createElement("div");n.id="page-rewritten-old-status";n.style.cssText="position:fixed;right:22px;bottom:22px;z-index:2147483647";document.documentElement.append(n)}')
   tab,result=inject_translate();assert result['ok'],result
   expect(page.locator('.nb-translation')).to_have_count(3,timeout=15000)
   expect(page.locator('.cgpt-news-status')).to_have_count(1)
   expect(page.locator('#page-rewritten-old-status')).to_have_count(0)
   if host=='www.wsj.com':
    assert page.locator('h1 + .nb-translation').evaluate('(el)=>getComputedStyle(el).color')=='rgb(240, 240, 240)'
    assert page.locator('.paywall .nb-translation').count()==2
   worker.evaluate('id=>chrome.tabs.sendMessage(id,{action:"restore"})',tab);expect(page.locator('.nb-translation')).to_have_count(0)
  home='''<main><h2>Top Stories</h2><h3><a data-testid="flexcard-headline" href="/finance/article">Wall Street starts calling the shots in AI</a></h3><div id="summary"><a aria-hidden="true" href="/finance/article"><span><p data-testid="flexcard-text">Lenders and investors are demanding stricter terms.</p></span></a></div><aside><h3><a data-testid="flexcard-headline" href="/opinion/example">An important opinion headline for today</a></h3></aside></main>'''
  home_url='https://www.wsj.com/'
  page.route(home_url,lambda r:r.fulfill(content_type='text/html',body=home))
  page.goto(home_url);tab,result=inject_translate();assert result['ok'],result
  expect(page.locator('.nb-translation')).to_have_count(3,timeout=15000)
  assert page.locator('h3 + .nb-translation').count()==2
  assert page.locator('#summary > a + .nb-translation').count()==1
  assert page.locator('h2 + .nb-translation').count()==0
  worker.evaluate('id=>chrome.tabs.sendMessage(id,{action:"restore"})',tab)
  expect(page.locator('.nb-translation')).to_have_count(0)
  cues=''.join('<ytd-transcript-segment-renderer><div class="segment-timestamp">0:%02d</div><div class="segment-text">English caption number %d for testing.</div></ytd-transcript-segment-renderer>'%(i*5,i) for i in range(6))
  html='''<html><meta charset="utf-8"><style>body{background:#171b21;color:#ddd;font:16px sans-serif;margin:40px}#movie_player{position:relative;width:900px;height:450px;background:#26382f;margin-bottom:30px}video{width:100%;height:100%}h1{padding:24px}ytd-transcript-segment-renderer{display:block;padding:8px}.segment-timestamp{color:#aaa}</style><body><div id="movie_player"><video></video></div><h1>YouTube 字幕模拟测试 · 非真实模型译文</h1>'''+cues+'</body></html>'
  url='https://www.youtube.com/watch?v=testvideo';page.route(url,lambda r:r.fulfill(content_type='text/html',body=html));page.goto(url)
  tab,result=inject_translate();assert result['ok'],result
  expect(page.locator('.cgpt-transcript-translation')).to_have_count(6,timeout=15000)
  assert page.locator('#cgpt-youtube-subtitles').count()==1
  # Read closed-shadow overlay through accessibility snapshot, just as a user can.
  page.wait_for_timeout(500)
  snapshot=page.locator('#cgpt-youtube-subtitles').locator('div').first.inner_text();assert 'caption number 0' in snapshot,snapshot
  box=page.locator('#caption-box');tools=page.locator('#cgpt-youtube-subtitles .tools')
  page.mouse.move(10,10);page.wait_for_timeout(160)
  expect(tools).to_be_hidden()
  old_size=box.evaluate('(el)=>parseFloat(getComputedStyle(el).fontSize)')
  page.evaluate('document.querySelector("#movie_player").addEventListener("click",()=>window.captionPlayerClicks=(window.captionPlayerClicks||0)+1)')
  box.hover();expect(tools).to_be_visible()
  handle=page.locator('.resize.se').bounding_box()
  x,y=handle['x']+handle['width']/2,handle['y']+handle['height']/2
  page.mouse.move(x,y);page.mouse.down();page.mouse.move(x+120,y+65,steps=10);page.mouse.up()
  page.wait_for_timeout(250)
  new_size=box.evaluate('(el)=>parseFloat(getComputedStyle(el).fontSize)')
  assert new_size>old_size*1.1,(old_size,new_size)
  saved=worker.evaluate('()=>chrome.storage.local.get("captionScale")')['captionScale']
  assert saved>100,saved
  assert page.evaluate('window.captionPlayerClicks||0')==0
  page.mouse.move(10,10);page.wait_for_timeout(180);expect(tools).to_be_hidden()
  worker.evaluate('id=>chrome.tabs.sendMessage(id,{action:"captionSettings",scale:100})',tab)
  worker.evaluate('()=>chrome.storage.local.set({captionScale:100})')
  page.evaluate('document.querySelector("video").currentTime=12');page.wait_for_timeout(500)
  snapshot=page.locator('#cgpt-youtube-subtitles').locator('div').first.inner_text();assert 'caption number 2' in snapshot,snapshot
  page.screenshot(path=str(root/'YouTube字幕预览（模拟译文）.png'),full_page=True)
  page.evaluate('document.querySelector("video").currentTime=2');page.wait_for_timeout(500)
  assert 'caption number 0' in page.locator('#cgpt-youtube-subtitles').locator('div').first.inner_text()
  # Player dimensions, rather than a fixed font cap or viewport width, drive subtitles.
  box=page.locator('#cgpt-youtube-subtitles').locator('div').first
  size=lambda:box.evaluate('(el)=>parseFloat(getComputedStyle(el).fontSize)')
  normal=size()
  assert 20<normal<24,normal
  page.set_viewport_size({'width':1600,'height':1000})
  page.wait_for_timeout(100)
  assert abs(size()-normal)<.1  # Same player, wider browser: font stays stable.
  page.add_style_tag(content='#movie_player:fullscreen{width:100vw;height:100vh}')
  page.evaluate('()=>{const b=document.createElement("button");b.id="fullscreen-test";b.textContent="Fullscreen";b.style.cssText="position:fixed;top:0;left:0;z-index:99999";b.onclick=()=>document.querySelector("#movie_player").requestFullscreen();document.querySelector("#movie_player").append(b)}')
  page.locator('#fullscreen-test').click()
  page.wait_for_function('document.fullscreenElement?.id === "movie_player"')
  page.wait_for_timeout(150)
  enlarged=size()
  assert enlarged>normal*1.6,(normal,enlarged)
  assert box.evaluate('(el)=>{const b=el.getBoundingClientRect();return b.left>=0&&b.top>=0&&b.right<=innerWidth&&b.bottom<=innerHeight}')
  worker.evaluate('id=>chrome.tabs.sendMessage(id,{action:"captionSettings",scale:150})',tab)
  page.wait_for_timeout(100)
  assert abs(size()-enlarged*1.5)<.1,(enlarged,size())
  worker.evaluate('id=>chrome.tabs.sendMessage(id,{action:"captionSettings",scale:100})',tab)
  page.evaluate('document.exitFullscreen()');page.wait_for_function('!document.fullscreenElement')
  page.wait_for_timeout(150)
  assert abs(size()-normal)<.1,(normal,size())
  page.set_viewport_size({'width':1100,'height':850})
  worker.evaluate('id=>chrome.tabs.sendMessage(id,{action:"restore"})',tab)
  expect(page.locator('#cgpt-youtube-subtitles')).to_have_count(0);expect(page.locator('.cgpt-transcript-translation')).to_have_count(0)
  page.goto('https://www.youtube.com/watch?v=empty') if False else None
  page.evaluate('document.querySelectorAll("ytd-transcript-segment-renderer").forEach(e=>e.remove())')
  tab,result=inject_translate();assert not result['ok'] and '转录文稿' in result['error'],result
  app.caption_store.fetch=lambda video:{'cues':[{'text':'English caption number 0 for testing.','start':0,'duration':5}], 'language':'en'}
  tab,result=inject_translate();assert result['ok'],result
  expect(page.locator('#cgpt-youtube-subtitles')).to_have_count(1)
  page.wait_for_timeout(1500)
  assert '中文' in page.locator('#cgpt-youtube-subtitles').locator('div').first.inner_text()
  worker.evaluate('id=>chrome.tabs.sendMessage(id,{action:"restore"})',tab)
  page.evaluate('document.body.insertAdjacentHTML("beforeend","<ytd-transcript-segment-renderer><div class=segment-timestamp>0:00</div><div class=segment-text>这是一段网页自动选择的中文字幕。</div></ytd-transcript-segment-renderer>")')
  tab,result=inject_translate();assert result['ok'],result
  expect(page.locator('#cgpt-youtube-subtitles')).to_have_count(1)
  page.wait_for_timeout(1000)
  assert 'English caption number 0' in page.locator('#cgpt-youtube-subtitles').locator('div').first.inner_text()
  worker.evaluate('id=>chrome.tabs.sendMessage(id,{action:"restore"})',tab)
  page.evaluate('document.querySelectorAll("ytd-transcript-segment-renderer").forEach(n=>n.remove());document.querySelector("video").currentTime=35')
  app.caption_store.fetch=lambda video:{'cues':[{'text':'English caption number %d for testing.'%i,'start':start,'duration':1} for i,start in enumerate([0,20,50])],'language':'en'}
  requests=[];original_start=app.start_job
  def capture_start(payload):requests.append(payload);return original_start(payload)
  app.start_job=capture_start
  tab,result=inject_translate();assert result['ok'],result
  page.wait_for_timeout(1500)
  assert len(requests)==1 and 'number 2' in requests[0]['paragraphs'][0],requests
  assert len(requests[0]['paragraphs'])==1,requests
  expect(page.locator('#caption-box')).to_be_hidden()
  page.evaluate('document.querySelector("video").currentTime=50');page.wait_for_timeout(500)
  assert 'caption number 2' in page.locator('#cgpt-youtube-subtitles').locator('div').first.inner_text()
  ctx.close()
 server.shutdown();app.pool.shutdown()
 print('PASS: WSJ body; Reuters div paragraphs; no newsletter/sidebar; YouTube six aligned translations; playback time/forward seek/back seek; restore; missing transcript')
