const $ = id => document.getElementById(id);
let key;
async function api(path,payload) {
  const response = await fetch('/api/'+path,{method:payload?'POST':'GET',headers:{Authorization:'Bearer '+key,'Content-Type':'application/json'},body:payload?JSON.stringify(payload):undefined});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || '请求失败');
  return data;
}
async function load() {
  try {
    const setup = await (await fetch('/setup')).json(); key=setup.pairingKey;
    if (!key) throw new Error('无法读取连接码，请重新打开本地助手主页。');
    $('key').value=key;
    const state=await api('status?provider=chatgpt');
    $('status').textContent=state.connected?'已连接 · '+state.email+(state.connectionMethod==='local-codex'?' · 本机官方组件':''):state.authError || '连接本机已登录的账号，或使用 ChatGPT 单独授权。';
    $('logout').hidden=!state.connected;
    const saved=await api('accounts');
    $('accounts').replaceChildren(new Option('添加 ChatGPT 账号',''));
    for(const a of saved.accounts) $('accounts').add(new Option(a.email+' · '+a.client_id.slice(-6),a.client_id));
    await installStatus();
  } catch(e) { $('message').textContent=e.message; }
}
$('copy').onclick=async()=>{try{await navigator.clipboard.writeText(key);$('copy').textContent='已复制';}catch(e){$('key').type='text';$('key').select();$('message').textContent='请手动复制选中的连接码。';}};
$('local').onclick=async()=>{try{await api('engine/local',{});location.reload();}catch(e){$('message').textContent=e.message;}};
$('login').onclick=async()=>{
  $('login').disabled=true;
  try{const r=await api('auth/start',{client_id:$('accounts').value||null});location.assign(r.url);}
  catch(e){$('message').textContent=e.message;$('login').disabled=false;}
};
$('logout').onclick=async()=>{try{const r=await api('logout',{});$('message').textContent=r.message;$('status').textContent='已退出 ChatGPT';$('logout').hidden=true;}catch(e){$('message').textContent=e.message;}};
$('clear').onclick=async()=>{try{await api('cache/clear',{});$('message').textContent='本机译文缓存已清除。';}catch(e){$('message').textContent=e.message;}};
load();

async function agyStatus(){
  try{const s=await api('status?provider=antigravity');$('agy-status').textContent=s.connected?'已连接 Google Antigravity，回到插件面板选择此来源即可使用。':s.authError||'请完成 Google 登录。';}
  catch(e){$('agy-status').textContent=e.message;}
}
$('agy-refresh').onclick=agyStatus;
$('agy-login').onclick=async()=>{
  $('agy-login').disabled=true;
  try{await api('antigravity/auth/start',{});$('agy-status').textContent='正在准备 Google 官方登录页…';
    for(let i=0;i<120;i++){const s=await api('antigravity/auth');if(s.url){location.assign(s.url);return;}if(s.stage==='connected'){await agyStatus();return;}if(s.stage==='error')throw new Error(s.error);await new Promise(r=>setTimeout(r,500));}
    throw new Error('登录页准备超时，请稍后重试。');
  }catch(e){$('agy-status').textContent=e.message;}finally{$('agy-login').disabled=false;}
};
setTimeout(agyStatus,500);

function syncProviderCard(){
  const cards=document.querySelectorAll('.account-card');
  const active=$('provider').value||'chatgpt';
  if(cards[0])cards[0].dataset.active=String(active==='chatgpt');
  if(cards[1])cards[1].dataset.active=String(active==='antigravity');
}
syncProviderCard();
async function installStatus(){
  try{
    const report=await api('diagnostics');$('installed-version').textContent='v'+report.version;
    $('provider').value=report.provider||'chatgpt';syncProviderCard();
    $('extension-status').textContent=report.extensionPaired?'✓ 已自动连接 Chrome 插件。':'安装完成后，打开一次 Chrome 插件即可自动连接。';
    const box=$('checks');box.replaceChildren();
    for(const c of report.checks||[]){const row=document.createElement('div');row.className=c.state;row.textContent=(c.state==='ok'?'✓ ':'· ')+c.label+'：'+c.detail;box.append(row);}
  }catch(e){$('checks').textContent=e.message;}
}
$('check-install').onclick=installStatus;
$('provider').onchange=async()=>{syncProviderCard();try{await api('provider',{provider:$('provider').value});$('message').textContent='已保存翻译来源。两边的账号连接都会保留。';}catch(e){$('message').textContent=e.message;}};
$('open-folder').onclick=async()=>{try{await api('open-extension-folder',{});$('message').textContent='插件文件夹已在 Finder 打开。';}catch(e){$('message').textContent=e.message;}};
