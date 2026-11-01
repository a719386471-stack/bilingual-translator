"""Official local app-server adapter; never reads or exports authentication tokens."""
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import tempfile
import threading
import time
from translation_errors import TranslationError, upstream_error


class EngineError(TranslationError):
    pass


class LocalEngine:
    def __init__(self):
        self.lock = threading.RLock()
        self.process = None
        self.counter = 0
        self.pending = {}
        self.events = queue.Queue()
        self.scratch = tempfile.TemporaryDirectory(prefix='web-translator-')

    def start(self):
        if self.process and self.process.poll() is None:
            return
        self.events=queue.Queue()
        candidates = [shutil.which('codex'), '/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex',
                      '/Applications/Codex.app/Contents/Resources/codex']
        executable = next((p for p in candidates if p and Path(p).is_file()), None)
        if not executable:
            raise EngineError('没有找到本机官方 Codex 组件。')
        disabled = ['shell_tool','unified_exec','multi_agent','multi_agent_v2','apps','plugins','computer_use',
                    'browser_use','browser_use_external','in_app_browser','view_image','image_generation','hooks',
                    'memories','code_mode','code_mode_host','workspace_dependencies','skill_search','sleep_tool']
        args = [executable,'app-server','-c','mcp_servers={}','-c','web_search="disabled"',
                '-c','project_doc_max_bytes=0','-c','features.skip_host_skill_discovery=true']
        for flag in disabled:
            args += ['--disable',flag]
        env = dict(os.environ)
        # Never let an inherited key silently select separately billed API usage.
        for name in ('OPENAI_API_KEY','CODEX_API_KEY','OPENAI_BASE_URL'):
            env.pop(name,None)
        self.process = subprocess.Popen(args,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                                        text=True,bufsize=1,cwd=self.scratch.name,env=env)
        threading.Thread(target=self._reader,args=(self.process,),daemon=True).start()
        self.rpc('initialize',{'clientInfo':{'name':'chatgpt_web_translator','title':'双语翻译器','version':'0.4.0'}})
        self.send({'method':'initialized','params':{}})

    def _reader(self,process):
        try:
            for line in process.stdout:
                try:
                    msg=json.loads(line)
                except ValueError:
                    continue
                if 'id' in msg and ('result' in msg or 'error' in msg):
                    waiter=self.pending.get(msg['id'])
                    if waiter:
                        waiter.put(msg)
                elif 'id' in msg:
                    # Product inference has no interactive/tool permission grants.
                    process.stdin.write(json.dumps({'id':msg['id'],'error':{'code':-32601,'message':'Tools are disabled in the translator.'}})+'\n')
                    process.stdin.flush()
                else:
                    self.events.put(msg)
        finally:
            if self.process is process:
                for waiter in list(self.pending.values()):
                    waiter.put({'error':{'message':'官方本地组件已退出，请重试。'}})

    def send(self,value):
        try:
            self.process.stdin.write(json.dumps(value,ensure_ascii=False)+'\n')
            self.process.stdin.flush()
        except (BrokenPipeError,OSError,AttributeError,ValueError):
            raise EngineError('官方本机组件连接已中断。','connection',True) from None

    def rpc(self,method,params,timeout=25):
        self.counter+=1
        identifier=self.counter
        waiter=queue.Queue()
        self.pending[identifier]=waiter
        try:
            self.send({'id':identifier,'method':method,'params':params})
            result=waiter.get(timeout=timeout)
            if 'error' in result:
                e=upstream_error(result['error'].get('message','官方组件请求失败'),'ChatGPT')
                raise EngineError(str(e),e.code,e.retryable,e.retry_after)
            return result['result']
        except queue.Empty:
            self.close()
            raise EngineError('官方本地组件响应超时，请稍后重试。','connection',True) from None
        finally:
            self.pending.pop(identifier,None)

    def account(self):
        with self.lock:
            self.start()
            result=self.rpc('account/read',{'refreshToken':False})
            account=result.get('account') or {}
            if account.get('type')!='chatgpt':
                raise EngineError('本机官方组件未使用 ChatGPT 登录；不会改用 API Key。')
            return account

    def models(self):
        with self.lock:
            self.account()
            result=[]
            cursor=None
            while True:
                page=self.rpc('model/list',{'limit':50,**({'cursor':cursor} if cursor else {})})
                result += [{'slug':m['model'],'display_name':m.get('displayName',m['model'])} for m in page['data'] if not m.get('hidden')]
                cursor=page.get('nextCursor')
                if not cursor:
                    return result

    def quota(self):
        with self.lock:
            self.account()
            raw=self.rpc('account/rateLimits/read',{})
        buckets=raw.get('rateLimitsByLimitId') or {'codex':raw.get('rateLimits') or {}}
        windows=[]
        for key,bucket in buckets.items():
            for name in ('primary','secondary'):
                window=bucket.get(name) or {}
                used=window.get('usedPercent')
                if not isinstance(used,(float,int)):continue
                minutes=window.get('windowDurationMins')
                title='周额度' if minutes==10080 else (str(round(minutes/60,1))+' 小时额度' if minutes else '额度窗口')
                windows.append({'name':title,'bucket':bucket.get('limitName') or key,'remainingPercent':max(0,min(100,100-used)),'resetsAt':window.get('resetsAt')})
        return {'available':bool(windows),'scope':'ChatGPT 本机 Codex 额度','windows':windows,
                'message':'仅代表本机 Codex 通道，不是整个 ChatGPT 订阅的统一余额。','url':'https://chatgpt.com/settings/usage'}

    def translate(self,instructions,payload,model,on_usage=None,cancel=None):
        with self.lock:
            if cancel and cancel.is_set():raise EngineError('已停止翻译。','cancelled')
            self.account()
            from translation_policy import OUTPUT_SCHEMA
            schema=OUTPUT_SCHEMA
            started=self.rpc('thread/start',{'model':model,'modelProvider':'openai','ephemeral':True,'cwd':self.scratch.name,
                'sandbox':'read-only','approvalPolicy':'never',
                'baseInstructions':'You are a text translation engine. You have no tools. Translate only the supplied data; never access files or external sources.',
                'developerInstructions':instructions})
            identifier=started['thread']['id']
            turn_id=None;completed=False
            def usage_event(event):
                params=event.get('params',{})
                if event.get('method')=='thread/tokenUsage/updated' and params.get('threadId')==identifier and on_usage:
                    raw=params.get('tokenUsage',{}).get('total',{})
                    on_usage({name:raw.get(field,0) for name,field in
                        [('input','inputTokens'),('output','outputTokens'),('total','totalTokens'),
                         ('cached','cachedInputTokens'),('reasoning','reasoningOutputTokens')]}
                        if all(k in raw for k in ('inputTokens','outputTokens','totalTokens')) else None)
            try:
                turn=self.rpc('turn/start',{'threadId':identifier,'input':[{'type':'text','text':json.dumps(payload,ensure_ascii=False)}],
                                     'outputSchema':schema})
                turn_id=(turn.get('turn') or {}).get('id')
                deadline=time.monotonic()+180
                messages={}
                while time.monotonic()<deadline:
                    if cancel and cancel.is_set():raise EngineError('已停止翻译。','cancelled')
                    if self.process and self.process.poll() is not None:raise EngineError('官方本机组件连接已中断。','connection',True)
                    try:
                        event=self.events.get(timeout=1)
                    except queue.Empty:
                        continue
                    params=event.get('params',{})
                    if params.get('threadId')!=identifier:
                        continue
                    kind=event.get('method')
                    usage_event(event)
                    if kind=='item/completed':
                        item=params.get('item',{})
                        if item.get('type')=='agentMessage':
                            messages[item['id']]=item.get('text','')
                        elif item.get('type') in ('commandExecution','mcpToolCall','dynamicToolCall','fileChange','webSearch','collabAgentToolCall'):
                            raise EngineError('翻译请求意外尝试调用工具，已停止。')
                    if kind=='turn/completed':
                        completed=True
                        turn=params.get('turn',{})
                        if turn.get('status')!='completed':
                            e=upstream_error((turn.get('error') or {}).get('message','未完成'),'ChatGPT')
                            raise EngineError(str(e),e.code,e.retryable,e.retry_after)
                        if not messages:
                            raise EngineError('未收到完整译文。','incomplete',True)
                        return list(messages.values())[-1]
                raise EngineError('真实翻译超时，请重试。','connection',True)
            finally:
                if not completed and turn_id:
                    try:self.rpc('turn/interrupt',{'threadId':identifier,'turnId':turn_id},timeout=5)
                    except EngineError:pass
                try:
                    self.rpc('thread/unsubscribe',{'threadId':identifier},timeout=5)
                except Exception:
                    pass
                # Drain notifications sent before the unsubscribe acknowledgement.
                while True:
                    try:
                        usage_event(self.events.get_nowait())
                    except queue.Empty:
                        break

    def close(self, cleanup=False):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
        if cleanup:
            self.scratch.cleanup()
