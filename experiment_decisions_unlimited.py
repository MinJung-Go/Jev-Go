"""50 original Go games, checkpointed, no move limit; resume from saved boards."""
import argparse,collections,hashlib,json,os,signal,statistics,threading,time
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
from pathlib import Path
from game import Game
from server import choose_jev
from decisions import choose_decisions

STOP=threading.Event()
def save(path,data):
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2));tmp.replace(path)
def board_from_moves(moves):
    g=Game(5)
    for move in moves:g.play(move)
    return g

def play(slot,out,config):
    path=out/f'game-{slot:02d}.json'
    result=json.loads(path.read_text()) if path.exists() else {'slot':slot,'black':'jev' if slot%2 else 'decisions','records':[],'game':Game(5).public(),'complete':False,'winner':None,'errors':[]}
    if result['complete']:return result
    g=board_from_moves(result['game']['moves']);records=result['records'];black=result['black'];consecutive_errors=0
    while not g.over and not STOP.is_set():
        provider=black if g.turn==1 else ('decisions' if black=='jev' else 'jev')
        started=time.perf_counter()
        try:
            move,d,req,resp=choose_jev(g) if provider=='jev' else choose_decisions(g,config)
            g.play(move);records.append({'ply':len(g.moves),'provider':provider,'decision':d,'request':req,'response':resp});consecutive_errors=0
        except Exception as e:
            err={'ply':len(g.moves)+1,'provider':provider,'type':type(e).__name__,'message':str(e),'elapsed_ms':round((time.perf_counter()-started)*1000)}
            result.setdefault('errors',[]).append(err);consecutive_errors+=1
            print('REQUEST_ERROR',slot,json.dumps(err,ensure_ascii=False),flush=True)
        result.update(plies=len(g.moves),complete=g.over,game=g.public(),area=g.area(),error=None)
        if g.over:result['winner']=black if g.area()['lead']>0 else ('decisions' if black=='jev' else 'jev')
        save(path,result)
        if consecutive_errors>=5:
            result['error']={'message':'Five consecutive request failures; checkpoint retained, no winner'};save(path,result);return result
        if consecutive_errors:STOP.wait(2)
    if g.over:print('GAME_COMPLETE',slot,black,result['winner'],len(g.moves),g.area()['lead'],flush=True)
    return result

def summarize(out):
    games=[json.loads(p.read_text()) for p in sorted(out.glob('game-*.json'))]
    complete=[g for g in games if g['complete']]
    metrics={}
    for provider in ('jev','decisions'):
        ds=[r['decision'] for g in complete for r in g['records'] if r['provider']==provider and not r['decision'].get('forced')];ls=sorted(d['latency_ms'] for d in ds)
        metrics[provider]={'successful_calls':len(ds),'median_latency_ms':statistics.median(ls) if ls else None,'p95_latency_ms':ls[__import__('math').ceil(len(ls)*.95)-1] if ls else None,'total_latency_ms':sum(ls),'input_tokens':sum(d['usage'].get('input_tokens',0) for d in ds),'output_tokens':sum(d['usage'].get('output_tokens',0) for d in ds),'forced_actions':sum(r['provider']==provider and bool(r['decision'].get('forced')) for g in complete for r in g['records']),'wins':sum(g['winner']==provider for g in complete),'wins_as_black':sum(g['winner']==provider and g['black']==provider for g in complete),'wins_as_white':sum(g['winner']==provider and g['black']!=provider for g in complete),'failed_requests':sum(e['provider']==provider for g in games for e in g.get('errors',[]))}
    summary={'completed':len(complete),'unfinished':len(games)-len(complete),'jev_black_completed':sum(g['black']=='jev' for g in complete),'decisions_black_completed':sum(g['black']=='decisions' for g in complete),'unique_completed_move_sequences':len({tuple(g['game']['moves']) for g in complete}),'metrics':metrics,'games':[{k:v for k,v in g.items() if k not in ('records','game')} for g in games]}
    save(out/'summary.json',summary);return summary

def main():
    p=argparse.ArgumentParser();p.add_argument('--live',action='store_true');p.add_argument('--output',required=True);p.add_argument('--seed-from');p.add_argument('--workers',type=int,default=4);args=p.parse_args()
    if not args.live:p.error('--live is required')
    for key in ('TYPESAFE_API_KEY','AEP_CONSUMER_SECRET','OPENAI_API_BASE'):
        if not os.environ.get(key):p.error('Missing '+key)
    out=Path(args.output)
    if not out.exists():
        out.mkdir(parents=True)
        source=Path(args.seed_from) if args.seed_from else None
        extras=[]
        if source:
            for path in source.glob('game-*-attempt-01.json'):
                d=json.loads(path.read_text());d['initial_interruption']=d.pop('error',None);d['errors']=[];d['seed_from']=str(path);save(out/f"game-{d['slot']:02d}.json",d)
            extras=[str(p) for p in source.glob('game-*-attempt-*.json') if not p.name.endswith('-attempt-01.json')]
        save(out/'plan.json',{'created_at':datetime.now(timezone.utc).isoformat(),'games':50,'size':5,'max_plies':None,'black_order':'odd Jev, even AEP: 25 each','models':['jev-1.13.0','gpt-6-luna'],'komi':6.5,'workers':args.workers,'ending':'two consecutive passes only; no move cutoff','resume_policy':'continue original first attempts from saved board; retain completed originals; exclude previous replacement games','excluded_replacement_files':extras,'request_errors':'save error, retry same position; pause after five consecutive errors; never declare loss for error','assistance':'unchanged shared Game.payload, no search, singleton actions by rules for both sides','source_sha256':{n:hashlib.sha256(Path(n).read_bytes()).hexdigest() for n in ('game.py','server.py','decisions.py','experiment_decisions_unlimited.py')}})
    signal.signal(signal.SIGTERM,lambda *_:STOP.set());signal.signal(signal.SIGINT,lambda *_:STOP.set())
    config={'auth_type':'aep','base_url':os.environ['OPENAI_API_BASE'],'model':'gpt-6-luna','api_key':os.environ['AEP_CONSUMER_SECRET']}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures=[pool.submit(play,i,out,config) for i in range(1,51)]
        for f in as_completed(futures):f.result()
    summary=summarize(out);print(json.dumps({k:v for k,v in summary.items() if k!='games'},ensure_ascii=False),flush=True)
if __name__=='__main__':main()
