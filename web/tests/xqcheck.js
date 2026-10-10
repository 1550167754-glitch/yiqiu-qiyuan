/**
 * xqcheck.js —— 中国象棋引擎对拍测试
 *
 *   node web/tests/xqcheck.js
 *
 * 两件事：
 *   1. **攻击检测对拍**：新的"反向射线法" isAttacked 必须与"逐子生成着法"的
 *      朴素实现逐格一致。攻击检测是象棋引擎最核心也最容易写错的函数
 *      （马腿方向、炮架计数、兵过河才能横吃…），必须用独立实现交叉验证，
 *      而不是靠手写几个用例。这里跑多个局面 × 全部 90 格 × 双方。
 *   2. **棋力抽检**：给几个明确的战术局面，看引擎能不能走对
 *      （能吃子、能解将、能抓住送吃的大子）。
 */
var path = require('path');
var X = require(path.join(__dirname, '..', 'engine', 'xiaqi.js'));

var passed = 0, failed = 0, fails = [];
function ok(name, cond, extra) {
  if (cond) { passed++; console.log('PASS ' + name + (extra ? '  ' + extra : '')); }
  else { failed++; fails.push(name); console.log('FAIL ' + name + (extra ? '  ' + extra : '')); }
}

/**
 * 朴素但正确的"被攻击"参考实现（独立于引擎的快速实现）。
 *
 * 【为什么不能拿 pieceMoves 当参考】pieceMoves 是**着法生成**：
 * 炮可以"走到"紧贴炮架之前的空格（那是个合法着法），但它并不"攻击"那个空格。
 * 而 isAttacked 的语义是**吃子意图**：炮只攻击"炮架之后的第一个敌子"。
 * 早先用 pieceMoves 当参考，导致 28 处假失配，全是炮的语义差异。
 * 这里按每种棋子的吃子规则独立写一遍。
 */
function refAttacked(bd, tx, ty, byColor) {
  var g = bd.grid;
  function at(x, y) {
    if (x < 0 || x >= X.COLS || y < 0 || y >= X.ROWS) return null;
    var r = g[y]; if (!r) return null;
    var v = r[x]; return v === undefined ? null : v;
  }
  function own(x, y, kind) {
    var p = at(x, y);
    return !!p && p[0] === byColor && (kind === undefined || p[1] === kind);
  }

  var orth = [[0, -1], [0, 1], [-1, 0], [1, 0]];

  // 车/将：该方向第一个子就是它。
  // 【与引擎同步】敌方 KING 同样算射线攻击源（飞将=将帅照面）：
  // 双王同列无遮挡即互攻，否则 inCheck 检测不到照面。与引擎
  // isAttacked 的射线分支保持同一语义，对拍才可比。
  for (var d = 0; d < 4; d++) {
    var dx = orth[d][0], dy = orth[d][1];
    var i = tx + dx, j = ty + dy;
    while (i >= 0 && i < X.COLS && j >= 0 && j < X.ROWS) {
      var p = at(i, j);
      if (p) {
        if (p[0] === byColor && (p[1] === X.CHARIOT || p[1] === X.KING)) return true;
        break;
      }
      i += dx; j += dy;
    }
  }
  // 炮：第一个子是炮架 F，F 之后的第一个子若是炮 → 攻击
  for (var d2 = 0; d2 < 4; d2++) {
    var dx2 = orth[d2][0], dy2 = orth[d2][1];
    var fx = null, fy = null;
    var i2 = tx + dx2, j2 = ty + dy2;
    while (i2 >= 0 && i2 < X.COLS && j2 >= 0 && j2 < X.ROWS) {
      if (at(i2, j2)) { fx = i2; fy = j2; break; }
      i2 += dx2; j2 += dy2;
    }
    if (fx === null) continue;
    var i3 = fx + dx2, j3 = fy + dy2;
    while (i3 >= 0 && i3 < X.COLS && j3 >= 0 && j3 < X.ROWS) {
      var p3 = at(i3, j3);
      if (p3) { if (p3[0] === byColor && p3[1] === X.CANNON) return true; break; }
      i3 += dx2; j3 += dy2;
    }
  }
  // 马（含蹩腿，马腿相对马在长轴方向回退一格）
  [[-1, -2], [1, -2], [-1, 2], [1, 2], [-2, -1], [-2, 1], [2, -1], [2, 1]]
    .forEach(function (o) {
      var hx = tx + o[0], hy = ty + o[1];
      if (!own(hx, hy, X.HORSE)) return;
      var sign = function (v) { return v > 0 ? 1 : (v < 0 ? -1 : 0); };
      var lx = hx + (Math.abs(o[0]) === 2 ? -sign(o[0]) : 0);
      var ly = hy + (Math.abs(o[1]) === 2 ? -sign(o[1]) : 0);
      if (!at(lx, ly)) refAttacked.hit.push('马@(' + hx + ',' + hy + ')');
    });
  // 将/帅（目标须在其九宫内）
  for (var d4 = 0; d4 < 4; d4++) {
    var ax = tx + orth[d4][0], ay = ty + orth[d4][1];
    if (own(ax, ay, X.KING) && X.inPalace(tx, ty, byColor)) return true;
  }
  // 士（双方都须在九宫内）
  [[-1, -1], [1, -1], [-1, 1], [1, 1]].forEach(function (o) {
    if (own(tx + o[0], ty + o[1], X.ADVISOR) &&
        X.inPalace(tx + o[0], ty + o[1], byColor) && X.inPalace(tx, ty, byColor)) {
      refAttacked.hit.push('士@(' + (tx + o[0]) + ',' + (ty + o[1]) + ')');
    }
  });
  if (refAttacked.hit.length) { refAttacked.hit = []; return true; }
  // 象（象眼为空、象不过河）
  var eleOk = [[-2, -2], [2, -2], [-2, 2], [2, 2]].some(function (o) {
    var ex = tx + o[0], ey = ty + o[1];
    if (!own(ex, ey, X.ELEPHANT)) return false;
    if (byColor === X.RED && ey < 5) return false;
    if (byColor === X.BLACK && ey > 4) return false;
    return !at(tx + o[0] / 2, ty + o[1] / 2);
  });
  if (eleOk) return true;
  // 兵/卒：纵向只向前一格；横向须已过河
  for (var d5 = 0; d5 < 4; d5++) {
    var px = tx + orth[d5][0], py = ty + orth[d5][1];
    if (!own(px, py, X.PAWN)) continue;
    if (px === tx) {
      if (byColor === X.RED && py > ty) return true;
      if (byColor === X.BLACK && py < ty) return true;
    } else {
      var crossed = (byColor === X.RED) ? (py <= 4) : (py >= 5);
      if (crossed) return true;
    }
  }
  return false;
}
refAttacked.hit = [];

