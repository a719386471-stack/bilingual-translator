importScripts('home-snapshots.js');
const BASE = 'http://127.0.0.1:19487';
chrome.storage.local.setAccessLevel({accessLevel: 'TRUSTED_CONTEXTS'});
const startingTabs = new Set();
let recoveryStart=null,lastRecovery=0;
let lastAlertCheck=0,alertCheck=null;
function failure(message,code='connection',retryable=true){return Object.assign(new Error(message),{code,retryable});}
const captionScale = value => Math.max(50,Math.min(200,Number(value)||100));
async function connectLocal(){
  const data=await service('connect');
  if(!data?.pairingKey)throw failure('请先运行“安装与修复”，再点击重新连接。','setup',false);
  await chrome.storage.local.set({pairingKey:data.pairingKey});
  return {paired:true,running:data.running,version:data.version};
}
async function activeTab() {
  const [tab]=await chrome.tabs.query({active:true,currentWindow:true});
  return tab;
}
async function pageKey(raw) {
  try {
    const u=new URL(raw);
    if(!/^https?:$/.test(u.protocol))return '';
    const page=/(^|\.)youtube\.com$/.test(u.hostname)
      ? 'https://www.youtube.com/watch?v='+(u.searchParams.get('v')||'')
      : u.origin+u.pathname;
    const hash=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(page));
    return [...new Uint8Array(hash)].map(n=>n.toString(16).padStart(2,'0')).join('');
  } catch {return '';}
}
async function helper(action,payload,id,pageUrl,tabId) {
  let hasSession=false;
  if(['start','poll','transcript'].includes(action)){
    const {serviceWanted}=await chrome.storage.local.get('serviceWanted');
    if(serviceWanted===false)throw failure('翻译服务已关闭，打开面板开关后可以继续。','service_off',false);
  }
  const paths={status:['GET','/api/status'],models:['GET','/api/models'],
    start:['POST','/api/jobs'],clearCache:['POST','/api/cache/clear'],transcript:['POST','/api/youtube/transcript'],
    usage:['GET','/api/usage'],provider:['POST','/api/provider'],quota:['GET','/api/quota']};
  let route=paths[action];
  if(['poll','cancel'].includes(action)&&/^[a-f0-9]{32}$/.test(id))route=[action==='poll'?'GET':'DELETE','/api/jobs/'+id];
  if(!route)throw failure('不支持的操作。','invalid',false);
  if(action==='usage'){
    const key=await pageKey(pageUrl),storageKey='translation-session:'+tabId;
    const info=tabId?(await chrome.storage.session.get(storageKey))[storageKey]:null;
    const session=info?.pageKey===key?info.id:'';
    hasSession=!!session;
    route=[route[0],route[1]+'?page='+key+'&session='+(session||'')];
  }
  let {pairingKey}=await chrome.storage.local.get('pairingKey');
  if(!pairingKey){await connectLocal();({pairingKey}=await chrome.storage.local.get('pairingKey'));}
  if(!pairingKey)throw failure('请先在插件中填写本地助手的连接码。','auth',false);
  if(action==='start')payload={...payload,pageKey:await pageKey(pageUrl)};
  let response;
  try {
    response=await fetch(BASE+route[1],{method:route[0],headers:{'Content-Type':'application/json','Authorization':'Bearer '+pairingKey},
      body:route[0]==='POST'?JSON.stringify(payload||{}):undefined,
      signal:AbortSignal.timeout(['models','quota'].includes(action)?90000:action==='transcript'?25000:15000),cache:'no-store'});
  } catch(e) {
    // Only active translation work may recover a crashed helper. An explicit off
    // switch prevents other tabs from starting it again in their retry loop.
    if(['start','poll','transcript'].includes(action)){
      const {serviceWanted}=await chrome.storage.local.get('serviceWanted');
      if(serviceWanted===false)throw failure('翻译服务已关闭，打开面板开关后可以继续。','service_off',false);
      if(serviceWanted&&Date.now()-lastRecovery>5000){
        if(!recoveryStart){lastRecovery=Date.now();recoveryStart=service('start').finally(()=>{recoveryStart=null;});}
        await recoveryStart.catch(()=>{});
      }
    }
    throw failure('连接暂时中断，正在重新连接本机翻译服务。');
  }
  let data;
  try{data=await response.json();}catch{throw failure('连接中断，未收到完整结果，正在重新连接。');}
  if(!response.ok)throw failure(data.error||'本地助手请求失败',data.errorCode||'request_failed',data.retryable??response.status>=500);
  if(action==='usage')data.hasSession=hasSession;
  return data;
}
async function service(action) {
  try {
    const result=await chrome.runtime.sendNativeMessage('local.chatgpt_web_translator',{action});
    if(!result?.ok)throw new Error(result?.error||'服务操作未完成。');
    return result.data;
  } catch(e) {
    throw new Error('本机连接尚未就绪。请双击“安装与修复”，完成后重新打开插件。');
  }
}
async function pageAction(action,tab,ensureService=false) {
  tab=tab||await activeTab();
  if(!tab?.id||!/^https?:/.test(tab.url||''))throw new Error('请在新闻网页或 YouTube 视频页使用。');
  if(startingTabs.has(tab.id))throw new Error('当前页正在准备翻译，请稍等。');
  startingTabs.add(tab.id);
  try {
    const saved=await chrome.storage.local.get(['model','modelsByProvider','captionScale']);
    let model,provider,sessionId='';
    if(action==='translate'){
      if(ensureService){await service('start');await chrome.storage.local.set({serviceWanted:true});}
      const state=await helper('status');
      if(!state.connected)throw new Error(state.authError||'请先在插件中连接 ChatGPT。');
      provider=state.provider||'chatgpt';
      await chrome.storage.local.set({serviceWanted:true});
      model=saved.modelsByProvider?.[provider]||(provider==='chatgpt'?saved.model:null);
      if(!model){
        const {models}=await helper('models');
        model=(models.find(m=>/(?:^|[-_])(?:luna|mini)(?:$|[-_])|flash.*low/i.test(m.slug))||models[0])?.slug;
        if(!model)throw new Error('没有可用翻译模型。');
        await chrome.storage.local.set({modelsByProvider:{...(saved.modelsByProvider||{}),[provider]:model},...(provider==='chatgpt'?{model}:{} )});
      }
    }
    await chrome.scripting.executeScript({target:{tabId:tab.id},files:['recovery.js','youtube.js','content.js']});
    const storageKey='translation-session:'+tab.id;
    if(action==='translate'){
      sessionId=crypto.randomUUID().replaceAll('-','');
      await chrome.storage.session.set({[storageKey]:{id:sessionId,pageKey:await pageKey(tab.url)}});
    }
    let result;
    try{result=await chrome.tabs.sendMessage(tab.id,{action,model,provider,sessionId,captionScale:captionScale(saved.captionScale)});}
    catch(e){if(sessionId)await chrome.storage.session.remove(storageKey);throw e;}
    if(!result?.ok){if(sessionId)await chrome.storage.session.remove(storageKey);throw new Error(result?.error||'无法读取本页');}
    if(sessionId)await maybeDailyAlert(tab,true);
    return {ok:true};
  } finally {startingTabs.delete(tab.id);}
}
async function commandMessage(tab,message) {
  if(!tab?.id)return;
  await chrome.scripting.executeScript({target:{tabId:tab.id},func:text=>{
    let box=document.getElementById('cgpt-command-message');
    if(!box){box=document.createElement('div');box.id='cgpt-command-message';document.documentElement.append(box);}
    box.textContent=text;
    box.setAttribute('role','status');
    box.style.cssText='position:fixed;right:20px;top:20px;z-index:2147483647;background:linear-gradient(135deg,rgba(20,42,34,.95),rgba(14,30,24,.97));color:#f2f7f4;font:500 12.5px/1.5 -apple-system,BlinkMacSystemFont,"SF Pro Text","PingFang SC",sans-serif;padding:9px 15px;border-radius:999px;border:1px solid rgba(168,230,193,.22);max-width:min(340px,calc(100vw - 40px));box-shadow:0 10px 28px -4px rgba(8,22,16,.38),0 2px 6px rgba(0,0,0,.18);backdrop-filter:blur(14px) saturate(140%);-webkit-backdrop-filter:blur(14px) saturate(140%);';
    clearTimeout(box._newsBridgeTimer);box._newsBridgeTimer=setTimeout(()=>box.remove(),8000);
  },args:[message]}).catch(()=>{});
}
async function maybeDailyAlert(tab,force=false){
  const {dailyAlert}=await chrome.storage.local.get('dailyAlert');
  if(!Number.isSafeInteger(dailyAlert)||dailyAlert<1||!tab?.id)return;
  if(!force&&Date.now()-lastAlertCheck<10000)return;
  if(alertCheck)return alertCheck;
  lastAlertCheck=Date.now();
  alertCheck=(async()=>{
    try{
      const usage=await helper('usage',null,null,tab.url,tab.id),today=usage.today;
      if((today.total||0)+(today.estimated_total||0)<dailyAlert)return;
      const key='daily-alert:'+usage.day+':'+dailyAlert;
      if((await chrome.storage.session.get(key))[key])return;
      const current=await chrome.tabs.get(tab.id);
      if(await pageKey(current.url)!==await pageKey(tab.url))return;
      await chrome.storage.session.set({[key]:true});
      await commandMessage(tab,'今日 Token 已达到提醒值'+(today.estimated_total?'（含估算）':'')+'。翻译仍会继续。');
    }catch{} // A warning never interrupts translation.
  })().finally(()=>{alertCheck=null;});
  return alertCheck;
}
chrome.tabs.onRemoved.addListener(id=>chrome.storage.session.remove('translation-session:'+id));
function handleCommand(command,tab){
  if(command!=='translate-page')return;
  return (async()=>{
    tab=tab||await activeTab();
    await commandMessage(tab,'正在开始翻译…');
    await chrome.action.setBadgeText({tabId:tab.id,text:'…'});
    await pageAction('translate',tab,true);
    await chrome.action.setBadgeText({tabId:tab.id,text:''});
    await chrome.action.setTitle({tabId:tab.id,title:'双语翻译器'});
  })().catch(async error=>{
    await commandMessage(tab,error.message);
    if(tab?.id){
      await chrome.action.setBadgeText({tabId:tab.id,text:'!'});
      await chrome.action.setTitle({tabId:tab.id,title:error.message});
    }
  });
}
chrome.commands.onCommand.addListener(handleCommand);
chrome.runtime.onMessage.addListener((message,sender,respond)=>{
  if(sender.id!==chrome.runtime.id)return;
  const trusted=sender.url?.startsWith(chrome.runtime.getURL(''));
  const action=message?.action;
  const captionDrag=action==='saveCaptionSize'&&/^https:\/\/(?:www\.)?youtube\.com\//.test(sender.url||'');
  if(!trusted&&!captionDrag&&!['start','poll','cancel','transcript','homeSnapshotSave','homeSnapshotRead','homeSnapshotRemove'].includes(action))return;
  (async()=>{
    if(['homeSnapshotSave','homeSnapshotRead','homeSnapshotRemove'].includes(action))return homeSnapshot(action,message.payload,sender);
    if(action==='clearCache')await changeHomeSnapshots(()=>[]);
    if(action==='connect')return connectLocal();
    if(action==='diagnose')return service('diagnose');
    if(action==='service'){
      if(!['status','start','stop'].includes(message.payload?.action))throw new Error('不支持的操作。');
      const value=message.payload.action;
      if(value!=='status')await chrome.storage.local.set({serviceWanted:value==='start'});
      return service(value);
    }
    if(action==='pageAction'){
      if(!['translate','restore'].includes(message.payload?.action))throw new Error('不支持的操作。');
      return pageAction(message.payload.action);
    }
    if(action==='captionSettings'||captionDrag){
      const scale=captionScale(message.payload?.scale);
      await chrome.storage.local.set({captionScale:scale});
      const tab=await activeTab();
      if(!captionDrag&&tab?.id)await chrome.tabs.sendMessage(tab.id,{action:'captionSettings',scale}).catch(()=>{});
      return {scale};
    }
    const tab=action==='usage'?await activeTab():sender.tab;
    const data=await helper(action,message.payload,message.id,tab?.url||sender.url,tab?.id);
    if(action==='poll'&&tab)await maybeDailyAlert(tab,['done','error','cancelled'].includes(data.status));
    return data;
  })().then(data=>respond({ok:true,data})).catch(error=>respond({ok:false,error:error.message,errorCode:error.code||'request_failed',retryable:!!error.retryable}));
  return true;
});
