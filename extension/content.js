(() => {
  if (globalThis.__newsBridge) return;
  globalThis.__newsBridge = true;
  let generation = 0, job = null, inserted = [], panel = null, lastURL = location.href;
  let pageObserver=null,pageCheckTimer=null,homeObserver=null,homeTimer=null,homeSaveTimer=null;
  let homeRecords=new Map(),homeMeta=null,homeRestoring=false;
  const homeMessage=(action,payload)=>(chrome.runtime.sendMessage?.({action,payload})||Promise.resolve(null));
  function saveHome(){
    if(!homeMeta||!wsjHome())return;
    clearTimeout(homeSaveTimer);
    homeSaveTimer=setTimeout(()=>{homeMessage('homeSnapshotSave',{...homeMeta,records:[...homeRecords.values()]}).catch(()=>{});},100);
  }
  async function restoreHome(){
    if(!wsjHome()||homeRestoring||homeMeta)return;
    homeRestoring=true;const epoch=generation,url=location.href;
    try{
      const reply=await homeMessage('homeSnapshotRead');const saved=reply?.data;
      if(!saved||epoch!==generation||url!==location.href||homeMeta)return;
      homeMeta=saved;homeRecords=new Map(saved.records.map(r=>[r.group+'\u0000'+r.text,r]));
      function mount(){
        homeTimer=null;if(epoch!==generation||!wsjHome())return;
        const entries=collect();let count=0;
        for(const entry of entries){
          const record=homeRecords.get(entry.group+'\u0000'+entry.text);
          if(!record)continue;
          const after=entry.insertAfter||entry.el;
          if(!after.nextElementSibling?.classList.contains('nb-translation'))mountTranslation(entry,record.value);
          count++;
        }
        if(count)status(`已恢复 ${count} 段译文 · 本次不消耗 Token`+(entries.length>count?' · 有新内容待译':''),false,
          entries.length>count?()=>begin(saved.model,saved.provider,saved.sessionId):null);
      }
      homeObserver=new MutationObserver(()=>{if(!homeTimer)homeTimer=setTimeout(mount,350);});
      homeObserver.observe(document.body,{childList:true,subtree:true,characterData:true});mount();
    }catch{}finally{homeRestoring=false;}
  }
  const excluded = 'nav,footer,aside,form,button,textarea,input,select,pre,code,[role="navigation"],[role="dialog"],[aria-hidden="true"],[contenteditable="true"],.nb-translation';
  const textOf = el => (el.innerText || '').replace(/\s+/g, ' ').trim();
  const visible = el => {
    const s = getComputedStyle(el);
    return s.display !== 'none' && s.visibility !== 'hidden' && el.getClientRects().length > 0;
  };
  const wsjHome = () => /(^|\.)wsj\.com$/.test(location.hostname) && /^\/(?:news\/?)?$/.test(location.pathname);
  const feedExcluded = 'nav,footer,form,button,[role="navigation"],[role="dialog"],[contenteditable="true"],.nb-translation,time,[class*="Byline"],[class*="byline"],[data-testid="Byline"],[data-testid="AuthorName"],[data-testid="Author"],[data-testid="Timestamp"],[data-testid="advertisement"],[class*="newsletter"]';
  const articleSelectors = () => /(^|\.)reuters\.com$/.test(location.hostname)
    ? '[data-testid="ArticleBody"],[data-testid="article-body"],[class*="article-body__content"]'
    : /(^|\.)wsj\.com$/.test(location.hostname) ? '.article-content,.articleBody,[data-type="article-body"],[class*="articleBody"]' : '';
  function storyURL(anchor, loose = false) {
    if (!anchor?.getAttribute('href')) return '';
    try {
      const url = new URL(anchor.getAttribute('href'), location.href);
      if (!/^https?:$/.test(url.protocol) || url.hostname.replace(/^www\./,'') !== location.hostname.replace(/^www\./,'')) return '';
      if (url.pathname === '/' || url.pathname === location.pathname) return '';
      if (/(^|\.)reuters\.com$/.test(location.hostname) && !loose && !(/-\d{4}-\d{2}-\d{2}\/?$/.test(url.pathname) || /\/(article|graphics)\//.test(url.pathname))) return '';
      url.search = ''; url.hash = '';
      return url.href.slice(0, 1000);
    } catch { return ''; }
  }
  function storyGroup(el, root, loose = false) {
    const direct = storyURL(el.closest('a[href]'), loose);
    if (direct) return 'story:' + direct;
    // Stop before the first ancestor spanning multiple stories. A summary with
    // no unambiguous card never inherits whichever headline happens to precede it.
    for (let node = el; node && node !== root; node = node.parentElement) {
      const urls = [...new Set([...node.querySelectorAll('a[href]')].map(a => storyURL(a,loose)).filter(Boolean))];
      if (urls.length === 1) return 'story:' + urls[0];
      if (urls.length > 1) break;
    }
    return '';
  }
  function textFingerprint(text) {
    let hash=2166136261;
    for (const character of text) hash=Math.imul(hash^character.charCodeAt(0),16777619);
    return (hash>>>0).toString(36);
  }
  function readableFeedEntry({el,text}) {
    return visible(el) && !el.closest(feedExcluded) && text.length >= 6 && text.length < 12000 &&
      (text.match(/[a-zA-Z]/g)||[]).length > (text.match(/[\u3400-\u9fff]/g)||[]).length*2;
  }
  function collectFeed(root, wsj = false) {
    let elements;
    if (wsj) elements = [...root.querySelectorAll('[data-testid="flexcard-headline"],[data-testid="flexcard-text"]')].map(node => {
      const headline=node.matches('[data-testid="flexcard-headline"]');
      const el=headline?(node.closest('h1,h2,h3')||node):node;
      return {el, text:textOf(el), insertAfter:headline?el:(el.closest('a')||el)};
    });
    else {
      const headlines = [...root.querySelectorAll('h1 a[href],h2 a[href],h3 a[href],h4 a[href],a[data-testid="Heading"],a[data-testid="Title"],[data-testid="Heading"] a[href],[data-testid="Title"] a[href]')]
        .filter(a => storyURL(a)).map(a => a.closest('h1,h2,h3,h4') || a);
      // Descriptions vary by layout, but only text inside a single-story card
      // qualifies. Section introductions and unrelated paragraphs are excluded.
      const summaries = [...root.querySelectorAll('p,[data-testid="Description"],[data-testid="description"],[data-testid="CardDescription"]')]
        .filter(el => !el.querySelector('p') && storyGroup(el,root));
      elements = [...new Set([...headlines,...summaries])].sort((a,b) => a === b ? 0 : a.compareDocumentPosition(b)&Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1)
        .map(el => ({el,text:textOf(el),insertAfter:el.closest('a')||el}));
    }
    return elements.filter(readableFeedEntry).map((entry,index) => ({...entry,
      group:storyGroup(entry.el,root,wsj) || 'unlinked-card:' + index + ':' + textFingerprint(entry.text)}));
  }
  function collect() {
    const site = location.hostname;
    const selector = articleSelectors();
    const specific = selector ? [...document.querySelectorAll(selector)].filter(visible) : [];
    const articles = [...document.querySelectorAll('article,[itemprop="articleBody"]')].filter(visible);
    const main = document.querySelector('main,[role="main"]') || document.body;
    const hasArticleMetadata = document.querySelector('meta[property="og:type"][content="article"],[itemprop="articleBody"],[itemtype$="/NewsArticle"],[itemtype$="/Article"]');
    const reutersDatedArticle = /(^|\.)reuters\.com$/.test(site) && /-\d{4}-\d{2}-\d{2}\/?$/.test(location.pathname);
    const singleArticle = articles.length === 1 && (articles[0].querySelector('h1') || [...articles[0].querySelectorAll('p')].filter(p => textOf(p).length >= 15).length >= 2);
    const storyLinks = [...new Set([...main.querySelectorAll('h1 a[href],h2 a[href],h3 a[href],h4 a[href],a[data-testid="Heading"],a[data-testid="Title"]')].map(a => storyURL(a)).filter(Boolean))];
    if (wsjHome()) return collectFeed(main,true);
    if (!specific.length && !hasArticleMetadata && !reutersDatedArticle && !singleArticle && storyLinks.length >= 2) return collectFeed(main);
    const roots = specific.length ? specific : articles.length ? articles : [...document.querySelectorAll('main,[role="main"]')].filter(visible);
    const score = el => [...el.querySelectorAll('p')].filter(p => !p.closest(excluded)).reduce((n,p) => n + textOf(p).length, 0);
    const root = roots.sort((a,b) => score(b)-score(a))[0] || document.body;
    let elements = [...root.querySelectorAll('h1,h2,h3,p,blockquote,li,[data-testid^="paragraph-"]')];
    const headings = [document.querySelector('h1')];
    if (/(^|\.)wsj\.com$/.test(site)) headings.push(document.querySelector('h2'));
    for (const heading of headings.reverse()) if (heading && !root.contains(heading)) elements.unshift(heading);
    elements = [...new Set(elements)].filter(el => !el.querySelector('p,li,blockquote,[data-testid^="paragraph-"]') && !el.closest(excluded+',time,[class*="Byline"],[class*="byline"],[data-testid="RelatedContent"],[class*="related-content"],[class*="newsletter"],.paywall-prompt,[data-testid="paywall-message"],[data-testid="advertisement"]') && visible(el));
    return elements.map(el => ({el,text:textOf(el),group:'article'})).filter(({el,text}) => {
      if (text.length < (/^H[123]$/.test(el.tagName) ? 6 : 15) || text.length > 12000) return false;
      const latin = (text.match(/[a-zA-Z]/g) || []).length;
      const han = (text.match(/[\u3400-\u9fff]/g) || []).length;
      const links = [...el.querySelectorAll('a')].reduce((n,a)=>n+textOf(a).length,0);
      return latin >= 5 && latin > han * 2 && links / text.length < .75;
    });
  }
  const api=(...args)=>globalThis.__cgptBridge.raw(...args);
  function status(message, isError = false, retry = null) {
    if (!panel) {
      panel = document.createElement('div');
      panel.id = 'cgpt-news-status';
      panel.className='cgpt-news-status';panel.dataset.cgptNewsStatus='1';
      panel.style.cssText = 'all:initial;position:fixed;right:22px;bottom:22px;z-index:2147483647;';
      const shadow = panel.attachShadow({mode:'closed'});
      const style = document.createElement('style');
      style.textContent = `
        @keyframes nbPillIn{from{opacity:0;transform:translateY(8px) scale(.98)}to{opacity:1;transform:translateY(0) scale(1)}}
        .box{display:flex;align-items:center;gap:8px;font:500 12.5px/1.45 -apple-system,BlinkMacSystemFont,"SF Pro Text","PingFang SC","Microsoft YaHei",sans-serif;background:linear-gradient(135deg,rgba(20,42,34,.95),rgba(14,30,24,.97));color:#f2f7f4;padding:8px 10px 8px 13px;border-radius:999px;border:1px solid rgba(168,230,193,.2);box-shadow:0 10px 28px -4px rgba(8,22,16,.38),0 2px 6px rgba(0,0,0,.18);backdrop-filter:blur(14px) saturate(140%);-webkit-backdrop-filter:blur(14px) saturate(140%);max-width:min(380px,calc(100vw - 44px));animation:nbPillIn .2s cubic-bezier(.16,1,.3,1)}
        .dot{width:7px;height:7px;border-radius:50%;background:#5be3a6;box-shadow:0 0 8px rgba(91,227,166,.7);flex:none}
        .dot.err{background:#ffb46b;box-shadow:0 0 8px rgba(255,180,107,.7)}
        #label{letter-spacing:.01em;overflow-wrap:anywhere}
        button{margin-left:2px;border:1px solid rgba(255,255,255,.15);background:rgba(255,255,255,.1);color:#f4faf6;border-radius:999px;padding:4px 10px;cursor:pointer;font-family:inherit;font-size:11.5px;font-weight:500;line-height:1.3;white-space:nowrap;transition:background .15s,border-color .15s,transform .1s}
        button:hover{background:rgba(255,255,255,.2);border-color:rgba(255,255,255,.28)}
        button:active{transform:scale(.97)}
      `;
      const box = document.createElement('div');
      box.className = 'box';
      box.setAttribute('role','status');box.setAttribute('aria-live','polite');
      const dot = document.createElement('i'); dot.className = 'dot'; dot.setAttribute('aria-hidden','true');
      const label = document.createElement('span'); label.id = 'label';
      const close = document.createElement('button'); close.textContent = '恢复原文';
      close.onclick = ()=>restore();
      const again = document.createElement('button'); again.textContent = '继续翻译'; again.hidden = true;
      box.append(dot,label,again,close); shadow.append(style,box);
      panel.label = label; panel.retry = again; panel.dot = dot;
      document.documentElement.append(panel);
    }
    panel.retry.hidden=!retry;panel.retry.onclick=()=>{panel.retry.hidden=true;retry?.();};
    panel.label.textContent = message;
    panel.label.style.color = isError ? '#ffd2a0' : '#f2f7f4';
    panel.dot?.classList.toggle('err', !!isError);
  }
  function restore(forget=true) {
    if(forget&&wsjHome())homeMessage('homeSnapshotRemove').catch(()=>{});
    homeMeta=null;homeRecords.clear();homeObserver?.disconnect();homeObserver=null;
    clearTimeout(homeTimer);clearTimeout(homeSaveTimer);
    generation++;
    pageObserver?.disconnect();pageObserver=null;
    clearTimeout(pageCheckTimer);pageCheckTimer=null;
    if (job) api('cancel',null,job).catch(()=>{});
    job = null;
    for (const node of inserted) node.remove();
    // Reloading an extension destroys script state but can leave its DOM behind.
    document.querySelectorAll('.nb-translation[lang="zh-CN"][translate="no"]').forEach(node=>node.remove());
    document.querySelectorAll('#cgpt-news-status,.cgpt-news-status,[data-cgpt-news-status="1"]').forEach(n=>n.remove());
    // Older injected panels can have their id rewritten by the page. Migrate
    // only that revision's exact top-level inline positioning signature.
    for(const n of [...document.documentElement.children]){
      if(n.tagName==='DIV'&&n.attributes.length===2&&n.hasAttribute('id')&&n.hasAttribute('style')&&
         n.style.position==='fixed'&&n.style.right==='22px'&&n.style.bottom==='22px'&&n.style.zIndex==='2147483647')n.remove();
    }
    inserted = [];
    panel?.remove(); panel = null;
  }
  function watchForNewContent(entries,run,model,provider,sessionId){
    pageObserver?.disconnect();clearTimeout(pageCheckTimer);pageCheckTimer=null;
    // Count rather than deduplicate, so identical text in two cards stays distinct.
    const signature=e=>e.group+'\u0000'+e.text;
    const known=new Map();for(const e of entries){const k=signature(e);known.set(k,(known.get(k)||0)+1);}
    let nextCheck=0;
    function check(){
      pageCheckTimer=null;
      if(run!==generation)return;
      nextCheck=Date.now()+5000;
      const available=new Map(known);let added=0;
      for(const e of collect()){
        const key=signature(e),count=available.get(key)||0;
        if(count)available.set(key,count-1);else added++;
      }
      if(added){
        pageObserver?.disconnect();pageObserver=null;
        status(`网页新增 ${added} 段 · 继续翻译可能增加用量`,false,()=>begin(model,provider,sessionId));
      }
    }
    const schedule=()=>{if(!pageCheckTimer)pageCheckTimer=setTimeout(check,Math.max(1200,nextCheck-Date.now()));};
    pageObserver=new MutationObserver(schedule);
    pageObserver.observe(document.body,{childList:true,subtree:true,characterData:true});
    // Content may already have arrived while the model was processing the page.
    schedule();
  }
  function mountTranslation(entry,translated){
    const node = document.createElement('div');
    node.className = 'nb-translation'; node.lang = 'zh-CN'; node.translate = false;
    const cs = getComputedStyle(entry.el);
    node.style.color = cs.color;
    // Shadow DOM prevents page typography and translation markup from colliding.
    const root = node.attachShadow({mode:'closed'});
    const isHeading = /^H[1-3]$/.test(entry.el.tagName);
    const isSerif = /(georgia|times|serif|exchange|escrow|chronicle|tiempos|mercury|miller|garamond|caslon|palatino|baskerville)/i.test(cs.fontFamily||'') && !/sans-serif/i.test(cs.fontFamily||'');
    const family = isHeading && isSerif
      ? '"Songti SC","STSong","Noto Serif SC",-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",serif'
      : '-apple-system,BlinkMacSystemFont,"SF Pro Text","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif';
    const p = document.createElement('div');
    p.textContent = translated;
    p.style.cssText = `font:400 .95em/1.78 ${family};letter-spacing:.015em;color:inherit;color:color-mix(in srgb,currentColor 85%,#1e5a44);border-left:2.5px solid #4d8b70;border-radius:0 6px 6px 0;background:linear-gradient(90deg,rgba(45,114,86,.05) 0%,rgba(45,114,86,.012) 65%,transparent 100%);padding:4px 10px 4px 13px;margin:6px 0 18px;white-space:pre-wrap;overflow-wrap:anywhere;`;
    if(isHeading){
      const size=parseFloat(cs.fontSize);
      if(Number.isFinite(size))p.style.fontSize=Math.min(Math.round(size*.88),28)+'px';
      p.style.fontWeight='580';p.style.lineHeight='1.42';p.style.letterSpacing='-.005em';
      p.style.borderLeftWidth='3px';p.style.borderLeftColor='#2e6f54';p.style.margin='8px 0 16px';
    }
    root.append(p); (entry.insertAfter||entry.el).after(node); inserted.push(node);
    return node;
  }
  async function translate(model, entries, run,provider,sessionId) {
    try {
      const done = new Set(entries.map((e,i)=>(e.insertAfter||e.el).nextElementSibling?.classList.contains('nb-translation')?String(i):null).filter(x=>x!==null));
      const priority=entries.flatMap((e,i)=>{const r=e.el.getBoundingClientRect();return r.bottom>0&&r.top<innerHeight?[i]:[];});
      await globalThis.__cgptBridge.run({model,provider,sessionId:sessionId||'',kind:'news',newsMode:entries.every(e=>e.group==='article')?'article':'feed',priority,groups:entries.map(e=>e.group),title:document.title,paragraphs:entries.map(e=>e.text)},{
        cancelled:()=>run!==generation,id:id=>{job=id;},notice:message=>{if(run===generation)status(message);},
        update:state=>{
        if(run!==generation)return;
        for (const [index, translated] of Object.entries(state.results)) {
          if (done.has(index)) continue;
          let entry = entries[Number(index)];
          if (!entry) continue;
          if (!entry.el.isConnected || textOf(entry.el) !== entry.text) {
            const fresh=collect().find(e=>e.group===entry.group&&e.text===entry.text&&!((e.insertAfter||e.el).nextElementSibling?.classList.contains('nb-translation')));
            if(!fresh)continue;
            entry=entries[Number(index)]=fresh;
          }
          const node=mountTranslation(entry,translated);
          if(wsjHome()){homeRecords.set(entry.group+'\u0000'+entry.text,{group:entry.group,text:entry.text,value:translated});saveHome();}
          if(node.isConnected)done.add(index);
        }
        status(`新闻双语 · ${done.size}/${entries.length}`);

        if (['done','cancelled'].includes(state.status)) {
          job = null;
          if(done.size===entries.length){status(`双语已就绪 · ${done.size} 段`);watchForNewContent(entries,run,model,provider,sessionId);}
          else status(`仅显示 ${done.size}/${entries.length} 段 · 网页内容已变化，请重新翻译`,true);
        }
      }});
      job=null;
    } catch(e) { if (run === generation){job=null;status(e.message+' · 已完成译文已保留',true,()=>translate(model,entries,run,provider,sessionId));} }
  }
  async function begin(model,provider,sessionId) {
    restore(false);lastURL=location.href;
    if(wsjHome())homeMeta={model,provider,sessionId};
    const run=generation,started=Date.now();
    const wsj=/(^|\.)wsj\.com$/.test(location.hostname)&&!wsjHome();
    let entries=[],previous='',stable=0;
    status('正在读取正文…');
    // A shortcut can arrive while an article is still hydrating after navigation.
    while(Date.now()-started<8000){
      if(run!==generation)return {ok:true};
      entries=collect();
      const signature=entries.map(e=>e.text).join('\n');
      stable=signature===previous?stable+1:0;previous=signature;
      const articleReady=!wsj||document.querySelector('article .paywall p,.article-content p,.articleBody p,[data-type="article-body"] p');
      if(entries.length&&articleReady&&stable>=3&&(!wsj||Date.now()-started>=1800))break;
      await new Promise(resolve=>setTimeout(resolve,300));
    }
    if(run!==generation)return {ok:true};
    if(!entries.length){status('没有找到英文正文，请打开一篇新闻文章再试。',true);return {ok:false,error:'没有找到英文正文，请打开一篇新闻文章再试。'};}
    if(entries.reduce((n,e)=>n+e.text.length,0)>180000||entries.length>500){status('本篇正文过长，请使用较短的文章。',true);return {ok:false,error:'本篇正文过长，请使用较短的文章。'};}
    status(`准备翻译 · ${entries.length} 段`);
    translate(model,entries,run,provider,sessionId);return {ok:true};
  }
  chrome.runtime.onMessage.addListener((m,s,respond) => {
    if (s.id !== chrome.runtime.id) return;
    if (/(^|\.)youtube\.com$/.test(location.hostname)) return;
    if(m.action==='restoreHome'){restoreHome();respond({ok:true});}
    if (m.action === 'restore') { restore(); respond({ok:true}); }
    if (m.action === 'translate') {
      begin(m.model,m.provider,m.sessionId).then(respond).catch(()=>respond({ok:false,error:'无法读取正文，请稍后重试。'}));return true;
    }
  });
  // Stop an old article's translation after client-side navigation.
  setInterval(()=>{if(location.href!==lastURL){restore(false);lastURL=location.href;restoreHome();}},500);
  addEventListener('pagehide',()=>restore(false));
  addEventListener('pageshow',()=>restoreHome());
  restoreHome();
})();
