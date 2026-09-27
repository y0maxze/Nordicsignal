const {test}=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const {JSDOM}=require('jsdom');
const script=fs.readFileSync('frontend/company_context.js','utf8');
test('company facts escape content and preserve unknowns',()=>{const d=new JSDOM('',{runScripts:'outside-only'});d.window.eval(script);const html=d.window.AksjerCompany.render({score_effect:0,status:'partial',description:'<img src=x onerror=alert(1)>',financials:[{label:'Gjeld',value:12,period:'2025-12-31'}],source_url:'javascript:alert(1)',financing_documents:[]});d.window.document.body.innerHTML=html;assert.equal(d.window.document.querySelector('img'),null);assert.equal(d.window.document.querySelector('a'),null);assert.match(html,/valuta ukjent/);assert.match(html,/utelukker ikke emisjon/);assert.match(html,/ingen score-effekt/);});
test('failed fetch is not absence of financing risk',async()=>{const d=new JSDOM('<section></section>',{runScripts:'outside-only'});d.window.eval(script);d.window.AbortSignal.timeout=()=>undefined;d.window.fetch=async()=>({ok:false});await d.window.AksjerCompany.mount(d.window.document.querySelector('section'),'TECH');assert.match(d.window.document.body.textContent,/UTILGJENGELIG/);assert.match(d.window.document.body.textContent,/sier ingenting om finansieringsrisikoen/);});

test('financing shows historical evidence, source failure and explicit missing terms',()=>{
 const d=new JSDOM('',{runScripts:'outside-only'});d.window.eval(script);
 d.window.document.body.innerHTML=d.window.AksjerCompany.render({score_effect:0,status:'partial',financing_documents:[{title:'Example rights issue',url:'https://live.euronext.com/en/node/1',financing_type:'rights_issue',lifecycle:'open',lifecycle_evidence:'Subscription period opens for rights issue',evidence_scope:'official_title',published_at:'2026-06-01T10:00:00Z',document:{status:'unavailable'}}]});
 const text=d.window.document.body.textContent;
 assert.match(text,/Dokumentstatus: Åpnet/);assert.match(text,/Dagens status er ikke bekreftet/);assert.match(text,/Kilden utilgjengelig/);assert.match(text,/Utvanning: Ukjent/);assert.match(text,/TegningsfristUkjent/);
 assert.equal(d.window.document.querySelectorAll('.financingDocument').length,1);
});
test('terms require evidence and do not lose qualifications or expose HTML',()=>{
 const d=new JSDOM('',{runScripts:'outside-only'});d.window.eval(script);
 const html=d.window.AksjerCompany.render({score_effect:0,financing_documents:[{title:'Terms',lifecycle:'completed',document:{status:'partial',terms:{subscription_price:{status:'documented',value:'NOK 2 subject to approval <img src=x>',evidence:'Subscription price: NOK 2 subject to approval <img src=x>'},new_shares:{status:'documented',value:'5000000'},record_date:{status:'ambiguous',value:'2026-01-01'}}}}]});
 d.window.document.body.innerHTML=html;
 assert.match(d.window.document.body.textContent,/Dokumentstatus: Ukjent/);
 assert.match(d.window.document.body.textContent,/subject to approval/);
 assert.equal(d.window.document.querySelector('img'),null);
 assert.doesNotMatch(d.window.document.body.textContent,/5000000|2026-01-01/);
});
test('dilution exposes exact inputs and limitation only for calculated data',()=>{
 const d=new JSDOM('',{runScripts:'outside-only'});d.window.eval(script);
 const html=d.window.AksjerCompany.render({score_effect:0,financing_documents:[{document:{dilution:{status:'calculated',percentage:'20.0000',existing_shares:4000000,new_shares:1000000,share_class:'Ordinary shares',limitation:'Dokumentscenario, ikke kurstap.'}}}],financing_documents_truncated:true,financing_document_count:25});
 d.window.document.body.innerHTML=html;
 assert.match(d.window.document.body.textContent,/20 % · beregnet dokumentscenario/);
 assert.match(d.window.document.body.textContent,/1000000 \/ \(4000000 \+ 1000000\)/);
 assert.match(d.window.document.body.textContent,/ikke kurstap/);
 assert.match(d.window.document.body.textContent,/20 nyeste av 25/);
});
test('registry activity and stale description keep separate financial provenance',()=>{
 const d=new JSDOM('',{runScripts:'outside-only'});d.window.eval(script);
 const html=d.window.AksjerCompany.render({score_effect:0,description:'Registered activity',description_kind:'registered_activity',field_sources:{description:{source:'Brønnøysundregistrene',source_url:'https://data.brreg.no/enhetsregisteret/api/enheter/977037093',status:'stale',captured_at:'2026-09-01T00:00:00Z'},financials:{source:'Yahoo Finance',source_url:'https://finance.yahoo.com/quote/TECH.OL/'}},registry:{official_name:'TECHSTEP ASA',organisation_number:'977037093'},financials:[]});
 d.window.document.body.innerHTML=html;
 assert.match(d.window.document.body.textContent,/Registrert aktivitet · kan avvike/);
 assert.match(d.window.document.body.textContent,/Eldre opplysning/);
 assert.match(d.window.document.body.textContent,/TECHSTEP ASA/);
 assert.match(d.window.document.body.textContent,/ISIN: Ukjent/);
 assert.equal(d.window.document.querySelectorAll('a').length,2);
});

