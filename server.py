"""Local-only demo. Keys remain server-side; live API failures never fall back silently."""
import argparse
import json
import math
import os
from pathlib import Path
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from game import replay

ROOT=Path(__file__).parent
MODEL='jev-1.13.0'
API='https://api.typesafe.ai/v1/systemone'
LOCK=threading.Lock()

def choose_jev(g):
    key=os.environ.get('TYPESAFE_API_KEY')
    if not key: raise RuntimeError('尚未配置 TYPESAFE_API_KEY。可选择本地规则练习，但它不是 Jev。')
    payload=g.payload(MODEL)
    request=Request(API,data=json.dumps(payload).encode(),headers={
        'Authorization':'Bearer '+key,'Content-Type':'application/json'},method='POST')
    started=time.perf_counter()
    try:
        with urlopen(request,timeout=25) as r: data=json.load(r)
    except HTTPError as e: raise RuntimeError(f'Jev 接口返回 HTTP {e.code}；本手未落子，可稍后重试。') from None
    except (URLError,TimeoutError): raise RuntimeError('Jev 请求超时或网络不可用；本手未落子。') from None
    answer=data.get('answers',{}).get('move',{})
    criteria=payload['questions']['move']['criteria']
    choice=answer.get('choice')
    probs=answer.get('probabilities')
    confidence=answer.get('confidence')
    if answer.get('type')!='choice' or choice not in criteria: raise RuntimeError('Jev 返回了无效选项，已拒绝落子。')
    if not isinstance(probs,dict) or set(probs)!=set(criteria): raise RuntimeError('Jev 概率字段缺失或不匹配，已拒绝落子。')
    def valid(v): return type(v) in (float,int) and math.isfinite(v) and 0<=v<=1
    if not all(valid(v) for v in probs.values()) or abs(sum(probs.values())-1)>0.02 or not valid(confidence):
        raise RuntimeError('Jev 返回了无效概率，已拒绝落子。')
    mapping={g.coord(i):i for i in g.legal()};mapping['PASS']=None
    decision={'provider':'jev','model':data.get('model',MODEL),'choice':choice,
              'probabilities':probs,'confidence':confidence,'latency_ms':round((time.perf_counter()-started)*1000),
              'usage':data.get('usage',{}),'candidate_count':len(criteria),'assistance':payload['state'].get('candidate_policy','')}
    return mapping[choice],decision,payload,data

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def send(self,status,value,kind='application/json; charset=utf-8'):
        raw=json.dumps(value,ensure_ascii=False).encode() if kind.startswith('application/json') else value
        self.send_response(status);self.send_header('Content-Type',kind)
        self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(raw)
    def trusted(self):
        host=self.headers.get('Host','')
        allowed={f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}
        return host in allowed and (not self.headers.get('Origin') or self.headers['Origin'] in {'http://'+h for h in allowed})
    def do_GET(self):
        if not self.trusted(): return self.send(403,{'error':'仅允许本机访问'})
        if self.path=='/api/config': return self.send(200,{'jev_ready':bool(os.environ.get('TYPESAFE_API_KEY')),'model':MODEL})
        assets={'/':('index.html','text/html; charset=utf-8'),'/app.js':('app.js','text/javascript; charset=utf-8'),'/style.css':('style.css','text/css; charset=utf-8')}
        if self.path not in assets:return self.send(404,{'error':'Not found'})
        name,kind=assets[self.path];return self.send(200,(ROOT/'static'/name).read_bytes(),kind)
    def do_POST(self):
        if not self.trusted(): return self.send(403,{'error':'仅允许同源请求'})
        if self.path not in ('/api/state','/api/decision','/api/payload'): return self.send(404,{'error':'Not found'})
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=20000:raise ValueError('请求大小不合法')
            if 'application/json' not in self.headers.get('Content-Type',''):raise ValueError('需要JSON请求')
            body=json.loads(self.rfile.read(length))
            if not isinstance(body,dict):raise ValueError('需要JSON对象')
            g=replay(body.get('size',9),body.get('moves',[]),body.get('kind','go'))
            if self.path=='/api/state':return self.send(200,g.public())
            if g.over:raise ValueError('对局已结束')
            if self.path=='/api/payload':return self.send(200,g.payload(MODEL))
            if g.turn!=2:raise ValueError('模型只能在白棋回合落子')
            if len(g.moves)>=500:raise ValueError('达到本实验500手上限，请重开一局')
            if body.get('mode')=='local':
                move=g.local_move();decision={'provider':'local','choice':g.coord(move),'model':'handcrafted-rules','confidence':None,'latency_ms':None}
                payload=raw=None
            elif body.get('mode')=='jev':
                if not LOCK.acquire(blocking=False):raise RuntimeError('已有 Jev 请求进行中，请稍后重试')
                try: move,decision,payload,raw=choose_jev(g)
                finally:LOCK.release()
            else:raise ValueError('请选择 Jev 或本地规则模式')
            g.play(move)
            return self.send(200,{'game':g.public(),'decision':decision,'request':payload,'response':raw})
        except (ValueError,TypeError) as e:return self.send(400,{'error':str(e)})
        except RuntimeError as e:return self.send(503,{'error':str(e)})
        except Exception:return self.send(500,{'error':'服务内部错误，本手未确认，请重试'})

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8765);args=parser.parse_args()
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    print(f'Jev Go: http://127.0.0.1:{args.port} | Jev key configured: {bool(os.environ.get("TYPESAFE_API_KEY"))}',flush=True)
    server.serve_forever()
