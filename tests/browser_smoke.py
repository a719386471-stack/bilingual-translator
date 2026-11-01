# -*- coding: utf-8 -*-
import sys,tempfile,threading,shutil,json,time
from pathlib import Path
from http.server import ThreadingHTTPServer
from playwright.sync_api import sync_playwright,expect
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
import helper
helper.PORT=19489
helper.BASE='http://127.0.0.1:19489'
fixture='''<!doctype html><html lang="en"><meta charset="utf-8"><title>Scientists report progress on cleaner batteries</title><style>body{background:#faf9f6;color:#26302c;font:19px/1.7 Georgia;max-width:760px;margin:50px auto}h1{font-size:42px;line-height:1.2}nav,aside{font-size:14px;color:#89938d}</style><body><nav>NEWSBRIDGE · 演示文章 / 模拟译文</nav><main><article><header><h1>Scientists report progress on cleaner batteries</h1><p>A new study points to a possible route to reducing waste.</p></header><p>Researchers said on Tuesday that a new battery design could reduce the amount of rare metals needed for energy storage.</p><p>The team tested 120 prototypes over six months. The results suggest an improvement, but the technology is not yet ready for commercial use.</p><blockquote><p>“We still need to understand how the cells perform over several years,” the lead researcher said.</p></blockquote><p hidden>This hidden English text must never be translated.</p><p>这是一段中文，应该保留原样，不应再次翻译。</p><aside><p>Subscribe to our newsletter for the latest science news.</p></aside></article></main><footer>Terms of service and privacy policy</footer></body></html>'''
zh=['科学家报告清洁电池研究取得进展','一项新研究提出了一条可能减少废弃物的路径。','研究人员周二表示，一种新的电池设计可能减少储能所需的稀有金属用量。','研究团队在六个月内测试了 120 个原型。结果显示性能有所改善，但该技术尚未达到商业应用阶段。','“我们仍需了解这些电池在数年使用中的表现，”首席研究员说。']
import re
fixture_css=re.search(r'<style>(.*?)</style>',fixture).group(1)
fixture=re.sub(r'<style>.*?</style>', '<link rel="stylesheet" href="/fixture.css">',fixture)
class Handler(helper.Handler):
 def do_GET(self):
  if self.path=='/article': self.send(fixture,kind='text/html; charset=utf-8')
  elif self.path=='/fixture.css':self.send(fixture_css,kind='text/css; charset=utf-8')
  else: super().do_GET()
