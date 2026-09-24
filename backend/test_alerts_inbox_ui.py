import json
import subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def test_inbox_uses_read_only_feed_and_canonical_stock_links():
    script=(ROOT/'frontend/alerts.js').read_text()
    program=r'''
const vm=require('node:vm'),assert=require('node:assert/strict');
const elements=new Map(['alertList','summary','refreshAlerts'].map(k=>[k,{innerHTML:'',textContent:'',disabled:false}]));let fail=false;const requests=[];
const ctx={AbortSignal,document:{getElementById:k=>elements.get(k)},fetch:async(url,options)=>{requests.push([url,options]);return {ok:!fail,status:503,json:async()=>({items:[{ticker:'AKSO',name:'<script>bad</script>',event:'Trend',updated_at:'2026-09-24T12:00:00Z',url:'javascript:bad'}]})}}};
vm.createContext(ctx);vm.runInContext(SCRIPT,ctx);
(async()=>{await new Promise(setImmediate);assert.equal(requests.length,1);assert.ok(requests[0][0].startsWith('/api/signal-events?'));const html=elements.get('alertList').innerHTML;assert.ok(html.includes('/stock?ticker=AKSO'));assert.ok(!html.includes('javascript:'));assert.ok(!html.includes('<script>'));fail=true;await elements.get('refreshAlerts').onclick();assert.ok(elements.get('alertList').innerHTML.includes('UTILGJENGELIG'));assert.equal(elements.get('refreshAlerts').disabled,false);assert.ok(requests.every(x=>!x[1].method||x[1].method==='GET'))})().catch(e=>{console.error(e);process.exit(1)});
'''.replace('SCRIPT',json.dumps(script))
    subprocess.run(['node','-e',program],check=True,capture_output=True,text=True)
