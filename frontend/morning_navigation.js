/* Resolve missing announcement tickers only after user interaction. Never infer
   a ticker from the headline or accept a fuzzy result as an exact identity. */
(function(){
 const normalize=value=>String(value||'').toLocaleLowerCase('nb-NO').replace(/[.,]/g,' ').replace(/\s+(asa|as|ab|plc|ltd|limited)\s*$/,'').replace(/\s+/g,' ').trim();
 function candidates(data){
  const seen=new Set();
  return (Array.isArray(data)?data:(data.items||[])).filter(x=>{
   const symbol=String(x.market_symbol||x.symbol||x.ticker||'').trim().toUpperCase();
   const kind=String(x.quote_type||x.asset_class||'').toUpperCase();
   if(!(x.tracked===true||symbol.endsWith('.OL'))||!['EQUITY','AKSJER','STOCK'].includes(kind))return false;
   const ticker=String(x.ticker||symbol).trim().toUpperCase().replace(/\.OL$/,'');
   if(!/^[A-Z0-9][A-Z0-9.-]{0,19}$/.test(ticker)||seen.has(ticker))return false;
   seen.add(ticker);return true;
  }).map(x=>({...x,ticker:String(x.ticker||x.market_symbol||x.symbol).trim().toUpperCase().replace(/\.OL$/,'')}));
 }
 async function resolve(button){
  if(button.disabled)return;
  const row=button.closest('.eventRow,.newsRow'),query=button.dataset.companyQuery;
  let box=row.querySelector('.morningStockChoices');
  if(!box){box=document.createElement('div');box.className='morningStockChoices';box.setAttribute('aria-live','polite');row.appendChild(box)}
  button.disabled=true;box.textContent='Søker etter aksjen…';
  try{
   const response=await fetch('/api/search?q='+encodeURIComponent(query)+'&limit=12',{cache:'no-store',signal:AbortSignal.timeout(15000)});
   if(!response.ok)throw Error('search unavailable');
   const data=await response.json();if(!button.isConnected)return;
   const items=candidates(data),exact=items.filter(x=>normalize(x.name)===normalize(query));
   if(exact.length===1&&!data.warning){location.href='/stock?ticker='+encodeURIComponent(exact[0].ticker);return}
   box.textContent=items.length?'Velg riktig aksje:':data.warning?'Aksjesøket er delvis utilgjengelig. Prøv igjen.':'Ingen Oslo-aksje funnet. Se originalmeldingen for selskapsinformasjon.';
   for(const item of items){const a=document.createElement('a');a.href='/stock?ticker='+encodeURIComponent(item.ticker);a.textContent=(item.name||item.ticker)+' · '+item.ticker;a.className='morningStockChoice';box.appendChild(a)}
  }catch{if(button.isConnected)box.textContent='Aksjesøket er utilgjengelig. Trykk på selskapsnavnet for å prøve igjen.'}
  finally{button.disabled=false}
 }
 document.addEventListener('click',event=>{
  const button=event.target.closest('[data-company-query]');if(button){resolve(button);return}
  if(event.target.closest('a,button'))return;
  const row=event.target.closest('[data-stock-url]');if(row)location.href=row.dataset.stockUrl;
 });
 document.addEventListener('keydown',event=>{if((event.key==='Enter'||event.key===' ')&&event.target.matches('[data-stock-url]')){event.preventDefault();location.href=event.target.dataset.stockUrl}});
})();