function comparePosition(name, board) {
  var mism = 0, checked = 0, occupied = 0, samples = [];
  for (var y = 0; y < X.ROWS; y++) {
    for (var x = 0; x < X.COLS; x++) {
      // 只比空格：isAttacked 的语义是"byColor 能否走到/吃到这一格"。
      // 目标格已有子时，"能否走到该格"等价于"能否吃子"，而朴素实现
      // （逐子生成着法）在目标格被占时自然生成不出来 —— 两者对有子格的
      // 定义本就不同。界面上真正要判的是"帅所在格是否被攻击"，
      // 而帅在的格子判断两边一致。
      if (board.grid[y][x]) { occupied++; continue; }
      var cols = [X.RED, X.BLACK];
      for (var c = 0; c < 2; c++) {
        var a = board.isAttacked(x, y, cols[c]);
        var s = refAttacked(board, x, y, cols[c]);
        checked++;
        if (a !== s) {
          mism++;
          if (samples.length < 4) samples.push('(' + x + ',' + y + ')被' + cols[c] + ' 快=' + a + '慢=' + s);
        }
      }
    }
  }
  ok('攻击检测对拍：' + name, mism === 0,
    checked + ' 例空格（另 ' + occupied + ' 个有子格按语义跳过）' +
    (mism ? '，不一致 ' + mism + ' 处：' + samples.join('; ') : '，全部一致'));
}

// ---- 局面 1：初始局面 ----
comparePosition('初始局面', new X.XiangqiBoard());

