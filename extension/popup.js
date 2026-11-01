const $=id=>document.getElementById(id);
const number=n=>new Intl.NumberFormat('zh-CN').format(n||0);
let running=false,loadSerial=0,usageLoading=false,lastUsage=null,quotaSerial=0;
async function api(action,payload){
  const result=await chrome.runtime.sendMessage({action,payload});
  if(!result?.ok)throw new Error(result?.error||'连接失败');
  return result.data;
}
function notify(message){
  $('message').textContent=message;
  $('settings-message').textContent=message;
  $('settings-message').hidden=!message;
}
function showView(view){
  for(const name of ['settings','usage','quota'])$(name+'-view').hidden=name!==view;
  if(view)$(view+'-view').querySelector('.back').focus();
  else $('open-settings').focus();
}
for(const button of document.querySelectorAll('.back'))button.onclick=()=>showView(null);
$('open-settings').onclick=$('open-settings-footer').onclick=()=>showView('settings');
$('open-usage').onclick=()=>{renderUsageDetails();showView('usage');};
$('open-quota').onclick=()=>{showView('quota');if(running)loadQuota();};
$('version').textContent='v'+chrome.runtime.getManifest().version;

async function renderPage(current){
  const tab=current||(await chrome.tabs.query({active:true,currentWindow:true}))[0];
  let url;try{url=new URL(tab?.url);}catch{}
  const web=url&&/^https?:$/.test(url.protocol);
  const video=web&&/(^|\.)youtube\.com$/.test(url.hostname)&&url.pathname==='/watch';
  $('caption-control').hidden=!video;
  $('page-kind').textContent=web?url.hostname.replace(/^www\./,'')+(video?' · 视频字幕':' · 网页阅读'):'当前页面';
  $('page-title').textContent=web?(tab.title||'当前页面'):'打开英文新闻或 YouTube 视频';
  $('page-hint').textContent=video?'英文字幕对照中文，优先使用视频原有人工字幕':'英文原文下方显示中文';
  $('translate-label').textContent=video?'开启双语字幕':'翻译当前页';
}
function reflectProvider(){
  for(const button of document.querySelectorAll('[data-provider]')){
    button.setAttribute('aria-pressed',String(button.dataset.provider===$('provider').value));
    button.disabled=!running||$('provider').disabled;
  }
}
function setService(value){
  running=!!value;
  $('service-toggle').setAttribute('aria-checked',String(running));
  $('service-state').textContent=running?'已开启':'已关闭';
  $('provider').disabled=!running;reflectProvider();
  if(!running){
    loadSerial++;$('account').textContent='翻译服务已关闭；打开面板开关或使用快捷键可按需启动。';
    $('pairing').hidden=true;$('translate').disabled=true;$('clear').disabled=true;
    $('quota-short').textContent='服务已关闭';$('quota-content').textContent='开启服务后查看';
  }
}
async function saveModel(){
  const {modelsByProvider={}}=await chrome.storage.local.get('modelsByProvider');
  const provider=$('provider').value,model=$('model').value;
  if(model)await chrome.storage.local.set({modelsByProvider:{...modelsByProvider,[provider]:model},...(provider==='chatgpt'?{model}:{})});
}
$('model').onchange=saveModel;
async function load(){
  const serial=++loadSerial;
  $('translate').disabled=true;$('clear').disabled=true;
  try{
    const state=await api('status');if(serial!==loadSerial)return;
    const provider=state.provider||'chatgpt';$('provider').value=provider;reflectProvider();
    $('connect-provider').hidden=provider!=='antigravity'||state.connected;
    $('account').textContent=state.connected?'已连接 '+(state.providerName||'ChatGPT')+(state.connectionMethod==='local-codex'?'（本机官方组件）':'')+' · '+(state.email||'账号'):state.authError||'请连接所选来源的账号。';
    $('pairing').hidden=true;
    if(!state.connected){$('model').replaceChildren(new Option('请先连接所选来源',''));$('quota-short').textContent='请先连接账号';$('quota-content').textContent='连接账号后查看额度。';notify('请先在设置中连接账号。');return;}
    notify('准备就绪');$('clear').disabled=false;loadQuota();
    const saved=await chrome.storage.local.get(['model','modelsByProvider','modelCatalogs']);
    if(serial!==loadSerial)return;
    const savedModel=saved.modelsByProvider?.[provider]||(provider==='chatgpt'?saved.model:null);
    const cached=Array.isArray(saved.modelCatalogs?.[provider])?saved.modelCatalogs[provider]:[];
    const list=cached.filter(m=>typeof m?.slug==='string'&&typeof m?.display_name==='string').slice(0,100);
    if(savedModel&&!list.some(m=>m.slug===savedModel))list.unshift({slug:savedModel,display_name:savedModel});
    if(list.length){$('model').replaceChildren(...list.map(m=>new Option(m.display_name,m.slug)));if(savedModel)$('model').value=savedModel;$('translate').disabled=false;}
    else $('model').replaceChildren(new Option('正在加载模型…',''));
    try{
      const {models}=await api('models');if(serial!==loadSerial)return;
      $('model').replaceChildren(...models.map(m=>new Option(m.display_name,m.slug)));
      if(models.some(m=>m.slug===savedModel))$('model').value=savedModel;
      else {const preferred=models.find(m=>/(?:^|[-_])(?:luna|mini)(?:$|[-_])|flash.*low/i.test(m.slug))||models[0];if(preferred)$('model').value=preferred.slug;}
      $('translate').disabled=!models.length;
      if(models.length){await saveModel();const current=await chrome.storage.local.get('modelCatalogs');await chrome.storage.local.set({modelCatalogs:{...(current.modelCatalogs||{}),[provider]:models.map(m=>({slug:m.slug,display_name:m.display_name}))}});}
      else notify('当前账号没有可用的翻译模型。');
    }catch(e){if(serial===loadSerial){if(!list.length)$('translate').disabled=true;notify(list.length?'暂未刷新模型列表，仍可尝试上次使用的模型。':e.message);}}
  }catch(e){if(serial===loadSerial){$('account').textContent=e.message;notify(e.message);}}
}
for(const button of document.querySelectorAll('[data-provider]'))button.onclick=()=>{
  if($('provider').value===button.dataset.provider)return;
  $('provider').value=button.dataset.provider;$('provider').dispatchEvent(new Event('change'));
};
$('provider').onchange=async()=>{
  loadSerial++;$('provider').disabled=true;reflectProvider();$('translate').disabled=true;$('model').replaceChildren(new Option('正在切换…',''));
  try{await api('provider',{provider:$('provider').value});await load();await loadUsage();}
  catch(e){notify(e.message);await load();}
  finally{$('provider').disabled=!running;reflectProvider();}
};
async function openSetup(){try{await api('service',{action:'start'});await chrome.tabs.create({url:'http://127.0.0.1:19487/'});}catch(e){notify(e.message);}}
$('open-setup').onclick=$('connect-provider').onclick=$('helper').onclick=openSetup;
async function init(){
  try{
    await renderPage();
    const saved=await chrome.storage.local.get(['captionScale','dailyAlert']);
    $('caption-size').value=saved.captionScale||100;$('caption-value').textContent=$('caption-size').value+'%';
    $('daily-alert').value=saved.dailyAlert||'';
    const command=(await chrome.commands.getAll()).find(c=>c.name==='translate-page');
    $('shortcut').textContent=command?.shortcut?'快捷键：'+command.shortcut+' · 按需启动并翻译':'快捷键未绑定，请在 Chrome 的扩展快捷键页设置';
    $('shortcut-key').textContent=command?.shortcut||'未绑定';
    let linked;try{linked=await api('connect');}catch{}
    const state=linked||await api('service',{action:'status'});
    setService(state.running);$('service-toggle').disabled=false;
    if(state.running)await load();else notify('服务已关闭，打开开关即可使用。');
    await loadUsage();
  }catch(e){$('service-state').textContent='暂不可用';notify(e.message);await load();await loadUsage();}
}
$('service-toggle').onclick=async()=>{
  const turnOn=$('service-toggle').getAttribute('aria-checked')!=='true';
  $('service-toggle').disabled=true;$('translate').disabled=true;$('service-state').textContent=turnOn?'启动中…':'关闭中…';
  try{
    if(!turnOn)await api('pageAction',{action:'restore'}).catch(()=>{});
    const state=await api('service',{action:turnOn?'start':'stop'});setService(state.running);
    if(state.running)await load();else notify('服务已关闭，账号和译文缓存已保留。');
    await loadUsage();
  }catch(e){notify(e.message);await init();}
  finally{$('service-toggle').disabled=false;}
};
$('save').onclick=async()=>{await chrome.storage.local.set({pairingKey:$('key').value.trim()});await load();};
async function loadQuota(){
  const serial=++quotaSerial;
  try{
    const q=await api('quota');if(serial!==quotaSerial)return;
    const node=$('quota-content');node.replaceChildren();
    const title=document.createElement('div');title.textContent=q.scope||'所选服务';node.append(title);
    if(q.available)for(const w of q.windows||[]){
      const p=document.createElement('div');
      const reset=w.resetsAt?' · '+new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Singapore',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(w.resetsAt*1000))+' 重置（新加坡时间）':'';
      p.textContent=w.name+' 剩余 '+w.remainingPercent+'%'+reset;node.append(p);
    }
    const note=document.createElement('small');note.textContent=q.message||'官方未提供可核验的余额。';node.append(note);
    $('quota-short').textContent=q.available&&(q.windows||[]).length?'可查看':'暂不可用';
  }catch(e){if(serial!==quotaSerial)return;$('quota-content').textContent='暂时无法读取官方额度；不会用 Token 推算订阅余额。';$('quota-short').textContent='暂不可用';}
}
$('quota-refresh').onclick=loadQuota;
async function changeCaption(){const scale=Number($('caption-size').value);$('caption-value').textContent=scale+'%';try{await api('captionSettings',{scale});}catch(e){notify(e.message);}}
$('caption-size').oninput=changeCaption;
$('caption-reset').onclick=()=>{$('caption-size').value=100;changeCaption();};
function formatUsage(value,empty=false){
  if(empty)return '—';
  const estimated=value?.estimated_total||0;
  return (estimated?'≈':'')+number((value?.total||0)+estimated)+(value?.unreported?'＋':'');
}
function renderUsageDetails(){
  const node=$('usage-details');node.replaceChildren();if(!lastUsage)return;
  for(const [kind,label]of [['session','本次翻译'],['page','本页累计'],['today','今日累计']]){
    const value=lastUsage[kind]||{};const card=document.createElement('div');card.className='usage-card';
    const title=document.createElement('div');title.className='usage-name';title.textContent=label;card.append(title);
    const strong=document.createElement('strong');strong.textContent=formatUsage(value,kind==='session'&&!lastUsage.hasSession);card.append(strong);
    const detail=document.createElement('p');
    detail.textContent=kind==='session'&&!lastUsage.hasSession?'本页面尚未开始新的翻译。':'官方 '+number(value.total)+' · 估算 '+number(value.estimated_total)+' · 未返回 '+number(value.unreported)+' 次\n官方输入 '+number(value.input)+' · 输出 '+number(value.output);
    detail.style.whiteSpace='pre-line';card.append(detail);node.append(card);
  }
}
async function loadUsage(){
  if(usageLoading)return;usageLoading=true;
  try{
    const data=await api('usage');lastUsage=data;
    for(const kind of ['session','page','today']){
      const node=$('usage-'+kind),value=formatUsage(data[kind],kind==='session'&&!data.hasSession);
      node.textContent=value;node.classList.toggle('compact',value.length>=10);node.classList.toggle('extra-wide',value.length>=13);
    }
    const missing=['session','page','today'].some(k=>data[k]?.unreported);
    const estimated=['session','page','today'].some(k=>data[k]?.estimated_total);
    $('usage-note').textContent=(missing?'＋ 部分请求未返回用量\n':'')+(estimated?'≈ 含可见文本估算，不含内部提示和推理\n':'')+'官方输入中的缓存及输出中的推理已包含在总量内。缓存命中不新增模型请求；不能用 Token 推算订阅额度。';
    const {dailyAlert}=await chrome.storage.local.get('dailyAlert');
    const reached=Number.isSafeInteger(dailyAlert)&&dailyAlert>0&&(data.today.total+data.today.estimated_total)>=dailyAlert;
    $('usage-alert').hidden=!reached;$('usage-alert').textContent=reached?'今日用量已达到提醒值'+(data.today.estimated_total?'（含估算）':'')+'。':'';
    if(!$('usage-view').hidden)renderUsageDetails();
  }catch(e){
    lastUsage=null;for(const kind of ['session','page','today'])$('usage-'+kind).textContent='—';
    $('usage-note').textContent='开启翻译服务后查看用量';$('usage-alert').hidden=true;
  }finally{usageLoading=false;}
}
$('save-alert').onclick=async()=>{
  const input=$('daily-alert').value.trim(),value=input?Number(input):0;
  if(input&&(!Number.isSafeInteger(value)||value<1||value>1000000000)){$('alert-setting-note').textContent='请输入 1 到 1,000,000,000 的整数，或留空关闭。';return;}
  await chrome.storage.local.set({dailyAlert:value});$('alert-setting-note').textContent=value?'已保存 · 今日达到 '+number(value)+' Token 时提醒':'已关闭每日提醒';await loadUsage();
};
$('translate').onclick=async()=>{
  $('translate').disabled=true;
  try{await saveModel();await api('pageAction',{action:'translate'});notify('翻译已开始，进度显示在网页中。');await loadUsage();}
  catch(e){notify(e.message);}
  finally{$('translate').disabled=!running;}
};
$('restore').onclick=async()=>{try{await api('pageAction',{action:'restore'});notify('已停止翻译并恢复原文。');}catch(e){notify(e.message);}};
$('clear').onclick=async()=>{try{await api('clearCache');notify('本机译文缓存已清除，账号及用量记录保留。');}catch(e){notify(e.message);}};
$('apply-update').onclick=()=>chrome.runtime.reload();
$('check-update').onclick=()=>chrome.tabs.create({url:'https://github.com/a719386471-stack/bilingual-translator/releases'});
$('reconnect').onclick=async()=>{
  $('reconnect').disabled=true;
  try{await api('connect');await init();notify('已连接本机助手，无需复制连接码。');}
  catch(e){notify(e.message);$('pairing').hidden=false;}
  finally{$('reconnect').disabled=false;}
};
$('diagnose').onclick=async()=>{
  $('diagnostics').hidden=false;const box=$('diagnostic-results');box.replaceChildren();$('diagnose').disabled=true;
  try{const report=await api('diagnose');for(const c of report.checks||[]){const line=document.createElement('div');line.className=c.state;line.textContent=(c.state==='ok'?'✓ ':'· ')+c.label+'：'+c.detail;box.append(line);}if(!report.checks?.length)box.textContent='请运行安装与修复，完成本机检查。';}
  catch(e){box.textContent=e.message;}
  finally{$('diagnose').disabled=false;}
};
init();
setInterval(()=>{if(running)loadUsage();},3000);
