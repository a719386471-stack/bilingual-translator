(() => {
  if (globalThis.__cgptYT || !/(^|\.)youtube\.com$/.test(location.hostname)) return;
  globalThis.__cgptYT = true;
  let run = 0, active = false, job = null, timer = null, overlay, label, source, target, shell;
  let dragging=false,suppressClick=null,finishDrag=null,retryButton;
  let batchSerial=0,pendingRange=null,latency=6,hasWindow=false,suspended=false,failedStart=0;
  let playerResize = null, resizeFrame = null;
  let fontScale=100, nativeCount=0, nativeTimeline=[];
  let seekVideo=null,seekHandler=null,seekPending=false,warmupNeeded=false;
  const nativeIndices=new Set();
  const validScale=value=>Math.max(50,Math.min(200,Number(value)||100));
  let cues = [], translated = new Map(), annotations = [], loading = false, model, provider, sessionId='', currentVideo = '';
  const text = el => el?.textContent?.replace(/\s+/g,' ').trim() || '';
  const wait = ms => new Promise(r => setTimeout(r,ms));
  const api=(...args)=>globalThis.__cgptBridge.raw(...args);
  function stamp(value) {
    if (!/^\d+(?::\d{1,2}){1,2}$/.test(value.trim())) return NaN;
    return value.trim().split(':').reduce((a,n)=>a*60+Number(n),0);
  }
  function readCues() {
    return [...document.querySelectorAll('ytd-transcript-segment-renderer, ytd-transcript-segment-view-model, transcript-segment-view-model')].map(el => {
      const ts=el.querySelector('.segment-timestamp,[class*="timestamp"]');
      const body=el.querySelector('.segment-text,[class*="segment-text"],.yt-core-attributed-string');
      return {el,start:stamp(text(ts)),text:text(body)};
    }).filter(c=>Number.isFinite(c.start)&&c.text&&c.text.length<12000)
      .sort((a,b)=>a.start-b.start).filter((c,i,a)=>!i||c.start!==a[i-1].start||c.text!==a[i-1].text);
  }
  function stop() {
    active=false;run++;batchSerial++;loading=false;dragging=false;pendingRange=null;hasWindow=false;suspended=false;latency=6;
    if(suppressClick){document.removeEventListener('click',suppressClick,true);suppressClick=null;}
    if(finishDrag){for(const type of ['pointerup','mouseup','pointercancel'])document.removeEventListener(type,finishDrag,true);finishDrag=null;}
    clearInterval(timer);timer=null;
    if(seekHandler)seekVideo?.removeEventListener('seeking',seekHandler);
    seekVideo=null;seekHandler=null;seekPending=false;warmupNeeded=false;
    playerResize?.disconnect();playerResize=null;
    document.removeEventListener('fullscreenchange',scheduleOverlayResize);
    window.removeEventListener('resize',scheduleOverlayResize);
    if(resizeFrame!==null)cancelAnimationFrame(resizeFrame);resizeFrame=null;
    if(job) api('cancel',null,job).catch(()=>{});
    job=null;overlay?.remove();overlay=null;
    document.querySelectorAll('#cgpt-youtube-subtitles,.cgpt-transcript-translation').forEach(node=>node.remove());
    annotations.forEach(n=>n.remove());annotations=[];
    cues=[];translated.clear();nativeCount=0;nativeTimeline=[];nativeIndices.clear();
  }
  function resizeOverlay() {
    resizeFrame=null;
    const player=overlay?.parentElement;
    if(!player)return;
    // Use the actual player, including theater/fullscreen transitions, not viewport vw.
    const {width,height}=player.getBoundingClientRect();
    if(!width||!height)return;
    const size=Math.max(14,Math.min(56,width*.024,height*.05))*fontScale/100;
    overlay.style.setProperty('--cgpt-caption-size',size+'px');
    overlay.style.bottom=Math.max(40,Math.min(76,height*.065))+'px';
  }
  function scheduleOverlayResize() {
    if(resizeFrame===null)resizeFrame=requestAnimationFrame(resizeOverlay);
  }
  function makeOverlay() {
    overlay=document.createElement('div');overlay.id='cgpt-youtube-subtitles';
    overlay.dataset.layoutProtocol='paired-clause-v3';overlay.dataset.resizeProtocol='pointer-v2';overlay.dataset.bufferProtocol='stream-prefetch-v2';
    overlay.dataset.captionSource=nativeCount?(nativeCount===cues.length?'manual-chinese':'manual-chinese-and-ai'):'ai';
    overlay.style.cssText='position:absolute;left:8%;right:8%;bottom:70px;z-index:65;text-align:center;pointer-events:none;';
    const shadow=overlay.attachShadow({mode:'closed'});
    const style=document.createElement('style');style.textContent=`
      #caption-box{position:relative;display:inline-block;box-sizing:border-box;max-width:100%;color:#fff;pointer-events:auto;
        font:500 var(--cgpt-caption-size,22px)/1.18 -apple-system,BlinkMacSystemFont,"SF Pro Text","PingFang SC","Microsoft YaHei",sans-serif;white-space:normal;
        background:linear-gradient(180deg,rgba(14,22,18,.30),rgba(10,16,13,.40));backdrop-filter:none;-webkit-backdrop-filter:none;
        border:1px solid rgba(255,255,255,.06);box-shadow:0 2px 6px rgba(0,0,0,.12);padding:.07em .34em .09em;
        text-shadow:0 1px 3px #000,0 0 2px #000;outline:1.5px solid transparent;outline-offset:4px;border-radius:.32em;transition:outline-color .15s,box-shadow .15s}
      #caption-box[hidden]{display:none}.line{display:block;box-sizing:border-box;max-width:100%;margin:0 auto;padding:0;border-radius:.1em;white-space:normal;overflow-wrap:anywhere}
      .line:empty{display:none}
      .original{font-size:.74em;font-weight:450;line-height:1.16;color:rgba(232,242,237,.86);letter-spacing:.005em}
      .translated{margin-top:.05em;font-weight:560;line-height:1.18;color:#fff;letter-spacing:.015em}
      .tools{position:absolute;left:50%;bottom:calc(100% + 12px);transform:translateX(-50%);display:flex;align-items:center;gap:8px;
        opacity:0;visibility:hidden;pointer-events:none;white-space:nowrap;font:500 12px/1.45 -apple-system,BlinkMacSystemFont,"SF Pro Text","PingFang SC",sans-serif;
        background:linear-gradient(135deg,rgba(20,42,34,.95),rgba(14,30,24,.97));color:#f1f7f3;border:1px solid rgba(168,230,193,.22);
        border-radius:999px;padding:5px 10px 5px 12px;text-shadow:none;box-shadow:0 8px 22px rgba(0,0,0,.42);backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);transition:opacity .15s}
      .tools button{border:1px solid rgba(255,255,255,.16);background:rgba(255,255,255,.1);color:#fff;padding:2px 8px;border-radius:999px;font-family:inherit;font-size:11px;font-weight:500;line-height:1.35;cursor:pointer;transition:background .15s,border-color .15s}
      .tools button:hover{background:rgba(255,255,255,.22);border-color:rgba(255,255,255,.3)}
      .resize{position:absolute;width:13px;height:13px;padding:0;border:2px solid #163327;border-radius:50%;background:#7ce8b8;box-shadow:0 2px 6px rgba(0,0,0,.45);opacity:0;visibility:hidden;pointer-events:none;transition:opacity .15s,transform .15s,background .15s}
      .resize:hover{transform:scale(1.18);background:#aaf7d4}
      .nw{left:-8px;top:-8px;cursor:nwse-resize}.ne{right:-8px;top:-8px;cursor:nesw-resize}
      .sw{left:-8px;bottom:-8px;cursor:nesw-resize}.se{right:-8px;bottom:-8px;cursor:nwse-resize}
      #caption-box:hover,#caption-box:focus-within,#caption-box.resizing{outline-color:rgba(134,228,186,.65)}
      #caption-box:hover .tools,#caption-box:focus-within .tools,#caption-box.resizing .tools,#caption-box.notice .tools,
      #caption-box:hover .resize,#caption-box:focus-within .resize,#caption-box.resizing .resize{opacity:1;visibility:visible;pointer-events:auto}
      #caption-box.resizing{user-select:none}
    `;
    shell=document.createElement('div');shell.id='caption-box';shell.title='移到字幕上，拖动角点调整大小';
    source=document.createElement('div');source.className='line original';
    target=document.createElement('div');target.className='line translated';
    target.title=nativeCount?'视频原有人工中文字幕；未覆盖部分使用所选 AI 翻译':'所选 AI 翻译';
    const tools=document.createElement('div');tools.className='tools';
    label=document.createElement('span');
    const off=document.createElement('button');off.textContent='关闭翻译';off.onclick=e=>{e.stopPropagation();stop();};
    retryButton=document.createElement('button');retryButton.textContent='继续翻译';retryButton.hidden=true;
    retryButton.onclick=e=>{e.stopPropagation();suspended=false;retryButton.hidden=true;loadBatch(failedStart,run);};
    tools.append(label,retryButton,off);shell.append(source,target,tools);
    const corners={nw:'左上角',ne:'右上角',sw:'左下角',se:'右下角'};
    for(const [corner,name]of Object.entries(corners)){
      const handle=document.createElement('button');handle.className='resize '+corner;
      handle.setAttribute('aria-label','调整字幕大小（'+name+'）');handle.title='拖动调整字幕大小';
      let origin;
      handle.onpointerdown=e=>{
        if(e.button!==0)return;e.preventDefault();e.stopPropagation();
        const rect=shell.getBoundingClientRect();
        const video=document.querySelector('video');
        origin={x:e.clientX,y:e.clientY,scale:fontScale,length:Math.max(100,rect.width+rect.height),epoch:run,video,paused:video?.paused};
        suppressClick=event=>{event.preventDefault();event.stopImmediatePropagation();};
        document.addEventListener('click',suppressClick,true);
        finishDrag=finish;for(const type of ['pointerup','mouseup','pointercancel'])document.addEventListener(type,finish,true);
        dragging=true;shell.classList.add('resizing');handle.setPointerCapture(e.pointerId);
      };
      handle.onpointermove=e=>{
        if(!dragging||!origin)return;e.preventDefault();e.stopPropagation();
        const dx=(e.clientX-origin.x)*(corner.includes('e')?1:-1),dy=(e.clientY-origin.y)*(corner.includes('s')?1:-1);
        const nextScale=validScale(Math.round(origin.scale*(1+(dx+dy)/origin.length)/10)*10);
        if(nextScale!==fontScale){fontScale=nextScale;resizeOverlay();api('saveCaptionSize',{scale:fontScale}).catch(()=>{});}
        label.textContent='字幕大小 '+fontScale+'%';
      };
      const finish=e=>{
        if(!dragging||!origin)return;e.preventDefault();e.stopPropagation();
        for(const type of ['pointerup','mouseup','pointercancel'])document.removeEventListener(type,finish,true);finishDrag=null;
        dragging=false;shell?.classList.remove('resizing');
        if(Number.isFinite(e.pointerId)&&handle.hasPointerCapture(e.pointerId))handle.releasePointerCapture(e.pointerId);
        const finished=origin,clickBlock=suppressClick;
        if(origin.epoch===run)api('saveCaptionSize',{scale:fontScale}).catch(()=>{});origin=null;
        setTimeout(()=>{
          document.removeEventListener('click',clickBlock,true);if(suppressClick===clickBlock)suppressClick=null;
          if(finished.epoch!==run||!finished.video)return;
          if(finished.paused&&!finished.video.paused)finished.video.pause();
          else if(!finished.paused&&finished.video.paused)finished.video.play().catch(()=>{});
        },0);
      };
      handle.onpointerup=finish;handle.onpointercancel=finish;
      handle.onkeydown=e=>{
        if(!['ArrowUp','ArrowDown','ArrowLeft','ArrowRight'].includes(e.key))return;
        e.preventDefault();e.stopPropagation();fontScale=validScale(fontScale+(['ArrowUp','ArrowRight'].includes(e.key)?10:-10));resizeOverlay();
        api('saveCaptionSize',{scale:fontScale}).catch(()=>{});
      };
      handle.onclick=e=>{e.preventDefault();e.stopPropagation();};shell.append(handle);
    }
    for(const event of ['click','dblclick','mousedown','mouseup','pointerdown'])shell.addEventListener(event,e=>e.stopPropagation());
    shadow.append(style,shell);
    (document.querySelector('#movie_player')||document.querySelector('video').parentElement).append(overlay);
    playerResize=new ResizeObserver(scheduleOverlayResize);playerResize.observe(overlay.parentElement);
    document.addEventListener('fullscreenchange',scheduleOverlayResize);
    window.addEventListener('resize',scheduleOverlayResize);
    resizeOverlay();
  }
  function cueAt(time) {
    let lo=0,hi=cues.length;
    while(lo<hi){const mid=(lo+hi)>>1;if(cues[mid].start<=time)lo=mid+1;else hi=mid;}
    const i=lo-1;
    // Do not leave the final line on screen after its unknown end time.
    return i>=0 && time < (cues[i].end ?? (cues[i+1]?.start ?? cues[i].start+8)) ? i : -1;
  }
  // Keep both languages on the same complete cue. Independent character-based
  // paging cannot preserve meaning across languages (especially reordered clauses).
  function lineAt(value,cue,time,node) {
    const full=String(value||'').replace(/\s+/g,' ').trim();
    node.title=full;return full;
  }
  function manualAt(time){
    let lo=0,hi=nativeTimeline.length;
    while(lo<hi){const mid=(lo+hi)>>1;if(nativeTimeline[mid].start<=time)lo=mid+1;else hi=mid;}
    const cue=nativeTimeline[lo-1];return cue&&time<cue.end?cue:null;
  }
  function annotateCue(i,value) {
    if(!cues[i].el?.isConnected)return;
    if(cues[i].translationEl?.isConnected){cues[i].translationEl.textContent=value;return;}
    const node=document.createElement('div');node.className='cgpt-transcript-translation';node.textContent=value;node.lang='zh-CN';
    node.style.cssText='color:var(--yt-spec-text-primary,#e2eae5);opacity:.88;font:400 13.5px/1.65 -apple-system,BlinkMacSystemFont,"SF Pro Text","PingFang SC","Microsoft YaHei",sans-serif;letter-spacing:.01em;border-left:2px solid #4d8b70;margin:2px 12px 10px 10px;padding:3px 10px;background:rgba(77,139,112,.075);border-radius:0 6px 6px 0;white-space:pre-wrap;';
    cues[i].el.after(node);cues[i].translationEl=node;annotations.push(node);
  }
  function groupRollingCues(items) {
    // Prefer clause boundaries over arbitrary ASR line breaks. A punctuation break
    // inside one ASR cue is estimated within that cue's time span; both languages
    // always use the same resulting interval, never separate language pagination.
    const pieces=items.flatMap(cue=>{
      const parts=cue.text.match(/.*?[.!?;,](?:\s+|$)|.+$/gu)||[cue.text];
      let offset=0;
      return parts.map(part=>{
        const start=cue.start+(cue.end-cue.start)*offset/cue.text.length;
        offset+=part.length;
        return {...cue,text:part.trim(),start,end:cue.start+(cue.end-cue.start)*offset/cue.text.length,el:parts.length===1?cue.el:null};
      }).filter(c=>c.text);
    });
    const groups=[];
    for(const cue of pieces){
      const prev=groups.at(-1);
      if(prev&&cue.start<=prev.end+.4&&cue.end-prev.start<=10&&
          prev.text.length+cue.text.length+1<=180&&!/[.!?]["”']?$/.test(prev.text)&&
          !(prev.text.length>=45&&/[,;]$/.test(prev.text))&&!/^\s*>>/.test(cue.text)){
        prev.text+=' '+cue.text;prev.end=cue.end;prev.el=null;
      }else groups.push({...cue});
    }
    return groups;
  }
  function sourceLabel() {
    return nativeCount?(nativeCount===cues.length?'字幕来源：视频原有人工中文字幕':'字幕来源：人工中文字幕＋AI 补译'):'字幕来源：所选 AI';
  }
  function contextFor(indices) {
    const first=indices[0],last=indices.at(-1);
    const contextBefore=[];
    for(let i=Math.max(0,first-3);i<first;i++){
      const en=cues[i].text,zh=translated.get(i);
      // At most 600 characters per pair, 1800 for the side. Missing zh is omitted.
      contextBefore.push(zh?{en:en.slice(0,300),zh:zh.slice(0,300)}:{en:en.slice(0,600)});
    }
    const contextAfter=cues.slice(last+1,last+4).map(c=>c.text.slice(0,600));
    return {contextBefore,contextAfter,cueIds:indices};
  }
  async function loadBatch(start,epoch) {
    const token=++batchSerial;loading=true;
    const valid=()=>epoch===run&&token===batchSerial&&active;
    const video=document.querySelector('video');
    const rate=Math.max(.5,Math.min(3,video?.playbackRate||1));
    // Quick initial result, then larger time-based buffers to amortize context.
    const initial=!hasWindow;warmupNeeded=false;
    const horizon=(initial?9:Math.min(100,Math.max(65,latency*3+25)))*rate;
    const indices=[];let chars=0;
    for(let i=start;i<cues.length;i++){
      if(indices.length>=(initial?3:32)||(indices.length>=(initial?1:6)&&(cues[i].start-cues[start].start>=horizon||chars+cues[i].text.length>6500)))break;
      if(!translated.has(i)){indices.push(i);chars+=cues[i].text.length;}
    }
    pendingRange={first:start,last:indices.at(-1)??start};
    const began=performance.now();
    try{
      if(!indices.length)return;
      label.textContent=hasWindow?'正在准备后续字幕…':'正在翻译当前字幕…';
      await globalThis.__cgptBridge.run({title:document.title,model,provider,sessionId,kind:'captions',paragraphs:indices.map(i=>cues[i].text),...contextFor(indices)},{
        cancelled:()=>!valid(),id:id=>{if(valid())job=id;},notice:message=>{if(valid())label.textContent=message;},
        update:state=>{
          if(!valid())return;
          for(const [k,value]of Object.entries(state.results)){
            const i=indices[Number(k)];if(i===undefined||translated.get(i)===value)continue;
            translated.set(i,value);
            annotateCue(i,value);
          }
          label.textContent=`${sourceLabel()} · 已就绪 ${translated.size} / ${cues.length} 条`;
          tick();
        }
      });
      if(valid()){latency=Math.max(2,Math.min(45,latency*.5+(performance.now()-began)/2000));hasWindow=true;warmupNeeded=initial;}
    }catch(e){
      if(valid()){
        suspended=true;failedStart=start;label.textContent=e.message+' · 已有字幕保留';retryButton.hidden=false;
      }
    }finally{if(valid()){loading=false;pendingRange=null;job=null;}}
  }
  function tick() {
    if(!active)return;
    if(new URL(location.href).searchParams.get('v')!==currentVideo){stop();return;}
    const video=document.querySelector('video');if(!video)return;
    if(document.querySelector('.ad-showing')){source.textContent='';target.textContent='';shell.hidden=true;return;}
    const index=cueAt(video.currentTime);
    const cue=index>=0?cues[index]:null,manual=manualAt(video.currentTime);
    shell.hidden=!cue&&!manual&&!dragging;
    source.textContent=lineAt(cue?.text||'',cue,video.currentTime,source);
    const originalManualGap=nativeTimeline.length&&nativeIndices.has(index)&&!manual;
    const chinese=manual?.text||(originalManualGap?'':index>=0?(translated.get(index)||(suspended?'暂未翻译 · 移到字幕上可继续':'正在翻译…')):'');
    target.textContent=lineAt(chinese,manual||cue,video.currentTime,target);
    const next=index>=0?index:cues.findIndex(c=>c.start>video.currentTime);
    if(next<0)return;
    // A far seek must not wait for a stale buffer from a different part of the video.
    if(seekPending&&loading&&pendingRange&&!translated.has(next)&&(next<pendingRange.first-2||next>pendingRange.last+2)){
      if(job)api('cancel',null,job).catch(()=>{});
      batchSerial++;loading=false;pendingRange=null;job=null;
    }
    seekPending=false;
    if(loading||suspended)return;
    let missing=next;while(missing<cues.length&&translated.has(missing))missing++;
    if(missing>=cues.length)return;
    const ahead=cues[missing].start-video.currentTime;
    const lead=Math.max(35,Math.min(70,latency*2+12))*(video.playbackRate||1);
    if(!hasWindow||!translated.has(next)||warmupNeeded||(!video.paused&&ahead<lead))loadBatch(missing,run);
  }
  async function start(chosen,scale,chosenProvider,chosenSession) {
    stop();fontScale=validScale(scale);const epoch=run;model=chosen;provider=chosenProvider;sessionId=chosenSession||'';currentVideo=new URL(location.href).searchParams.get('v');
    if(!currentVideo||!document.querySelector('video'))throw new Error('请打开一个 YouTube 视频，再点击翻译。');
    // Prefer the same public English segmentation on every start. The website's
    // transcript may switch between sentence-sized and short rolling fragments.
    let transcriptError=null,canonical=null;
    try{canonical=await api('transcript',{videoId:currentVideo});}catch(e){transcriptError=e;}
    if(epoch!==run)return;
    if(canonical){
      const dom=new Map(readCues().map(c=>[c.start.toFixed(1)+'|'+c.text,c.el]));
      cues=canonical.cues.map(c=>({el:dom.get(c.start.toFixed(1)+'|'+c.text)||null,start:c.start,end:c.start+c.duration,text:c.text}));
    }else{
      cues=readCues();
      if(!cues.length){
        const expand=document.querySelector('#description-inline-expander #expand');
        if(expand){expand.click();await wait(500);}
        const button=[...document.querySelectorAll('button')].find(b=>b.getClientRects().length&&/^(show transcript|显示转录文稿|显示转写文稿|转写文稿|内容转文字|显示文字稿|顯示轉錄稿|显示字幕文本)$/i.test(text(b)));
        if(button){button.click();for(let n=0;n<40&&!cues.length;n++){if(epoch!==run)return;await wait(250);cues=readCues();}}
      }
      const sample=cues.slice(0,20).map(c=>c.text).join('');
      const english=cues.length&&(sample.match(/[a-z]/gi)||[]).length>(sample.match(/[\u3400-\u9fff]/g)||[]).length;
      if(!english){
        if(transcriptError?.retryable){
          const data=await globalThis.__cgptBridge.request('transcript',{videoId:currentVideo},null,{cancelled:()=>epoch!==run});
          if(epoch!==run)return;
          canonical=data;cues=data.cues.map(c=>({el:null,start:c.start,end:c.start+c.duration,text:c.text}));
        }else throw transcriptError||new Error('没有找到公开英文字幕，请尝试打开网页转录文稿。');
      }
    }
    // Rolling ASR cues overlap; advance the pair at the next source boundary.
    cues=cues.map((c,i)=>({...c,end:Math.min(c.end??Infinity,cues[i+1]?.start??c.end??c.start+8)}));
    if(canonical?.isGenerated&&!canonical.nativeChinese)cues=groupRollingCues(cues);
    const sample=cues.slice(0,20).map(c=>c.text).join('');
    if((sample.match(/[a-z]/gi)||[]).length<(sample.match(/[\u3400-\u9fff]/g)||[]).length)throw new Error('请将转录文稿语言切换为英文后重试。');
    // Manual Chinese is already a translation: reuse it without a model request.
    const native=canonical?.nativeChinese;
    if(native?.source==='manual'&&Array.isArray(native.translations)&&native.translations.length===cues.length){
      native.translations.forEach((value,i)=>{
        if(typeof value==='string'&&value.trim()&&/[\u3400-\u9fff]/.test(value)){
          translated.set(i,value);nativeIndices.add(i);nativeCount++;annotateCue(i,value);
        }
      });
    }
    if(native?.source==='manual'&&Array.isArray(native.cues))nativeTimeline=native.cues
      .filter(c=>typeof c.text==='string'&&Number.isFinite(c.start)&&Number.isFinite(c.duration)&&c.duration>0)
      .map(c=>({text:c.text,start:c.start,end:c.start+c.duration})).sort((a,b)=>a.start-b.start);
    hasWindow=nativeCount>0;
    active=true;makeOverlay();label.textContent=sourceLabel()+' · 已就绪 '+translated.size+' / '+cues.length+' 条';seekVideo=document.querySelector('video');seekHandler=()=>{seekPending=true;tick();};
    seekVideo.addEventListener('seeking',seekHandler);timer=setInterval(tick,100);tick();
  }
  chrome.runtime.onMessage.addListener((m,s,reply)=>{
    if(s.id!==chrome.runtime.id)return;
    if(m.action==='restore'){stop();reply({ok:true});}
    if(m.action==='captionSettings'){fontScale=validScale(m.scale);resizeOverlay();if(label)label.textContent='字幕大小 '+fontScale+'%';reply({ok:true});}
    if(m.action==='translate'){start(m.model,m.captionScale,m.provider,m.sessionId).then(()=>reply({ok:true})).catch(e=>reply({ok:false,error:e.message}));return true;}
  });
  addEventListener('pagehide',stop);
})();
