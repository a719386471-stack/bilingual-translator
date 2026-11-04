"""Compact subtitles retain all text, use native timing, and stay within the player."""
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
root=Path(__file__).resolve().parents[1]
script=(root/'extension/youtube.js').read_text().replace("mode:'closed'","mode:'open'")
with sync_playwright() as p:
 b=p.chromium.launch(headless=True,channel='chromium');page=b.new_page(viewport={'width':1100,'height':800})
 page.route('https://www.youtube.com/**',lambda r:r.fulfill(content_type='text/html',body='<style>body{margin:20px;background:#17211c}#movie_player{position:relative;width:960px;height:540px;background:#31463a}video{width:100%;height:100%}</style><div id="movie_player"><video></video></div>'))
 page.goto('https://www.youtube.com/watch?v=abcdefghijk')
 page.evaluate('''()=>{
  window.clock=0;window.requests=0;Object.defineProperty(document.querySelector('video'),'currentTime',{get:()=>clock});
  window.chrome={runtime:{id:'fixture',onMessage:{addListener:f=>window.listener=f}}};
  const texts=['这是前一句。','这样就能轻易地避开孩子们喜欢的科目。','从小就不让他们碰触。'];
  window.__cgptBridge={raw:async()=>({cues:[{text:'So you were probably steered benignly away from things at school.',start:0,duration:9}],nativeChinese:{source:'manual',translations:[texts.join(' ')],cues:texts.map((text,i)=>({text,start:i*3,duration:3}))}}),run:async()=>{requests++}};
 }''')
 page.add_script_tag(content=script)
 page.evaluate('()=>new Promise(resolve=>listener({action:"translate",model:"fixture",provider:"chatgpt",captionScale:90},{id:"fixture"},resolve))')
 for time,text in [(0,'这是前一句。'),(3.2,'这样就能轻易地避开孩子们喜欢的科目。'),(6.2,'从小就不让他们碰触。')]:
  page.evaluate('t=>clock=t',time);expect(page.locator('.translated')).to_have_text(text)
  box=page.locator('#caption-box').bounding_box();assert box['height']<540*.16,box
 assert page.evaluate('requests')==0
 page.evaluate('clock=9.2');expect(page.locator('#caption-box')).to_be_hidden()
 # Long cues wrap as a complete pair, never independently page or truncate.
 page.evaluate('''()=>{listener({action:'restore'},{id:'fixture'},()=>{});clock=0;window.longText='这是一段需要完整显示的较长中文字幕，不能截断丢失内容，也不能把好几句话同时堆叠遮挡整个画面。';__cgptBridge.raw=async()=>({cues:[{text:'A longer English sentence that remains fully available while the caption display uses compact timed fragments instead of stacking multiple lines.',start:0,duration:20}],nativeChinese:{source:'manual',translations:[longText]}})}''')
 page.evaluate('()=>new Promise(resolve=>listener({action:"translate",model:"fixture",provider:"chatgpt",captionScale:180},{id:"fixture"},resolve))')
 segments=[]
 for time in range(20):
  page.evaluate('t=>clock=t',time);page.wait_for_timeout(370)
  text=page.locator('.translated').inner_text()
  if not segments or segments[-1]!=text:segments.append(text)
  assert text==page.evaluate('longText'),text
  box=page.locator('#caption-box').bounding_box();assert box['height']<540*.45,box
  assert box['x']>=20 and box['x']+box['width']<=980,box
 assert ''.join(segments)==page.evaluate('longText'),segments
 page.screenshot(path=str(root/'compact-captions-fixture.png'))
 b.close()
print('PASS: native Chinese timeline, no adjacent-cue concatenation, gaps hidden, all long-cue text retained, bounded overlay at 180%, zero model requests')
