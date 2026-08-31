(()=>{
  if(!('ServiceWorkerRegistration' in window))return;
  const proto=ServiceWorkerRegistration.prototype;
  const original=proto.showNotification;
  if(typeof original!=='function'||proto.__nsAlertHistoryWrapped)return;
  proto.__nsAlertHistoryWrapped=true;

  proto.showNotification=async function(title,options={}){
    const result=await original.call(this,title,options);
    try{
      const tag=String(options?.tag||'').slice(0,280);
      const url=String(options?.data?.url||'/alerts');
      fetch('/api/alerts/record',{
        method:'POST',cache:'no-store',keepalive:true,
        headers:{'content-type':'application/json'},
        body:JSON.stringify({
          event_key:tag||`${String(title||'NordicSignal')}|${String(options?.body||'')}|${Date.now()}`,
          title:String(title||'NordicSignal'),
          body:String(options?.body||''),
          url:url.startsWith('/')?url:'/alerts',
          timestamp:new Date().toISOString()
        })
      }).catch(()=>{});
    }catch{}
    return result;
  };
})();
