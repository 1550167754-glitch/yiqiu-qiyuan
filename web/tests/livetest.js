/**
 * livetest.js —— 在**公网地址**上验三种棋都能真正开局、AI 都会应手
 *
 *   node web/tests/livetest.js [url] [cdpPort]
 *
 * 只验一件事：页面不是白屏、三种棋的"落子 → AI 应对"链路都通。
 * 几何按各棋种的真实参数复算（连珠类用 boardview.GEOM_MARGIN，象棋用 xqview.MARGIN），
 * 否则会点到别的格子，把好代码误判成坏的。
 */

var URL_TARGET = process.argv[2] || 'https://1550167754-glitch.github.io/yiqiu-qiyuan/';
var PORT = process.argv[3] || 9470;

var passed = 0, failed = 0, fails = [];
function ok(name, cond, extra) {
  if (cond) { passed++; console.log('PASS ' + name + (extra ? '  ' + extra : '')); }
  else { failed++; fails.push(name); console.log('FAIL ' + name + (extra ? '  ' + extra : '')); }
}
function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

async function main() {
  var page = await (await fetch('http://127.0.0.1:' + PORT + '/json/new?' +
    encodeURIComponent(URL_TARGET), { method: 'PUT' })).json();
  var ws = new WebSocket(page.webSocketDebuggerUrl);
  var id = 0, pending = {}, errors = [];
  function send(m, p) {
    return new Promise(function (res) {
      var mid = ++id; pending[mid] = res;
      ws.send(JSON.stringify({ id: mid, method: m, params: p || {} }));
    });
  }
  ws.addEventListener('message', function (ev) {
    var m = JSON.parse(ev.data);
    if (m.id && pending[m.id]) { pending[m.id](m); delete pending[m.id]; return; }
    if (m.method === 'Runtime.consoleAPICalled' && m.params.type === 'error') {
      errors.push((m.params.args || []).map(function (a) {
        return a.value !== undefined ? a.value : (a.description || '');
      }).join(' '));
    }
  });
  await new Promise(function (r) { ws.addEventListener('open', r); });
  await send('Runtime.enable'); await send('Page.enable');
  await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });
  await send('Page.navigate', { url: URL_TARGET });
  await sleep(4000);

  async function ev(expr) {
    var r = await send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true });
    var inner = r && r.result ? r.result : {};
    if (inner.exceptionDetails) {
      var ed = inner.exceptionDetails;
      return 'ERR: ' + ((ed.exception && (ed.exception.description || ed.exception.value)) || ed.text);
    }
    return inner.result ? inner.result.value : undefined;
  }

  // 页面是否真的加载了引擎
  var boot = await ev('JSON.stringify({rs:document.readyState, E:typeof window.E, keys:(typeof window.E!=="undefined")?Object.keys(window.E):[]})');
  ok('页面加载了引擎（window.E 就绪）', String(boot).indexOf('"E":"object"') >= 0, String(boot));

  // 通用：设置棋种 → 点两下 → 看棋谱有没有两步
  async function playVariant(variant, clicks, label) {
    await ev('(function(){var v=document.getElementById("variant");v.value="' + variant +
      '";v.onchange();return v.value;})()');
    await sleep(1200);
    var res = await ev('(function(){' +
      'var c=document.getElementById("board");var rect=c.getBoundingClientRect();' +
      'var isXQ=' + (variant === 'xiangqi') + ';' +
      'var MG=isXQ?window.E.xqview.MARGIN:window.E.boardview.GEOM_MARGIN;' +
      'var cols=isXQ?9:(' + (variant === 'gomoku' ? 15 : 19) + ');' +
      'var rows=isXQ?10:cols;' +
      'var cw=rect.width,ch=rect.height;' +
      'var cell=isXQ?Math.min((cw-MG*2)/(cols-1+0.9),(ch-MG*2)/(rows-1+0.9))' +
      '          :Math.min(cw-MG*2,ch-MG*2)/(cols-1+0.9);' +
      'var x0=isXQ?(cw-cell*(cols-1))/2:(cw-cell*(cols-1))/2;' +
      'var y0=isXQ?(ch-cell*(rows-1))/2:(ch-cell*(rows-1))/2;' +
      'function click(cx,cy){c.dispatchEvent(new MouseEvent("click",{clientX:rect.left+x0+cx*cell,clientY:rect.top+y0+cy*cell,bubbles:true}));}' +
      'var list=' + JSON.stringify(clicks) + ';' +
      'for(var i=0;i<list.length;i++){click(list[i][0],list[i][1]);}' +
      'return JSON.stringify({moves:document.getElementById("moves").textContent.slice(0,50),hint:document.getElementById("hint").textContent.slice(0,30)});' +
      '})()');
    await sleep(4000);   // 等 AI
    var after = await ev('JSON.stringify({moves:document.getElementById("moves").textContent.slice(0,60),turn:document.getElementById("lblTurn").textContent.slice(0,20)})');
    var mv = String(after).match(/(\d+\.)/g);
    ok(label + '：落子后 AI 有应对（棋谱出现 2 步以上）',
      (mv ? mv.length : 0) >= 2, String(after));
  }

  // 各棋种的点击序列（必须符合规则，否则会"点两下=取消选择"这种自坑）：
  //   六子棋首轮只能下 1 子 → 只点一下（点两下同一点 = 取消选择）
  //   五子棋每轮 1 子 → 只点一下
  //   象棋是"点子 → 点目标"
  await playVariant('connect6', [[9, 9]], '六子棋');
  await playVariant('gomoku', [[7, 7]], '五子棋');
  await playVariant('xiangqi', [[7, 7], [4, 7]], '中国象棋');

  ok('全程无控制台报错', errors.length === 0, errors.length ? JSON.stringify(errors).slice(0, 200) : '');

  console.log('\n合计：' + passed + ' passed, ' + failed + ' failed');
  ws.close();
  process.exit(failed ? 1 : 0);
}

main().catch(function (e) { console.error('失败：' + e.message); process.exit(2); });
