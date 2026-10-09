/**
 * drop-probe.js —— 探查 Netlify Drop 页面的上传控件结构（为自动部署做准备）
 *   node web/tests/drop-probe.js [cdpPort]
 */
var PORT = process.argv[2] || 9460;

function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

async function main() {
  var page = await (await fetch('http://127.0.0.1:' + PORT + '/json/new?' +
    encodeURIComponent('https://app.netlify.com/drop'), { method: 'PUT' })).json();
  var ws = new WebSocket(page.webSocketDebuggerUrl);
  var id = 0, pending = {};
  function send(m, p) {
    return new Promise(function (res) {
      var mid = ++id; pending[mid] = res;
      ws.send(JSON.stringify({ id: mid, method: m, params: p || {} }));
    });
  }
  ws.addEventListener('message', function (ev) {
    var m = JSON.parse(ev.data);
    if (m.id && pending[m.id]) { pending[m.id](m); delete pending[m.id]; }
  });
  await new Promise(function (r) { ws.addEventListener('open', r); });
  await send('Runtime.enable'); await send('Page.enable');
  await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });
  await send('Page.navigate', { url: 'https://app.netlify.com/drop' });
  await sleep(6000);

  async function ev(expr) {
    var r = await send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true });
    var inner = r && r.result ? r.result : {};
    if (inner.exceptionDetails) {
      var ed = inner.exceptionDetails;
      return 'ERR: ' + ((ed.exception && (ed.exception.description || ed.exception.value)) || ed.text);
    }
    return inner.result ? inner.result.value : undefined;
  }

  console.log('URL/标题：' + await ev('JSON.stringify({u:location.href,t:document.title})'));
  console.log('页面文本：' + await ev('(document.body?document.body.innerText:"").replace(/\\s+/g," ").slice(0,600)'));
  console.log('\n所有 input 元素：');
  console.log(await ev(`JSON.stringify(Array.from(document.querySelectorAll('input')).map(function(el,i){
    return {i:i, type:el.type, name:el.name, id:el.id, accept:el.accept, cls:(el.className||'').toString().slice(0,60), hidden:el.hidden, display:getComputedStyle(el).display};
  }), null, 1)`));
  console.log('\n疑似 dropzone / 上传相关元素：');
  console.log(await ev(`JSON.stringify(Array.from(document.querySelectorAll('[class*=drop],[data-testid*=drop],[class*=upload],[data-testid*=upload],label,form')).slice(0,20).map(function(el){
    return {tag:el.tagName, cls:(el.className||'').toString().slice(0,70), testid:el.getAttribute('data-testid'), html:(el.outerHTML||'').slice(0,120)};
  }), null, 1)`));

  ws.close();
  process.exit(0);
}

main().catch(function (e) { console.error('失败：' + e.message); process.exit(2); });
