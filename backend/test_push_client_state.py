"""Execute the real push client: stale preferences and failed registration are not success."""
import json
import subprocess
from pathlib import Path


def test_push_client_requires_confirmed_registration_and_has_no_legacy_polling():
    script = (Path(__file__).resolve().parents[1] / 'frontend/mobile_shell.js').read_text()
    program = r'''
const vm=require('node:vm'),assert=require('node:assert/strict');
const elements=new Map(),requests=[];let mode='denied',timers=0;
const saved=new Map([['ns-mobile-alerts-v1','1']]);
const sub={endpoint:'https://push.example.test/device',toJSON:()=>({endpoint:sub.endpoint,keys:{p256dh:'key',auth:'auth'}})};
const reg={pushManager:{getSubscription:async()=>sub}};
const ctx={AbortSignal,URLSearchParams,Uint8Array,atob,setTimeout,clearTimeout,
 setInterval(){timers++;},localStorage:{getItem:k=>saved.get(k),setItem:(k,v)=>saved.set(k,v),removeItem:k=>saved.delete(k)},
 location:{pathname:'/alerts',search:''},Notification:{permission:'granted'},
 navigator:{userAgent:'test',serviceWorker:{register:async()=>reg,ready:Promise.resolve(reg)}},
 document:{readyState:'complete',getElementById:k=>elements.get(k),createElement:()=>({})},
 fetch:async(url,options)=>{requests.push(url);return {ok:mode!=='denied'||!options.method,redirected:false,json:async()=>url.endsWith('public-key')?{configured:true,public_key:'key'}:url.endsWith('status')?{delivery_ready:true}:{status:'ok',delivery_ready:mode==='ready'}}},
 console,matchMedia:()=>({matches:false}),addEventListener(){},PushManager:function(){}};
ctx.window=ctx;vm.createContext(ctx);vm.runInContext(SCRIPT,ctx);
(async()=>{
 await new Promise(setImmediate);
 assert.equal(requests.length,0,'Opening inbox with old preference must do no push/portfolio reads');
 assert.equal(timers,0);
 const button={classList:{toggle(){}},insertAdjacentElement(_,el){elements.set(el.id,el)}};
 elements.set('nsEnableAlerts',button);elements.set('alertStatus',{textContent:''});
 let state=await ctx.NordicSignalMobile.currentPushState();
 assert.equal(state.active,false,'Browser subscription plus configured server does not prove registration');
 for(const value of ['denied','not_configured']){
   mode=value;await ctx.NordicSignalMobile.enableAlerts();
   assert.equal(saved.has('ns-mobile-alerts-v1'),false);
   assert.equal(elements.get('nsTestPush').hidden,true);
   assert.equal(button.disabled,false);
 }
 mode='ready';await ctx.NordicSignalMobile.enableAlerts();
 assert.equal(saved.get('ns-mobile-alerts-v1'),'1');
 assert.equal((await ctx.NordicSignalMobile.currentPushState()).active,true);
 assert.equal(elements.get('nsTestPush').hidden,false);
 assert.equal(timers,0);
 assert.ok(requests.every(p=>p.startsWith('/api/push/')));
})().catch(e=>{console.error(e);process.exit(1)});
'''.replace('SCRIPT', json.dumps(script))
    subprocess.run(['node','-e',program],check=True,capture_output=True,text=True)
