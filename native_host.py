"""Chrome native messaging: fixed translator control, pairing and diagnostics."""
import fcntl,json,os,socket,struct,subprocess,sys,time
from pathlib import Path
from urllib import request,error
from install_support import DEFAULT_DATA,NAME,VERSION,read_json

def connection(data):
    cfg=read_json(Path(data)/'service/native-config.json')
    port=cfg.get('port',19487)
    if type(port) is not int or not 1024<=port<=65535:raise ValueError('本机端口配置无效，请运行安装与修复。')
    return cfg,port

def helper_request(method='GET',data=DEFAULT_DATA):
    try:
        data=Path(data);cfg,port=connection(data);key=read_json(data/'connection.json')['pairing_key']
        req=request.Request('http://127.0.0.1:%d/api/service'%port,method=method,data=b'{}' if method=='POST' else None,
                            headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
        with request.build_opener(request.ProxyHandler({})).open(req,timeout=1) as r:result=json.load(r)
        return result.get('service')=='chatgpt-web-translator'
    except (OSError,ValueError,KeyError,error.URLError):return False

def port_busy(port):
    try:
        with socket.create_connection(('127.0.0.1',port),timeout=.3):return True
    except OSError:return False

def process_alive(pid):
    if type(pid) is not int or pid<=0:return False
    try:os.kill(pid,0);return True
    except OSError:return False

def control(action,data=DEFAULT_DATA):
    if action not in ('status','start','stop','connect','diagnose'):raise ValueError('不支持的服务操作。')
    data=Path(data);service=data/'service';data.mkdir(parents=True,exist_ok=True,mode=0o700)
    with (data/'service-control.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX);cfg,port=connection(data);running=helper_request(data=data)
        if action=='start' and not running:
            python=data/'runtime/bin/python3'
            if not python.is_file():raise ValueError('运行环境尚未安装，请运行“安装与修复”。')
            if port_busy(port):raise ValueError('本机翻译端口被占用，请检查诊断；不会关闭其他程序。')
            log=data/'helper.log'
            with log.open('ab') as output:
                log.chmod(0o600)
                args=[str(python),'-u',str(service/'helper.py'),'--data-dir',str(data),'--no-browser']
                if 'port' in cfg:args+=['--port',str(port)]
                child=subprocess.Popen(args,
                    cwd=service,stdin=subprocess.DEVNULL,stdout=output,stderr=output,start_new_session=True)
                from install_support import write_json
                write_json(data/'service-process.json',{'pid':child.pid})
            for _ in range(80):
                if helper_request(data=data):running=True;break
                if child.poll() is not None:break
                time.sleep(.1)
            if not running:raise ValueError('翻译服务未能启动，请运行“安装与修复”。')
        elif action=='stop' and running:
            if not helper_request('POST',data):raise ValueError('无法停止翻译服务，请稍后再试。')
            for _ in range(100):
                if not helper_request(data=data):running=False;break
                time.sleep(.1)
            if running:raise ValueError('翻译服务正在结束请求，请稍后再试。')
            pid=read_json(data/'service-process.json').get('pid')
            for _ in range(80):
                if not process_alive(pid):break
                time.sleep(.1)
            if process_alive(pid):raise ValueError('后台仍在结束已发送的请求，请稍后再试；账号记录已保留。')
        if action=='connect':
            key=read_json(data/'connection.json').get('pairing_key')
            if not isinstance(key,str) or len(key)<20:raise ValueError('尚未建立本机连接，请先打开翻译服务。')
            from install_support import write_json
            write_json(data/'extension-connected.json',{'version':VERSION,'connectedAt':time.time()})
            return {'running':running,'pairingKey':key,'version':VERSION}
        if action=='diagnose':
            from diagnostics import collect
            return collect(data,running)
        return {'running':running,'version':VERSION}

def main():
    os.umask(0o077)
    service=Path(__file__).resolve().parent
    cfg=read_json(service/'native-config.json');allowed=cfg.get('origins') or [cfg.get('origin')]
    if len(sys.argv)<2 or sys.argv[1] not in allowed:return
    prefix=sys.stdin.buffer.read(4)
    if len(prefix)!=4:return
    length=struct.unpack('=I',prefix)[0]
    if not 0<length<=4096:return
    try:
        message=json.loads(sys.stdin.buffer.read(length))
        result={'ok':True,'data':control(message.get('action'),service.parent)}
    except (ValueError,OSError,AttributeError):
        result={'ok':False,'error':'本机连接未完成，请在面板运行检查，或重新运行“安装与修复”。'}
    payload=json.dumps(result,ensure_ascii=False).encode()
    sys.stdout.buffer.write(struct.pack('=I',len(payload))+payload);sys.stdout.buffer.flush()

if __name__=='__main__':main()
