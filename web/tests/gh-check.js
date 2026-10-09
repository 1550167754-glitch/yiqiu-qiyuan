/**
 * gh-check.js —— 通过 CDP 检查浏览器里的 github.com 登录态
 *   node web/tests/gh-check.js [port]
 * 只读检查，不做任何修改操作。
 */
var PORT = process.argv[2] || 9444;

function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

async function main() {
  var list = await (await fetch('http://127.0.0.1:' + PORT + '/json/list')).json();
  var page = list.filter(function (t) {
    return t.type === 'page' && /github\.com/.test(t.url || '');
  })[0];
  if (!page) { console.log('没有 github.com 页签'); process.exit(2); }

  var ws = new WebSocket(page.webSocketDebuggerUrl);
  var id = 0, pending = {};
  function send(method, params) {
    return new Promise(function (res) {
      var mid = ++id; pending[mid] = res;
      ws.send(JSON.stringify({ id: mid, method: method, params: params || {} }));
    });
  }
  ws.addEventListener('message', function (ev) {
    var m = JSON.parse(ev.data);
    if (m.id && pending[m.id]) { pending[m.id](m.result); delete pending[m.id]; }
  });
  await new Promise(function (r) { ws.addEventListener('open', r); });
  await send('Runtime.enable');
  await send('Page.enable');
  await send('Page.navigate', { url: 'https://github.com/' });
  await sleep(4000);

  var r = await send('Runtime.evaluate', {
    expression: [
      '(function(){',
      '  var out = {};',
      '  out.url = location.href;',
      '  out.title = document.title;',
      // 登录后右上角会有一个用户菜单按钮，含用户名；未登录是 Sign in / Sign up
      '  var meta = document.querySelector(\'meta[name="user-login"]\');',
      '  out.userLogin = meta ? meta.getAttribute("content") : null;',
      '  var body = document.body ? document.body.innerText.slice(0, 400) : "";',
      '  out.signInVisible = /Sign in|Sign up/i.test(body);',
      '  out.snippet = body.replace(/\\s+/g, " ").slice(0, 220);',
      '  return JSON.stringify(out);',
      '})()'
    ].join('\n'),
    returnByValue: true
  });
  console.log(r && r.result ? r.result.value : '(无返回)');
  ws.close();
  process.exit(0);
}

main().catch(function (e) { console.error('失败：' + e.message); process.exit(2); });