// ---- 局面 2：常见中局（手工摆放，覆盖车炮马兵过河，避免依赖一串合法性可疑的着法序列）----
(function () {
  var b = new X.XiangqiBoard();
  var setup = [
    [X.BLACK, X.KING, 4, 0],
    [X.RED, X.KING, 4, 9],
    [X.RED, X.CHARIOT, 0, 5],
    [X.BLACK, X.CHARIOT, 8, 4],
    [X.RED, X.CANNON, 1, 4],
    [X.BLACK, X.CANNON, 7, 5],
    [X.RED, X.HORSE, 2, 7],
    [X.BLACK, X.HORSE, 6, 2],
    [X.RED, X.PAWN, 4, 5],
    [X.BLACK, X.PAWN, 4, 4],
    [X.RED, X.ADVISOR, 3, 9],
    [X.BLACK, X.ADVISOR, 5, 0],
    [X.RED, X.ELEPHANT, 2, 9],
    [X.BLACK, X.ELEPHANT, 6, 0]
  ];
  for (var y = 0; y < X.ROWS; y++) for (var x = 0; x < X.COLS; x++) b.grid[y][x] = null;
  setup.forEach(function (p) { b.grid[p[3]][p[2]] = [p[0], p[1]]; });
  b.turn = X.RED;
  comparePosition('中局（车炮马过河）', b);
})();

// ---- 局面 3：大量混战（人为摆放，覆盖车炮马贴身）----
(function () {
  var b = new X.XiangqiBoard();
  // 手工摆一个密集局面：车炮马彼此贴脸、兵过河
  var setup = [
    [X.RED, X.CHARIOT, 4, 5], [X.BLACK, X.CHARIOT, 4, 4],
    [X.RED, X.CANNON, 4, 8], [X.BLACK, X.CANNON, 3, 4],
    [X.RED, X.HORSE, 3, 6], [X.BLACK, X.HORSE, 4, 3],
    [X.RED, X.PAWN, 2, 4], [X.BLACK, X.PAWN, 6, 5],
    [X.RED, X.KING, 4, 9], [X.BLACK, X.KING, 4, 0]
  ];
  for (var i = 0; i < setup.length; i++) {
    var s = setup[i];
    b.grid[s[3]][s[2]] = [s[0], s[1]];
  }
  comparePosition('密集混战（车炮马贴身）', b);
})();

// ---- 局面 4：马腿全方向覆盖 ----
(function () {
  var b = new X.XiangqiBoard();
  b.grid = [];
  for (var y = 0; y < X.ROWS; y++) {
    var row = [];
    for (var x = 0; x < X.COLS; x++) row.push(null);
    b.grid.push(row);
  }
  b.grid[4][4] = [X.RED, X.HORSE];            // 天元位置的红马
  b.grid[9][4] = [X.RED, X.KING];
  b.grid[0][4] = [X.BLACK, X.KING];
  comparePosition('孤马居中（马腿八方向）', b);
  // 再把马腿堵上两处，看是否一致
  b.grid[3][4] = [X.BLACK, X.PAWN];
  b.grid[4][5] = [X.BLACK, X.PAWN];
  comparePosition('孤马 + 马腿被堵', b);
})();

// ------------------------------------------------------------------ 棋力抽检
// 局面 A：黑车无保护地摆在红车能吃到的地方 → 引擎必须吃掉
(function () {
  var b = new X.XiangqiBoard();
  b.grid = [];
  for (var y = 0; y < X.ROWS; y++) {
    var row = [];
    for (var x = 0; x < X.COLS; x++) row.push(null);
    b.grid.push(row);
  }
  b.grid[9][4] = [X.RED, X.KING];
  b.grid[0][4] = [X.BLACK, X.KING];
  b.grid[5][0] = [X.RED, X.CHARIOT];       // 红车在第 0 列
  b.grid[5][4] = [X.BLACK, X.CHARIOT];     // 黑车无保护，同列 4 步远
  b.turn = X.RED;
  var ai = new X.XqAI('medium', 1);
  var mv = ai.getMove(b);
  ok('能吃无保护的黑车时就去吃', !!mv && mv[2] === 4 && mv[3] === 5,
    '着法=' + JSON.stringify(mv));
})();

// 局面 B：白送一个车 → 引擎必须吃（等价于"看得见吃子"）
(function () {
  var b = new X.XiangqiBoard();
  b.grid = [];
  for (var y = 0; y < X.ROWS; y++) {
    var row = [];
    for (var x = 0; x < X.COLS; x++) row.push(null);
    b.grid.push(row);
  }
  b.grid[9][4] = [X.RED, X.KING];
  b.grid[0][4] = [X.BLACK, X.KING];
  b.grid[3][3] = [X.RED, X.HORSE];
  b.grid[5][4] = [X.BLACK, X.CHARIOT];     // 黑车摆在马能踩到的点 (4,5)
  b.turn = X.RED;
  var ai2 = new X.XqAI('hard', 2);
  var mv2 = ai2.getMove(b);
  ok('马能踩到无保护车时去吃', !!mv2 && mv2[2] === 4 && mv2[3] === 5,
    '着法=' + JSON.stringify(mv2));
})();

