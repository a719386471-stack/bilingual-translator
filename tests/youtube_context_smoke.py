"""Isolated browser checks of caption context, seek isolation and manual-track reuse."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1]
SCRIPT=(ROOT/'extension/youtube.js').read_text().replace("mode:'closed'","mode:'open'")
HTML='''<html><meta charset="utf-8"><style>#movie_player{position:relative;width:900px;height:450px}video{width:100%;height:100%}</style><div id="movie_player"><video></video></div></html>'''
with sync_playwright() as p:
 browser=p.chromium.launch(channel='chromium',headless=True)
 page=browser.new_page()
 page.route('https://www.youtube.com/**',lambda r:r.fulfill(content_type='text/html',body=HTML))
 def setup(native=None,long=False):
  page.goto('https://www.youtube.com/watch?v=abcdefghijk')
  page.evaluate('''({native,long})=>{
   const video=document.querySelector('video');window.clock=0;
   Object.defineProperty(video,'currentTime',{get:()=>clock,set:v=>clock=v});
   const cues=Array.from({length:60},(_,i)=>({text:'English cue number '+i+' '+(long?'topic '.repeat(140):'for context testing.'),start:i*5,duration:5}));
   window.requests=[];
   window.chrome={runtime:{id:'fixture',onMessage:{addListener:f=>window.listener=f}}};
   window.__cgptBridge={raw:async action=>action==='transcript'?{cues,language:'en',...(native?{nativeChinese:{source:'manual',language:'zh-Hans',translations:cues.map((_,i)=>native==='all'?'人工中文字幕 '+i:(i===3?'':'人工中文字幕 '+i))}}:{})}: {},
    run:async(payload,h)=>{requests.push(payload);await new Promise(r=>setTimeout(r,20));h.update({results:Object.fromEntries(payload.cueIds.map((id,i)=>[i,'模型译文 '+id])),status:'done'});}};
  }''',{'native':native,'long':long})
  page.add_script_tag(content=SCRIPT)
  page.evaluate('''()=>new Promise(resolve=>listener({action:'translate',model:'fixture',provider:'antigravity'}, {id:'fixture'},resolve))''')
 setup()
 page.wait_for_function('requests.length===1')
 page.wait_for_function('document.querySelector("#cgpt-youtube-subtitles").shadowRoot.querySelector(".translated").textContent.includes("模型译文")')
 first=page.evaluate('requests[0]');assert first['cueIds']==list(range(2)),first
 assert first['contextBefore']==[]
 assert all('number '+str(i) in v for i,v in zip(range(2,5),first['contextAfter']))
 page.wait_for_function('requests.length===2')
 second=page.evaluate('requests[1]')
 assert second['cueIds'][0]==2 and len(second['contextBefore'])==2,second
 for n,pair in zip(range(2),second['contextBefore']):
  assert 'number '+str(n)+' ' in pair['en'] and pair['zh']=='模型译文 '+str(n),pair
 assert second['contextAfter'][0].startswith('English cue number '+str(second['cueIds'][-1]+1)+' ')
 page.evaluate('clock=150')
 page.wait_for_function('requests.length===3')
 third=page.evaluate('requests[2]')
 assert third['cueIds'][0]==30,third
 for n,pair in zip(range(27,30),third['contextBefore']):
  assert pair['en'].startswith('English cue number '+str(n)+' ') and 'zh' not in pair,pair
 # Long individual captions never make either context side grow without bound.
 setup(long=True)
 page.wait_for_function('requests.length===2')
 bounded=page.evaluate('requests[1]')
 assert sum(len(x['en'])+len(x.get('zh','')) for x in bounded['contextBefore'])<=1800
 assert sum(map(len,bounded['contextAfter']))<=1800
 # A complete manual Chinese track displays without making an AI request.
 setup(native='all')
 expect(page.locator('#cgpt-youtube-subtitles')).to_have_attribute('data-caption-source','manual-chinese')
 expect(page.locator('.translated')).to_have_text('人工中文字幕 0')
 assert page.evaluate('requests.length')==0
 page.locator('#caption-box').hover();expect(page.locator('.tools')).to_be_visible()
 assert '人工中文字幕' in page.locator('.tools').inner_text()
 # An uncovered subtitle remains a real missing item and uses AI only when reached.
 setup(native='partial');page.evaluate('clock=15')
 page.wait_for_function('requests.length===1')
 partial=page.evaluate('requests[0]');assert partial['cueIds']==[3],partial
 expect(page.locator('#cgpt-youtube-subtitles')).to_have_attribute('data-caption-source','manual-chinese-and-ai')
 page.wait_for_function('document.querySelector("#cgpt-youtube-subtitles").shadowRoot.querySelector(".translated").textContent==="模型译文 3"')
 browser.close()
print('PASS: adjacent translated/source context; 1800-character bounds; seek-local context; stable cue IDs; manual Chinese zero AI calls; uncovered cues AI only')
