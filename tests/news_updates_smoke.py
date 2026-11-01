"""Warn about newly loaded article content without automatically spending tokens."""
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
root=Path(__file__).resolve().parents[1]
script=(root/'extension/content.js').read_text().replace("mode:'closed'","mode:'open'")
url='https://news.example.com/late-article'
body='''<html><body><article><h1>A news article with delayed content</h1><p>A paragraph that is present before the article finishes loading.</p></article><aside id="sidebar"></aside></body></html>'''
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True,channel='chromium');page=browser.new_page()
 page.route(url,lambda r:r.fulfill(content_type='text/html',body=body));page.goto(url)
 page.evaluate('''()=>{
  window.requests=[];
  window.chrome={runtime:{id:'fixture',onMessage:{addListener(fn){window.listener=fn}}}};
  window.__cgptBridge={raw:async()=>({}),run:async(payload,opts)=>{
   requests.push(payload);opts.update({results:Object.fromEntries(payload.paragraphs.map((p,i)=>[i,'中文：'+p])),status:'done'});
  }};
 }''')
 page.add_script_tag(content=script)
 result=page.evaluate('''()=>new Promise(resolve=>listener({action:'translate',model:'fixture',provider:'chatgpt',sessionId:'a'.repeat(32)},{id:'fixture'},resolve))''')
 assert result['ok'],result
 expect(page.locator('.nb-translation')).to_have_count(2,timeout=10000)
 expect(page.locator('#cgpt-news-status #label')).to_contain_text('已就绪')
 # Unrelated changes must not generate a new warning or model request.
 page.evaluate('document.querySelector("#sidebar").textContent="A ticker in the sidebar changed"')
 page.wait_for_timeout(1500)
 expect(page.locator('#cgpt-news-status #label')).to_contain_text('已就绪')
 assert page.evaluate('requests.length')==1
 # Even identical repeated paragraphs represent an additional visible block.
 page.evaluate('''()=>{const p=document.createElement('p');p.textContent=document.querySelector('article p').textContent;document.querySelector('article').append(p)}''')
 expect(page.locator('#cgpt-news-status #label')).to_contain_text('新增 1 段',timeout=10000)
 expect(page.locator('#cgpt-news-status #label')).to_contain_text('可能增加用量')
 assert page.evaluate('requests.length')==1
 page.get_by_role('button',name='继续翻译').click()
 expect(page.locator('.nb-translation')).to_have_count(3,timeout=10000)
 expect(page.locator('#cgpt-news-status #label')).to_contain_text('已就绪')
 assert page.evaluate('requests.length')==2
 assert page.evaluate('requests[1].sessionId')=='a'*32
 page.evaluate('''()=>listener({action:'restore'},{id:'fixture'},()=>{})''')
 expect(page.locator('#cgpt-news-status')).to_have_count(0)
 browser.close()
print('PASS: newly loaded paragraphs detected; unrelated mutations ignored; no model request until user continues; session and restore preserved')
