/* Geographic trip preview. Coordinates share one projection with the Natural Earth coast.
   Routes are schematic links, never driving directions. Unknown locations stay off-map.
   One animation clock; persistent progress; independent visit IDs and place IDs. */
'use strict';
const TripStage = (() => {
  const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const project=ll=>Array.isArray(ll)&&ll.length===2&&ll.every(Number.isFinite)?{x:60+(ll[1]-127.55)*1000,y:70+(26.91-ll[0])*1120}:null;
  const layout=steps=>Array.isArray(steps)?steps.map(s=>project(s.ll)):[];
  const H=()=>1100;
  const POSE={meal:'eat',rest:'rest',hotel:'rest',poi:'look',flight:'wait'};
  const BUBBLE={meal:'맛있겠다',hotel:'잠깐 쉬자',rest:'여유롭게',poi:'둘러보자!',flight:'우리 여행 시작'};
  const reduced=()=>typeof matchMedia==='function'&&matchMedia('(prefers-reduced-motion: reduce)').matches;
  const COAST='M319.8,265.5 L321.2,297.4 L295.7,302.3 L268.6,290.8 L264.6,273.2 L278.8,267.1 L305.7,269.9 L319.8,265.5Z M847.7,196.6 L843.3,201.0 L840.3,207.5 L839.8,215.2 L844.2,223.4 L847.7,233.2 L843.3,241.7 L836.8,248.7 L833.4,253.6 L819.7,281.5 L818.8,285.3 L819.7,299.9 L818.1,304.2 L814.2,303.7 L810.0,302.3 L806.6,303.7 L774.4,358.5 L753.3,379.9 L727.1,388.5 L682.2,390.9 L668.9,396.1 L661.6,403.3 L652.8,415.2 L645.3,428.3 L642.1,438.2 L645.0,441.9 L650.9,443.3 L655.8,447.0 L655.2,457.4 L651.8,465.8 L648.4,468.7 L643.1,469.6 L618.7,478.6 L600.3,481.4 L581.6,479.9 L565.9,472.7 L546.4,498.6 L494.1,553.3 L482.0,560.7 L470.0,561.8 L460.9,566.5 L457.3,583.9 L450.3,587.7 L380.6,588.1 L369.9,590.1 L361.7,595.0 L348.9,612.9 L353.0,621.6 L364.7,626.7 L374.8,633.9 L379.8,648.5 L383.4,680.6 L388.3,695.1 L398.8,709.4 L420.2,727.4 L429.9,742.4 L411.9,747.6 L392.1,741.2 L371.5,731.5 L350.8,726.4 L338.3,735.0 L287.5,827.9 L281.0,846.7 L278.4,867.8 L285.4,881.9 L301.5,881.4 L319.9,877.3 L333.6,880.0 L324.2,903.4 L306.9,932.7 L285.7,952.8 L264.9,948.9 L251.7,959.7 L235.4,988.9 L220.1,994.7 L161.7,994.7 L167.1,952.8 L145.9,874.9 L148.2,848.7 L168.5,851.4 L187.7,830.9 L202.6,802.2 L210.2,780.0 L228.3,782.2 L241.3,765.1 L249.1,742.9 L251.9,730.2 L248.6,706.8 L234.4,657.5 L230.7,633.9 L232.5,607.7 L241.3,596.5 L257.7,594.3 L291.1,595.0 L303.7,593.4 L315.2,587.9 L320.1,576.2 L323.7,576.2 L338.8,548.2 L340.6,542.2 L374.3,522.8 L412.7,510.8 L447.5,493.2 L470.2,457.4 L472.4,437.4 L465.9,423.0 L450.6,414.4 L404.3,406.8 L395.6,394.6 L394.8,377.2 L395.8,357.3 L387.9,320.2 L388.3,311.3 L395.4,309.6 L429.9,311.3 L474.6,308.4 L497.3,313.1 L511.2,327.3 L509.5,336.8 L502.5,346.3 L498.5,357.9 L505.6,373.3 L514.4,378.3 L524.9,378.2 L567.4,367.1 L621.1,334.3 L613.3,315.0 L621.3,301.4 L662.4,269.9 L667.0,263.6 L672.0,241.2 L679.2,236.7 L686.1,235.2 L689.5,231.4 L698.0,215.0 L735.9,192.1 L744.6,177.6 L748.5,156.9 L764.4,121.1 L765.1,96.5 L841.4,178.2 L847.7,196.6Z M450.8,795.7 L455.1,797.1 L456.0,807.1 L449.5,820.9 L444.7,816.1 L442.6,808.6 L444.0,806.9 L446.9,801.9 L450.8,795.7Z M498.7,669.4 L503.8,672.0 L505.2,677.9 L499.1,687.7 L488.2,691.8 L477.7,686.4 L483.0,667.6 L487.6,663.9 L497.1,659.1 L500.4,663.2 L498.7,669.4Z';
  function landmarkIndex(s){const id=s.placeId||s.ref||'';if(/churaumi/.test(id))return 0;if(/kouri/.test(id))return 1;if(/amvillage|sunset/.test(id))return 2;if(/shisa|ryukyumura/.test(id))return 3;if(/umikaji/.test(id))return 4;if(s.k==='hotel'||/hotel/.test(id))return 5;if(/kokusai|shuri/.test(id))return 7;if(s.k==='flight'||/airport/.test(id))return 8;return 6;}
  function art(s,x=-72,y=-115,size=144){const n=landmarkIndex(s);return `<svg x="${x}" y="${y}" width="${size}" height="${size}" viewBox="${n%3*512} ${Math.floor(n/3)*512} 512 512" overflow="hidden"><image href="assets/trip/landmarks.webp" width="1536" height="1536"/></svg>`;}
  function create(svg,opts){
    const o=Object.assign({onStep:()=>{},onState:()=>{},onOpen:()=>{},onMode:()=>{}},opts);
    let steps=[],pts=[],nodes=[],idx=0,sig='',playing=false,speed=1,phase='at',progress=0,to=null,raf=0,timer=0,dead=false,fit=true,manual=false,cam=[0,0,800,1050],target=cam.slice(),camFrame=0;
    let chars,car,routeEls=[],drag=null,dragged=false;
    const stop=()=>{cancelAnimationFrame(raf);clearTimeout(timer);raf=timer=0;};
    const state=()=>({idx,n:steps.length,step:steps[idx]||null,nextStep:to!=null?steps[to]:null,playing,speed,phase,progress,fitAll:fit,manual});
    const emit=()=>o.onState(state());
    function frame(n){const e=svg.querySelector('.sprite');if(e)e.setAttribute('viewBox',`${n%3*512} ${Math.floor(n/3)*512} 512 512`);}
    function pose(cls){const e=svg.querySelector('.char');if(e)e.setAttribute('class','char man '+cls);frame(cls==='eat'?4:cls==='rest'?5:3);}
    function bubble(t){const b=svg.querySelector('.bubble');b.querySelector('text').textContent=t||'';b.style.display=t?'':'none';}
    function ratio(){const b=svg.getBoundingClientRect();return b.width&&b.height?b.width/b.height:.9;}
    function bounds(ps,minW=390){if(!ps.length)return [0,40,780,1040];let l=Math.min(...ps.map(p=>p.x))-120,r=Math.max(...ps.map(p=>p.x))+120,t=Math.min(...ps.map(p=>p.y))-150,b=Math.max(...ps.map(p=>p.y))+125;let w=Math.max(minW,r-l),h=Math.max(400,b-t);const ar=ratio();if(w/h<ar)w=h*ar;else h=w/ar;return [(l+r-w)/2,(t+b-h)/2,w,h];}
    function setCam(box,instant=false){target=box;cancelAnimationFrame(camFrame);if(instant||reduced()){cam=box.slice();svg.setAttribute('viewBox',cam.join(' '));return;}const from=cam.slice(),start=performance.now();const tick=now=>{const k=Math.min(1,(now-start)/350),e=1-Math.pow(1-k,3);cam=from.map((v,i)=>v+(box[i]-v)*e);svg.setAttribute('viewBox',cam.join(' '));if(k<1&&!dead)camFrame=requestAnimationFrame(tick);};camFrame=requestAnimationFrame(tick);}
    function camera(instant=false){if(manual)return;const sel=fit?nodes.map(n=>n.pos):[nodes.find(n=>n.visits.includes(idx))?.pos,nodes.find(n=>n.visits.includes(to??Math.min(idx+1,steps.length-1)))?.pos].filter(Boolean);setCam(bounds(sel,fit?430:390),instant);}
    function uniqueNodes(){const map=new Map();steps.forEach((s,i)=>{if(!pts[i])return;const key=s.placeId||s.ref||s.uid;if(!map.has(key))map.set(key,{key,s,anchor:pts[i],pos:{...pts[i]},visits:[]});map.get(key).visits.push(i);});const ns=[...map.values()];
      // A leader line keeps the anchor honest when neighboring illustrations need separation.
      for(let iter=0;iter<24;iter++)for(let a=0;a<ns.length;a++)for(let b=a+1;b<ns.length;b++){const p=ns[a].pos,q=ns[b].pos;let dx=q.x-p.x,dy=q.y-p.y;if(Math.abs(dx)<175&&Math.abs(dy)<155){const shift=(175-Math.abs(dx))/2+2;const sign=dx===0?(b%2?1:-1):Math.sign(dx);p.x-=shift*sign;q.x+=shift*sign;}}
      return ns;
    }
    function build(){pts=layout(steps);nodes=uniqueNodes();svg.setAttribute('preserveAspectRatio','xMidYMid meet');
      svg.innerHTML=`<defs>${typeof TRIP_CHARS!=='undefined'?TRIP_CHARS.defs:''}<linearGradient id="ocean" x2="1" y2="1"><stop stop-color="#c8efe6"/><stop offset="1" stop-color="#77c8cd"/></linearGradient><linearGradient id="land" x2="1" y2="1"><stop stop-color="#d7e8b2"/><stop offset="1" stop-color="#8fbc95"/></linearGradient><pattern id="ripples" width="90" height="75" patternUnits="userSpaceOnUse"><path d="M5 35q10-5 20 0t20 0" fill="none" stroke="white" stroke-opacity=".25" stroke-width="2"/></pattern><filter id="landshadow" x="-20%" y="-20%" width="140%" height="140%"><feDropShadow dx="0" dy="8" stdDeviation="5" flood-color="#237f82" flood-opacity=".2"/></filter></defs>
      <rect x="-5000" y="-5000" width="10000" height="10000" fill="url(#ocean)"/><rect x="-5000" y="-5000" width="10000" height="10000" fill="url(#ripples)"/>
      <path class="coast" d="${COAST}" fill="url(#land)" stroke="#f9edcb" stroke-width="9" stroke-linejoin="round" filter="url(#landshadow)"/>
      <g fill="#3f7868" opacity=".65" font-size="17" font-weight="700"><text x="435" y="380">やんばる</text><text x="350" y="620">OKINAWA</text><text x="235" y="860">那覇</text></g>
      <g class="routes">${steps.slice(1).map((s,j)=>{const a=pts[j],b=pts[j+1];if(!a||!b||Math.hypot(a.x-b.x,a.y-b.y)<1)return '';return `<path class="route" data-to="${j+1}" d="M${a.x},${a.y} L${b.x},${b.y}" fill="none" stroke-width="4" stroke-linecap="round" pathLength="1"/><path class="route-progress" data-to="${j+1}" d="M${a.x},${a.y} L${b.x},${b.y}" fill="none" stroke="#c56c4d" stroke-width="6" stroke-linecap="round" pathLength="1"/>`;}).join('')}</g>
      <g class="nodes">${nodes.map(n=>`<g class="node" data-i="${n.visits[0]}" tabindex="0" role="button" aria-label="${esc(n.s.name)} 상세"><title>${esc(n.s.name)}</title><path d="M${n.anchor.x},${n.anchor.y} L${n.pos.x},${n.pos.y}" fill="none" stroke="#47695a" stroke-opacity=".6" stroke-width="1.5"/><circle class="anchor" cx="${n.anchor.x}" cy="${n.anchor.y}" r="6" fill="#fff" stroke="#226b69" stroke-width="3"/><g transform="translate(${n.pos.x},${n.pos.y})"><ellipse class="halo" cy="-2" rx="67" ry="23" fill="#fffdf5" fill-opacity=".48"/>${art(n.s)}<g class="lbl"><rect x="-89" y="29" width="178" height="45" rx="14" fill="#fffdf6" stroke="#d5e2d2"/><text class="visit-number" x="0" y="45" text-anchor="middle" fill="#b65a3d" font-size="11" font-weight="800">${n.visits.map(i=>i+1).join(' · ')}</text><text x="0" y="63" text-anchor="middle" fill="#224e4a" font-size="13" font-weight="700">${esc(n.s.name.length>14?n.s.name.slice(0,14)+'…':n.s.name)}</text></g></g></g>`).join('')}</g>
      <g class="car" style="display:none"><svg x="-32" y="-74" width="64" height="64" viewBox="0 512 512 512" overflow="hidden"><image href="assets/trip/couple.webp" width="1536" height="1024"/></svg><ellipse cy="7" rx="29" ry="7" fill="#183b3b" opacity=".15"/><use href="#pr-car" x="-37" y="-36" width="74" height="40"/></g>
      <g class="chars" pointer-events="none"><ellipse cy="2" rx="23" ry="6" fill="#183b3b" opacity=".2"/><g class="pair"><g class="char man"><svg class="sprite" x="-49" y="-91" width="98" height="98" viewBox="0 512 512 512" overflow="hidden"><image href="assets/trip/couple.webp" width="1536" height="1024"/></svg></g></g><g class="bubble"><rect x="-51" y="-116" width="102" height="24" rx="12" fill="#fffdf6"/><text x="0" y="-100" font-size="11" text-anchor="middle" fill="#28544e"></text></g></g>`;
      chars=svg.querySelector('.chars');car=svg.querySelector('.car');routeEls=[...svg.querySelectorAll('.route')];camera(true);
    }
    function paintRoutes(){routeEls.forEach(e=>{const n=+e.dataset.to;e.setAttribute('stroke',n<=idx?'#559995':n===to?'#e4b399':'#fffdf5');e.setAttribute('stroke-dasharray',n<=idx?'none':'.018 .025');});svg.querySelectorAll('.route-progress').forEach(e=>{const active=+e.dataset.to===to;e.style.opacity=active?'1':'0';e.setAttribute('stroke-dasharray',`${active?progress:0} 1`);});}
    function highlight(){svg.querySelectorAll('.node').forEach(e=>{const n=nodes.find(x=>x.visits.includes(+e.dataset.i));const selected=n.visits.includes(idx);e.classList.toggle('cur',selected);e.classList.toggle('done',n.visits.some(i=>steps[i].done));e.dataset.i=selected?idx:n.visits[0];});paintRoutes();}
    function place(p,byCar=false){chars.style.display=p&&!byCar?'':'none';car.style.display=p&&byCar?'':'none';if(p)(byCar?car:chars).setAttribute('transform',`translate(${p.x},${p.y})`);}
    function arrive(i){idx=i;to=null;progress=0;phase='at';pose(POSE[steps[i]?.k]||'look');bubble(BUBBLE[steps[i]?.k]||'여기서 잠깐');place(pts[i]);highlight();camera();o.onStep(state());if(playing&&idx<steps.length-1)timer=setTimeout(()=>go(idx+1),1700/speed);else playing=false;emit();}
    function go(next){stop();if(!steps[next])return;to=next;phase='moving';pose('walk');bubble('다음 장소로');highlight();camera();const a=pts[idx],b=pts[to];
      if(!a||!b){phase='unlocated';place(null);emit();timer=setTimeout(()=>arrive(next),reduced()?1:900/speed);return;}
      const same=Math.hypot(a.x-b.x,a.y-b.y)<1;if(same){arrive(next);return;}
      const byCar=steps[next].car!==false;let last=performance.now();const tick=now=>{if(dead||!playing)return;const dt=Math.min(100,now-last);last=now;progress=Math.min(1,progress+dt*speed/(reduced()?1:2600));const p={x:a.x+(b.x-a.x)*progress,y:a.y+(b.y-a.y)*progress};place(p,byCar);if(!byCar)frame(Math.floor(now/160)%3);paintRoutes();emit();if(progress<1)raf=requestAnimationFrame(tick);else arrive(next);};raf=requestAnimationFrame(tick);emit();
    }
    const api={
      setSteps(next,opt){const key=next.map(s=>[s.uid,s.k,s.ref,s.name,s.ll].join('|')).join(';');if(key===sig&&!opt?.force){steps=next;highlight();return;}const uid=steps[idx]?.uid;stop();playing=false;to=null;progress=0;steps=next;sig=key;idx=Math.max(0,steps.findIndex(s=>s.uid===uid));manual=false;fit=true;build();if(steps.length)arrive(Math.min(idx,steps.length-1));else{place(null);emit();}o.onMode(true);},
      play(){if(!steps.length||playing)return;playing=true;if(to!=null)go(to);else if(idx>=steps.length-1){arrive(0);}else go(idx+1);emit();},
      pause(){playing=false;stop();if(to!=null)phase='paused';emit();},toggle(){playing?api.pause():api.play();},
      goto(i){stop();playing=false;if(i>=0&&i<steps.length)arrive(i);},gotoUid(uid){api.goto(steps.findIndex(s=>s.uid===uid));},next(){api.goto(idx+1);},prev(){api.goto(idx-1);},
      setSpeed(v){speed=Math.max(.5,Math.min(2,Number(v)||1));emit();},fitAll(on){fit=on==null?!fit:!!on;manual=false;camera();o.onMode(fit);emit();return fit;},
      state,isPlaying:()=>playing,destroy(){dead=true;stop();cancelAnimationFrame(camFrame);observer?.disconnect();for(const [e,f]of listeners)svg.removeEventListener(e,f);svg.innerHTML='';}
    };
    const listeners=[];function listen(e,f){svg.addEventListener(e,f);listeners.push([e,f]);}
    listen('click',ev=>{if(dragged){dragged=false;return;}const n=ev.target.closest('.node');if(n){ev.preventDefault();o.onOpen(+n.dataset.i);}});
    listen('keydown',ev=>{const n=ev.target.closest('.node');if(n&&(ev.key==='Enter'||ev.key===' ')){ev.preventDefault();o.onOpen(+n.dataset.i);}});
    // Map pans on an explicit background drag; the page retains vertical scrolling on touch.
    listen('pointerdown',ev=>{if(ev.target.closest('.node'))return;drag={x:ev.clientX,y:ev.clientY,box:cam.slice(),id:ev.pointerId};dragged=false;});
    listen('pointermove',ev=>{if(!drag)return;const dx=ev.clientX-drag.x,dy=ev.clientY-drag.y;if(!dragged&&Math.abs(dx)<8)return;dragged=true;manual=true;cancelAnimationFrame(camFrame);const b=svg.getBoundingClientRect(),unit=cam[2]/(b.width||600);cam=[drag.box[0]-dx*unit,drag.box[1]-dy*unit,cam[2],cam[3]];svg.setAttribute('viewBox',cam.join(' '));o.onMode(null);});
    listen('pointerup',()=>{drag=null;});listen('pointercancel',()=>{drag=null;});listen('pointerleave',()=>{drag=null;});
    const observer=typeof ResizeObserver!=='undefined'?new ResizeObserver(()=>camera(true)):null;observer?.observe(svg);
    return api;
  }
  return {create,layout,H,project,art,POSE,BUBBLE};
})();
if(typeof module!=='undefined')module.exports=TripStage;
