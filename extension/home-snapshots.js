// Session-only render cache. Restoring this cache never contacts a model/helper.
const HOME_SNAPSHOTS='news-home-snapshots-v1';
let homeSnapshotWrites=Promise.resolve();
function wsjHomeURL(raw){
  try{const u=new URL(raw);return u.protocol==='https:'&&/(^|\.)wsj\.com$/.test(u.hostname)&&/^\/(?:news\/?)?$/.test(u.pathname)?u.origin+u.pathname:'';}catch{return '';}
}
function changeHomeSnapshots(fn){
  const work=homeSnapshotWrites.catch(()=>{}).then(async()=>{
    const saved=(await chrome.storage.session.get(HOME_SNAPSHOTS))[HOME_SNAPSHOTS]||[];
    const rows=saved.filter(r=>r.at>Date.now()-6*60*60*1000);
    const result=fn(rows);
    await chrome.storage.session.set({[HOME_SNAPSHOTS]:result.slice(-8)});
  });homeSnapshotWrites=work;return work;
}
async function homeSnapshot(action,payload,sender){
  const url=wsjHomeURL(sender.url),tabId=sender.tab?.id;
  if(!url||!tabId)return null;
  const key=tabId+'|'+url;
  if(action==='homeSnapshotRead'){
    await homeSnapshotWrites.catch(()=>{});
    const rows=(await chrome.storage.session.get(HOME_SNAPSHOTS))[HOME_SNAPSHOTS]||[];
    return rows.find(r=>r.key===key&&r.at>Date.now()-6*60*60*1000)?.snapshot||null;
  }
  if(action==='homeSnapshotRemove'){await changeHomeSnapshots(rows=>rows.filter(r=>r.key!==key));return null;}
  const p=payload||{};
  if(!Array.isArray(p.records)||!['chatgpt','antigravity'].includes(p.provider)||typeof p.model!=='string')return null;
  let chars=0;const records=[];
  for(const r of p.records.slice(0,500)){
    if(!r||!['group','text','value'].every(k=>typeof r[k]==='string')||r.group.length>1200||r.text.length>12000||r.value.length>24000)continue;
    chars+=r.group.length+r.text.length+r.value.length;if(chars>200000)break;
    records.push({group:r.group,text:r.text,value:r.value});
  }
  const snapshot={records,provider:p.provider,model:p.model.slice(0,200),sessionId:/^[a-f0-9]{32}$/.test(p.sessionId||'')?p.sessionId:''};
  await changeHomeSnapshots(rows=>[...rows.filter(r=>r.key!==key),{key,tabId,url,at:Date.now(),snapshot}]);return null;
}
chrome.tabs.onUpdated.addListener((id,change,tab)=>{
  if(!(change.status==='complete'||change.url)||!wsjHomeURL(tab.url))return;
  (async()=>{
    const snapshot=await homeSnapshot('homeSnapshotRead',null,{url:tab.url,tab:{id}});
    if(!snapshot)return;
    const current=await chrome.tabs.get(id);
    if(wsjHomeURL(current.url)!==wsjHomeURL(tab.url))return;
    // activeTab remains valid for same-origin navigation. If it was revoked,
    // leave the page untouched; never request broader host permissions here.
    await chrome.scripting.executeScript({target:{tabId:id},files:['recovery.js','content.js']});
    await chrome.tabs.sendMessage(id,{action:'restoreHome'});
  })().catch(()=>{});
});
chrome.tabs.onRemoved.addListener(id=>changeHomeSnapshots(rows=>rows.filter(r=>r.tabId!==id)).catch(()=>{}));
