(function(){
  function cleanTicker(value){return String(value||'').trim().toUpperCase().replace(/\.OL$/,'')}
  window.showStock=function(ticker){
    const t=cleanTicker(ticker);if(!t)return;
    location.href='/stock?ticker='+encodeURIComponent(t);
  };
  function load(src){return new Promise((resolve,reject)=>{const s=document.createElement('script');s.src=src;s.onload=resolve;s.onerror=reject;document.body.appendChild(s)})}
  load('/dashboard_enhancements.js')
    .catch(console.error)
    .finally(()=>load('/dashboard_performance.js').catch(console.error))
    .finally(()=>load('/portfolio_dashboard.js').catch(console.error));
})();
