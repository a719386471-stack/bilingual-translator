(() => {
  if(globalThis.__cgptBridge)return;
  const error=data=>Object.assign(new Error(data?.error||'连接暂时中断'),{code:data?.errorCode||'connection',retryable:data?.retryable??true});
  async function raw(action,payload,id){
    let r;
    try{r=await chrome.runtime.sendMessage({action,payload,id});}
    catch{throw error({error:'插件连接已失效，请应用更新后刷新本页。',errorCode:'extension',retryable:false});}
    if(!r?.ok)throw error(r);
    return r.data;
  }
  // Wake early when connectivity returns; cancellation is checked without long sleeps.
  async function delay(ms,cancelled=()=>false){
    await new Promise(resolve=>{
      let timer,check;
      const done=()=>{clearTimeout(timer);clearInterval(check);removeEventListener('online',done);resolve();};
      timer=setTimeout(done,ms);check=setInterval(()=>{if(cancelled())done();},150);
      addEventListener('online',done,{once:true});
    });
  }
  async function request(action,payload,id,{cancelled=()=>false,notice=()=>{}}={}){
    for(let n=0;;n++){
      if(cancelled())throw error({error:'已停止翻译',errorCode:'cancelled',retryable:false});
      try{return await raw(action,payload,id);}
      catch(e){
        if(!e.retryable||e.code==='job_missing'||n>=7)throw e;
        notice('连接暂时中断 · 保留已完成译文，正在重连…');
        await delay(Math.min(20000,1000*2**n),cancelled);
      }
    }
  }
  async function run(payload,{cancelled=()=>false,update=()=>{},notice=()=>{},id=()=>{}}={}){
    const data={...payload,requestId:payload.requestId||crypto.randomUUID().replaceAll('-','')};
    let job=null,resumes=0,restarts=0;
    const opts={cancelled,notice};
    try{
      while(!cancelled()){
        if(!job){
          const r=await request('start',data,null,opts);job=r.id;id(job);
          if(cancelled())break;
        }
        let state;
        try{state=await request('poll',null,job,opts);}
        catch(e){
          if(e.code==='job_missing'&&restarts++<3){job=null;notice('本机服务已恢复 · 正在接续未完成部分…');continue;}
          throw e;
        }
        update(state);
        if(state.status==='done')return state;
        if(state.status==='cancelled')throw error({error:'已停止翻译',errorCode:'cancelled',retryable:false});
        if(state.status==='error'){
          if(state.retryable&&state.errorCode!=='format'&&resumes<2){
            notice('暂时无法连接 · 已完成译文保留，稍后自动继续…');
            await delay((++resumes)*15000,cancelled);
            data.resume=true;job=null;continue;
          }
          throw error(state);
        }
        if(state.phase==='retrying')notice('翻译连接暂时中断 · 正在重试未完成部分…');
        await delay(650,cancelled);
      }
      throw error({error:'已停止翻译',errorCode:'cancelled',retryable:false});
    }finally{
      // A timed-out POST can still create a task: its id is known before sending.
      if(cancelled())raw('cancel',null,job||data.requestId).catch(()=>{});
    }
  }
  globalThis.__cgptBridge={run,request,raw,delay};
})();
