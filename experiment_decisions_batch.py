"""Live balanced Go batch; preserve failed attempts and checkpoint every move."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime,timezone
import hashlib,json,os,statistics,time
from pathlib import Path
from game import Game
from server import choose_jev
from decisions import choose_decisions


def save(path,data):
    tmp=path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2));tmp.replace(path)


def play_slot(slot,out,config):
    black='jev' if slot%2 else 'decisions'
    existing=sorted(out.glob(f'game-{slot:02d}-attempt-*.json'))
    for path in existing:
        old=json.loads(path.read_text())
        if old.get('complete'):return old
    for attempt in range(len(existing)+1,len(existing)+6):
        g=Game(5);records=[];error=None
        path=out/f'game-{slot:02d}-attempt-{attempt:02d}.json'
        started=time.perf_counter()
        result={'slot':slot,'attempt':attempt,'black':black,'complete':False,'winner':None,'records':records}
        for ply in range(100):
            if g.over:break
            provider=black if g.turn==1 else ('decisions' if black=='jev' else 'jev')
            before=time.perf_counter()
            try:
                move,d,req,resp=choose_jev(g) if provider=='jev' else choose_decisions(g,config)
                g.play(move)
                records.append({'ply':ply+1,'provider':provider,'decision':d,'request':req,'response':resp})
            except Exception as e:
                error={'ply':ply+1,'provider':provider,'type':type(e).__name__,'message':str(e),'elapsed_ms':round((time.perf_counter()-before)*1000)}
            result.update(complete=g.over,plies=len(g.moves),game=g.public(),area=g.area(),error=error,elapsed_s=round(time.perf_counter()-started,3))
            if g.over:result['winner']=black if g.area()['lead']>0 else ('decisions' if black=='jev' else 'jev')
            save(path,result)
            if error:break
        if not g.over and not error:
            result['error']={'type':'PlyLimit','message':'100-ply limit; no winner declared'};save(path,result)
        print(json.dumps({k:v for k,v in result.items() if k not in ('records','game')},ensure_ascii=False),flush=True)
        if g.over:return result
        time.sleep(2)
    return result


def summarize(out):
    attempts=[json.loads(p.read_text()) for p in sorted(out.glob('game-*-attempt-*.json'))]
    complete=[g for g in attempts if g['complete']]
    metrics={}
    for provider in ('jev','decisions'):
        def stats(games):
            ds=[r['decision'] for g in games for r in g['records'] if r['provider']==provider and not r['decision'].get('forced')]
            ls=sorted(d['latency_ms'] for d in ds)
            return {'successful_calls':len(ds),'median_latency_ms':statistics.median(ls) if ls else None,'p95_latency_ms':ls[max(0,__import__('math').ceil(len(ls)*.95)-1)] if ls else None,'total_latency_ms':sum(ls),'input_tokens':sum(d['usage'].get('input_tokens',0) for d in ds),'output_tokens':sum(d['usage'].get('output_tokens',0) for d in ds),'forced_actions':sum(r['provider']==provider and bool(r['decision'].get('forced')) for g in games for r in g['records'])}
        metrics[provider]={'completed_games':stats(complete),'all_attempts':stats(attempts),'wins':sum(g['winner']==provider for g in complete),'wins_as_black':sum(g['winner']==provider and g['black']==provider for g in complete),'wins_as_white':sum(g['winner']==provider and g['black']!=provider for g in complete),'failed_calls':sum(g.get('error',{}).get('provider')==provider for g in attempts if g.get('error'))}
    summary={'attempts':len(attempts),'completed':len(complete),'unfinished':len(attempts)-len(complete),'jev_black_completed':sum(g['black']=='jev' for g in complete),'decisions_black_completed':sum(g['black']=='decisions' for g in complete),'unique_completed_move_sequences':len({tuple(g['game']['moves']) for g in complete}),'metrics':metrics,'games':[{k:v for k,v in g.items() if k not in ('records','game')} for g in attempts]}
    save(out/'summary.json',summary)
    return summary


def main():
    p=argparse.ArgumentParser();p.add_argument('--live',action='store_true');p.add_argument('--output',required=True);p.add_argument('--resume',action='store_true');p.add_argument('--workers',type=int,default=4);args=p.parse_args()
    if not args.live:p.error('--live is required')
    for name in ('TYPESAFE_API_KEY','AEP_CONSUMER_SECRET','OPENAI_API_BASE'):
        if not os.environ.get(name):p.error('Missing '+name)
    out=Path(args.output)
    if args.resume:
        assert (out/'plan.json').exists()
    else:
        out.mkdir(parents=True,exist_ok=False)
        save(out/'plan.json',{'created_at':datetime.now(timezone.utc).isoformat(),'target_completed_games':50,'size':5,'games_per_black_provider':25,'max_plies':100,'max_attempts_per_slot_per_run':5,'workers':args.workers,'models':['jev-1.13.0','gpt-6-luna'],'komi':6.5,'rules':'positional superko, no suicide, two passes end; area without dead-stone adjudication','assistance':'unchanged shared Game.payload: same state, candidate order, instructions, computed tactical features; no tree search','singleton':'same rule for both sides; sole candidate executed by rules, not counted as model call','failure_policy':'end failed attempt, preserve it; restart same-color slot from empty board; success means completed, not winner-dependent','scope':'50 NEW games, excluding earlier smoke and two-game experiment','source_sha256':{n:hashlib.sha256(Path(n).read_bytes()).hexdigest() for n in ('game.py','server.py','decisions.py','experiment_decisions_batch.py')}})
    config={'auth_type':'aep','base_url':os.environ['OPENAI_API_BASE'],'model':'gpt-6-luna','api_key':os.environ['AEP_CONSUMER_SECRET']}
    started=time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures=[pool.submit(play_slot,slot,out,config) for slot in range(1,51)]
        finished=0
        for f in as_completed(futures):
            f.result();finished+=1
            print('SLOTS_FINISHED',finished,'/50',flush=True)
    summary=summarize(out);summary['run_wall_seconds']=round(time.perf_counter()-started,2);save(out/'summary.json',summary)
    print(json.dumps({k:v for k,v in summary.items() if k!='games'},ensure_ascii=False),flush=True)

if __name__=='__main__':main()
