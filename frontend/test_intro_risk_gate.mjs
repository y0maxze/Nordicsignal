import fs from 'node:fs';
const html=fs.readFileSync(new URL('./home.html',import.meta.url),'utf8');
const css=fs.readFileSync(new URL('./home.css',import.meta.url),'utf8');
const shell=fs.readFileSync(new URL('./ui_shell.js',import.meta.url),'utf8');
for(const token of ['/nordicsignal-intro.jpg','NS-RISK-2026-08-27-2','nordicsignal_policy_session_acceptance','riskAccept','Godta og åpne NordicSignal',"location.assign('/app')"]){
  if(!html.includes(token)) throw new Error(`missing intro/risk token: ${token}`);
}
if(html.includes('/home.js')) throw new Error('obsolete cinematic homepage script must not load');
for(const token of ['.introArt','.riskGate','prefers-reduced-motion']){
  if(!css.includes(token)) throw new Error(`missing intro style: ${token}`);
}
if(shell.includes('installHero')) throw new Error('dashboard must not duplicate landing hero');
console.log('image-first intro and risk gate checks passed');
