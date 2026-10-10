"""Color-swapped Go probe, fixed candidates, no retries or fallback."""
import argparse,json,os,statistics
from pathlib import Path
from datetime import datetime,timezone
from game import Game
from server import choose_jev
from decisions import choose_decisions

def run():
    parser=argparse.ArgumentParser()
    parser.add_argument('--live',action='store_true')
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    if not args.live:parser.error('Use --live for billable requests')
    for key in ('TYPESAFE_API_KEY','AEP_CONSUMER_SECRET','OPENAI_API_BASE'):
        if not os.environ.get(key):parser.error('Missing '+key)
    out=Path(args.output);out.mkdir(parents=True,exist_ok=False)
    config={'auth_type':'aep','base_url':os.environ['OPENAI_API_BASE'],'model':'gpt-6-luna','api_key':os.environ['AEP_CONSUMER_SECRET']}
    plan={'created_at':datetime.now(timezone.utc).isoformat(),'size':5,'games':2,'max_plies':100,'black_order':['jev','decisions'],'komi':6.5,'models':['jev-1.13.0','gpt-6-luna'],'rules':'positional superko, no suicide, two passes end; area without dead-stone adjudication','assistance':'same state, instructions, legal candidates and computed tactical features','errors':'stop game, no retry/fallback; incomplete games have no winner'}
    (out/'plan.json').write_text(json.dumps(plan,indent=2))
    games=[]
    for num,black in enumerate(plan['black_order'],1):
        g=Game(5);records=[];error=None
        for ply in range(plan['max_plies']):
            if g.over:break
            provider=black if g.turn==1 else ('decisions' if black=='jev' else 'jev')
            try:
                move,d,req,resp=choose_jev(g) if provider=='jev' else choose_decisions(g,config)
                g.play(move)
                records.append({'ply':ply+1,'provider':provider,'decision':d,'request':req,'response':resp})
                print(num,ply+1,provider,d['choice'],d['latency_ms'],flush=True)
            except Exception as e:
                error={'provider':provider,'ply':ply+1,'message':str(e)}
            winner=(black if g.area()['lead']>0 else ('decisions' if black=='jev' else 'jev')) if g.over else None
            result={'black':black,'complete':g.over,'winner':winner,'plies':len(g.moves),'area':g.area(),'error':error,'game':g.public(),'records':records}
            (out/f'game-{num}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
            if error:break
        games.append(result)
    metrics={}
    for provider in ('jev','decisions'):
        ds=[r['decision'] for g in games for r in g['records'] if r['provider']==provider and not r['decision'].get('forced')]
        metrics[provider]={'successful_calls':len(ds),'median_latency_ms':statistics.median(d['latency_ms'] for d in ds) if ds else None,'input_tokens':sum(d['usage'].get('input_tokens',0) for d in ds),'output_tokens':sum(d['usage'].get('output_tokens',0) for d in ds),'wins':sum(g['winner']==provider for g in games)}
    summary={'games':[{k:v for k,v in g.items() if k not in ('game','records')} for g in games],'metrics':metrics}
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    print(json.dumps(summary,ensure_ascii=False),flush=True)
if __name__=='__main__':run()
