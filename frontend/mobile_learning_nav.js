(function(){
  function mountLearningNav(){
    const nav=document.getElementById('nsMobileNav');
    if(!nav||nav.querySelector('a[href="/learning"]'))return;
    nav.style.gridTemplateColumns='repeat(6,1fr)';
    const link=document.createElement('a');
    link.href='/learning';
    link.className=location.pathname.startsWith('/learning')||location.pathname.startsWith('/signal-performance')?'active':'';
    link.innerHTML='<span class="nsMobileNavIcon">◇</span>Læring';
    const news=nav.querySelector('a[href="/news"]');
    if(news)nav.insertBefore(link,news);else nav.appendChild(link);
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(mountLearningNav,0),{once:true});
  else setTimeout(mountLearningNav,0);
})();
