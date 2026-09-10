(()=>{
  const root=document.documentElement;
  const progress=document.getElementById('scrollProgress');
  const nav=document.getElementById('homeNav');
  const scene=document.getElementById('systemScene');
  const stars=document.getElementById('stars');
  const reduce=window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const clamp=(v,min,max)=>Math.min(max,Math.max(min,v));

  if(stars){
    const frag=document.createDocumentFragment();
    for(let i=0;i<74;i++){
      const s=document.createElement('i');
      s.className='star';
      s.style.left=((i*37)%101)+'%';
      s.style.top=((i*61)%97)+'%';
      s.style.opacity=(.10+((i*17)%35)/100).toFixed(2);
      s.style.transform=`scale(${.7+((i*13)%18)/10})`;
      frag.appendChild(s);
    }
    stars.appendChild(frag);
  }

  function onScroll(){
    const max=Math.max(1,document.documentElement.scrollHeight-innerHeight);
    const p=clamp(scrollY/max,0,1);
    progress.style.transform=`scaleX(${p})`;
    nav.classList.toggle('scrolled',scrollY>24);
    if(!reduce && scene){
      const hero=document.querySelector('.hero');
      const hp=hero?clamp(scrollY/Math.max(1,hero.offsetHeight),0,1):0;
      root.style.setProperty('--scroll',hp.toFixed(3));
    }
  }
  addEventListener('scroll',onScroll,{passive:true});onScroll();

  if(!reduce){
    addEventListener('pointermove',e=>{
      const x=(e.clientX/innerWidth-.5)*2;
      const y=(e.clientY/innerHeight-.5)*2;
      root.style.setProperty('--mx',x.toFixed(3));
      root.style.setProperty('--my',y.toFixed(3));
    },{passive:true});
  }

  const observer=new IntersectionObserver(entries=>entries.forEach(entry=>{
    if(entry.isIntersecting)entry.target.classList.add('visible');
  }),{threshold:.12,rootMargin:'0px 0px -6%'});
  document.querySelectorAll('.reveal').forEach(el=>observer.observe(el));

  const flowLabel=document.getElementById('flowLabel');
  const stepObserver=new IntersectionObserver(entries=>{
    const active=entries.filter(x=>x.isIntersecting).sort((a,b)=>b.intersectionRatio-a.intersectionRatio)[0];
    if(active&&flowLabel)flowLabel.textContent=active.target.dataset.flow||'NORDICSIGNAL';
  },{threshold:[.25,.55,.8]});
  document.querySelectorAll('.step[data-flow]').forEach(el=>stepObserver.observe(el));

  async function json(path){
    const r=await fetch(path,{cache:'no-store'});
    if(!r.ok)throw new Error(path+' '+r.status);
    return r.json();
  }
  const text=(id,value)=>{const el=document.getElementById(id);if(el)el.textContent=value};
  const dot=document.getElementById('statusDot');
  async function loadStatus(){
    const [stocks,push,ipo]=await Promise.allSettled([
      json('/api/stocks'),
      json('/api/push/status'),
      json('/api/ipo-radar/autoscan/status')
    ]);
    const ok=stocks.status==='fulfilled';
    text('systemStatus',ok?'SYSTEM ONLINE':'SYSTEM DEGRADED');
    if(dot)dot.className='statusDot '+(ok?'ok':'bad');
    text('dataStatus',ok?`${(stocks.value.items||[]).length||'Live'} tracked`:'Utilgjengelig');
    if(push.status==='fulfilled'){
      const p=push.value||{};
      const active=p.active_subscriptions ?? p.subscriptions_active ?? p.subscriptions;
      text('pushStatus',active!=null?`${active} aktiv`:(p.ready===false?'Ikke klar':'Klar'));
    }else text('pushStatus','Utilgjengelig');
    if(ipo.status==='fulfilled'){
      const x=ipo.value||{};
      text('ipoStatus',x.last_scan_status==='no_verified_upcoming_listings'?'Ingen nye':(x.last_scan_status||x.status||'Aktiv'));
    }else text('ipoStatus','Utilgjengelig');
  }
  loadStatus().catch(()=>{});

  document.querySelectorAll('a[href^="#"]').forEach(a=>a.addEventListener('click',e=>{
    const id=a.getAttribute('href');
    const target=id&&id.length>1?document.querySelector(id):null;
    if(target){e.preventDefault();target.scrollIntoView({behavior:reduce?'auto':'smooth',block:'start'});}
  }));
})();