test('history distinguishes recording from publication and escapes source titles',()=>{
 const d=new JSDOM('',{runScripts:'outside-only'});d.window.eval(script);
 d.window.document.body.innerHTML=d.window.AksjerCompany.render({score_effect:0,evidence_history:{status:'available',coverage:'Registreringstid er ikke publiseringstid.',truncated:true,entries:[{kind:'financing_document',revision:2,title:'<img src=x>',recorded_at:'2026-09-27T00:00:00Z',published_at:'2026-06-01T00:00:00Z',source_url:'javascript:alert(1)',changed_fields:['title','document']}]}});
 assert.equal(d.window.document.querySelector('img'),null);assert.equal(d.window.document.querySelector('a'),null);
 assert.match(d.window.document.body.textContent,/Endret lagret versjon 2/);
 assert.match(d.window.document.body.textContent,/Dokument publisert/);
 assert.match(d.window.document.body.textContent,/Eldre versjoner er bevart/);
 assert.match(d.window.document.body.textContent,/Dokumentvilkår eller innhentingsstatus/);
});

test('overview exposes partial coverage and missing data instead of reassuring on zero hits',()=>{
 const d=new JSDOM('',{runScripts:'outside-only'});d.window.eval(script);
 d.window.document.body.innerHTML=d.window.AksjerCompany.render({score_effect:0,financials:[{value:1}],financing_documents:[]});
 const t=d.window.document.querySelector('.companyOverview').textContent;
 assert.match(t,/Finansieringsrisiko er fortsatt ukjent/);
 assert.match(t,/Valuta eller rapporteringsperiode/);
 assert.match(t,/Bekreftet nåværende finansieringsstatus og komplett historikk/);
});
test('since-last-view tracks evidence revisions only after successful rendering and by issuer',async()=>{
 const d=new JSDOM('<section></section>',{url:'https://app.test/stock',runScripts:'outside-only'});d.window.eval(script);d.window.AbortSignal.timeout=()=>undefined;
 const root=d.window.document.querySelector('section');
 let p={score_effect:0,ticker:'TECH',identity:'techstep',evidence_history:{status:'available',entries:[{entity_key:'doc',revision:1}]}};
 d.window.fetch=async()=>({ok:true,json:async()=>p});
 await d.window.AksjerCompany.mount(root,'TECH');assert.match(root.textContent,/Første registrerte visning/);
 p.evidence_history.entries.push({entity_key:'doc',revision:2});
 await d.window.AksjerCompany.mount(root,'TECH');assert.match(root.textContent,/1 nye lagrede versjoner/);
 await d.window.AksjerCompany.mount(root,'TECH');assert.match(root.textContent,/0 nye lagrede versjoner/);
 p.evidence_history={status:'unavailable'};
 await d.window.AksjerCompany.mount(root,'TECH');assert.match(root.textContent,/Endringer siden sist er ukjent/);
 p.evidence_history={status:'available',entries:[{entity_key:'doc',revision:3}]};
 await d.window.AksjerCompany.mount(root,'TECH');assert.match(root.textContent,/1 nye lagrede versjoner/);
 p.identity='different issuer';
 await d.window.AksjerCompany.mount(root,'TECH');assert.match(root.textContent,/Første registrerte visning/);
});
test('blocked browser storage does not hide company facts',async()=>{
 const d=new JSDOM('<section></section>',{runScripts:'outside-only'});d.window.eval(script);d.window.AbortSignal.timeout=()=>undefined;
 d.window.fetch=async()=>({ok:true,json:async()=>({score_effect:0,ticker:'TECH',identity:'techstep',description:'Verified description',evidence_history:{status:'available',entries:[]}})});
 await d.window.AksjerCompany.mount(d.window.document.querySelector('section'),'TECH');
 assert.match(d.window.document.body.textContent,/Verified description/);
 assert.match(d.window.document.body.textContent,/Besøkshistorikk kan ikke lagres/);
});

test('historical version loads on demand, preserves old evidence and does not leak unverified financials',async()=>{
 const d=new JSDOM('<section></section>',{url:'https://app.test',runScripts:'outside-only'});d.window.eval(script);d.window.AbortSignal.timeout=()=>undefined;
 const calls=[];
 d.window.fetch=async url=>{calls.push(url);return {ok:true,json:async()=>url.includes('/evidence?')?{kind:'profile',revision:1,recorded_at:'2026-09-01T00:00:00Z',payload:{description:'Older <script>alert(1)</script>',financials:[{label:'Unverified',value:987654321}]}}:{score_effect:0,ticker:'TECH',identity:'techstep',evidence_history:{status:'available',entries:[{kind:'profile',entity_key:'profile|TECH',revision:1}]}}};};
 await d.window.AksjerCompany.mount(d.window.document.querySelector('section'),'TECH');
 assert.equal(calls.length,1);
 d.window.document.querySelector('[data-version-key]').click();await new Promise(r=>setImmediate(r));
 assert.equal(calls.length,2);assert.match(calls[1],/entity_key=profile%7CTECH&revision=1/);
 assert.match(d.window.document.body.textContent,/Historisk lagret versjon 1/);
 assert.match(d.window.document.body.textContent,/Older/);assert.doesNotMatch(d.window.document.body.textContent,/Unverified|987654321/);
 assert.equal(d.window.document.querySelector('script'),null);
});

test('outdated extraction is explicitly awaiting revalidation',()=>{
 const d=new JSDOM('',{runScripts:'outside-only'});d.window.eval(script);
 const html=d.window.AksjerCompany.render({score_effect:0,financing_documents:[{document:{status:'revalidation_required',terms:{},dilution:{status:'unknown'}}}]});
 assert.match(html,/Venter på ny dokumentkontroll/);assert.match(html,/Utvanning: Ukjent/);
});
