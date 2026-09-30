"""Two capped matches through the demo HTTP API. Set DEEPSEEK_API_KEY; no secrets saved."""
import argparse,datetime,json,os,statistics,subprocess,time
from pathlib import Path
from urllib.request import Request,build_opener,ProxyHandler
from urllib.error import HTTPError
from game import replay

parser=argparse.ArgumentParser()
parser.add_argument('--live',action='store_true')
parser.add_argument('--url',default='http://127.0.0.1:8769')
parser.add_argument('--out',required=True)
args=parser.parse_args()
if not args.live:parser.error('--live explicitly enables up to 60 paid model requests')
key=os.environ.get('DEEPSEEK_API_KEY')
if not key:parser.error('Set DEEPSEEK_API_KEY')
out=Path(args.out);out.mkdir(parents=True,exist_ok=False)
opener=build_opener(ProxyHandler({}))
def save(name,data):
    text=json.dumps(data,ensure_ascii=False,indent=2)
    if key in text:raise RuntimeError('Credential found in output')
    (out/name).write_text(text)
plan=dict(started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),implementation_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),board_size=15,kind='gomoku',rules='freestyle, alternating, >=5 wins, no passes/captures/forbidden moves',max_rounds_per_game=15,max_plies_per_game=30,models={'llm':'deepseek-flash','jev':'jev-1.13.0'},llm_settings={'thinking':'disabled','response_format':'json_object','max_tokens':128},black_providers=['llm','jev'],assistance='Same state, instructions and criteria construction; code filters immediate wins then blocks, otherwise all legal moves with contiguous run/open end features',stopping='Stop on win, full board, 30 plies or first error; no automatic retries; no parameter tuning between games',limitations='Two games only; capped unfinished games are not draws; no equal compute budget; LLM model ID may be a provider alias')
save('plan.json',plan)
matches=[]
for black in plan['black_providers']:
    game=replay(15,[],kind='gomoku');records=[];error=None
    for ply in range(30):
        if game.over:break
        provider=black if game.turn==1 else ('jev' if black=='llm' else 'llm')
        payload=dict(kind='gomoku',size=15,moves=game.moves,arena=True,black_provider=black,mode=provider)
        if provider=='llm':payload['llm']=dict(base_url='https://api.deepseek.com/v1',model='deepseek-flash',api_key=key)
        started=time.perf_counter()
        try:
            req=Request(args.url+'/api/decision',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
            with opener.open(req,timeout=90) as response:data=json.load(response)
            updated=data['game'];expected=replay(15,game.moves,kind='gomoku');expected.play(updated['moves'][-1])
            assert updated==json.loads(json.dumps(expected.public())),'Returned board differs from replay'
            assert updated['moves'][:-1]==game.moves and len(updated['moves'])==ply+1
            assert data['decision']['provider']==provider
            game=expected
            record={'ply':ply+1,'color':'black' if ply%2==0 else 'white','http_elapsed_ms':round((time.perf_counter()-started)*1000),**data}
            records.append(record)
            print(f"{black}-black ply {ply+1}: {provider} {data['decision']['choice']} ({data['decision']['latency_ms']}ms)",flush=True)
        except Exception as exc:
            if isinstance(exc,HTTPError):detail=exc.read(1000).decode(errors='replace')
            else:detail=str(exc)
            error={'ply':ply+1,'provider':provider,'detail':detail.replace(key,'[REDACTED]')};break
        finally:
            save(f'{black}-black.json',dict(black_provider=black,records=records,final_game=game.public(),error=error))
    winner=black if game.winner==1 else ('jev' if black=='llm' else 'llm') if game.winner==2 else None
    matches.append(dict(black_provider=black,plies=len(game.moves),completed_rounds=len(game.moves)//2,winner=winner,winner_color=game.winner or None,stop_reason='error' if error else 'win' if game.winner else 'draw_full_board' if game.over else 'ply_limit',error=error,records=records))
summary={'plan':plan,'matches':[{k:v for k,v in m.items() if k!='records'} for m in matches],'providers':{}}
for provider in ('llm','jev'):
    rs=[r for m in matches for r in m['records'] if r['decision']['provider']==provider]
    lat=[r['decision']['latency_ms'] for r in rs]
    summary['providers'][provider]={'successful_calls':len(rs),'median_latency_ms':statistics.median(lat) if lat else None,'total_latency_ms':sum(lat),'single_candidate_calls':sum(r['decision']['candidate_count']==1 for r in rs),'filtered_tactical_calls':sum(r['decision']['assistance'].startswith('代码筛选') for r in rs)}
summary['finished_at']=datetime.datetime.now(datetime.timezone.utc).isoformat()
save('summary.json',summary)
print(json.dumps({k:v for k,v in summary.items() if k!='plan'},ensure_ascii=False),flush=True)
