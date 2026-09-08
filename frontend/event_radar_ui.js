(()=>{
  if(!location.pathname.startsWith('/stock'))return;
  const q=new URLSearchParams(location.search), ticker=(q.get('ticker')||'').toUpperCase();
  if(!ticker)return;
  const tabs=document.querySelector('.tabs'), content=document.getElementById('content');
  if(!tabs||!content||tabs.querySelector('[data-tab="events"]'))return;
  const esc=v=>String(v??'—').replace(/[&<>\"]/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[m]));
  const button=document.createElement('button');button.className='tab';button.dataset.tab='events';button.textContent='Hendelser';tabs.appendChild(button);
  async function show(){
    document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('active',x===button));
    content.innerHTML='<section class="card"><h2>Hendelsesradar · '+esc(ticker)+'</h2><div class="notice">Laster verifiserte Oslo Børs-hendelser…</div></section>';
    try{
      const r=await fetch('/api/event-radar?ticker='+encodeURIComponent(ticker)+'&limit=50',{cache:'no-store'}),d=await r.json();if(!r.ok)throw Error('HTTP '+r.status);
      const items=d.items||[];
      content.innerHTML='<section class="card"><h2>Hendelsesradar · '+esc(ticker)+'</h2><div class="notice">Kontrakter, ordre, avtaler, oppkjøp, guiding og storeierhendelser fra verifiserte Euronext / Oslo Børs-meldinger. Dette endrer ikke NordicSignal-score.</div>'+(items.length?items.map(x=>'<article class="item"><span class="pill">'+esc(x.event_label)+'</span><h3>'+esc(x.title)+'</h3><div class="muted">'+esc(x.published_at||'—')+' · '+esc(x.source||'Euronext / Oslo Børs')+'</div>'+(x.url?'<a href="'+esc(x.url)+'" target="_blank" rel="noopener">Åpne originalmelding</a>':'')+'</article>').join(''):'<div class="notice">Ingen klassifiserte hendelser funnet i den tilgjengelige offisielle meldingsstrømmen.</div>')+'</section>';
    }catch(e){content.innerHTML='<section class="card"><h2>Hendelsesradar · '+esc(ticker)+'</h2><div class="notice">Hendelsesradaren er midlertidig utilgjengelig.</div></section>'}
  }
  button.addEventListener('click',e=>{e.preventDefault();show()});
})();
