/* The mobile viewport has separate header, scroll area and navigation rows.
   Navigation never overlays the scrolling analysis or follows its transforms. */
(function(){
 function mount(){
  let nav=document.getElementById('nsMobileNav');
  if(!nav){nav=document.createElement('nav');nav.id='nsMobileNav'}
  nav.className='nsMobileNav';nav.setAttribute('aria-label','Aksjer navigasjon');
  const morning=location.pathname.startsWith('/morning');
  nav.innerHTML='<a href="/app"'+(!morning?' class="active"':'')+'>Marked</a><a href="/morning"'+(morning?' class="active"':'')+'>Før børs</a>';
  let content=document.getElementById('aksjerScrollArea');
  if(!content){
   content=document.createElement('div');content.id='aksjerScrollArea';content.tabIndex=0;content.setAttribute('aria-label','Sideinnhold');
   for(const el of [...document.body.children]){
    if(el===nav||el.id==='aksjerHeader'||['SCRIPT','STYLE','LINK'].includes(el.tagName))continue;
    content.appendChild(el);
   }
   document.body.appendChild(content);
  }
  document.body.appendChild(nav);document.body.classList.add('aksjerMobileLayout');
  if(!document.getElementById('aksjerMobileNavStyle')){
   const s=document.createElement('style');s.id='aksjerMobileNavStyle';
   s.textContent=`#aksjerScrollArea{display:contents}
@media(max-width:900px){
 html:root body.aksjerMobileLayout{display:grid!important;grid-template-rows:auto minmax(0,1fr) auto!important;height:100vh;height:100dvh;margin:0!important;padding:0!important;overflow:hidden!important}
 #aksjerHeader{grid-row:1;min-width:0}
 #aksjerScrollArea{display:block;grid-row:2;min-height:0;min-width:0;overflow:auto;overscroll-behavior-y:contain;scroll-padding:16px;padding-bottom:16px}
 #aksjerScrollArea .app{min-height:0!important}
 html:root body #nsMobileNav{grid-row:3;display:grid!important;grid-template-columns:minmax(0,1fr) minmax(0,1fr)!important;position:relative!important;inset:auto!important;z-index:20!important;margin:0!important;padding:4px 12px max(4px,env(safe-area-inset-bottom))!important;background:var(--surface,#07111f)!important;border:0!important;border-top:1px solid var(--line,#20354d)!important;border-radius:0!important;transform:none!important;box-shadow:none!important}
 html:root body #nsMobileNav a{height:48px!important;min-height:48px!important;min-width:0;display:flex!important;align-items:center!important;justify-content:center!important;text-decoration:none!important;color:var(--m,#91a5bd)!important;font-weight:700!important;margin:0!important;white-space:nowrap!important;transform:none!important}
 html:root body #nsMobileNav a.active{color:var(--t,#eef5ff)!important;background:var(--surface-2,#10243a)!important;border-radius:0!important}
}
@media(min-width:901px){#nsMobileNav{display:none!important}}`;
   document.head.appendChild(s);
  }
 }
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount,{once:true});else mount();
})();
