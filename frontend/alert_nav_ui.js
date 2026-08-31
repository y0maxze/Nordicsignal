(()=>{
  if(location.pathname.startsWith('/alerts')||document.getElementById('nsAlertShortcut'))return;
  const style=document.createElement('style');style.textContent=`@media(max-width:900px){.nsAlertShortcut{position:fixed;z-index:2147483100;right:14px;bottom:88px;width:48px;height:48px;border-radius:16px;border:1px solid #333;background:rgba(15,15,15,.97);color:#fff!important;text-decoration:none!important;display:grid;place-items:center;font:700 21px system-ui;box-shadow:0 14px 38px rgba(0,0,0,.45);backdrop-filter:blur(12px)}.nsAlertBadge{position:absolute;right:-4px;top:-5px;min-width:20px;height:20px;border-radius:10px;background:#f2f2f2;color:#050505;font:800 10px/20px system-ui;text-align:center;padding:0 5px;border:2px solid #0b0b0b}.nsAlertBadge[hidden]{display:none}}`;document.head.appendChild(style);
  const a=document.createElement('a');a.id='nsAlertShortcut';a.className='nsAlertShortcut';a.href='/alerts';a.setAttribute('aria-label','Åpne varsler');a.innerHTML='♢<span class="nsAlertBadge" hidden></span>';document.body.appendChild(a);
  const badge=a.querySelector('.nsAlertBadge');
  fetch('/api/alerts?limit=1',{cache:'no-store'}).then(r=>r.ok?r.json():null).then(data=>{const n=Number(data?.unread||0);if(n>0){badge.textContent=n>99?'99+':String(n);badge.hidden=false}}).catch(()=>{});
})();
