import fs from 'node:fs';
const html=fs.readFileSync(new URL('./home.html',import.meta.url),'utf8');
const css=fs.readFileSync(new URL('./home.css',import.meta.url),'utf8');
const js=fs.readFileSync(new URL('./home.js',import.meta.url),'utf8');
const shell=fs.readFileSync(new URL('./ui_shell.js',import.meta.url),'utf8');
for(const token of ['NORDICSIGNAL','MARKET DATA','FUNDAMENTALS','INSIDER DATA','EVENT RADAR','HIGH CONVICTION','IPO · PUSH · BRIEF']){
  if(!html.includes(token)) throw new Error(`missing homepage token: ${token}`);
}
if(!css.includes('prefers-reduced-motion')) throw new Error('reduced-motion fallback missing');
if(!js.includes('IntersectionObserver')) throw new Error('scroll reveal logic missing');
if(!js.includes('/api/stocks')) throw new Error('live homepage status missing');
if(shell.includes('installHero')) throw new Error('dashboard must not duplicate landing hero');
console.log('cinematic homepage checks passed');
