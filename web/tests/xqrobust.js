/**
 * xqrobust.js —— 象棋引擎"绝不卡死/崩溃"回归测试
 *
 *   node web/tests/xqrobust.js
 *
 * 背景（真实事故）：置换表用 32bit Zobrist 做键，中局一次搜索动辄 50 万~90 万节点，
 * 哈希碰撞必然发生；碰撞命中后 `_moveToFront` 会把"别局的着法"**无条件**塞进着法列表，
 * search 拿去 apply 时源格为空 → `TypeError` 崩溃。浏览器里表现为：worker 报错→回退同步
 * →同步又崩→`thinking` 永远为 true→界面永久卡在"AI 思考中"。
 *
 * 本测试把"不崩"钉死：
 *   1) `_moveToFront` 对"不在列表里的着法"必须原样返回（根因的直接单测）；
 *   2) hard 档自对弈（关开局库）若干手，每手都必须：不抛异常、返回合法着法、限时内返回；
 *   3) 棋盘增量 Zobrist 与"重算 Zobrist"必须完全一致（apply/undo 对称性）。
 */
var path = require('path');
var X = require(path.join(__dirname, '..', 'engine', 'xiaqi.js'));

var passed = 0, failed = 0, fails = [];
function ok(name, cond, extra) {
  if (cond) { passed++; console.log('PASS ' + name + (extra ? '  ' + extra : '')); }
  else { failed++; fails.push(name); console.log('FAIL ' + name + (extra ? '  ' + extra : '')); }
}
function fmt(mv) { return mv ? '(' + mv[0] + ',' + mv[1] + ')->(' + mv[2] + ',' + mv[3] + ')' : 'null'; }

// ---------------------------------------------------------------- 1. _moveToFront 不变量
(function () {
  var ai = new X.XqAI('hard', 1);
  var list = [[1, 1, 1, 2], [2, 2, 2, 3], [3, 3, 3, 4]];
  var foreign = [9, 9, 9, 9];                        // 不在列表里（模拟碰撞来的别局着法）
  var out = ai._moveToFront(list, foreign);
  ok('_moveToFront 不注入列表外的着法（长度不变）', out.length === list.length, 'len=' + out.length);
  ok('_moveToFront 不把列表外着法放到最前', out[0][0] !== 9, '首元素=' + JSON.stringify(out[0]));

  var out2 = ai._moveToFront(list, [2, 2, 2, 3]);   // 在列表里 → 提到最前
  ok('_moveToFront 把列表内着法提到最前', out2[0][0] === 2 && out2.length === 3, JSON.stringify(out2));
  ok('_moveToFront 对 null 安全', ai._moveToFront(list, null).length === list.length);
})();

// ---------------------------------------------------------------- 2. Zobrist 增量 vs 重算
(function () {
  var b = new X.XiangqiBoard();
  ok('初始局面 zobrist2 已计算', typeof b.zobrist2 === 'number', 'zobrist=' + b.zobrist + ' z2=' + b.zobrist2);
  var mv = b.legalMoves(b.turn)[0];
  var z0 = b.zobrist, z20 = b.zobrist2;
  b.apply([mv[0], mv[1]], [mv[2], mv[3]], true);
  var inc = b.zobrist, inc2 = b.zobrist2;
  b.recomputeZobrist();
  ok('apply 的增量 zobrist 与重算一致', b.zobrist === inc, 'inc=' + inc + ' recompute=' + b.zobrist);
  ok('apply 的增量 zobrist2 与重算一致', b.zobrist2 === inc2, 'inc2=' + inc2 + ' recompute=' + b.zobrist2);
  b.undo();
  ok('undo 后 zobrist 回到原点', b.zobrist === z0, 'now=' + b.zobrist + ' want=' + z0);
  ok('undo 后 zobrist2 回到原点', b.zobrist2 === z20, 'now=' + b.zobrist2 + ' want=' + z20);
})();

// ---------------------------------------------------------------- 3. hard 自对弈：不崩、着法合法、限时
(function () {
  var b = new X.XiangqiBoard();
  var plies = 12;
  var allLegal = true, maxDt = 0, worst = '';
  var crashed = null;
  try {
    for (var ply = 0; ply < plies; ply++) {
      var ai = new X.XqAI('hard', 4242 + ply * 13);
      ai.useBook = false;                 // 关库，强制真搜索（碰撞才可能复现）
      ai.timeLimit = 1500;                // 缩短每手时限，保持测试总时长可控
      var legal = b.legalMoves(b.turn);
      var t0 = Date.now();
      var mv = ai.getMove(b);
      var dt = Date.now() - t0;
      if (dt > maxDt) { maxDt = dt; worst = 'ply ' + ply + '=' + dt + 'ms'; }
      var inList = !!mv && legal.some(function (m) {
        return m[0] === mv[0] && m[1] === mv[1] && m[2] === mv[2] && m[3] === mv[3];
      });
      if (!inList) { allLegal = false; console.log('  非法着法 ply=' + ply + ' ' + fmt(mv) + ' 合法数=' + legal.length); break; }
      b.apply([mv[0], mv[1]], [mv[2], mv[3]], true);
      if (b.gameOver) break;
    }
  } catch (e) {
    crashed = e;
  }
  ok('hard 自对弈 ' + plies + ' 手不抛异常（回归：曾因哈希碰撞注入非法着法崩溃）',
    !crashed, crashed ? (crashed.message || String(crashed)) : '');
  ok('hard 每手返回都是合法着法', allLegal);
  ok('hard 每手都在时限内返回（< 4s）', maxDt > 0 && maxDt < 4000, '最大耗时 ' + worst);
})();

console.log('\n合计：' + passed + ' passed, ' + failed + ' failed');
if (failed) { console.log('失败项：' + fails.join('、')); process.exit(1); }
