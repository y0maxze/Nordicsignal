(function(){
  const STORAGE_KEY='nordicsignal-theme';
  const root=document.documentElement;
  const prefersLight=()=>window.matchMedia&&window.matchMedia('(prefers-color-scheme: light)').matches;
  function current(){
    const saved=localStorage.getItem(STORAGE_KEY);
    if(saved==='light'||saved==='dark')return saved;
    return prefersLight()?'light':'dark';
  }
  function apply(theme){
    const next=theme==='light'?'light':'dark';
    root.dataset.theme=next;
    root.style.colorScheme=next;
    const themeColor=next==='light'?'#f4f4f2':'#070707';
    let meta=document.querySelector('meta[name="theme-color"]');
    if(!meta){meta=document.createElement('meta');meta.name='theme-color';document.head.appendChild(meta)}
    meta.content=themeColor;
    document.querySelectorAll('[data-ns-theme-toggle]').forEach(btn=>{
      btn.setAttribute('aria-label',next==='dark'?'Bytt til lyst tema':'Bytt til mørkt tema');
      btn.setAttribute('title',next==='dark'?'Lyst tema':'Mørkt tema');
      btn.textContent=next==='dark'?'☀︎':'☾';
    });
  }
  function toggle(){
    const next=(root.dataset.theme||current())==='dark'?'light':'dark';
    localStorage.setItem(STORAGE_KEY,next);
    apply(next);
  }
  window.NordicSignalTheme={apply,toggle,current};
  apply(current());
  document.addEventListener('click',e=>{
    const btn=e.target.closest&&e.target.closest('[data-ns-theme-toggle]');
    if(btn){e.preventDefault();toggle();}
  });
})();
