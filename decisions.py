"""OpenAI Decisions adapter, with explicit opt-in AEP authentication."""
import json
import math
import subprocess
import time
from urllib.parse import urlsplit


def choose_decisions(g, config):
    from llm import endpoint
    raw_base=config.get('base_url','')
    if not isinstance(raw_base,str):raise ValueError('Base URL 不合法')
    base=raw_base.strip().rstrip('/')
    endpoint(base)  # Apply the existing URL validation policy.
    if not urlsplit(base).path.endswith('/decisions'):
        base += '/decisions'
    key=config.get('api_key','')
    model=config.get('model','')
    if not isinstance(key,str) or any(c in key for c in '\r\n') or len(key)>4096:
        raise ValueError('API Key 不合法')
    auth=config.get('auth_type','bearer')
    if auth not in ('bearer','aep'):raise ValueError('未知认证方式')
    if urlsplit(base).hostname=='api.openai.com':
        if urlsplit(base).scheme!='https' or auth!='bearer':raise ValueError('OpenAI 官方接口需要 HTTPS 和 Bearer 认证')
        if not key.strip():raise ValueError('请填写 OpenAI API Key')
    if not isinstance(model,str) or not model.strip() or len(model)>200:
        raise ValueError('请填写模型名称')
    model=model.strip()
    source=g.payload()
    from game import forced_candidate
    forced=forced_candidate(g,source)
    if forced:return forced
    q=source['questions']['move']
    payload={'model':model,'input':json.dumps(source['state'],ensure_ascii=False),
             'questions':[{'type':'choice','name':'move','instructions':q['instructions'],
                           'choices':[{'value':k,'description':v} for k,v in q['criteria'].items()]}]}
    # Credentials go through stdin, not process arguments or evidence files.
    header=('X-AEP-CONSUMER-SECRET: ' if auth=='aep' else 'Authorization: Bearer ')+key
    config_text=('header = '+json.dumps(header)+'\n') if key else ''
    started=time.perf_counter()
    try:
        r=subprocess.run(['curl','--disable','--config','-','--silent','--show-error','--max-time','60',
                          '--max-filesize','2000000','--write-out','\n%{http_code}',
                          '--header','Content-Type: application/json','--data',json.dumps(payload),base],
                         input=config_text,text=True,capture_output=True,timeout=65)
        if r.returncode:raise RuntimeError('Decisions 网络错误或超时；本手未落子')
        body,status=r.stdout.rsplit('\n',1)
        if status!='200':
            hint={'400':'请求参数不兼容','401':'认证失败，请检查当前服务商的密钥','403':'接口拒绝访问','404':'接口或模型不可用','429':'频率或配额受限'}.get(status,'服务请求失败')
            raise RuntimeError(f'Decisions HTTP {status}：{hint}；本手未落子')
        data=json.loads(body)
        answers=data['answers']
        if len(answers)!=1:raise ValueError()
        a=answers[0]
        if a.get('type')=='refusal':raise RuntimeError('Decisions 拒绝回答；本手未落子')
        if a['name']!='move' or a['type']!='choice' or a['choice'] not in q['criteria']:raise ValueError()
        entries=a['probabilities'];probs={p['value']:p['probability'] for p in entries}
        valid=lambda v:type(v) in (int,float) and math.isfinite(v) and 0<=v<=1
        if len(entries)!=len(probs) or set(probs)!=set(q['criteria']):raise ValueError()
        if not all(valid(v) for v in probs.values()) or abs(sum(probs.values())-1)>.02 or not valid(a['confidence']):raise ValueError()
    except (KeyError,TypeError,ValueError,IndexError):
        raise RuntimeError('Decisions 返回无效候选或概率；本手未落子') from None
    except FileNotFoundError:
        raise RuntimeError('Decisions 接口需要系统安装 curl') from None
    except subprocess.TimeoutExpired:
        raise RuntimeError('Decisions 请求超时；本手未落子') from None
    usage=data.get('usage',{})
    usage={k:v for k,v in usage.items() if k in ('input_tokens','output_tokens','total_tokens') and type(v) is int} if isinstance(usage,dict) else {}
    decision={'provider':'llm','protocol':'decisions','model':model,'choice':a['choice'],
              'probabilities':probs,'confidence':a['confidence'],'usage':usage,
              'candidate_count':len(probs),'latency_ms':round((time.perf_counter()-started)*1000),
              'assistance':source['state'].get('candidate_policy','')}
    mapping={g.coord(i):i for i in g.legal()}
    if 'PASS' in q['criteria']:mapping['PASS']=None
    safe_answer={'type':'choice','name':'move','choice':a['choice'],'confidence':a['confidence'],
                 'probabilities':[{'value':k,'probability':v} for k,v in probs.items()]}
    return mapping[a['choice']],decision,payload,{'answers':[safe_answer],'usage':usage}
