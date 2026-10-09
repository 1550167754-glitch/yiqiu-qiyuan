/**
 * apptest.js —— 用假 DOM + 假 Canvas 真跑一遍网页版 app.js
 *
 *   node web/tests/apptest.js
 *
 * 为什么值得这么做：app.js 是浏览器代码，光"语法检查"抓不到运行期错误
 * （取不到元素、方法名写错、状态机死循环）。这里塞一个最小可用的假 DOM
 * 和假 2D 上下文，把 app.js 真跑起来，并模拟点击完成"落子 → AI 应对 → 悔棋"
 * 整条链路，从而在不开浏览器的情况下验证交互。
 *
 * 【踩过的坑·务必注意】
 * 1) 假元素的 textContent 与 innerHTML 必须共享同一份内容。真实 DOM 里两者是
 *    同一棵子树的两种视图，而 app 的 renderMoves 有时写 textContent、有时写
 *    innerHTML。早期版本让它们各存一个字段，测试读到的是上一次 innerHTML 写的
 *    旧内容，把好代码误判成了 bug。
 * 2) 等待动画/AI 绝不能用 while 死转：那会饿死 Node 的定时器队列，让
 *    setTimeout 回调永远不执行，同样会误判成"界面卡死"。
 */

var fs = require('fs');
var path = require('path');
var vm = require('vm');

var WEB = path.join(__dirname, '..');
var E = require(path.join(WEB, 'dist', 'engine.bundle.js'));

var passed = 0, failed = 0, fails = [];
function ok(name, cond, extra) {
  if (cond) { passed++; console.log('PASS ' + name + (extra ? '  ' + extra : '')); }
  else { failed++; fails.push(name); console.log('FAIL ' + name + (extra ? '  ' + extra : '')); }
}

// ------------------------------------------------------------------ 假 2D 上下文
function makeCtx() {
  var calls = { fill: 0, stroke: 0, text: 0, gradient: 0 };
  return {
    _calls: calls,
    fillStyle: '', strokeStyle: '', lineWidth: 1, globalAlpha: 1,
    font: '', textAlign: 'left',
    clearRect: function () {}, fillRect: function () {},
    beginPath: function () {}, closePath: function () {},
    moveTo: function () {}, lineTo: function () {},
    arc: function () {}, stroke: function () { calls.stroke++; },
    fill: function () { calls.fill++; },
    fillText: function () { calls.text++; },
    strokeRect: function () {},
    save: function () {}, restore: function () {},
    setTransform: function () {},
    createRadialGradient: function () {
      calls.gradient++;
      return { addColorStop: function () {} };
    }
  };
}

// ------------------------------------------------------------------ 假 DOM
function makeEl(id, tag) {
  var el = {
    id: id, tagName: tag || 'div',
    _content: '', value: '', disabled: false,
    style: {}, children: [], _handlers: {},
    clientWidth: 900, clientHeight: 900,
    parentElement: null,
    classList: {
      _set: {},
      add: function (c) { this._set[c] = true; },
      remove: function (c) { delete this._set[c]; },
      toggle: function (c, on) { if (on) this._set[c] = true; else delete this._set[c]; },
      contains: function (c) { return !!this._set[c]; }
    },
    // textContent 与 innerHTML 共享同一份内容（对齐真实 DOM 的语义）
    get textContent() { return this._content; },
    set textContent(v) { this._content = String(v); this.children = []; },
    get innerHTML() { return this._content; },
    set innerHTML(v) { this._content = String(v); if (v === '') this.children = []; },
    getContext: function () { return this._ctx || (this._ctx = makeCtx()); },
    // 真实 DOM 里 getBoundingClientRect 返回的是**渲染后的 CSS 尺寸**，
    // 必须跟着 app 设置的 style.width/height 走 —— 早期固定返回 600×600，
    // 结果 app 的"像素→棋盘格"换算全部偏掉，象棋那几步怎么也点不中。
    getBoundingClientRect: function () {
      var w = parseFloat(this.style.width) || 600;
      var h = parseFloat(this.style.height) || 600;
      return { left: 0, top: 0, width: w, height: h, right: w, bottom: h };
    },
    addEventListener: function (t, fn) { (this._handlers[t] = this._handlers[t] || []).push(fn); },
    removeEventListener: function () {},
    appendChild: function (c) { this.children.push(c); return c; },
    querySelector: function () { return makeEl('qs'); },
    setAttribute: function (k, v) { this[k] = v; },
    getAttribute: function (k) { return this[k]; },
    onclick: null, onchange: null,
    focus: function () {}, blur: function () {}
  };
  return el;
}

