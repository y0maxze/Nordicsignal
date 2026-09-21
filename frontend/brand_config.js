/* Single source of truth for user-facing NordicSignal brand metadata.
   This file is intentionally runtime-safe in both browsers and the Cloudflare Worker bundle. */
(function(root){
  if(root.NORDICSIGNAL_BRAND)return;
  root.NORDICSIGNAL_BRAND=Object.freeze({
    name:'Aksjer',
    label:'AKSJER',
    appleTitle:'Aksjer',
    mark:'/aksjer-mark.svg',
    accent:'#19a7ff',
    themeDark:'#040712',
    themeLight:'#eef5ff'
  });
})(globalThis);
