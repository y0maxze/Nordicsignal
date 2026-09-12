(function(){
  const STORAGE_KEY='nordicsignal-theme';
  const LIGHT_FIX_ID='ns-light-theme-fix';
  const root=document.documentElement;
  const media=window.matchMedia?window.matchMedia('(prefers-color-scheme: light)'):null;
  const prefersLight=()=>!!(media&&media.matches);

  function ensureContrastLayer(){
    if(document.getElementById(LIGHT_FIX_ID))return;
    const link=document.createElement('link');
    link.id=LIGHT_FIX_ID;
    link.rel='stylesheet';
    link.href='/theme_light_fix.css';
    document.head.appendChild(link);
  }

  function current(){
    const saved=localStorage.getItem(STORAGE_KEY);
    if(saved==='light'||saved==='dark')return saved;
    return prefersLight()?'light':'dark';
  }

  function apply(theme){
    ensureContrastLayer();
    const next=theme==='light'?'light':'dark';
    root.dataset.theme=next;
    root.style.colorScheme=next;
    const themeColor=next==='light'?'#eef5ff':'#040712';
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

  if(media){
    const syncSystemTheme=()=>{
      if(!localStorage.getItem(STORAGE_KEY))apply(prefersLight()?'light':'dark');
    };
    if(media.addEventListener)media.addEventListener('change',syncSystemTheme);
    else if(media.addListener)media.addListener(syncSystemTheme);
  }

  document.addEventListener('click',e=>{
    const btn=e.target.closest&&e.target.closest('[data-ns-theme-toggle]');
    if(btn){e.preventDefault();toggle();}
  });
})();
