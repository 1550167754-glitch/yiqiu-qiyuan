/**
 * cdpshot.js —— 用 CDP 打开网页版并截图 + 收集控制台错误（真实浏览器验证）
 *
 *   node web/tests/cdpshot.js [url] [outPng]
 *
 * 需要先用 --remote-debugging-port 启动 Edge/Chrome。
 * 这里只用 Node 内置能力（fetch + WebSocket），不装 puppeteer。
 */

var fs = require('fs');

var URL_TARGET = process.argv[2] || 'http://127.0.0.1:5178/';
var OUT = process.argv[3] || 'web/tests/shot.png';
var PORT = process.argv[4] || 9333;

function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

async function main() {
  // 找一个已打开的页签（或者新建）
  var list = await (await fetch('http://127.0.0.1:' + PORT + '/json/list')).json();
  var page = list.filter(function (t) { return t.type === 'page'; })[0];
  if (!page) {
    page = await (await fetch('http://127.0.0.1:' + PORT + '/json/new?' + encodeURIComponent(URL_TARGET),
      { method: 'PUT' })).json();
  }
  console.log('目标页签：' + page.id + '  ' + page.url);

  var ws = new WebSocket(page.webSocketDebuggerUrl);
  var id = 0;
  var pending = {};
  var consoleErrors = [];
  var pageErrors = [];

  function send(method, params) {
    return new Promise(function (resolve) {
      var mid = ++id;
      pending[mid] = resolve;
      ws.send(JSON.stringify({ id: mid, method: method, params: params || {} }));
    });
  }

  ws.addEventListener('message', function (ev) {
    var msg = JSON.parse(ev.data);
    if (msg.id && pending[msg.id]) { pending[msg.id](msg.result); delete pending[msg.id]; return; }
    if (msg.method === 'Runtime.consoleAPICalled' && msg.params.type === 'error') {
      consoleErrors.push((msg.params.args || []).map(function (a) {
        return a.value !== undefined ? a.value : (a.description || a.type);
      }).join(' '));
    }
    if (msg.method === 'Runtime.exceptionThrown') {
      var d = msg.params.exceptionDetails;
      pageErrors.push((d.exception && d.exception.description) || d.text);
    }
  });

  await new Promise(function (res) { ws.addEventListener('open', res); });
  await send('Runtime.enable');
  await send('Page.enable');
  // 用设备指标固定视口尺寸（否则 headless 默认窗口很小，截不到完整布局）
  await send('Emulation.setDeviceMetricsOverride', {
    width: parseInt(process.argv[5] || 1440, 10),
    height: parseInt(process.argv[6] || 900, 10),
    deviceScaleFactor: 1,
    mobile: process.argv[7] === 'mobile'
  });
  await send('Page.navigate', { url: URL_TARGET });
  await sleep(2500);

  // 读一下页面自检信息
  var evalRes = await send('Runtime.evaluate', {
    expression: [
      'JSON.stringify({',
      '  hasE: typeof E !== "undefined",',
      '  keys: (typeof E !== "undefined") ? Object.keys(E) : [],',
      '  canvasW: document.getElementById("board") ? document.getElementById("board").width : -1,',
      '  canvasCss: document.getElementById("board") ? document.getElementById("board").style.width : "",',
      '  turn: (document.getElementById("lblTurn")||{}).textContent || "",',
      '  step: (document.getElementById("lblStep")||{}).textContent || "",',
      '  confirmDisabled: document.getElementById("btnConfirm") ? document.getElementById("btnConfirm").disabled : null',
      '})'
    ].join('\n'),
    returnByValue: true
  });
  console.log('页面自检：' + (evalRes && evalRes.result ? evalRes.result.value : '(无返回)'));

  // 在棋盘上点一手，验证真实交互
  await send('Runtime.evaluate', {
    expression: [
      '(function(){',
      '  var c = document.getElementById("board");',
      '  if (!c) return "no canvas";',
      '  var r = c.getBoundingClientRect();',
      '  var ev = new MouseEvent("click", {clientX: r.left + r.width/2, clientY: r.top + r.height/2, bubbles: true});',
      '  c.dispatchEvent(ev);',
      '  return "clicked at " + Math.round(r.left + r.width/2) + "," + Math.round(r.top + r.height/2);',
      '})()'
    ].join('\n'),
    returnByValue: true
  }).then(function (r) {
    console.log('模拟点击：' + (r && r.result ? r.result.value : '?'));
  });

  await sleep(3000);   // 等 AI 应对
  var after = await send('Runtime.evaluate', {
    expression: 'JSON.stringify({moves: (document.getElementById("moves")||{}).textContent||"", step: (document.getElementById("lblStep")||{}).textContent||""})',
    returnByValue: true
  });
  console.log('落子后状态：' + (after && after.result ? after.result.value : '(无)'));

  var shot = await send('Page.captureScreenshot', { format: 'png' });
  if (shot && shot.data) {
    fs.writeFileSync(OUT, Buffer.from(shot.data, 'base64'));
    console.log('截图已保存：' + OUT + '（' + (fs.statSync(OUT).size / 1024).toFixed(1) + ' KB）');
  } else {
    console.log('截图失败');
  }

  console.log('控制台错误：' + (consoleErrors.length ? JSON.stringify(consoleErrors, null, 1) : '无'));
  console.log('未捕获异常：' + (pageErrors.length ? JSON.stringify(pageErrors, null, 1) : '无'));
  ws.close();
  process.exit(consoleErrors.length || pageErrors.length ? 1 : 0);
}

main().catch(function (e) {
  console.error('CDP 脚本失败：' + e.message);
  process.exit(2);
});
