const $ = id => document.getElementById(id);
async function api(action, payload) {
  const result = await chrome.runtime.sendMessage({action, payload});
  if (!result?.ok) throw new Error(result?.error || '连接失败');
  return result.data;
}
async function load() {
  $('translate').disabled = true;
  $('clear').disabled = true;
  try {
    const state = await api('status');
    const provider=state.provider||'chatgpt';
    $('provider').value=provider;
    $('connect-provider').hidden=provider!=='antigravity'||state.connected;
    $('account').textContent = state.connected ? '已连接 '+(state.providerName||'ChatGPT')+(state.connectionMethod==='local-codex'?'（本机官方组件）':'')+' · '+state.email : state.authError || '请连接所选来源的账号。';
    $('pairing').hidden = true;
    if (!state.connected){$('model').replaceChildren(new Option('请先连接所选来源',''));$('quota-content').textContent='连接账号后查看额度。';return;}
    loadQuota();
    $('model').replaceChildren(new Option('正在加载模型…',''));
    const {models} = await api('models');
    $('model').replaceChildren();
    for (const m of models) $('model').add(new Option(m.display_name, m.slug));
    const saved=await chrome.storage.local.get(['model','modelsByProvider']);
    const model=saved.modelsByProvider?.[provider]||(provider==='chatgpt'?saved.model:null);
    if (models.some(m => m.slug === model)) $('model').value = model;
    else {
      const preferred = models.find(m => /(?:^|[-_])(?:luna|mini)(?:$|[-_])|flash.*low/i.test(m.slug)) || models[0];
      if (preferred) $('model').value = preferred.slug;
    }
    $('translate').disabled = !models.length;
    if(models.length)await saveModel();
    $('clear').disabled = false;
  } catch (e) { $('account').textContent = e.message; }
}
function setService(running) {
  $('service-toggle').setAttribute('aria-checked',String(running));
  $('service-state').textContent=running?'已开启':'已关闭';
  $('provider').disabled=!running;
  if(!running){
    $('account').textContent='翻译服务已关闭，打开上方开关即可使用。';
    $('pairing').hidden=true;
    $('translate').disabled=true;
    $('clear').disabled=true;
  }
}
$('provider').onchange=async()=>{
  $('provider').disabled=true;$('translate').disabled=true;$('model').replaceChildren(new Option('正在加载模型…',''));
  try{await api('provider',{provider:$('provider').value});await load();await loadUsage();}
  catch(e){$('message').textContent=e.message;}
  finally{$('provider').disabled=false;}
};
async function openSetup(){
  try{await api('service',{action:'start'});await chrome.tabs.create({url:'http://127.0.0.1:19487/'});}
  catch(e){$('message').textContent=e.message;}
}
$('connect-provider').onclick=openSetup;
$('open-setup').onclick=openSetup;
async function init() {
  const saved=await chrome.storage.local.get('captionScale');
  $('caption-size').value=saved.captionScale||100;
  $('caption-value').textContent=$('caption-size').value+'%';
  const command=(await chrome.commands.getAll()).find(c=>c.name==='translate-page');
  $('shortcut').textContent=command?.shortcut?'快捷键：'+command.shortcut+' · 按需启动并翻译':'快捷键未绑定：请在 Chrome 的扩展快捷键页设为 ⌥E';
  try {
    let linked;try{linked=await api('connect');}catch{}
    const state=linked||await api('service',{action:'status'});
    setService(state.running);
    $('service-toggle').disabled=false;
    if(state.running)await load();
    await loadUsage();
  } catch(e) {
    $('service-state').textContent='暂不可用';
    $('message').textContent=e.message;
    // Existing manually started helpers remain usable if the switch needs repair.
    await load();
    await loadUsage();
  }
}
$('service-toggle').onclick=async()=>{
  const turnOn=$('service-toggle').getAttribute('aria-checked')!=='true';
  $('service-toggle').disabled=true;
  $('translate').disabled=true;
  $('service-state').textContent=turnOn?'启动中…':'关闭中…';
  $('message').textContent='';
  try {
    if(!turnOn)await pageMessage('restore').catch(()=>{});
    const state=await api('service',{action:turnOn?'start':'stop'});
    setService(state.running);
    if(state.running)await load();
    else $('message').textContent='翻译服务已关闭，账号连接和译文缓存已保留。';
    await loadUsage();
  } catch(e){$('message').textContent=e.message;await init();}
  finally{$('service-toggle').disabled=false;}
};
$('helper').onclick = openSetup;
$('save').onclick = async () => { await chrome.storage.local.set({pairingKey: $('key').value.trim()}); await load(); };
async function pageMessage(action) {
  return api('pageAction',{action});
}
async function saveModel(){
  const {modelsByProvider={}}=await chrome.storage.local.get('modelsByProvider');
  const provider=$('provider').value,model=$('model').value;
  if(model)await chrome.storage.local.set({modelsByProvider:{...modelsByProvider,[provider]:model},...(provider==='chatgpt'?{model}:{})});
}
$('model').onchange=saveModel;
async function loadQuota(){
  try{
    const q=await api('quota');const node=$('quota-content');node.replaceChildren();
    const title=document.createElement('div');title.textContent=q.scope||'所选服务';node.append(title);
    if(q.available)for(const w of q.windows||[]){
      const p=document.createElement('div');
      const reset=w.resetsAt?' · '+new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Singapore',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(w.resetsAt*1000))+' 重置':'';
      p.textContent=w.name+' 剩余 '+w.remainingPercent+'%'+reset;node.append(p);
    }
    const note=document.createElement('small');note.textContent=q.message||'官方未提供可核验的余额。';node.append(note);
  }catch(e){$('quota-content').textContent='暂时无法读取官方额度；不会用 Token 推算订阅余额。';}
}
$('quota-refresh').onclick=loadQuota;
async function changeCaption() {
  const scale=Number($('caption-size').value);
  $('caption-value').textContent=scale+'%';
  try {await api('captionSettings',{scale});} catch(e){$('message').textContent=e.message;}
}
$('caption-size').oninput=changeCaption;
$('caption-reset').onclick=()=>{$('caption-size').value=100;changeCaption();};
let usageLoading=false;
async function loadUsage() {
  if(usageLoading)return;
  usageLoading=true;
  try {
    const data=await api('usage');
    const number=n=>new Intl.NumberFormat('zh-CN').format(n);
    for(const kind of ['page','today']){
      const value=data[kind];
      const estimated=value.estimated_total||0;
      $('usage-'+kind).textContent=(estimated?'≈':'')+number(value.total+estimated)+(value.unreported?'＋':'');
      $('usage-'+kind+'-detail').textContent=estimated?'实测 '+number(value.total)+' · 估算 '+number(estimated):'输入 '+number(value.input)+' · 输出 '+number(value.output);
      $('usage-'+kind).title='官方计数；输入缓存 '+number(value.cached)+'（已包含在输入中）；推理 '+number(value.reasoning)+'（已包含在输出中）';
    }
    const missing=data.today.unreported||data.page.unreported;
    const estimated=data.today.estimated_total||data.page.estimated_total;
    $('usage-note').textContent=(missing?'＋ 部分请求未返回用量\n':'')+(estimated?'≈ 含可见文本估算，不含内部提示和推理\n':'')+'仅本插件 · 新加坡时间 · 本机缓存不新增 Token';
  } catch(e) {
    for(const kind of ['page','today']){$('usage-'+kind).textContent='—';$('usage-'+kind+'-detail').textContent='';}
    $('usage-note').textContent='开启翻译服务后查看用量';
  } finally {usageLoading=false;}
}
$('translate').onclick = async () => {
  $('translate').disabled = true;
  try {
    await saveModel();
    await pageMessage('translate'); $('message').textContent = '翻译已开始，可以关闭此面板。进度显示在网页右下角。';
  } catch (e) { $('message').textContent = e.message; }
  finally { $('translate').disabled = false; }
};
$('restore').onclick = async () => { try { await pageMessage('restore'); $('message').textContent = '已停止翻译并恢复原文。'; } catch(e) { $('message').textContent = e.message; } };
$('clear').onclick = async () => { try { await api('clearCache'); $('message').textContent = '本机译文缓存已清除。'; } catch(e) { $('message').textContent = e.message; } };
init();
setInterval(()=>{if($('service-toggle').getAttribute('aria-checked')==='true')loadUsage();},2000);

$('apply-update').onclick=()=>chrome.runtime.reload();

$('reconnect').onclick=async()=>{
  $('reconnect').disabled=true;
  try{await api('connect');$('message').textContent='已自动连接本机助手，无需复制连接码。';await init();}
  catch(e){$('message').textContent=e.message;$('pairing').hidden=false;}
  finally{$('reconnect').disabled=false;}
};
$('diagnose').onclick=async()=>{
  $('diagnostics').hidden=false;const box=$('diagnostic-results');box.replaceChildren();
  $('diagnose').disabled=true;
  try{
    const report=await api('diagnose');
    for(const c of report.checks||[]){const line=document.createElement('div');line.className=c.state;line.textContent=(c.state==='ok'?'✓ ':'· ')+c.label+'：'+c.detail;box.append(line);}
    if(!report.checks?.length)box.textContent='请运行安装与修复，完成本机检查。';
  }catch(e){box.textContent=e.message;}
  finally{$('diagnose').disabled=false;}
};
