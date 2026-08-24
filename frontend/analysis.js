(function(){
  function load(src){return new Promise((resolve,reject)=>{const s=document.createElement('script');s.src=src;s.onload=resolve;s.onerror=reject;document.body.appendChild(s)})}
  load('/frontend/analysis_legacy.js').then(()=>load('/frontend/enhancements.js')).catch(console.error);
})();
