var PORT=9460;
(async function(){
  var list = await (await fetch('http://127.0.0.1:'+PORT+'/json/list')).json();
  var pages = list.filter(t=>t.type==='page' && (t.url||'').indexOf('netlify')>=0);
  console.log('找到 '+pages.length+' 个 netlify 页签');
  for (var p of pages){
    console.log('\n=== ' + p.url + ' ===');
    var ws = new WebSocket(p.webSocketDebuggerUrl);
    var id=0, pending={};
    function send(m,pa){ return new Promise(r=>{ var mid=++id; pending[mid]=r; ws.send(JSON.stringify({id:mid,method:m,params:pa||{}})); }); }
    ws.addEventListener('message', ev=>{ var m=JSON.parse(ev.data); if(m.id&&pending[m.id]){pending[m.id](m); delete pending[m.id];} });
    await new Promise(r=>ws.addEventListener('open',r));
    await send('Runtime.enable');
    var r = await send('Runtime.evaluate', {expression:'(document.body?document.body.innerText:"").replace(/\\s+/g," ").slice(0,700)', returnByValue:true});
    console.log((r.result && r.result.result && r.result.result.value) || '(空)');
    var r2 = await send('Runtime.evaluate', {expression:'JSON.stringify(Array.from(document.querySelectorAll("a[href*=netlify], input[type=password], button")).slice(0,25).map(function(e){return {tag:e.tagName, href:e.getAttribute&&e.getAttribute("href"), txt:(e.innerText||"").slice(0,40)}}))', returnByValue:true});
    console.log('控件: ' + ((r2.result && r2.result.result && r2.result.result.value) || ''));
    ws.close();
  }
  process.exit(0);
})().catch(e=>{console.error('ERR',e.message);process.exit(2);});