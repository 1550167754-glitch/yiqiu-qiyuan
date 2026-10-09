/**
 * xqshot.js —— 在真实浏览器里切到中国象棋、走两步、截图验证
 *
 *   node web/tests/xqshot.js [url] [outPng] [cdpPort]
 */

var fs = require('fs');

var URL_TARGET = process.argv[2] || 'http://127.0.0.1:5178/';
var OUT = process.argv[3] || 'web/tests/shot-xiangqi.png';
var PORT = process.argv[4] || 9445;

function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

async function main() {
  // 直接用 /json/new 开一个我们自己的页签。
  // 不能图省事复用"第一个页签"：headless Edge 常带一个 edge:// 内部页签，
  // 或者连到 about:blank，于是脚本对着空页面求值，什么都拿不到。
  var page = await (await fetch('http://127.0.0.1:' + PORT + '/json/new?' +
    encodeURIComponent(URL_TARGET), { method: 'PUT' })).json();
  console.log('目标页签：' + page.url);
  await sleep(600);

  var ws = new WebSocket(page.webSocketDebuggerUrl);
  var id = 0, pending = {}, errors = [], exceptions = [];
  function send(m, p) {
    return new Promise(function (res) {
      var mid = ++id; pending[mid] = res;
      ws.send(JSON.stringify({ id: mid, method: m, params: p || {} }));
    });
  }
  ws.addEventListener('message', function (ev) {
    var m = JSON.parse(ev.data);
    if (m.id && pending[m.id]) { pending[m.id](m.result); delete pending[m.id]; return; }
    if (m.method === 'Runtime.consoleAPICalled' && m.params.type === 'error') {
      errors.push((m.params.args || []).map(function (a) {
        return a.value !== undefined ? a.value : (a.description || a.type);
      }).join(' '));
    }
    if (m.method === 'Runtime.exceptionThrown') {
      var d = m.params.exceptionDetails;
      exceptions.push((d.exception && d.exception.description) || d.text);
    }
  });
  await new Promise(function (r) { ws.addEventListener('open', r); });
  await send('Runtime.enable');
  await send('Page.enable');
  await send('Emulation.setDeviceMetricsOverride', {
    width: 1440, height: 900, deviceScaleFactor: 1, mobile: false
  });
  await send('Page.navigate', { url: URL_TARGET });

  // 等页面真正就绪：光 sleep 不可靠，这里轮询 document.readyState 与资源是否到位
  var ready = false;
  for (var i = 0; i < 40; i++) {
    await sleep(250);
    var chk = await send('Runtime.evaluate', {
      expression: 'JSON.stringify({rs: document.readyState, hasSel: !!document.getElementById("variant"), hasE: typeof window.E})',
      returnByValue: true
    });
    var v = chk && chk.result ? chk.result.value : '';
    if (v.indexOf('"rs":"complete"') >= 0 && v.indexOf('"hasSel":true') >= 0 &&
        v.indexOf('"hasE":"object"') >= 0) { ready = true; break; }
  }
  console.log('页面就绪：' + ready);
  if (!ready) { console.log('页面未就绪，放弃'); ws.close(); process.exit(3); }

  // 切到象棋
  // 【坑】表达式里必须写 window.E 而不是 E：DevTools/CDP 的求值环境里
  // `E` 会被它自己的全局（一个 Symbol）遮蔽，`typeof E` 返回 "symbol"，
  // 于是脚本报错、返回 undefined，看上去像"应用没加载"。
  var r1 = await send('Runtime.evaluate', {
    expression: [
      '(function(){',
      '  var v = document.getElementById("variant");',
      '  if (!v) return "no-select";',
      '  v.value = "xiangqi";',
      '  if (v.onchange) v.onchange(); else v.dispatchEvent(new Event("change"));',
      '  return "ok:" + v.value;',
      '})()'
    ].join('\n'), returnByValue: true
  });
  console.log('切换象棋：' + (r1 && r1.result ? r1.result.value : JSON.stringify(r1)));
  await sleep(1200);

  // 用真实几何点两下：选红炮 (7,7)，再平中炮 (4,7)
  var r2 = await send('Runtime.evaluate', {
    expression: [
      '(function(){',
      '  var c = document.getElementById("board");',
      '  var rect = c.getBoundingClientRect();',
      '  var MG = window.E.xqview.MARGIN;',
      '  var cw = rect.width, ch = rect.height;',
      '  var cell = Math.min((cw - MG*2)/(9-1+0.9), (ch - MG*2)/(10-1+0.9));',
      '  var x0 = (cw - cell*8)/2, y0 = (ch - cell*9)/2;',
      '  function clickCell(cx, cy){',
      '    c.dispatchEvent(new MouseEvent("click", {',
      '      clientX: rect.left + x0 + cx*cell,',
      '      clientY: rect.top + y0 + cy*cell, bubbles: true}));',
      '  }',
      '  clickCell(7,7);',
      '  clickCell(4,7);',
      '  return JSON.stringify({',
      '    moves: document.getElementById("moves").textContent.slice(0,60),',
      '    step: document.getElementById("lblStep").textContent});',
      '})()'
    ].join('\n'), returnByValue: true
  });
  console.log('走子结果：' + (r2 && r2.result ? r2.result.value : JSON.stringify(r2)));

  await sleep(3500);   // 等象棋 AI 应对

  var r3 = await send('Runtime.evaluate', {
    expression: 'JSON.stringify({moves:(document.getElementById("moves")||{}).textContent||"", turn:(document.getElementById("lblTurn")||{}).textContent||"", step:(document.getElementById("lblStep")||{}).textContent||""})',
    returnByValue: true
  });
  console.log('AI 应对后：' + (r3 && r3.result ? r3.result.value : '?'));

  var shot = await send('Page.captureScreenshot', { format: 'png' });
  if (shot && shot.data) {
    fs.writeFileSync(OUT, Buffer.from(shot.data, 'base64'));
    console.log('截图已保存：' + OUT + '（' + (fs.statSync(OUT).size / 1024).toFixed(1) + ' KB）');
  }
  console.log('控制台错误：' + (errors.length ? JSON.stringify(errors) : '无'));
  console.log('未捕获异常：' + (exceptions.length ? JSON.stringify(exceptions) : '无'));
  ws.close();
  process.exit((errors.length || exceptions.length) ? 1 : 0);
}

main().catch(function (e) { console.error('失败：' + e.message); process.exit(2); });
