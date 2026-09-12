(function(){
  if(!location.pathname.startsWith('/history'))return;

  function activate(){
    const mobileNav=document.getElementById('nsMobileNav');
    const moreToggle=document.getElementById('nsMobileMoreToggle');
    const moreMenu=document.getElementById('nsMobileMoreMenu');
    if(mobileNav){mobileNav.querySelectorAll('.active').forEach(node=>node.classList.remove('active'))}
    if(moreToggle){moreToggle.classList.add('active')}
    if(moreMenu){
      let link=moreMenu.querySelector('a[href="/history"]');
      if(!link){link=document.createElement('a');link.href='/history';link.textContent='Kurshistorikk';moreMenu.appendChild(link)}
      moreMenu.querySelectorAll('a').forEach(node=>{node.classList.remove('active');node.removeAttribute('aria-current')});
      link.classList.add('active');link.setAttribute('aria-current','page');
    }
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(activate,0),{once:true});
  else setTimeout(activate,0);
})();
