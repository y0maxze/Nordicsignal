/* Shared cached company facts. No model changes or background per-row requests. */
(()=>{'use strict';
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const date=v=>{const d=new Date(v);return v&&Number.isFinite(d.getTime())?d.toLocaleString('nb-NO',{timeZone:'Europe/Oslo'}):'ukjent';};
const link=(url,label)=>{try{const u=new URL(url);if(u.protocol==='https:'&&!u.username&&!u.password)return '<a href="'+esc(u.href)+'" target="_blank" rel="noopener noreferrer">'+esc(label)+' ↗</a>';}catch{}return '';};
const number=v=>Number.isFinite(v)?new Intl.NumberFormat('nb-NO',{notation:'compact',maximumFractionDigits:2}).format(v):'Ukjent';
const financingTypes={rights_issue:'Fortrinnsrettsemisjon',private_placement:'Rettet emisjon',repair_offering:'Reparasjonsemisjon',subsequent_offering:'Etterfølgende tilbud',convertible:'Konvertibel finansiering',debt_or_refinancing:'Gjeld / refinansiering',share_capital_increase:'Kapitalforhøyelse',other_financing:'Type ikke entydig dokumentert'};
const lifecycleLabels={proposed:'Foreslått',approved:'Godkjent',open:'Åpnet',completed:'Gjennomført',cancelled:'Kansellert',unknown:'Ukjent'};
const termLabels={subscription_price:'Tegningskurs',new_shares:'Nye aksjer',maximum_new_shares:'Maksimalt antall nye aksjer',existing_shares:'Aksjer før emisjonen',share_class:'Felles aksjeklasse',gross_proceeds:'Brutto proveny',net_proceeds:'Netto proveny',subscription_period:'Tegningsperiode',subscription_deadline:'Tegningsfrist',ex_date:'Ex-dato',record_date:'Record date',settlement_date:'Oppgjørsdato',delivery_date:'Leveringsdato',subscription_rights:'Tegningsrettigheter',eligibility:'Hvem kan delta',primary_secondary:'Nye aksjer / eiersalg',use_of_proceeds:'Kapitalbruk',lock_up:'Lock-up',underwriting:'Garanti / underwriting'};
function financingDocument(e){
 const d=e.document||{}, terms=d.terms||{}, dilution=d.dilution||{};
 const hasEvidence=e.evidence_scope==='official_title'&&typeof e.lifecycle_evidence==='string'&&e.lifecycle_evidence.trim();
 const status=hasEvidence?(lifecycleLabels[e.lifecycle]||'Ukjent'):'Ukjent';
 const sourceStatus={partial:'Delvis tolket',unavailable:'Kilden utilgjengelig',stale:'Eldre dokumentdata',unsupported_document:'Dokumentformat støttes ikke ennå'};
 const facts=Object.entries(termLabels).map(([key,label])=>{const f=terms[key];const known=f?.status==='documented'&&typeof f.value==='string'&&f.value.trim()&&typeof f.evidence==='string'&&f.evidence.trim();return '<div><dt>'+esc(label)+'</dt><dd>'+esc(known?f.value:f?.status==='ambiguous'?'Ukjent · motstridende eller gjentatte felt':'Ukjent')+(known?'<details class="financingEvidence"><summary>Vis tekstbelegg</summary><blockquote>'+esc(f.evidence)+'</blockquote></details>':'')+'</dd></div>';}).join('');
 const calculated=dilution.status==='calculated'&&Number.isFinite(Number(dilution.percentage))&&Number(dilution.percentage)>0&&Number(dilution.percentage)<100&&Number.isSafeInteger(dilution.existing_shares)&&Number.isSafeInteger(dilution.new_shares)&&dilution.existing_shares>0&&dilution.new_shares>0;
 return '<article class="financingDocument"><p class="financingType">'+esc(financingTypes[e.financing_type]||financingTypes.other_financing)+'</p><h4>'+link(e.url,e.title)+'</h4><p>Dokumentstatus: <strong>'+esc(status)+'</strong> · '+esc(date(e.published_at))+'</p><p class="muted">Historisk utsagn. Dagens status er ikke bekreftet.</p>'+
 (hasEvidence?'<details class="financingEvidence"><summary>Belegg for dokumentstatus</summary><blockquote>'+esc(e.lifecycle_evidence)+'</blockquote><p>Kun offisiell tittel · publisert '+esc(date(e.published_at))+'</p></details>':'<p class="muted">Tittelen gir ikke entydig belegg for en lifecycle-status.</p>')+
 '<p class="muted">Dokumentvilkår: '+esc(sourceStatus[d.status]||'Ikke innhentet ennå')+' · hentet '+esc(date(d.captured_at))+' · siste forsøk '+esc(date(d.attempted_at))+'.</p>'+
 '<details><summary>Vilkår, frister og kilder</summary><p>Ordlyd fra dette dokumentet; vilkår kan være foreløpige eller senere endret. Ukjent betyr at feltet ikke er sikkert tolket.</p><dl class="financingTerms">'+facts+'</dl>'+link(e.url,'Åpne originaldokumentet')+'</details>'+
 '<div class="financingDilution"><strong>Utvanning: '+(calculated?esc(new Intl.NumberFormat('nb-NO',{maximumFractionDigits:4}).format(Number(dilution.percentage)))+' % · beregnet dokumentscenario':'Ukjent')+'</strong>'+
 (calculated?'<p>'+esc(dilution.new_shares)+' / ('+esc(dilution.existing_shares)+' + '+esc(dilution.new_shares)+') × 100 · '+esc(dilution.share_class)+'</p><p>'+esc(dilution.limitation)+'</p>':'<p>Kan ikke beregnes uten dokumenterte og kompatible aksjetall for samme emisjon og aksjeklasse.</p>')+'</div></article>';
}
function provenance(meta){
 if(!meta)return '';
 const stale=meta.status==='stale'?'Eldre opplysning · ':'';
 return '<p class="muted">'+esc(stale)+link(meta.source_url,meta.source||'Datakilde')+' · hentet '+esc(date(meta.captured_at))+' · siste forsøk '+esc(date(meta.attempted_at))+(meta.license?' · '+esc(meta.license):'')+'</p>';
}
function historyPanel(h){
 if(h?.status!=='available')return '<p class="muted">Endringshistorikk er utilgjengelig. Dette betyr ikke at opplysningene er uendret.</p>';
 const labels={title:'Tittel',published_at:'Publiseringsdato',identity:'Selskapsidentitet',company:'Selskapsnavn',description:'Virksomhetsbeskrivelse',financials:'Regnskapstall',registry:'Registeropplysninger',document:'Dokumentvilkår eller innhentingsstatus',field_sources:'Kilder eller datastatus',source_status:'Kildestatus',sector:'Sektor',isin:'ISIN',lifecycle:'Dokumentstatus',lifecycle_evidence:'Statusbelegg'};
 const entries=(h.entries||[]).map(e=>'<li><strong>'+(e.kind==='profile'?'Selskapsopplysninger':esc(e.title||'Finansieringsdokument'))+'</strong><p>'+esc(e.revision===1?'Første lagrede versjon':'Endret lagret versjon '+e.revision)+' · registrert '+esc(date(e.recorded_at))+'</p>'+(e.revision>1?'<p>Endrede felt: '+esc([...new Set((e.changed_fields||[]).map(k=>labels[k]||'Øvrige opplysninger eller tolkning'))].join(', '))+'</p>':'')+(e.published_at?'<p>Dokument publisert '+esc(date(e.published_at))+'</p>':'')+link(e.source_url,'Åpne kilden')+(e.entity_key?'<details class="companyVersion"><summary data-version-key="'+esc(e.entity_key)+'" data-version-number="'+esc(e.revision)+'">Se lagret versjon</summary><div data-version-content></div></details>':'')+'</li>').join('');
 return '<details class="companyHistory"><summary>Hva har endret seg i datagrunnlaget?</summary><p>'+esc(h.coverage)+'</p>'+(entries?'<ol>'+entries+'</ol>':'<p>Ingen versjoner er lagret ennå.</p>')+(h.truncated?'<p>Viser de 30 nyeste versjonene. Eldre versjoner er bevart.</p>':'')+'</details>';
}
function overview(p){
 const docs=p.financing_documents||[], latest=docs[0], missing=[];
 if(!p.description)missing.push('Virksomhetsbeskrivelse');
 if(!p.isin)missing.push('ISIN');
 if(!p.financials?.length)missing.push('Regnskapstall');
 else if(p.financials.some(f=>!f.currency||!f.period))missing.push('Valuta eller rapporteringsperiode for enkelte regnskapstall');
 if(!docs.some(e=>Object.values(e.document?.terms||{}).some(t=>t.status==='documented'&&t.evidence)))missing.push('Sikkert tolkede emisjonsvilkår');
 missing.push('Bekreftet nåværende finansieringsstatus og komplett historikk');
 return '<section class="companyOverview" aria-label="Oversikt over datagrunnlaget"><h3>Rask oversikt</h3><div class="companyOverviewGrid"><div><h4>Hvilke kapitalhendelser er observert?</h4>'+(latest?'<p>'+esc(p.financing_document_count??docs.length)+' lagrede dokumenter. Nyeste publiserte dokument:</p><p>'+link(latest.url,latest.title)+' · '+esc(date(latest.published_at))+'</p>':'<p>Ingen treff i innhentet materiale. Finansieringsrisiko er fortsatt ukjent.</p>')+'<p class="muted">Dokumenter kan gjelde ulike transaksjoner. Ingen aktiv emisjon utledes automatisk.</p></div><div><h4>Hva mangler i datagrunnlaget?</h4><ul>'+missing.map(x=>'<li>'+esc(x)+'</li>').join('')+'</ul></div></div><p class="companySince" data-company-since>Endringer siden sist krever en vellykket tidligere visning på denne enheten.</p></section>';
}
function markVisit(root,p){
 const target=root.querySelector('[data-company-since]'),h=p.evidence_history;
 if(!target)return;
 if(h?.status!=='available'){target.textContent='Endringer siden sist er ukjent fordi historikken ikke kunne hentes.';return;}
 if(!p.identity||!p.ticker)return;
 try{
  const key='ns-company-seen-v1:'+p.ticker+':'+p.identity;
  const previous=JSON.parse(localStorage.getItem(key)||'null');
  const entries=(h.entries||[]).filter(e=>typeof e.entity_key==='string'&&Number.isInteger(e.revision)&&e.revision>0);
  const before=previous&&typeof previous==='object'&&!Array.isArray(previous)?previous:null;
  const fresh=before?entries.filter(e=>e.revision>(Number(before[e.entity_key])||0)).length:0;
  target.textContent=before?fresh+' nye lagrede versjoner siden forrige vellykkede visning på denne enheten. Gjelder de inntil 30 nyeste versjonene; dette er ikke en vurdering av økonomisk betydning.':'Første registrerte visning på denne enheten. Nye endringer vises ved neste besøk.';
  const next=Object.create(null);
  // Keep the current bounded window only; this avoids unbounded local storage.
  for(const e of entries)next[e.entity_key]=Math.max(next[e.entity_key]||0,e.revision);
  localStorage.setItem(key,JSON.stringify(next));
 }catch{target.textContent='Besøkshistorikk kan ikke lagres på denne enheten. Dokumenthistorikken er fortsatt tilgjengelig.';}
}
function bindHistory(root,p,requestKey){
 for(const summary of root.querySelectorAll('[data-version-key]')){
  let busy=false,loaded=false;
  summary.addEventListener('click',async()=>{
   if(summary.parentElement.open||busy||loaded)return;busy=true;
   const content=summary.parentElement.querySelector('[data-version-content]');content.textContent='Laster lagret versjon…';
   try{
    const url='/api/company-context/'+encodeURIComponent(p.ticker)+'/evidence?entity_key='+encodeURIComponent(summary.dataset.versionKey)+'&revision='+encodeURIComponent(summary.dataset.versionNumber);
    const r=await fetch(url,{signal:AbortSignal.timeout(15000)});if(!r.ok||r.redirected)throw Error();const v=await r.json();
    if(!root.isConnected||root._companyRequest!==requestKey)return;
    const old=v.payload;if(!old||!['profile','financing_document'].includes(v.kind))throw Error();
    const body=v.kind==='financing_document'?financingDocument(old):'<p>'+esc(old.description||'Virksomhetsbeskrivelse manglet i denne versjonen.')+'</p>'+provenance(old.field_sources?.description)+(old.yahoo_identity_verified===true&&old.financials?.length?'<dl>'+old.financials.map(f=>'<dt>'+esc(f.label)+'</dt><dd>'+esc(number(f.value))+' '+esc(f.currency||'(valuta ukjent)')+' · periode '+esc(f.period||'ukjent')+'</dd>').join('')+'</dl>'+provenance(old.field_sources?.financials):'<p>Ingen identitetsverifiserte regnskapstall i denne versjonen.</p>');
    content.innerHTML='<p><strong>Historisk lagret versjon '+esc(v.revision)+'</strong> · registrert '+esc(date(v.recorded_at))+'. Kan være erstattet av nyere opplysninger. Kildelenken åpner originalkilden, som kan ha endret seg.</p>'+body;loaded=true;
   }catch{if(root.isConnected&&root._companyRequest===requestKey)content.textContent='Denne versjonen kunne ikke hentes. Lukk og åpne for å prøve igjen.';}
   finally{busy=false;}
  });
 }
}
function render(p){
 if(!p||p.score_effect!==0)return '<p>Selskapsopplysninger er utilgjengelige.</p>';
 const statuses={collecting:'Venter på automatisk innhenting',unavailable:'Kildene er utilgjengelige',partial:'Delvis dekning · lagrede opplysninger',stale:'Eldre opplysninger · må kontrolleres'};
 return '<div class="companyContext">'+overview(p)+'<h3>Selskapsinformasjon</h3><p class="muted">'+esc(statuses[p.status]||'Ukjent datastatus')+' · sist hentet '+esc(date(p.captured_at))+'</p>'+historyPanel(p.evidence_history)+
 (p.description_kind==='registered_activity'?'<p class="muted">Registrert aktivitet · kan avvike fra konsernets samlede virksomhet.</p>':'')+
 '<p>'+esc(p.description||'Virksomhetsbeskrivelse er ikke tilgjengelig fra datakilden ennå.')+'</p>'+provenance(p.field_sources?.description)+'<p>Sektor: '+esc(p.sector||'Ukjent')+'</p>'+
 (p.registry?'<p>Juridisk navn: '+esc(p.registry.official_name)+' · org.nr. '+esc(p.registry.organisation_number)+'</p><p>Registrert næring: '+esc(p.registry.industry||'Ukjent')+'</p>'+provenance(p.registry):'')+
 '<p>ISIN: '+esc(p.isin||'Ukjent')+(p.isin?' · '+link(p.isin_source_url,p.isin_source||'Kilde ukjent')+' · noteringsdato '+esc(p.isin_listing_date||'ukjent'):'')+'</p>'+
 (p.financials?.length?'<dl>'+p.financials.map(f=>'<dt>'+esc(f.label)+'</dt><dd>'+esc(number(f.value))+' '+esc(f.currency||'(valuta ukjent)')+' <span class="muted">· periode '+esc(f.period)+' · '+esc(f.period_type)+'</span></dd>').join('')+'</dl>':'<p>Regnskapstall er ikke tilgjengelige ennå.</p>')+
 provenance(p.field_sources?.financials)+(p.field_sources?'':link(p.source_url,'Datakilde: '+(p.source||'ukjent')))+
 '<h3>Finansiering og utvanning</h3><p>Dokumenterte observasjoner · ingen bekreftelse på aktiv emisjon.</p>'+(p.financing_documents?.length?p.financing_documents.map(financingDocument).join(''):'<p>Ingen finansieringsmeldinger i innhentet materiale. Dette utelukker ikke emisjon eller kapitalbehov.</p>')+
 (p.financing_documents_truncated?'<p class="muted">Viser de 20 nyeste av '+esc(p.financing_document_count)+' lagrede dokumenter. Eldre dokumenter er bevart.</p>':'')+
 '<p class="muted">'+esc(p.coverage||'Dekning ukjent')+' Kildestatus: '+esc(p.news_status==='partial'?'delvis dekning':'utilgjengelig')+'. Siste forsøk: '+esc(date(p.news_checked_at))+'.</p>'+
 '<details><summary>Hva bør kontrolleres ved en emisjon?</summary><ul><li>Er emisjonen foreslått, vedtatt, gjennomført eller avlyst? Les siste melding.</li><li>Tegningskurs og antall nye aksjer: eierandelen kan bli redusert dersom du ikke deltar.</li><li>Rett til å delta, eks-dato og tegningsfrist må bekreftes i vilkårene.</li><li>Skal pengene finansiere vekst, drift, gjeld eller refinansiering?</li><li>En ny kontrakt er ikke det samme som kontanter nå og opphever ikke en emisjon.</li></ul><p>Eksisterende aksjer er ikke mindreverdige bare fordi de er «gamle». Rettigheter og aksjeklasse avhenger av dokumenterte vilkår.</p></details>'+
 '<p class="muted">Verdsettelse, kapitalbruk, eiersalg og lock-up må kontrolleres i siste rapport/prospekt når de ikke er dokumentert her. Forskning · ingen score-effekt.</p></div>';
}
async function mount(root,ticker){
 if(!root)return;const key={};root._companyRequest=key;root.innerHTML='<h2>Selskapsinformasjon og finansiering</h2><p>Laster lagrede opplysninger…</p>';
 try{const r=await fetch('/api/company-context/'+encodeURIComponent(ticker),{signal:AbortSignal.timeout(15000)});if(!r.ok||r.redirected)throw Error();const p=await r.json();if(root.isConnected&&root._companyRequest===key){root.innerHTML=render(p);if(p?.score_effect===0){markVisit(root,p);bindHistory(root,p,key);}}}
 catch{if(root.isConnected&&root._companyRequest===key)root.innerHTML='<h2>Selskapsinformasjon</h2><p>UTILGJENGELIG · selskapsopplysninger kunne ikke hentes. Dette sier ingenting om finansieringsrisikoen.</p>';}
}
window.AksjerCompany={render,mount};
})();
