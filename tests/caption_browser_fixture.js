// Runs in a dedicated local test page with the real caption renderer and a fake bridge.
(async()=>{
const results=[];
const assert=(ok,message)=>{if(!ok)throw Error(message);};
const wait=ms=>new Promise(r=>setTimeout(r,ms));
const until=async f=>{for(let i=0;i<100;i++){if(f())return;await wait(20);}throw Error('condition timed out');};
const player=document.querySelector('#movie_player'),video=player.querySelector('video');
let clock=0,paused=true,mode='stream',requests=[],hooks=[],cancelled=[];
Object.defineProperties(video,{currentTime:{get:()=>clock},paused:{get:()=>paused}});
window.chrome={runtime:{id:'fixture',onMessage:{addListener:f=>window.listener=f}}};
const cues=Array.from({length:80},(_,i)=>({text:i===0?'to see.':'English fragment '+i,start:i*3,duration:6}));
window.__cgptBridge={raw:async(action,payload,id)=>{
 if(action==='cancel'){cancelled.push(id);return {};}
 return {cues,isGenerated:mode==='rolling',nativeChinese:mode==='native'?{source:'manual',translations:cues.map((_,i)=>'人工译文 '+i),cues:cues.map((c,i)=>({text:'人工译文 '+i,start:c.start,duration:3}))}:undefined};
},run:async(payload,h)=>{
 requests.push(payload);hooks.push(h);h.id('job-'+requests.length);
 if(mode==='hold')return new Promise(()=>{});
 h.update({results:{0:'译文 '+payload.cueIds[0]},status:'running'});
 await wait(120);
 h.update({results:Object.fromEntries(payload.cueIds.map((id,i)=>[i,'译文 '+id])),status:'done'});
}};
const stop=()=>listener({action:'restore'},{id:'fixture'},()=>{});
const start=()=>new Promise(r=>listener({action:'translate',model:'fixture',provider:'chatgpt',captionScale:100},{id:'fixture'},r));
const target=()=>document.querySelector('#cgpt-youtube-subtitles')?.shadowRoot.querySelector('.translated');
const source=()=>document.querySelector('#cgpt-youtube-subtitles')?.shadowRoot.querySelector('.original');
const seek=t=>{clock=t;video.dispatchEvent(new Event('seeking'));};
try{
 await window.loadCaptionScript();
 if(window.captionSample){
  const raw=window.captionSample.cues;
  const actual=window.__fixtureGroup(raw.map((c,i)=>({...c,end:Math.min(c.start+c.duration,raw[i+1]?.start??c.start+c.duration)})));
  assert(actual.map(c=>c.text).join(' ').replace(/\s+/g,' ').trim()===raw.map(c=>c.text).join(' ').replace(/\s+/g,' ').trim(),'punctuation grouping preserves every word');
  assert(actual.find(c=>c.text.includes('right after ChatGPT')).text.includes('launched'),'verb stays with ChatGPT clause');
  assert(actual.find(c=>c.text.includes('one of the highest')).text.includes('country'),'comparison stays with country');
  const data=document.createElement('pre');data.id='groups';data.hidden=true;data.textContent=JSON.stringify(actual);document.body.append(data);
  results.push('real video clauses preserve all words, including ChatGPT launched and highest country');
 }

 await start();
 await until(()=>target()?.textContent==='译文 0');
 assert(requests.length===1&&requests[0].cueIds.length===3,'first current window is three cues');
 results.push('first complete streamed subtitle appears before batch completion');
 await until(()=>requests.length===2);await wait(350);
 assert(requests.length===2,'paused warmup stops after one forward window');
 results.push('one bounded buffer prepared while paused');
 seek(3.1);await until(()=>target().textContent==='译文 1');
 assert(source().textContent==='English fragment 1','same source id advances with translated id');
 results.push('overlapping source cues switch as an English/Chinese pair');
 stop();mode='hold';clock=0;requests=[];hooks=[];cancelled=[];
 await start();const stale=hooks[0];seek(150);
 await until(()=>requests.length===2);
 assert(cancelled.length===1&&requests[1].cueIds[0]===50,'seek replaces stale job');
 stale.update({results:{0:'过期译文'},status:'done'});
 assert(!target().textContent.includes('过期'),'late seek result ignored');
 results.push('far seek prioritizes new cue and ignores stale response');
 stop();clock=0;requests=[];hooks=[];cancelled=[];await start();
 clock=25;await wait(250);
 assert(requests.length===1&&cancelled.length===0,'normal playback must not be mistaken for a seek');
 results.push('slow batch is not repeatedly cancelled by advancing playback');
 stop();mode='native';clock=0;requests=[];await start();
 seek(6.1);await until(()=>target().textContent==='人工译文 2');
 assert(requests.length===0,'manual captions do not use AI');
 results.push('manual Chinese keeps native timing with zero model calls');
 stop();mode='native';clock=0;
 const long='This full English sentence and its complete Chinese translation must stay visible together instead of paging independently as time advances.';
 cues[0]={text:long,start:0,duration:3};await start();const firstText=source().textContent;
 clock=2.6;await wait(150);assert(source().textContent===firstText&&firstText===long,'long source must not page independently');
 const rect=document.querySelector('#cgpt-youtube-subtitles').shadowRoot.querySelector('#caption-box').getBoundingClientRect();
 const bounds=player.getBoundingClientRect();assert(rect.left>=bounds.left&&rect.right<=bounds.right,'wrapped caption stays within player');
 results.push('long cue remains complete, paired and inside the player');
 stop();mode='rolling';clock=0;requests=[];
 cues.splice(0,cues.length,...[
 {text:'I think the UAE has consistently been',start:0,duration:5},
 {text:'the most forward-looking country in the',start:2,duration:5},
 {text:'world for AI adoption.',start:4,duration:3},
 {text:'Going back to the beginning.',start:7,duration:3}]);
 await start();await until(()=>target().textContent==='译文 0');
 assert(requests[0].paragraphs[0]==='I think the UAE has consistently been the most forward-looking country in the world for AI adoption.','ASR fragments form a bounded complete thought');
 clock=4.2;await wait(150);assert(source().textContent===requests[0].paragraphs[0]&&target().textContent==='译文 0','the entire bilingual unit shares source timestamps');
 seek(7.1);await until(()=>source().textContent==='Going back to the beginning.');
 results.push('automatic rolling fragments form short paired units on real timestamps');
 document.querySelector('#result').textContent='PASS '+results.length+' checks\n'+results.join('\n');
 window.fixtureResult={passed:true,results};
}catch(e){document.querySelector('#result').textContent='FAIL '+e.stack;window.fixtureResult={passed:false,error:e.stack,results};}
})();
