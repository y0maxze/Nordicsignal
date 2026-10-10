/* Reviewed, retrospective context only. Does not adjust prices or model outputs. */
(()=>{
 const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const link=value=>{try{const u=new URL(value);return u.protocol==='https:'&&!u.username&&!u.password?u.href:''}catch{return ''}};
 const time=value=>{const d=new Date(value);return value&&/(Z|[+-]\d{2}:\d{2})$/.test(value)&&Number.isFinite(d.getTime())?d.toLocaleString('nb-NO',{timeZone:'Europe/Oslo'}):'Ukjent'};
 function render(items,{windowContext=false}={}){
  return (Array.isArray(items)?items:[]).map(x=>{
   if(x.type!=='cash_dividend'||typeof x.amount!=='number'||!Number.isFinite(x.amount)||x.amount<=0||!link(x.source_url))return '';
   return `<aside class="corporateActionContext"><h3>Kildegjennomgått utbytte · ${esc(x.ticker)}</h3><p><strong>${esc(x.amount.toLocaleString('nb-NO',{minimumFractionDigits:2,maximumFractionDigits:4}))} ${esc(x.currency)} per aksje</strong> · eksdato ${esc(x.ex_date)} · vedtatt ${esc(x.approval_date)}.</p><p>${esc(x.issuer)} · ISIN ${esc(x.isin)}. Forventet betaling rundt ${esc(x.payment_date_expected)}; mottatt betaling er ikke bekreftet.</p><a href="${esc(link(x.source_url))}" target="_blank" rel="noopener noreferrer">${esc(x.source_title)} · s. ${esc(x.source_pages)} ↗</a><p class="muted">Gjennomgått ${esc(time(x.reviewed_at))} (Oslo) · revisjon ${esc(x.revision)}. ${windowContext?'Eksdato ligger i dette lagrede kursvinduet. Koblingen bygger på ticker; identiteten i den gamle måleposten er ikke verifisert. ':''}Dette er kontekst lagt til i ettertid, ikke bevis på hva systemet visste da signalet oppstod. Råutfall er uendret. Utvalgte hendelser gir ikke komplett dekning eller bekreftet totalavkastning.</p></aside>`;
  }).join('');
 }
 async function mount(root,ticker){
  if(!root)return;
  root.innerHTML='<h2>Selskapshendelser og kursutfall</h2><p>Laster kildegrunnlag…</p>';
  try{
   const r=await fetch('/api/corporate-action-evidence/'+encodeURIComponent(ticker),{cache:'no-store',signal:AbortSignal.timeout(15000)});
   if(!r.ok||r.redirected)throw Error();const d=await r.json();
   if(!Array.isArray(d.items)||d.status==='unavailable')throw Error();
   const body=render(d.items);
   root.innerHTML='<h2>Selskapshendelser og kursutfall</h2>'+(body||'<p>Ingen kildegjennomgåtte hendelser i dette utvalget. Det bekrefter ikke at aksjen mangler utbytte, splitt eller andre selskapshendelser.</p>');
  }catch{root.innerHTML='<h2>Selskapshendelser og kursutfall</h2><p>Kildegrunnlaget er utilgjengelig. Kursendring kan ikke bekreftes som totalavkastning.</p>'}
 }
 window.AksjerActions={render,mount};
})();
