"""Small, predeclared exploratory probe; not a strength benchmark. Uses live paid API."""
import argparse,json,os,statistics,time
from datetime import datetime,timezone
from pathlib import Path
from unittest.mock import patch
from game import Game
from server import choose_jev

OUT=Path(__file__).parent/'evidence'

def rotate(board,n):return [board[(n-1-c)*n+r] for r in range(n) for c in range(n)]

def run():
    OUT.mkdir(exist_ok=True)
    tests=[]
    fixtures=[('capture',['01000','12100','00000','00000','00000']),
              ('rescue',['02000','21200','00000','00000','00000'])]
    for name,rows in fixtures:
        board=[int(c) for r in rows for c in r]
        for rot in range(4):
            g=Game(5);g.board=board.copy();g.seen={tuple(board)}
            field='captures' if name=='capture' else 'rescued_stones'
            expected=[c for c,f in g.options().items() if f[field]>0]
            tests.append((f'{name}-rotation-{rot}',g,expected));board=rotate(board,5)
    plan={'created_at':datetime.now(timezone.utc).isoformat(),'model':'jev-1.13.0',
          'cases':[{'name':n,'board':g.board,'acceptable_moves':ex} for n,g,ex in tests],
          'conditions':['raw-board','computed-features'],'repeats':1,
          'warning':'Eight orientations of two handcrafted situations; not eight independent tactical concepts. No prompts tuned after results.',
          'match':{'size':5,'games':2,'max_plies':60,'opponent':'handcrafted local rules','jev_colors':['white','black']}}
    (OUT/'experiment-plan.json').write_text(json.dumps(plan,indent=2))
    records=[]
    for name,g,expected in tests:
        for condition in plan['conditions']:
            payload=g.payload()
            if condition=='raw-board':
                payload['state']['note']='All offered placements are legal. No tactical features or tree search are supplied.'
                payload['questions']['move']['criteria']={k:('Pass.' if k=='PASS' else f'Play at {k}.') for k in payload['questions']['move']['criteria']}
            try:
                with patch.object(g,'payload',return_value=payload): move,d,req,resp=choose_jev(g)
                record={'case':name,'condition':condition,'expected':expected,'success':g.coord(move) in expected,'decision':d,'request':req,'response':resp}
            except Exception as e:record={'case':name,'condition':condition,'expected':expected,'success':False,'error':str(e)}
            records.append(record);(OUT/'tactics.json').write_text(json.dumps(records,indent=2))
            print(name,condition,record.get('decision',{}).get('choice'),record['success'],flush=True)
    matches=[]
    for color in (2,1):
        g=Game(5);entries=[];error=None
        for ply in range(60):
            if g.over:break
            if g.turn==color:
                try:move,d,req,resp=choose_jev(g)
                except Exception as e:error=str(e);break
                entries.append({'ply':ply+1,'decision':d,'request':req,'response':resp})
            else:move=g.local_move()
            g.play(move)
            (OUT/f'match-jev-{color}.json').write_text(json.dumps({'jev_color':color,'game':g.public(),'records':entries,'error':error},indent=2))
        result={'jev_color':color,'game':g.public(),'records':entries,'error':error,'complete':g.over,
                'note':'Area counts remaining stones; no dead-stone adjudication. If ply limit reached, no winner declared.'}
        matches.append(result);(OUT/f'match-jev-{color}.json').write_text(json.dumps(result,indent=2))
        print('match',color,'plies',len(g.moves),'complete',g.over,'area',g.area(),'error',error,flush=True)
    decisions=[x['decision'] for x in records if 'decision'in x]+[x['decision'] for m in matches for x in m['records']]
    summary={'conditions':{c:{'hits':sum(r['success'] for r in records if r['condition']==c),'total':sum(r['condition']==c for r in records),'errors':sum('error'in r for r in records if r['condition']==c)} for c in plan['conditions']},
        'successful_api_calls':len(decisions),'median_latency_ms':statistics.median(d['latency_ms'] for d in decisions),
        'input_tokens':sum(d['usage'].get('input_tokens',0) for d in decisions),
        'matches':[{'jev_color':m['jev_color'],'plies':len(m['game']['moves']),'complete':m['complete'],'area':m['game']['area'],'error':m['error']} for m in matches]}
    summary['estimated_input_cost_usd']=summary['input_tokens']/1e6*.042
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--live',action='store_true',help='Allow real, billable API calls (up to 76 in this run)');args=parser.parse_args()
    if not args.live:parser.error('Pass --live to authorize API calls')
    if not os.environ.get('TYPESAFE_API_KEY'):parser.error('Set TYPESAFE_API_KEY server-side')
    run()
