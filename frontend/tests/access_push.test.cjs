const {test}=require('node:test'),assert=require('node:assert/strict');
// Real signed JWTs and the real Worker; only external JWKS/backend HTTP are mocked.
test('push proxy verifies identity and keeps every other write closed',async()=>{
 const {generateKeyPair,exportJWK,SignJWT}=await import('jose');
 const {publicKey,privateKey}=await generateKeyPair('RS256');
 const jwk={...await exportJWK(publicKey),kid:'test-key',alg:'RS256',use:'sig'};
 const issuer='https://unit-test.cloudflareaccess.com',audience='a'.repeat(64);
 const env={NORDICSIGNAL_ACCESS_ISSUER:issuer,NORDICSIGNAL_ACCESS_AUD:audience,NORDICSIGNAL_WRITE_TOKEN:'test-only-secret',ASSETS:{fetch:async()=>new Response('asset')}};
 const origin='https://app.example.test';let backend=[],keyCalls=0;
 const originalFetch=globalThis.fetch;
 globalThis.fetch=async(request)=>{
  const url=typeof request==='string'?request:request instanceof URL?request.href:request.url;
  if(url===issuer+'/cdn-cgi/access/certs'){keyCalls++;return Response.json({keys:[jwk]});}
  assert.ok(url.startsWith('https://nordicsignal-api.onrender.com/'));
  backend.push(request);return Response.json({status:'ok'});
 };
 try {
  const worker=(await import('../../worker.js')).default;
  const now=Math.floor(Date.now()/1000);
  async function token(overrides={},key=privateKey,alg='RS256') {
   return new SignJWT({iss:issuer,aud:[audience],sub:'owner',email:'owner@example.test',type:'app',iat:now,nbf:now-1,exp:now+300,...overrides}).setProtectedHeader({alg,kid:'test-key'}).sign(key);
  }
  const good=await token();
  const headers={'origin':origin,'sec-fetch-site':'same-origin','content-type':'application/json','cf-access-jwt-assertion':good};
  async function send(path='/api/push/subscribe',opts={}) {
   const {envOverride,...init}=opts;
   return worker.fetch(new Request(origin+path,{method:'POST',headers,body:'{"endpoint":"https://push.example.test/device"}',...init}),envOverride||env);
  }
  for(const bad of [null,'malformed',await token({aud:['wrong']}),await token({iss:'https://evil.test'}),await token({exp:now-1}),await token({exp:undefined}),await token({nbf:now+60}),await token({iat:now+60}),await token({sub:''}),await token({email:undefined}),await token({type:'org'}),await token({},(await generateKeyPair('RS256')).privateKey),await token({},new Uint8Array(32),'HS256')]) {
   const h={...headers};if(bad)h['cf-access-jwt-assertion']=bad;else delete h['cf-access-jwt-assertion'];
   h['cf-access-authenticated-user-email']='forged@example.test';
   assert.equal((await send(undefined,{headers:h})).status,403);
  }
  for(const path of ['/api/refresh','/api/opportunity-scan/run','/api/push/subscribe/','/api/push/subscribe?refresh=true','/api/push/test?x=1'])assert.equal((await send(path)).status,403,path);
  for(const method of ['PUT','PATCH','DELETE'])assert.equal((await send(undefined,{method})).status,403);
  for(const extra of [{origin:'https://evil.test'},{origin:'null'},{origin:''},{'sec-fetch-site':'cross-site'},{'content-type':'text/plain'}])assert.equal((await send(undefined,{headers:{...headers,...extra}})).status,403);
  for(const envOverride of [{...env,NORDICSIGNAL_ACCESS_AUD:''},{...env,NORDICSIGNAL_ACCESS_ISSUER:'https://evil.test'},{...env,NORDICSIGNAL_WRITE_TOKEN:''}])assert.equal((await send(undefined,{envOverride})).status,403);
  for(const body of ['[]','null','not json','{"huge":"'+'x'.repeat(17000)+'"}'])assert.equal((await send(undefined,{body})).status,400);
  assert.equal(backend.length,0,'Denied requests must never reach the token relay');
  for(const path of ['/api/push/subscribe','/api/push/unsubscribe','/api/push/test']){
   const response=await send(path,{headers:{...headers,cookie:'CF_Authorization=sensitive',authorization:'Bearer sensitive','cf-access-client-secret':'sensitive','x-nordicsignal-internal-token':'forged'}});
   assert.equal(response.status,200);
   const request=backend.at(-1);
   assert.equal(request.headers.get('x-nordicsignal-internal-token'),'test-only-secret');
   for(const name of ['cookie','authorization','cf-access-jwt-assertion','cf-access-client-secret'])assert.equal(request.headers.get(name),null);
   assert.equal((await request.json()).endpoint,'https://push.example.test/device');
  }
  assert.equal(backend.length,3);assert.equal(keyCalls,1,'JWKS should be cached');
  const access=await worker.fetch(new Request(origin+'/api/push/access',{headers}),env);
  assert.deepEqual(await access.json(),{push_write_allowed:true});
  assert.equal(backend.length,3,'Read-only access check has no backend mutation');
  const denied=await worker.fetch(new Request(origin+'/api/push/access'),env);
  assert.equal(denied.status,403);assert.deepEqual(await denied.json(),{push_write_allowed:false});
  globalThis.fetch=async()=>{throw Error('unavailable with sensitive diagnostic')};
  const outageEnv={...env,NORDICSIGNAL_ACCESS_ISSUER:'https://outage.cloudflareaccess.com'};
  assert.equal((await send(undefined,{envOverride:outageEnv,headers:{...headers,'cf-access-jwt-assertion':await token({iss:outageEnv.NORDICSIGNAL_ACCESS_ISSUER})}})).status,403);
 } finally {globalThis.fetch=originalFetch;}
});

test('push activation stays hidden until authenticated capability is confirmed',async()=>{
 const fs=require('fs'),{JSDOM}=require('jsdom');
 for(const allowed of [true,false,'failure']){
  const dom=new JSDOM(fs.readFileSync('frontend/alerts.html','utf8'),{url:'https://app.example.test/alerts',runScripts:'outside-only'}),w=dom.window;
  const calls=[];w.matchMedia=()=>({matches:false});w.AbortSignal=AbortSignal;
  w.navigator.serviceWorker={register:async()=>({})};
  w.fetch=async path=>{calls.push(path);if(allowed==='failure')throw Error('offline');return {ok:allowed,json:async()=>({push_write_allowed:allowed})}};
  w.eval(fs.readFileSync('frontend/mobile_shell.js','utf8'));
  await new Promise(setImmediate);
  const button=w.document.getElementById('nsEnableAlerts');
  assert.equal(button.hidden,allowed!==true);assert.equal(button.disabled,allowed!==true);
  assert.deepEqual(calls,['/api/push/access']);
  assert.equal(w.document.getElementById('nsTestPush').hidden,true);
  assert.match(w.document.getElementById('alertStatus').textContent,allowed===true?/ikke bekreftet registrert/:/utilgjengelig/);
  w.close();
 }
});
