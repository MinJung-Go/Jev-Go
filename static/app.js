const $=id=>document.getElementById(id);
let game=null,busy=false,records=[],ready=false;
const cols='ABCDEFGHJ';
const coord=i=>i===null?'PASS':cols[i%game.size]+(game.size-Math.floor(i/game.size));
function status(message,error=false){$('status').textContent=message;$('status').classList.toggle('error',error)}
async function api(path,data){const r=await fetch('/api/'+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});const d=await r.json();if(!r.ok)throw Error(d.error||'请求失败');return d}
function body(){return {size:game?game.size:Number($('size').value),moves:game?game.moves:[]}}
function draw(){if(!game)return;const n=game.size,board=$('board');board.replaceChildren();let lines='';for(let i=0;i<n;i++){const a=i*100/(n-1);lines+=`<line x1="${a}" y1="0" x2="${a}" y2="100"/><line x1="0" y1="${a}" x2="100" y2="${a}"/>`}
board.innerHTML=`<svg viewBox="-0.5 -0.5 101 101" aria-hidden="true"><g stroke="#796644" stroke-width=".19">${lines}</g><circle cx="50" cy="50" r=".65" fill="#796644"/></svg>`;
const legal=new Set(game.legal),human=$('mode').value==='human';
for(let i=0;i<n*n;i++){let b=document.createElement('button'),v=game.board[i];b.className='point '+(v===1?'black':v===2?'white':'empty');if(i===game.moves.at(-1))b.classList.add('last');b.style.left=(i%n)*100/(n-1)+'%';b.style.top=Math.floor(i/n)*100/(n-1)+'%';b.style.width=b.style.height=82/n+'%';b.setAttribute('aria-label',coord(i)+(v===1?' 黑棋':v===2?' 白棋':' 空点'));b.dataset.index=i;b.disabled=busy||game.over||!legal.has(i)||(!human&&game.turn===2);b.onclick=()=>play(i);board.appendChild(b)}
$('turn').textContent=game.over?'对局结束':busy?'正在处理…':game.turn===1?'轮到黑棋':'轮到白棋';$('move-count').textContent=`第 ${game.moves.length} 手`;$('captures').textContent=`提子 ${game.captures[1]} : ${game.captures[2]}`;
$('opponent-label').textContent=$('mode').value==='jev'?'Jev':human?'同机玩家':'本地规则';
for(const id of ['pass','undo','reset','mode','size'])$(id).disabled=busy;
$('pass').disabled=busy||game.over||(!human&&game.turn===2);$('undo').disabled=busy||!game.moves.length;
$('retry').hidden=busy||game.over||human||game.turn!==2;
if(game.over){const a=game.area;status(`盘面面积：黑 ${a.black}，白 ${a.white} + 6.5。${a.lead>0?'黑':'白'}领先 ${Math.abs(a.lead)} 点；未自动判死，请确认死子已提净。`)}
}
function decision(d){$('choice').textContent=d?.choice==='PASS'?'停手':d?.choice||'—';$('provider').textContent=d?(d.provider==='jev'?d.model:'本地规则 · 非模型'):'等待落子';$('confidence').textContent=d?.confidence==null?'—':(100*d.confidence).toFixed(1)+'%';$('latency').textContent=d?.latency_ms==null?'—':d.latency_ms+' ms';$('alternatives').textContent=d?.probabilities?'候选：'+Object.entries(d.probabilities).sort((a,b)=>b[1]-a[1]).slice(0,3).map(([k,v])=>`${k} ${(v*100).toFixed(1)}%`).join(' / '):''}
async function respond(){busy=true;draw();status($('mode').value==='jev'?'Jev 正在选择落点…':'本地规则正在选择落点…');try{const r=await api('decision',{...body(),mode:$('mode').value});game=r.game;records.push({move_number:game.moves.length,...r});decision(r.decision);status(`白棋 ${r.decision.choice==='PASS'?'停手':'落在 '+r.decision.choice}。轮到你了。`)}catch(e){status(e.message,true)}finally{busy=false;draw()}}
async function play(move){if(busy||!game)return;busy=true;draw();let ok=false;try{game=await api('state',{...body(),moves:[...game.moves,move]});ok=true;status(move===null?'你选择了停手。':'落子 '+coord(move)+'。')}catch(e){status(e.message,true)}finally{busy=false;draw()}if(ok&&!game.over&&$('mode').value!=='human'&&game.turn===2)await respond()}
async function reset(){busy=true;draw();try{game=await api('state',{size:Number($('size').value),moves:[]});records=[];decision(null);status($('mode').value==='jev'?'Jev 模式：你执黑先行。':'当前为'+($('mode').value==='human'?'双人同机':'本地规则练习，不代表 Jev 棋力')+'。')}catch(e){status(e.message,true)}finally{busy=false;draw()}}
$('pass').onclick=()=>play(null);$('reset').onclick=reset;$('mode').onchange=reset;$('size').onchange=reset;$('retry').onclick=respond;
$('undo').onclick=async()=>{if(busy||!game.moves.length)return;busy=true;draw();try{let m=game.moves.slice(0,-1);if($('mode').value!=='human'&&m.length%2===1)m=m.slice(0,-1);game=await api('state',{size:game.size,moves:m});records=records.filter(r=>r.move_number<=m.length);decision(records.at(-1)?.decision);status('已退回上一回合。')}catch(e){status(e.message,true)}finally{busy=false;draw()}};
$('export').onclick=()=>{const blob=new Blob([JSON.stringify({format:'jev-go-v1',exported_at:new Date().toISOString(),mode:$('mode').value,rules:'positional-superko,no-suicide,area,white-komi-6.5,no-dead-stone-adjudication',game,records},null,2)],{type:'application/json'});const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='jev-go-record.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)};
(async()=>{try{const c=await(await fetch('/api/config')).json();ready=c.jev_ready;$('mode').querySelector('[value="jev"]').disabled=!ready;$('connection').textContent=ready?'Jev 已连接配置 · '+c.model:'未配置 Jev 凭据，可先体验本地规则。';if(ready)$('mode').value='jev';await reset()}catch(e){console.error(e);status('无法连接服务：'+e.message,true)}})();