var elements = {};
function getEl(id) {
  if (!elements[id]) elements[id] = makeEl(id);
  return elements[id];
}
function contentOf(id) { return getEl(id).textContent; }

var selectDefaults = {
  variant: 'connect6', mode: 'human_ai', side: 'black',
  difficulty: 'medium', theme: '经典原木'
};
Object.keys(selectDefaults).forEach(function (id) {
  getEl(id).value = selectDefaults[id];
});

var boardWrap = makeEl('boardWrap');
boardWrap.clientWidth = 900;
getEl('board').parentElement = boardWrap;

var tabs = ['play', 'records', 'help'].map(function (p) {
  var t = makeEl('tab-' + p, 'button');
  t.setAttribute('data-page', p);
  return t;
});

var document = {
  readyState: 'complete',
  getElementById: getEl,
  createElement: function (tag) { return makeEl('', tag); },
  querySelector: function (sel) {
    if (sel === '#statTable tbody') return getEl('statTableBody');
    return makeEl('sel');
  },
  querySelectorAll: function (sel) {
    if (sel === '.tab') return tabs;
    return [];
  },
  addEventListener: function () {},
  body: makeEl('body')
};

var rafQueue = [];
var window = {
  innerWidth: 1200, innerHeight: 900,
  devicePixelRatio: 1,   // 测试里用 1，避免画布内部坐标与 CSS 坐标混淆
  addEventListener: function () {},
  removeEventListener: function () {},
  requestAnimationFrame: function (fn) { rafQueue.push(fn); return rafQueue.length; }
};

var memStore = {};
var sandbox = {
  E: E,
  document: document,
  window: window,
  console: console,
  performance: { now: function () { return Date.now(); } },
  requestAnimationFrame: window.requestAnimationFrame,
  cancelAnimationFrame: function () {},
  setTimeout: setTimeout,
  clearTimeout: clearTimeout,
  localStorage: {
    getItem: function (k) { return memStore[k] === undefined ? null : memStore[k]; },
    setItem: function (k, v) { memStore[k] = String(v); },
    removeItem: function (k) { delete memStore[k]; }
  },
  confirm: function () { return true; },
  alert: function () {}
};
sandbox.globalThis = sandbox;
sandbox.self = sandbox;

// ------------------------------------------------------------------ 执行 app.js
var src = fs.readFileSync(path.join(WEB, 'app.js'), 'utf8');
var bootError = null;
try {
  vm.createContext(sandbox);
  vm.runInContext(src, sandbox, { filename: 'app.js' });
} catch (e) {
  bootError = e;
}
ok('app.js 能在假 DOM 下启动', !bootError, bootError ? bootError.message : '');
if (bootError) {
  console.log(String(bootError.stack || '').split('\n').slice(0, 6).join('\n'));
  console.log('\n合计：' + passed + ' passed, ' + failed + ' failed');
  process.exit(1);
}

