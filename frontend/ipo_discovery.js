/* Shared, read-only listing discovery. No per-company requests or signal rules. */
(() => {
  'use strict';
  let pending, cached, selected = 'upcoming', query = '';
  const escape = value => String(value ?? '').replace(/[&<>"']/g, x => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[x]));
  const source = value => {try {const u = new URL(value);return u.protocol === 'https:' && ['live.euronext.com','www.euronext.com'].includes(u.hostname) && !u.username ? u.href : null;} catch {return null;}};
  const date = value => {if(!value)return 'Ukjent';const d=new Date(value);return Number.isFinite(d.getTime())?d.toLocaleDateString('nb-NO',{timeZone:'Europe/Oslo'}):'Ukjent';};
  const list = values => '<ul>'+values.map(v=>'<li>'+escape(v)+'</li>').join('')+'</ul>';
  async function load() {
    if(cached && Date.now()-cached.at < 60000)return cached.data;
    if(!pending)pending=(async()=>{
      const r=await fetch('/api/ipo-radar/discovery',{signal:AbortSignal.timeout(15000)});
      if(!r.ok||r.redirected)throw Error('Unavailable');
      const data=await r.json();
      if(!Array.isArray(data.items)||data.score_effect!==0||!data.counts)throw Error('Invalid discovery data');
      cached={data,at:Date.now()};return data;
    })().finally(()=>{pending=null;});
    return pending;
  }
  const documentSource=value=>{try{const u=new URL(value);return u.protocol==='https:'&&!u.username&&!u.password?u.href:null}catch{return null}};
  function citation(s,locator='') {const url=documentSource(s?.url);return url?'<a class="ipoDocumentLink" href="'+escape(url)+'" target="_blank" rel="noopener noreferrer">'+escape(s.label)+(locator?' · '+escape(locator):'')+' ↗</a><span class="muted"> · publisert '+date(s.published_at)+'</span>':'';}
  function profile(x) {
    const p=x.documented_profile;if(!p||p.status!=='reviewed_snapshot')return '';
    return '<section class="ipoProfile"><h4>Dokumenterte selskapsopplysninger</h4><p class="muted">Kildekontrollert '+date(p.reviewed_at)+' · lagret dokumentgjennomgang, ikke løpende selskapsdekning.</p>'+p.sections.map((s,i)=>{
      const content='<p>'+escape(s.text)+'</p><p class="muted">Opplysning per '+date(s.as_of)+'</p>'+citation(p.sources[s.source_id],s.locator);
      return i===0?'<h4>'+escape(s.title)+'</h4>'+content:'<details><summary>'+escape(s.title)+'</summary>'+content+'</details>';
    }).join('')+'</section>';
  }
  function card(x, stock=false) {
    const url=source(x.source_url), ticker=/^[A-Z0-9][A-Z0-9.-]{0,19}$/.test(x.ticker||'')?x.ticker:null;
    return '<article class="ipoCard"><div class="ipoCardHead"><div><span class="ipoTag">'+escape(x.display_status)+'</span><h3>'+escape(x.company)+'</h3><p class="muted">'+escape([ticker,x.market].filter(Boolean).join(' · '))+'</p></div></div>'+
      '<p><strong>'+escape(x.listing_date?'Notert '+date(x.listing_date):x.expected_listing_date?'Forventet '+date(x.expected_listing_date):'Noteringsdato ukjent')+'</strong><br><span class="muted">'+escape(x.confirmation)+'</span></p>'+
      profile(x)+'<h4>Hvorfor følge med?</h4>'+list(x.why_follow||[])+
      '<h4>Vær oppmerksom på</h4>'+list(x.risks||[])+
      '<p><strong>Neste hendelse</strong><br>'+escape(x.next_event)+'</p>'+citation(x.next_event_source)+
      '<details><summary>Hva mangler i vurderingen?</summary>'+list(x.unknowns||[])+'<p>'+escape(x.monitoring_note)+'</p></details>'+
      '<p class="muted">'+escape(x.assessment)+' · score_effect=0</p>'+
      '<div class="ipoActions">'+(url?'<a href="'+escape(url)+'" target="_blank" rel="noopener noreferrer">Offisiell kilde ↗</a>':'')+
      (!stock&&ticker&&x.analysis_available?'<a href="/stock?ticker='+encodeURIComponent(ticker)+'">Åpne analyse →</a>':!stock?'<span class="muted">Ordinær analysedekning ikke tilgjengelig</span>':'')+'</div>'+
      '<p class="muted">Kilde sist observert '+date(x.last_seen_at)+(x.published_at?' · melding publisert '+date(x.published_at):'')+'</p></article>';
  }
  function render(root,data) {
    const groups=[['upcoming','Kommende'],['recent','Nylig notert'],['year','Notert i '+data.year]];
    root.innerHTML='<h2>Nye på børs</h2><p>'+escape(data.coverage)+'</p><p class="muted">'+escape(data.policy)+'</p>'+
      (data.status==='partial'?'<p role="status">Noen kilder er utilgjengelige. Listen kan være ufullstendig.</p>':'')+
      '<div class="ipoGroups" aria-label="Noteringsperiode">'+groups.map(([key,label])=>'<button type="button" class="btn" data-ipo-group="'+key+'" aria-pressed="'+(selected===key)+'">'+label+' <span>'+escape(data.counts[key]??0)+'</span></button>').join('')+'</div>'+
      '<label class="ipoSearch">Søk i noteringer<input type="search" placeholder="Selskap eller ticker" value="'+escape(query)+'"></label><div class="ipoResults" aria-live="polite"></div>'+
      '<p class="muted">Listen satt sammen '+date(data.generated_at)+'. Dette er lagrede kilder, ikke sanntidsdata.</p>';
    const results=root.querySelector('.ipoResults');
    const draw=()=>{const q=query.toLocaleLowerCase('nb-NO');const rows=data.items.filter(x=>x.groups?.includes(selected)&&[x.company,x.ticker].join(' ').toLocaleLowerCase('nb-NO').includes(q));results.innerHTML=rows.length?rows.map(x=>card(x)).join(''):'<p class="notice">Ingen verifiserte treff i tilgjengelige kilder. Dette bekrefter ikke at det ikke finnes flere noteringer.</p>';};
    root.querySelectorAll('[data-ipo-group]').forEach(button=>button.addEventListener('click',()=>{selected=button.dataset.ipoGroup;root.querySelectorAll('[data-ipo-group]').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));draw();}));
    root.querySelector('input').addEventListener('input',e=>{query=e.target.value;draw();});draw();
  }
  async function mount(root,ticker=null) {
    if(!root)return;
    const request={};root._ipoRequest=request;
    root.innerHTML='<h2>'+(ticker?'Ny på børs':'Nye på børs')+'</h2><p role="status">Laster dokumenterte noteringer…</p>';
    try {
      const data=await load();if(!root.isConnected||root._ipoRequest!==request)return;
      if(ticker){const items=data.items.filter(x=>x.ticker===String(ticker).toUpperCase().replace(/\.OL$/,''));root.innerHTML='<h2>Ny på børs · forskning</h2><p>score_effect=0 · separat fra Aksjer Score og Opportunity</p>'+(items.length?items.map(x=>card(x,true)).join(''):'<p>Ingen dokumentert notering i år eller kommende plan for denne tickeren i tilgjengelige kilder.</p>')+(data.status==='partial'?'<p role="status">Noen noteringskilder er utilgjengelige.</p>':'');}
      else render(root,data);
    } catch {
      if(!root.isConnected||root._ipoRequest!==request)return;
      root.innerHTML='<h2>Nye på børs</h2><p role="status">UTILGJENGELIG · noteringskildene kunne ikke lastes.</p><button class="btn" type="button">Prøv igjen</button>';
      root.querySelector('button').addEventListener('click',()=>mount(root,ticker));
    }
  }
  window.AksjerIPO={load,mount};
})();
