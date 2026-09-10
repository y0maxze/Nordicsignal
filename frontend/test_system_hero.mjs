import fs from 'node:fs';
const src=fs.readFileSync(new URL('./ui_shell.js',import.meta.url),'utf8');
for(const token of ['nsHero','nsMark','NORDICSIGNAL','HIGH CONVICTION','prefers-reduced-motion','SYSTEM ONLINE']){
  if(!src.includes(token)) throw new Error(`missing hero token: ${token}`);
}
if(!src.includes("new URLSearchParams(location.search).get('view')==='signals'")) throw new Error('hero must stay out of signals view');
console.log('system hero checks passed');
