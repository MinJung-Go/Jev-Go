const $=id=>document.getElementById(id);
let game=null,busy=false,records=[],ready=false,llmConfig=null,running=false;
const arena=()=>$('mode').value==='arena';
const providerName=p=>p==='llm'?(llmConfig?.model||'LLM'):p==='jev'?'Jev':'本地规则';
const currentProvider=()=>arena()?(game.turn===1?$('black-provider').value:($('black-provider').value==='llm'?'jev':'llm')):$('mode').value;
const cols='ABCDEFGHJKLMNOPQRST';
const coord=i=>i===null?'停手':cols[i%game.size]+(game.size-Math.floor(i/game.size));
function status(message,error=false){$('status').textContent=message;$('status').classList.toggle('error',error)}
async function api(path,data){const r=await fetch('/api/'+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});const d=await r.json();if(!r.ok)throw Error(d.error||'请求失败');return d}
function body(){return {kind:game.kind,size:game.size,moves:game.moves}}
function draw(){
 if(!game)return;
 const n=game.size,board=$('board'),human=$('mode').value==='human',go=game.kind==='go';
 let lines='';for(let i=0;i<n;i++){const a=i*100/(n-1);lines+=`<line x1="${a}" y1="0" x2="${a}" y2="100"/><line x1="0" y1="${a}" x2="100" y2="${a}"/>`}
 board.innerHTML=`<svg viewBox="-0.5 -0.5 101 101" aria-hidden="true"><g stroke="#796644" stroke-width=".19">${lines}</g><circle cx="50" cy="50" r=".5" fill="#796644"/></svg>`;
 for(let i=0;i<n;i++){for(const [label,x,y] of [[cols[i],i*100/(n-1),-5],[String(n-i),-5,i*100/(n-1)]]){const el=document.createElement('span');el.className='coordinate';el.textContent=label;el.style.left=x+'%';el.style.top=y+'%';board.append(el)}}
 const legal=new Set(game.legal);
 for(let i=0;i<n*n;i++){const b=document.createElement('button'),v=game.board[i];b.className='point '+(v===1?'black':v===2?'white':'empty');if(i===game.moves.at(-1))b.classList.add('last');b.style.left=(i%n)*100/(n-1)+'%';b.style.top=Math.floor(i/n)*100/(n-1)+'%';b.style.width=b.style.height=82/n+'%';b.setAttribute('aria-label',coord(i)+(v===1?' 黑棋':v===2?' 白棋':' 空点'));b.dataset.index=i;b.disabled=busy||running||arena()||game.over||!legal.has(i)||(!human&&game.turn===2);b.onclick=()=>play(i);board.appendChild(b)}
 $('turn').textContent=game.over?'对局结束':busy?(game.turn===2&&!human?'白棋正在思考…':'正在处理…'):game.turn===1?'轮到黑棋':'轮到白棋';
 $('move-count').textContent=`第 ${game.moves.length} 手`;
 $('captures').textContent=go?`提子 ${game.captures[1]} : ${game.captures[2]}`:'自由五子棋 · 连五获胜';
 $('black-label').textContent=arena()?providerName($('black-provider').value):human?'同机玩家':'你';
 $('opponent-label').textContent=arena()?providerName($('black-provider').value==='llm'?'jev':'llm'):human?'同机玩家':providerName($('mode').value);
 $('arena-settings').hidden=!arena();
 $('auto').textContent=running?'暂停对战':'开始对战';$('auto').disabled=!running&&(busy||game.over||!llmConfig||!ready);
 $('step').disabled=running||busy||game.over||!llmConfig||!ready;
 for(const id of ['black-provider','step-limit','llm-base','llm-model','llm-key','apply-llm','clear-llm','test-llm','llm-preset'])$(id).disabled=busy||running;
 for(const id of ['pass','undo','reset','mode','size','kind'])$(id).disabled=busy||running;
 $('pass').hidden=!go||arena();$('pass').disabled=busy||running||game.over||(!human&&game.turn===2);$('undo').disabled=busy||running||!game.moves.length;
 $('retry').hidden=busy||running||arena()||game.over||human||game.turn!==2;
 $('history').replaceChildren();game.moves.slice(-8).forEach((move,k)=>{const idx=Math.max(0,game.moves.length-8)+k;const li=document.createElement('li');li.textContent=`${idx+1}. ${idx%2===0?'黑':'白'} ${coord(move)}`;if(move===null)li.className='pass';$('history').append(li)});
 $('rules').textContent=go?'围棋：黑先，提子、禁自杀、全局同形禁着。连续两次停手结束，白贴6.5；不自动判死，需先提净死子。开局候选限制停手，最多500手。':'自由五子棋：黑先、每人一手；横竖斜连续五颗及以上获胜，无禁手、不提子、不允许停手，满盘未成五为和棋。';
 if(game.over){if(go){const a=game.area;status(`盘面面积：黑 ${a.black}，白 ${a.white} + 6.5。${a.lead>0?'黑':'白'}领先 ${Math.abs(a.lead)} 点；未自动判死。`)}else status(game.winner?`${game.winner===1?'黑棋':'白棋'}连成五子，获胜！`:'棋盘已满，和棋。')}
}
function decision(d){$('choice').textContent=d?.choice==='PASS'?'停手':d?.choice||'—';$('provider').textContent=d?(d.provider!=='local'?d.model:'本地规则 · 非模型'):'等待落子';$('confidence').textContent=d?.confidence==null?'—':(100*d.confidence).toFixed(1)+'%';$('latency').textContent=d?.latency_ms==null?'—':d.latency_ms+' ms';$('alternatives').textContent=d?.probabilities?'候选：'+Object.entries(d.probabilities).sort((a,b)=>b[1]-a[1]).slice(0,3).map(([k,v])=>`${k} ${(v*100).toFixed(1)}%`).join(' / '):'';$('assistance').textContent=d?.assistance||''}
async function modelMoveLocked(){
 const provider=currentProvider();
 if(provider==='llm'&&!llmConfig)throw Error('请先填写并应用 LLM 配置');
 const color=game.turn===1?'黑':'白';draw();status(`${color}棋 ${providerName(provider)} 正在选择落点…`);
 const r=await api('decision',{...body(),mode:provider,arena:arena(),black_provider:$('black-provider').value,...(provider==='llm'?{llm:llmConfig}:{})});
 game=r.game;records.push({move_number:game.moves.length,...r});decision(r.decision);
 status(`${color}棋 ${providerName(provider)} ${r.decision.choice==='PASS'?'停手，没有放置棋子':'落在 '+r.decision.choice}。`);
}
async function respondLocked(){if(!game.over&&game.turn===2&&$('mode').value!=='human')await modelMoveLocked()}
async function arenaStep(){
 if(busy||running||!arena()||game.over)return;
 busy=true;draw();try{await modelMoveLocked()}catch(e){status(e.message,true)}finally{busy=false;draw()}
}
async function autoPlay(){
 if(running){running=false;$('auto').textContent='等待当前手完成…';$('auto').disabled=true;return}
 if(busy||!arena()||game.over)return;
 const limit=Number($('step-limit').value);
 if(!Number.isInteger(limit)||limit<1||limit>100){status('自动运行手数需为1到100',true);return}
 running=true;let count=0,failed=false;
 try{
  while(running&&!game.over&&count<limit){busy=true;draw();await modelMoveLocked();count++;busy=false;draw();await new Promise(r=>setTimeout(r,350))}
 }catch(e){failed=true;status(e.message+'；对战已暂停。',true)}
 finally{running=false;busy=false;draw();if(!failed&&!game.over)status(`已暂停，本次完成 ${count} 手。可以继续或单步。`)}
}
async function play(move){
 if(busy||running||arena()||!game||game.over||($('mode').value!=='human'&&game.turn!==1))return;
 busy=true;draw();try{game=await api('state',{...body(),moves:[...game.moves,move]});status(`${game.turn===2?'黑':'白'}棋${move===null?'停手':'落在 '+coord(move)}。`);await respondLocked()}catch(e){status(e.message,true)}finally{busy=false;draw()}
}
async function reset(){
 if(busy||running)return;busy=true;draw();try{game=await api('state',{kind:$('kind').value,size:Number($('size').value),moves:[]});records=[];decision(null);status(arena()?'LLM 对战 Jev：应用配置后，点击走一手或开始对战。':$('mode').value==='human'?'双人同机：黑白交替落子。':`${providerName($('mode').value)} 模式：你执黑，等待白棋回应后再下。`)}catch(e){status(e.message,true)}finally{busy=false;draw()}
}
$('pass').onclick=()=>play(null);$('reset').onclick=reset;$('mode').onchange=reset;$('size').onchange=reset;
$('kind').onchange=()=>{const sizes=$('kind').value==='go'?[19,13,9,5]:[15,9];$('size').replaceChildren(...sizes.map(n=>new Option(`${n} × ${n}`,n)));reset()};
$('retry').onclick=async()=>{if(busy||game.turn!==2||game.over)return;busy=true;try{await respondLocked()}catch(e){status(e.message,true)}finally{busy=false;draw()}};
$('undo').onclick=async()=>{if(busy||running||!game.moves.length)return;busy=true;draw();try{let m=game.moves.slice(0,-1);if(!arena()&&$('mode').value!=='human'&&m.length%2===1)m=m.slice(0,-1);game=await api('state',{...body(),moves:m});records=records.filter(r=>r.move_number<=m.length);decision(records.at(-1)?.decision);status('已退回上一回合。')}catch(e){status(e.message,true)}finally{busy=false;draw()}};
$('export').onclick=()=>{const blob=new Blob([JSON.stringify({format:'jev-board-v3',black_provider:arena()?$('black-provider').value:'human',exported_at:new Date().toISOString(),mode:$('mode').value,rules:game.kind==='go'?'positional-superko,no-suicide,area,white-komi-6.5,no-dead-stone-adjudication':'freestyle-gomoku,5-or-more,no-captures,no-pass',game,records},null,2)],{type:'application/json'});const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='jev-'+game.kind+'-record.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)};
$('step').onclick=arenaStep;$('auto').onclick=autoPlay;$('black-provider').onchange=reset;
function applyLLM(){
 const base=$('llm-base').value.trim().replace(/\/+$/,''),model=$('llm-model').value.trim();
 if(!base||!model){$('llm-status').textContent='请填写 Base URL 和模型名';return false}
 try{const u=new URL(base);if(!['http:','https:'].includes(u.protocol)||u.username||u.password||u.search||u.hash)throw Error()}catch(e){$('llm-status').textContent='接口地址格式不正确';return false}
 const sameEndpoint=llmConfig?.base_url===base;
 const key=$('llm-key').value.trim()||(sameEndpoint?llmConfig.api_key:'');
 if(!key&&['api.deepseek.com','api.openai.com'].includes(new URL(base).hostname)){$('llm-status').textContent='请填写该服务商的 API Key';return false}
 llmConfig={base_url:base,model,api_key:key};$('llm-key').value='';$('llm-key').placeholder=key?'已配置；留空沿用同一地址的密钥':'本地无认证服务可留空';
 $('llm-status').textContent=`已应用 ${model}。可先测试连接，再选择 LLM 对战 Jev。配置仅保留本页，刷新后清除。`;draw();return true;
}
$('apply-llm').onclick=()=>{if(!busy&&!running)applyLLM()};
$('clear-llm').onclick=()=>{if(busy||running)return;llmConfig=null;$('llm-key').value='';$('llm-key').placeholder='';$('llm-status').textContent='配置已清除。';draw()};
$('llm-preset').onchange=()=>{
 if(busy||running)return;
 llmConfig=null;$('llm-key').value='';$('llm-key').placeholder='请填写当前服务商的密钥';
 const provider=$('llm-preset').value;
 $('llm-base').value=provider==='deepseek'?'https://api.deepseek.com/v1':provider==='openai'?'https://api.openai.com/v1':'';
 $('llm-model').value=provider==='deepseek'?'deepseek-flash':'';
 $('llm-status').textContent='已切换服务商，请填写模型与密钥，重新应用配置。';draw();
};
$('test-llm').onclick=async()=>{
 if(busy||running||!applyLLM())return;
 busy=true;draw();$('llm-status').textContent='正在测试接口…';
 try{const d=await api('llm-test',{llm:llmConfig});$('llm-status').textContent=`连接成功：${d.model}，${d.latency_ms} ms。可以走一手或开始对战。`}
 catch(e){$('llm-status').textContent=e.message}
 finally{busy=false;draw()}
};
(async()=>{try{const c=await(await fetch('/api/config')).json();ready=c.jev_ready;$('mode').querySelector('[value="jev"]').disabled=!ready;$('connection').textContent=ready?'Jev 已连接配置 · '+c.model:'未配置 Jev 凭据，可先体验本地规则。';if(ready)$('mode').value='jev';await reset()}catch(e){status('无法连接服务：'+e.message,true)}})();
