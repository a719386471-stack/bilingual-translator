(() => {
  if (globalThis.__cgptYT || !/(^|\.)youtube\.com$/.test(location.hostname)) return;
  globalThis.__cgptYT = true;
  let run = 0, active = false, job = null, timer = null, overlay, label, source, target, shell;
  let dragging=false,suppressClick=null,finishDrag=null,retryButton;
  let batchSerial=0,pendingRange=null,latency=6,hasWindow=false,suspended=false,failedStart=0;
  let playerResize = null, resizeFrame = null;
  let fontScale=100, nativeCount=0;
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
    playerResize?.disconnect();playerResize=null;
    document.removeEventListener('fullscreenchange',scheduleOverlayResize);
    window.removeEventListener('resize',scheduleOverlayResize);
    if(resizeFrame!==null)cancelAnimationFrame(resizeFrame);resizeFrame=null;
    if(job) api('cancel',null,job).catch(()=>{});
    job=null;overlay?.remove();overlay=null;
    document.querySelectorAll('#cgpt-youtube-subtitles,.cgpt-transcript-translation').forEach(node=>node.remove());
    annotations.forEach(n=>n.remove());annotations=[];
    cues=[];translated.clear();nativeCount=0;
  }
  function resizeOverlay() {
    resizeFrame=null;
    const player=overlay?.parentElement;
    if(!player)return;
    // Use the actual player, including theater/fullscreen transitions, not viewport vw.
    const {width,height}=player.getBoundingClientRect();
    if(!width||!height)return;
    const size=Math.max(16,Math.min(72,width*.029,height*.062))*fontScale/100;
    overlay.style.setProperty('--cgpt-caption-size',size+'px');
    overlay.style.bottom=Math.max(48,Math.min(120,height*.085))+'px';
  }
  function scheduleOverlayResize() {
    if(resizeFrame===null)resizeFrame=requestAnimationFrame(resizeOverlay);
  }
  function makeOverlay() {
    overlay=document.createElement('div');overlay.id='cgpt-youtube-subtitles';
    overlay.dataset.resizeProtocol='pointer-v2';overlay.dataset.bufferProtocol='adaptive-v1';
    overlay.dataset.captionSource=nativeCount?(nativeCount===cues.length?'manual-chinese':'manual-chinese-and-ai'):'ai';
    overlay.style.cssText='position:absolute;left:8%;right:8%;bottom:70px;z-index:65;text-align:center;pointer-events:none;';
    const shadow=overlay.attachShadow({mode:'closed'});
    const style=document.createElement('style');style.textContent=`
      #caption-box{position:relative;display:inline-block;box-sizing:border-box;max-width:100%;color:white;pointer-events:auto;
        font:500 var(--cgpt-caption-size,24px)/1.35 -apple-system,"PingFang SC",sans-serif;white-space:pre-wrap;overflow-wrap:anywhere;
        text-shadow:0 1px 3px #000,1px 0 2px #000,-1px 0 2px #000;outline:1px solid transparent;outline-offset:5px;border-radius:3px}
      #caption-box[hidden]{display:none}.line{display:table;box-sizing:border-box;max-width:100%;margin:0 auto;background:#0006;padding:.04em .22em;border-radius:.1em}
      .line:empty{display:none}.original{font-size:.8em;opacity:.94}.translated{margin-top:.1em}
      .tools{position:absolute;left:50%;bottom:calc(100% + 12px);transform:translateX(-50%);display:flex;align-items:center;gap:9px;
        opacity:0;visibility:hidden;pointer-events:none;white-space:nowrap;font:12px/1.5 -apple-system,sans-serif;background:#203b31fa;color:#f1f6f2;
        border-radius:8px;padding:6px 9px;text-shadow:none;box-shadow:0 4px 14px #0004;transition:opacity .12s}
      .tools button{border:0;background:transparent;color:inherit;padding:1px 3px;font:inherit;cursor:pointer}
      .resize{position:absolute;width:14px;height:14px;padding:0;border:0;border-radius:2px;background:#d5fff0;opacity:0;visibility:hidden;pointer-events:none}
      .nw{left:-10px;top:-10px;cursor:nwse-resize}.ne{right:-10px;top:-10px;cursor:nesw-resize}
      .sw{left:-10px;bottom:-10px;cursor:nesw-resize}.se{right:-10px;bottom:-10px;cursor:nwse-resize}
      #caption-box:hover,#caption-box:focus-within,#caption-box.resizing{outline-color:#b3e6d4aa}
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
  function annotateCue(i,value) {
    if(!cues[i].el?.isConnected)return;
    const node=document.createElement('div');node.className='cgpt-transcript-translation';node.textContent=value;node.lang='zh-CN';
    node.style.cssText='color:var(--yt-spec-text-secondary,#aaa);font:14px/1.6 sans-serif;padding:4px 12px 9px;white-space:pre-wrap;';
    cues[i].el.after(node);annotations.push(node);
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
    const horizon=(hasWindow?Math.min(100,Math.max(55,latency*3+20)):18)*rate;
    const indices=[];let chars=0;
    for(let i=start;i<cues.length;i++){
      if(indices.length>=32||(indices.length>=6&&(cues[i].start-cues[start].start>=horizon||chars+cues[i].text.length>6500)))break;
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
            const i=indices[Number(k)];if(i===undefined||translated.has(i))continue;
            translated.set(i,value);
            annotateCue(i,value);
          }
          label.textContent=`${sourceLabel()} · 已就绪 ${translated.size} / ${cues.length} 条`;
        }
      });
      if(valid()){latency=Math.max(2,Math.min(45,latency*.5+(performance.now()-began)/2000));hasWindow=true;}
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
    shell.hidden=index<0&&!dragging;
    source.textContent=index>=0?cues[index].text:'';
    target.textContent=index>=0?(translated.get(index)||(suspended?'暂未翻译 · 移到字幕上可继续':'正在翻译…')):'';
    const next=index>=0?index:cues.findIndex(c=>c.start>video.currentTime);
    if(next<0)return;
    // A far seek must not wait for a stale buffer from a different part of the video.
    if(loading&&pendingRange&&!translated.has(next)&&(next<pendingRange.first-2||next>pendingRange.last+2)){
      if(job)api('cancel',null,job).catch(()=>{});
      batchSerial++;loading=false;pendingRange=null;job=null;
    }
    if(loading||suspended)return;
    let missing=next;while(missing<cues.length&&translated.has(missing))missing++;
    if(missing>=cues.length)return;
    const ahead=cues[missing].start-video.currentTime;
    const lead=Math.max(18,Math.min(55,latency*1.5+8))*(video.playbackRate||1);
    if(!hasWindow||!translated.has(next)||(!video.paused&&ahead<lead))loadBatch(missing,run);
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
    const sample=cues.slice(0,20).map(c=>c.text).join('');
    if((sample.match(/[a-z]/gi)||[]).length<(sample.match(/[\u3400-\u9fff]/g)||[]).length)throw new Error('请将转录文稿语言切换为英文后重试。');
    // Manual Chinese is already a translation: reuse it without a model request.
    const native=canonical?.nativeChinese;
    if(native?.source==='manual'&&Array.isArray(native.translations)&&native.translations.length===cues.length){
      native.translations.forEach((value,i)=>{
        if(typeof value==='string'&&value.trim()&&/[\u3400-\u9fff]/.test(value)){
          translated.set(i,value);nativeCount++;annotateCue(i,value);
        }
      });
    }
    hasWindow=nativeCount>0;
    active=true;makeOverlay();label.textContent=sourceLabel()+' · 已就绪 '+translated.size+' / '+cues.length+' 条';timer=setInterval(tick,350);tick();
  }
  chrome.runtime.onMessage.addListener((m,s,reply)=>{
    if(s.id!==chrome.runtime.id)return;
    if(m.action==='restore'){stop();reply({ok:true});}
    if(m.action==='captionSettings'){fontScale=validScale(m.scale);resizeOverlay();if(label)label.textContent='字幕大小 '+fontScale+'%';reply({ok:true});}
    if(m.action==='translate'){start(m.model,m.captionScale,m.provider,m.sessionId).then(()=>reply({ok:true})).catch(e=>reply({ok:false,error:e.message}));return true;}
  });
  addEventListener('pagehide',stop);
})();