with tempfile.TemporaryDirectory() as tmp:
 app=helper.App(Path(tmp)/'data')
 app.status=lambda:{'connected':True,'email':'browser-test@example.invalid','authError':'','provider':app.provider(),'providerName':'Antigravity' if app.provider()=='antigravity' else 'ChatGPT'}
 app.models=lambda *args:[{'slug':'fixture-flash-low','display_name':'Fixture Flash'}] if (args[0] if args else app.provider())=='antigravity' else [{'slug':'test-model','display_name':'Test model (fixture)'}]
 app.antigravity.quota=lambda:{'available':True,'scope':'Antigravity fixture','windows':[{'name':'Gemini 周额度','remainingPercent':90,'resetsAt':1793800000}],'message':'Fixture only'}
 app.local_engine.quota=lambda:{'available':False,'scope':'fixture','message':'No real account in fixture'}
 calls=[]
 def infer(title,paragraphs,previous,model,**kwargs):
  calls.append(paragraphs)
  return [zh[i] for i in range(len(paragraphs))]
 app.infer=infer
 server=ThreadingHTTPServer(('127.0.0.1',19489),Handler);server.app=app
 threading.Thread(target=server.serve_forever,daemon=True).start()
 ext=Path(tmp)/'extension';shutil.copytree(root/'extension',ext)
 bg=ext/'background.js';bg.write_text(bg.read_text().replace('19487','19489'))
 with sync_playwright() as p:
  ctx=p.chromium.launch_persistent_context(str(Path(tmp)/'profile'),channel='chromium',headless=True,args=['--disable-extensions-except='+str(ext),'--load-extension='+str(ext)],viewport={'width':1200,'height':1080})
  sw=ctx.service_workers[0] if ctx.service_workers else ctx.wait_for_event('serviceworker')
  extid=sw.url.split('/')[2]
  sw.evaluate('(key)=>chrome.storage.local.set({pairingKey:key})',app.config['pairing_key'])
  sw.evaluate('()=>{let running=true;chrome.runtime.sendNativeMessage=async(host,m)=>{if(m.action==="start")running=true;if(m.action==="stop")running=false;return {ok:true,data:{running}}}}')
  popup=ctx.new_page();popup.goto('chrome-extension://'+extid+'/popup.html')
  expect(popup.locator('#account')).to_contain_text('已连接 ChatGPT')
  expect(popup.locator('#translate')).to_be_enabled()
  expect(popup.locator('#shortcut')).to_contain_text(re.compile(r'⌥E|Alt\+E'))
  popup.locator('#provider').select_option('antigravity')
  expect(popup.locator('#account')).to_contain_text('已连接 Antigravity')
  expect(popup.locator('#model')).to_have_value('fixture-flash-low')
  popup.locator('#quota summary').click()
  expect(popup.locator('#quota-content')).to_contain_text('90%')
  popup.locator('#provider').select_option('chatgpt')
  expect(popup.locator('#model')).to_have_value('test-model')
  saved=sw.evaluate('()=>chrome.storage.local.get("modelsByProvider")')['modelsByProvider']
  assert saved['antigravity']=='fixture-flash-low' and saved['chatgpt']=='test-model',saved
  popup.locator('#caption-size').press('Home')
  for _ in range(10):popup.locator('#caption-size').press('ArrowRight')
  expect(popup.locator('#caption-value')).to_have_text('150%')
  popup.reload();expect(popup.locator('#caption-size')).to_have_value('150')
  popup.locator('#caption-reset').click();expect(popup.locator('#caption-value')).to_have_text('100%')
  expect(popup.locator('#service-toggle')).to_have_attribute('aria-checked','true')
  popup.locator('#service-toggle').click()
  expect(popup.locator('#service-toggle')).to_have_attribute('aria-checked','false')
  expect(popup.locator('#translate')).to_be_disabled()
  assert sw.evaluate('()=>chrome.storage.local.get("pairingKey")')['pairingKey']==app.config['pairing_key']
  popup.reload()
  expect(popup.locator('#service-toggle')).to_have_attribute('aria-checked','false')
  popup.locator('#service-toggle').click()
  expect(popup.locator('#translate')).to_be_enabled()
  # A popup rendered in a tab has activeTab access to itself; use the service worker
  # to inject the same shipped content script into the explicit test article.
  article=ctx.new_page();article.goto(helper.BASE+'/article')
  tabid=sw.evaluate('async()=>{const tabs=await chrome.tabs.query({}); return tabs.find(t=>t.url?.includes("/article")).id}')
  sw.evaluate('async id=>{await chrome.scripting.executeScript({target:{tabId:id},files:["recovery.js","content.js"]});return chrome.tabs.sendMessage(id,{action:"translate",model:"test-model"});}',tabid)
  expect(article.locator('.nb-translation')).to_have_count(5,timeout=20000)
  assert len(calls)==1 and len(calls[0])==5,calls
  assert 'hidden English' not in str(calls) and 'Subscribe' not in str(calls)
  assert app.usage.summary()['today']['unreported']==1  # Fixture reports no usage; never invent zero.
  # Shadow DOM contents render as text, without exposing translated HTML markup.
  article.screenshot(path=str(root/'双语效果预览（模拟译文）.png'),full_page=True)
  sw.evaluate('id=>chrome.tabs.sendMessage(id,{action:"restore"})',tabid)
  expect(article.locator('.nb-translation')).to_have_count(0)
  sw.evaluate('id=>chrome.tabs.sendMessage(id,{action:"translate",model:"test-model"})',tabid)
  expect(article.locator('.nb-translation')).to_have_count(5,timeout=10000)
  assert len(calls)==1,'Cache missed'
  sw.evaluate('id=>chrome.tabs.sendMessage(id,{action:"restore"})',tabid)
  article.goto(helper.BASE+'/article')
  sw.evaluate('async id=>{await chrome.scripting.executeScript({target:{tabId:id},files:["recovery.js","content.js"]});return chrome.tabs.sendMessage(id,{action:"translate",model:"test-model"});}',tabid)
  expect(article.locator('.nb-translation')).to_have_count(5,timeout=10000)
  article.evaluate('history.pushState({},"","/article?next=1")')
  expect(article.locator('.nb-translation')).to_have_count(0,timeout=4000)
  # Invoke the registered command path, rather than checking only its binding.
  sw.evaluate('async id=>handleCommand("translate-page",{id,url:"http://127.0.0.1:19489/article?next=1"})',tabid)
  expect(article.locator('.nb-translation')).to_have_count(5,timeout=10000)
  # Wrong pairing code is reported without returning any upstream credentials.
  sw.evaluate('()=>chrome.storage.local.set({pairingKey:"wrong"})')
  popup.reload();expect(popup.locator('#account')).to_contain_text('连接码无效')
  ctx.close()
 server.shutdown();app.pool.shutdown()
 print('PASS: real MV3 extension loads; popup connection/model list; 5 aligned paragraphs; excluded hidden/nav/Chinese; restore; cached repeat; navigation cancellation; invalid key')
