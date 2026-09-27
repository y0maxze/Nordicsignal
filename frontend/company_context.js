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
function render(p){
 if(!p||p.score_effect!==0)return '<p>Selskapsopplysninger er utilgjengelige.</p>';
 const statuses={collecting:'Venter på automatisk innhenting',unavailable:'Kildene er utilgjengelige',partial:'Delvis dekning · lagrede opplysninger',stale:'Eldre opplysninger · må kontrolleres'};
 return '<div class="companyContext"><h3>Selskapsinformasjon</h3><p class="muted">'+esc(statuses[p.status]||'Ukjent datastatus')+' · sist hentet '+esc(date(p.captured_at))+'</p>'+
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
 try{const r=await fetch('/api/company-context/'+encodeURIComponent(ticker),{signal:AbortSignal.timeout(15000)});if(!r.ok||r.redirected)throw Error();const p=await r.json();if(root.isConnected&&root._companyRequest===key)root.innerHTML=render(p);}
 catch{if(root.isConnected&&root._companyRequest===key)root.innerHTML='<h2>Selskapsinformasjon</h2><p>UTILGJENGELIG · selskapsopplysninger kunne ikke hentes. Dette sier ingenting om finansieringsrisikoen.</p>';}
}
window.AksjerCompany={render,mount};
})();
