/* Shared cached company facts. No model changes or background per-row requests. */
(()=>{'use strict';
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const date=v=>{const d=new Date(v);return v&&Number.isFinite(d.getTime())?d.toLocaleString('nb-NO',{timeZone:'Europe/Oslo'}):'ukjent';};
const link=(url,label)=>{try{const u=new URL(url);if(u.protocol==='https:'&&!u.username&&!u.password)return '<a href="'+esc(u.href)+'" target="_blank" rel="noopener noreferrer">'+esc(label)+' ↗</a>';}catch{}return '';};
const number=v=>Number.isFinite(v)?new Intl.NumberFormat('nb-NO',{notation:'compact',maximumFractionDigits:2}).format(v):'Ukjent';
function render(p){
 if(!p||p.score_effect!==0)return '<p>Selskapsopplysninger er utilgjengelige.</p>';
 const statuses={collecting:'Venter på automatisk innhenting',unavailable:'Kildene er utilgjengelige',partial:'Delvis dekning · lagrede opplysninger',stale:'Eldre opplysninger · må kontrolleres'};
 return '<div class="companyContext"><h3>Selskapsinformasjon</h3><p class="muted">'+esc(statuses[p.status]||'Ukjent datastatus')+' · sist hentet '+esc(date(p.captured_at))+'</p>'+
 '<p>'+esc(p.description||'Virksomhetsbeskrivelse er ikke tilgjengelig fra datakilden ennå.')+'</p><p>Sektor: '+esc(p.sector||'Ukjent')+'</p>'+
 (p.financials?.length?'<dl>'+p.financials.map(f=>'<dt>'+esc(f.label)+'</dt><dd>'+esc(number(f.value))+' '+esc(f.currency||'(valuta ukjent)')+' <span class="muted">· periode '+esc(f.period)+' · '+esc(f.period_type)+'</span></dd>').join('')+'</dl>':'<p>Regnskapstall er ikke tilgjengelige ennå.</p>')+
 link(p.source_url,'Datakilde: '+(p.source||'ukjent'))+
 '<h3>Vær oppmerksom på · finansiering</h3>'+(p.financing_documents?.length?'<ul>'+p.financing_documents.map(e=>'<li>'+link(e.url,e.title)+'<p class="muted">Publisert '+esc(date(e.published_at))+' · '+esc(e.status)+'</p></li>').join('')+'</ul>':'<p>Ingen finansieringsmeldinger i innhentet materiale. Dette utelukker ikke emisjon eller kapitalbehov.</p>')+
 '<p class="muted">'+esc(p.coverage||'Dekning ukjent')+' Kildestatus: '+esc(p.news_status==='partial'?'delvis dekning':'utilgjengelig')+'. Siste forsøk: '+esc(date(p.news_checked_at))+'.</p>'+
 '<details><summary>Hva bør kontrolleres ved en emisjon?</summary><ul><li>Er emisjonen foreslått, vedtatt, gjennomført eller avlyst? Les siste melding.</li><li>Tegningskurs og antall nye aksjer: eierandelen kan bli redusert dersom du ikke deltar.</li><li>Rett til å delta, eks-dato og tegningsfrist må bekreftes i vilkårene.</li><li>Skal pengene finansiere vekst, drift, gjeld eller refinansiering?</li><li>En ny kontrakt er ikke det samme som kontanter nå og opphever ikke en emisjon.</li></ul><p>Eksisterende aksjer er ikke mindreverdige bare fordi de er «gamle». Rettigheter og aksjeklasse avhenger av dokumenterte vilkår.</p></details>'+
 '<p class="muted">Verdsettelse, kapitalbruk, eiersalg og lock-up må kontrolleres i siste rapport/prospekt når de ikke er dokumentert her. Forskning · ingen score-effekt.</p></div>';
}
async function mount(root,ticker){
 if(!root)return;const key={};root._companyRequest=key;root.innerHTML='<h2>Selskapsinformasjon og finansiering</h2><p>Laster lagrede opplysninger…</p>';
 try{const r=await fetch('/api/company-context/'+encodeURIComponent(ticker),{signal:AbortSignal.timeout(15000)});if(!r.ok||r.redirected)throw Error();const p=await r.json();if(root.isConnected&&root._companyRequest===key)root.innerHTML=render(p);}
 catch{if(root.isConnected&&root._companyRequest===key)root.innerHTML='<h2>Selskapsinformasjon</h2><p>UTILGJENGELIG · selskapsopplysninger kunne ikke hentes. Dette sier ingenting om finansieringsrisikoen.</p>';}
}
window.AksjerCompany={render,mount};
})();