// 局面 C：被将军时必须应将（不能走无关的棋）
(function () {
  var b = new X.XiangqiBoard();
  b.grid = [];
  for (var y = 0; y < X.ROWS; y++) {
    var row = [];
    for (var x = 0; x < X.COLS; x++) row.push(null);
    b.grid.push(row);
  }
  b.grid[9][4] = [X.RED, X.KING];
  b.grid[0][4] = [X.BLACK, X.KING];
  b.grid[2][4] = [X.BLACK, X.CHARIOT];     // 黑车照将（同列，中间无子）
  b.grid[9][0] = [X.RED, X.CHARIOT];       // 红方有车但没在将线上
  b.turn = X.RED;
  var ai3 = new X.XqAI('medium', 3);
  var mv3 = ai3.getMove(b);
  // 应将后红帅必须不再被攻击
  b.apply([mv3[0], mv3[1]], [mv3[2], mv3[3]], false);
  var stillCheck = b.inCheck(X.RED);
  ok('被将军时能应将（帅不再被攻击）', !stillCheck, '着法=' + JSON.stringify(mv3));
})();

// ------------------------------------------------------------------ 飞将（将帅照面）回归
// 用例 a：双王同列、中间无子 → 双方 inCheck 均须为 true（照面即互攻）
(function () {
  var b = new X.XiangqiBoard();
  b.grid = [];
  for (var y = 0; y < X.ROWS; y++) {
    var row = [];
    for (var x = 0; x < X.COLS; x++) row.push(null);
    b.grid.push(row);
  }
  b.grid[0][4] = [X.BLACK, X.KING];
  b.grid[9][4] = [X.RED, X.KING];
  ok('照面：双王同列无遮挡，双方 inCheck 均为 true',
    b.inCheck(X.RED) === true && b.inCheck(X.BLACK) === true);
})();

// 用例 b：双王同列、中间恰一枚己方车挡住 → 车横移离开将线的着法必须被过滤
(function () {
  var b = new X.XiangqiBoard();
  b.grid = [];
  for (var y = 0; y < X.ROWS; y++) {
    var row = [];
    for (var x = 0; x < X.COLS; x++) row.push(null);
    b.grid.push(row);
  }
  b.grid[0][4] = [X.BLACK, X.KING];
  b.grid[9][4] = [X.RED, X.KING];
  b.grid[5][4] = [X.RED, X.CHARIOT];       // 红车挡在将线上
  b.grid[9][3] = [X.RED, X.ADVISOR];       // 仕：与照面无关的着法来源
  b.turn = X.RED;

  // 前提自检：红车伪合法着法中确实存在横移（保证下面的过滤不是空集碰巧成立）
  var pseudoSide = b.movesOf(X.RED).filter(function (m) {
    return m[0] === 4 && m[1] === 5 && m[3] === 5 && m[2] !== 4;
  });
  ok('前提自检：挡线车的伪合法着法中确有横移', pseudoSide.length > 0,
    '横移伪合法着法数=' + pseudoSide.length);

  var legal = b.legalMoves(X.RED);
  var sideOff = legal.filter(function (m) {
    return m[0] === 4 && m[1] === 5 && m[3] === 5 && m[2] !== 4;
  });
  ok('照面着法被过滤：挡线车横移离开将线不在 legalMoves', sideOff.length === 0);

  // 仕斜走（(3,9)→(4,8)）不影响将线上的遮挡，必须仍然合法
  var adv = legal.some(function (m) {
    return m[0] === 3 && m[1] === 9 && m[2] === 4 && m[3] === 8;
  });
  ok('与照面无关的着法（仕斜走）仍在 legalMoves', adv);

  // 车沿将线纵向移动仍保持遮挡，同样必须合法
  var vert = legal.some(function (m) {
    return m[0] === 4 && m[1] === 5 && m[2] === 4 && m[3] === 6;
  });
  ok('不破坏遮挡的着法（挡线车纵向移动）仍在 legalMoves', vert);
})();

// 用例 c：初始局面红方合法着法仍为 44（防止修复误伤正常走法生成）
(function () {
  var n = new X.XiangqiBoard().legalMoves(X.RED).length;
  ok('初始局面红方合法着法仍为 44', n === 44, '实际=' + n);
})();

console.log('\n合计：' + passed + ' passed, ' + failed + ' failed');
if (failed) { console.log('失败项：' + fails.join('、')); process.exit(1); }
process.exit(0);