// ------------------------------------------------------------------ 时间推进
function flushRaf(limit) {
  var n = limit || 50;
  while (rafQueue.length && n-- > 0) {
    var fn = rafQueue.shift();
    try { fn(Date.now()); } catch (e) { console.log('rAF 回调异常: ' + e.message); }
  }
}
function asyncWait(ms) {
  return new Promise(function (res) { setTimeout(res, ms); });
}
/** 推进 ms 毫秒：每 10ms 让出一次事件循环并喂 rAF（绝不死转，否则饿死定时器）。 */
async function pump(ms) {
  var steps = Math.max(1, Math.ceil(ms / 10));
  for (var i = 0; i < steps; i++) {
    flushRaf(400);
    await asyncWait(10);
  }
  flushRaf(400);
}

// ------------------------------------------------------------------ 用例
(async function run() {
  await pump(120);

  ok('画布拿到了 2D 上下文', !!getEl('board')._ctx);
  ok('画布已按 DPR 放大', getEl('board').width > 0,
    'width=' + getEl('board').width + ' css=' + getEl('board').style.width);
  ok('状态栏显示轮到人类', /轮到你/.test(contentOf('lblTurn')), contentOf('lblTurn'));
  ok('确认按钮初始禁用（未选点）', getEl('btnConfirm').disabled === true);

  var canvas = getEl('board');
  var onClick = (canvas._handlers.click || [])[0];
  ok('画布绑定了点击事件', typeof onClick === 'function');

  // 几何：600×600 的画布，中心 (300,300) 对应天元 (9,9)
  var clickAt = function (px, py) {
    onClick({ clientX: px, clientY: py, preventDefault: function () {} });
  };
  clickAt(300, 300);
  ok('点中心可选中（确认按钮可用）', getEl('btnConfirm').disabled === false);
  ok('提示文案提示"选满自动落子/结束回合"',
    /选满自动落子|结束本回合/.test(contentOf('hint')), contentOf('hint'));

  clickAt(300, 300);
  ok('再点同一点取消选择', getEl('btnConfirm').disabled === true);

  // --- 下一子并等 AI 应对 ---
  clickAt(300, 300);
  await pump(150);             // "选满自动落子"的 setTimeout(90)
  await pump(2500);            // AI 搜索
  var movesAfterPlay = contentOf('moves');
  ok('棋谱里已出现落子记录', /1\./.test(movesAfterPlay),
    '棋谱=' + JSON.stringify(movesAfterPlay.slice(0, 50)));
  ok('棋谱包含 AI 的应对着', /2\./.test(movesAfterPlay),
    '棋谱=' + JSON.stringify(movesAfterPlay.slice(0, 60)));

  // --- 悔棋：倒退动画 + 状态一致性 ---
  var beforeUndo = contentOf('moves');
  var btnUndo = getEl('btnUndo');
  ok('悔棋按钮已启用', btnUndo.disabled === false);

  var undoErr = null;
  try { btnUndo.onclick(); } catch (e) { undoErr = e; }
  ok('悔棋不抛异常', !undoErr, undoErr ? undoErr.message : '');
  ok('悔棋后动画期间按钮禁用', btnUndo.disabled === true);
  ok('悔棋立即反映到棋谱面板（不残留已撤的手数）',
    contentOf('moves') !== beforeUndo,
    '悔棋前=' + JSON.stringify(beforeUndo.slice(0, 40)) +
    ' 悔棋后=' + JSON.stringify(contentOf('moves').slice(0, 40)));

  await pump(900);             // 动画（每枚约 190ms）
  await pump(2500);            // 动画后 AI 的应对

  ok('动画结束后界面不停留在"AI 思考中"',
    /点击棋盘选点|本局已结束/.test(contentOf('hint')), contentOf('hint'));
  ok('动画结束后不遗留遮罩层',
    getEl('overlay').classList.contains('is-hidden') === true);

  // --- 切换页面 ---
  var recErr = null;
  try { tabs[1].onclick(); } catch (e) { recErr = e; }
  ok('切换到战绩页不报错', !recErr, recErr ? recErr.message : '');
  var helpErr = null;
  try { tabs[2].onclick(); } catch (e) { helpErr = e; }
  ok('切换到规则页不报错', !helpErr, helpErr ? helpErr.message : '');

  // --- 换棋种开新局（验证几何重算与状态复位） ---
  var newErr = null;
  try {
    getEl('variant').value = 'gomoku';
    getEl('btnNew').onclick();
  } catch (e) { newErr = e; }
  ok('切换五子棋并开新局不报错', !newErr, newErr ? newErr.message : '');
  await pump(300);
  ok('新局棋谱已清空', contentOf('moves') === '（暂无）' || contentOf('moves') === '',
    JSON.stringify(contentOf('moves')));
  ok('新局重新轮到人类', /轮到你/.test(contentOf('lblTurn')), contentOf('lblTurn'));

  // --- 中国象棋：选子 → 走子 → AI 应对 ---
  var xqErr = null;
  try {
    getEl('variant').value = 'xiangqi';
    getEl('variant').onchange();          // 会重设"我执"文案并开新局
  } catch (e) { xqErr = e; }
  ok('切到中国象棋不报错', !xqErr, xqErr ? xqErr.message : '');
  await pump(200);
  ok('象棋局面提示正确',
    /点自己的棋子选中/.test(contentOf('hint')) || /AI 正在思考/.test(contentOf('hint')),
    contentOf('hint'));
  // 象棋棋盘是 9 列 × 10 行，比宽高（竖长），与连珠类的正方棋盘不同
  ok('象棋画布按 9×10 竖长比例布局',
    parseFloat(getEl('board').style.height) > parseFloat(getEl('board').style.width),
    'w=' + getEl('board').style.width + ' h=' + getEl('board').style.height);

  // 用 bundle 里的真实常量精确复算格心（不要用估算值，估错就会点到别的格子）
  var cw = parseFloat(getEl('board').style.width);
  var chh = parseFloat(getEl('board').style.height);
  var MG = E.xqview.MARGIN;
  var estCell = Math.min((cw - MG * 2) / (9 - 1 + 0.9), (chh - MG * 2) / (10 - 1 + 0.9));
  var x0Est = (cw - estCell * 8) / 2;
  var y0Est = (chh - estCell * 9) / 2;
  function clickCell(cx, cy) {
    clickAt(x0Est + cx * estCell, y0Est + cy * estCell);
  }
  clickCell(7, 7);                       // 选红炮（第 7 列、第 7 行）
  ok('选中红炮后按钮与提示同步', /点自己的棋子/.test(contentOf('hint')),
    contentOf('hint'));
  clickCell(4, 7);                       // 炮二平五
  await pump(200);
  ok('走子后棋谱出现象棋记录', /→/.test(contentOf('moves')),
    JSON.stringify(contentOf('moves').slice(0, 60)));

  await pump(3500);                      // 等象棋 AI 应对（medium 约 1.4s）
  ok('象棋 AI 已应对（棋谱步数 >= 2）',
    (contentOf('moves').match(/→/g) || []).length >= 2,
    JSON.stringify(contentOf('moves').slice(0, 80)));
  ok('象棋 AI 走完后又轮到我方',
    /轮到你/.test(contentOf('lblTurn')), contentOf('lblTurn'));

  // --- 象棋悔棋 ---
  var xqUndo = getEl('btnUndo');
  ok('象棋悔棋按钮可用', xqUndo.disabled === false);
  var xqUndoErr = null;
  try { xqUndo.onclick(); } catch (e) { xqUndoErr = e; }
  ok('象棋悔棋不抛异常', !xqUndoErr, xqUndoErr ? xqUndoErr.message : '');
  await pump(1200);
  await pump(3000);                      // 动画 + 之后 AI 的应对
  ok('象棋悔棋后界面恢复正常（不停留在 AI 思考中）',
    /点自己的棋子|本局已结束/.test(contentOf('hint')), contentOf('hint'));

  console.log('\n合计：' + passed + ' passed, ' + failed + ' failed');
  if (failed) { console.log('失败项：' + fails.join('、')); process.exit(1); }
  process.exit(0);
})();
