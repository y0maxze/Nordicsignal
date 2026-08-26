(function(){
  function load(src){return new Promise((resolve,reject)=>{const s=document.createElement('script');s.src=src;s.onload=resolve;s.onerror=reject;document.body.appendChild(s)})}
  load('/analysis_legacy.js')
    .catch(console.error)
    .finally(()=>load('/dashboard_enhancements.js').catch(console.error))
    .finally(()=>load('/dashboard_performance.js').catch(console.error));
})();
