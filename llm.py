"""User-configured Chat Completions adapter; credentials never enter game records."""
import ipaddress
import json
import time
from urllib.parse import urlsplit
from urllib.request import Request,build_opener,HTTPRedirectHandler,ProxyHandler
from urllib.error import HTTPError,URLError

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

def endpoint(base):
    if not isinstance(base,str) or len(base)>2048:raise ValueError('Base URL 不合法')
    u=urlsplit(base.strip())
    if u.scheme not in ('http','https') or not u.hostname or u.username or u.password or u.query or u.fragment:
        raise ValueError('Base URL 需为 http(s) 地址，不含账号、查询参数或片段')
    try:address=ipaddress.ip_address(u.hostname)
    except ValueError:address=None
    if address and (address.is_link_local or address.is_unspecified or address.is_multicast):raise ValueError('不支持此接口地址')
    if u.scheme=='http' and not (u.hostname=='localhost' or address and (address.is_private or address.is_loopback)):
        raise ValueError('公网接口请使用 HTTPS')
    base=base.strip().rstrip('/')
    return base if u.path.rstrip('/').endswith('/chat/completions') else base+'/chat/completions'

def choose_llm(g,config):
    if not isinstance(config,dict):raise ValueError('请先配置 LLM')
    url=endpoint(config.get('base_url',''))
    model=config.get('model','');key=config.get('api_key','')
    if not isinstance(model,str) or not model.strip() or len(model)>200:raise ValueError('请填写模型名称')
    if not isinstance(key,str) or len(key)>4096 or '\n' in key or '\r' in key:raise ValueError('API Key 不合法')
    source=g.payload();question=source['questions']['move'];criteria=question['criteria']
    payload={'model':model.strip(),'messages':[
        {'role':'system','content':'You are a board-game decision engine. Follow the supplied rules and select exactly one offered action. Return only a JSON object with a string field "choice", for example {"choice":"D4"}. No markdown or reasoning text.'},
        {'role':'user','content':json.dumps({'state':source['state'],'instructions':question['instructions'],'criteria':criteria},ensure_ascii=False)}], 'stream':False}
    if urlsplit(url).hostname=='api.deepseek.com':
        payload.update(response_format={'type':'json_object'},thinking={'type':'disabled'},max_tokens=128)
    headers={'Content-Type':'application/json'}
    if key:headers['Authorization']='Bearer '+key
    request=Request(url,data=json.dumps(payload).encode(),headers=headers,method='POST')
    started=time.perf_counter()
    hostname=urlsplit(url).hostname
    try:local=ipaddress.ip_address(hostname).is_private
    except ValueError:local=hostname=='localhost'
    opener=build_opener(NoRedirect(),ProxyHandler({})) if local else build_opener(NoRedirect())
    try:
        with opener.open(request,timeout=60) as r:
            raw=r.read(2_000_001)
            if len(raw)>2_000_000:raise RuntimeError('LLM 响应过大，本手未落子')
            data=json.loads(raw)
    except HTTPError as e:
        hint={400:'请求参数不兼容，请检查模型名及接口协议',401:'认证失败，请检查 API Key；切换服务商后需重新填写',402:'账户余额不足，请检查服务商 API 账户余额',403:'接口拒绝访问，请检查账户权限',404:'接口或模型不存在，请检查 Base URL 与模型 ID',422:'请求参数无法处理，请检查模型与接口兼容性',429:'请求频率或配额受限，请稍后手动重试',500:'模型服务内部错误',502:'模型服务网关错误',503:'模型服务暂不可用'}.get(e.code,'服务商返回错误')
        raise RuntimeError(f'LLM HTTP {e.code}：{hint}；本手未落子') from None
    except (URLError,TimeoutError):raise RuntimeError('LLM 网络错误或超时，本手未落子') from None
    except (ValueError,UnicodeDecodeError):raise RuntimeError('LLM 响应不是有效 JSON，本手未落子') from None
    try:
        if data['choices'][0].get('finish_reason')=='length':
            raise RuntimeError('LLM 输出被截断，本手未落子；请检查输出长度或思考模式设置')
        content=data['choices'][0]['message']['content']
        if not isinstance(content,str):raise ValueError()
        text=content.strip()
        if text.startswith('```') and text.endswith('```'):
            text=text.split('\n',1)[1].rsplit('```',1)[0].strip()
        parsed=json.loads(text);choice=parsed['choice']
        if not isinstance(choice,str) or choice not in criteria:raise ValueError()
    except (KeyError,IndexError,TypeError,ValueError):
        raise RuntimeError('LLM 未返回有效候选坐标 JSON，本手未落子；可手动重试') from None
    mapping={g.coord(i):i for i in g.legal()}
    if 'PASS' in criteria:mapping['PASS']=None
    usage=data.get('usage',{})
    safe_usage={k:v for k,v in usage.items() if k in ('prompt_tokens','completion_tokens','total_tokens') and type(v) is int} if isinstance(usage,dict) else {}
    decision=dict(provider='llm',model=model.strip(),choice=choice,confidence=None,probabilities=None,latency_ms=round((time.perf_counter()-started)*1000),usage=safe_usage,candidate_count=len(criteria),assistance=source['state'].get('candidate_policy',''))
    # Never return arbitrary upstream fields, credentials or the endpoint URL.
    return mapping[choice],decision,payload,{'choice':choice,'usage':safe_usage}
