/**
 * run.js —— 引擎层回归测试（零依赖，直接 node 跑）
 *
 *   node web/tests/run.js
 *
 * 只测「平台无关的引擎层」：board / game / ai。渲染层不在这里测。
 * 这些断言对应桌面版 tests/ 里的逻辑用例，移植后必须保持同样的行为。
 */

var path = require('path');
var B = require(path.join(__dirname, '..', 'engine', 'board.js'));
var G = require(path.join(__dirname, '..', 'engine', 'game.js'));
var A = require(path.join(__dirname, '..', 'engine', 'ai.js'));

var BLACK = B.BLACK;
var WHITE = B.WHITE;
var EMPTY = B.EMPTY;
var Board = B.Board;
var Game = G.Game;
var Player = G.Player;

var passed = 0;
var failed = 0;
var fails = [];

function ok(name, cond, extra) {
  if (cond) {
    passed += 1;
    console.log('PASS ' + name + (extra ? '  ' + extra : ''));
  } else {
    failed += 1;
    fails.push(name);
    console.log('FAIL ' + name + (extra ? '  ' + extra : ''));
  }
}

function eq(name, a, b) {
  var sa = JSON.stringify(a);
  var sb = JSON.stringify(b);
  ok(name, sa === sb, sa === sb ? '' : '\n     实际 ' + sa + '\n     期望 ' + sb);
}

// ---------------------------------------------------------------- board
(function testBoard() {
  var bd = new Board(15, 5);
  eq('空盘候选点中心 3×3 = 9', bd.getCandidates(2).length, 9);

  bd.place(7, 7, BLACK);
  eq('一子后候选点数', bd.getCandidates(2).length, 24);
  eq('落子后 moveCount', bd.moveCount, 1);

  ok('非法落子返回 false（已占位）', bd.place(7, 7, WHITE) === false);
  ok('非法落子返回 false（越界）', bd.place(-1, 0, BLACK) === false);
  ok('非法颜色返回 false', bd.place(0, 0, 9) === false);

  var u = bd.undo();
  eq('undo 返回被撤的子', u, [7, 7, BLACK]);
  ok('undo 后该点为空', bd.isEmpty(7, 7));
  ok('undo 后 moveCount 归零', bd.moveCount === 0);
  ok('空盘 undo 返回 null', bd.undo() === null);

  // 连六判定（六子棋）
  var c6 = new Board(19, 6);
  for (var i = 0; i < 5; i++) c6.place(i, 0, BLACK);
  ok('五连不算胜（六子棋）', c6.checkWin(4, 0) === null);
  c6.place(5, 0, BLACK);
  var line = c6.checkWin(5, 0);
  ok('六连算胜且返回整条线', line && line.length === 6, '线长=' + (line ? line.length : 'null'));

  // 斜线
  var dg = new Board(19, 6);
  for (var k = 0; k < 6; k++) dg.place(k, k, WHITE);
  ok('斜向六连算胜', dg.checkWin(3, 3) && dg.checkWin(3, 3).length === 6);
  // 反斜线
  var ad = new Board(19, 6);
  for (var m = 0; m < 6; m++) ad.place(10 - m, m, BLACK);
  ok('反斜六连算胜', ad.checkWin(7, 3) && ad.checkWin(7, 3).length === 6);

  // 连五（五子棋）
  var c5 = new Board(15, 5);
  for (var j = 0; j < 5; j++) c5.place(j, 3, WHITE);
  ok('五连在五子棋算胜', c5.checkWin(4, 3) && c5.checkWin(4, 3).length === 5);

  // scanWin 与 checkWin 一致性
  var sw = c6.scanWin();
  ok('scanWin 与 checkWin 一致', sw[0] === BLACK && sw[1].length === 6);

  // snapshot 深拷贝隔离
  var snap = c6.snapshot();
  snap.place(10, 10, WHITE);
  ok('snapshot 与原盘隔离', c6.get(10, 10) === EMPTY && snap.get(10, 10) === WHITE);
  ok('snapshot 携带 winCount', snap.winCount === 6);

  // 边界：棋盘四角的连线不应越界报错
  var corner = new Board(19, 6);
  for (var q = 0; q < 6; q++) corner.place(0, q, BLACK);
  ok('左边界竖向连六正确', corner.checkWin(0, 2) && corner.checkWin(0, 2).length === 6);
})();

// ---------------------------------------------------------------- game
(function testGame() {
  var g = new Game({ black: new Player('甲'), white: new Player('乙') });
  ok('黑先第一轮只能 1 子', g.maxStones === 1);
  var r = g.place(7, 7);
  ok('第一子落子成功', r.ok === true);
  ok('落子后本轮已下 1 子', g.stonesThisRound === 1);
  var r2 = g.place(8, 8);
  ok('第一轮下第 2 子被拒', r2.ok === false, r2.msg);

  g.endRound();
  ok('换手后轮到白', g.current === WHITE);
  ok('白方每轮 2 子', g.maxStones === 2);

  g.place(0, 0); g.place(1, 0); g.endRound();
  ok('白方下满 2 子后换手', g.current === BLACK);

  // undoRound：撤最近一轮
  var before = g.board.moveCount;
  var n = g.undoRound(false);
  ok('undoRound 撤掉一整轮', g.board.moveCount === before - 2, '撤了 ' + n + ' 子');

  // pendingUndo 必须与实际撤销一致
  var g2 = new Game({ black: new Player('甲'), white: new Player('乙') });
  g2.place(1, 1); g2.endRound();
  g2.place(2, 2); g2.place(3, 3); g2.endRound();
  g2.place(4, 4); g2.place(5, 5); g2.endRound();
  var pred = g2.pendingUndo(false).map(function (m) { return [m.x, m.y]; });
  var histBefore = g2.board.history.slice();
  g2.undoRound(false);
  var actual = histBefore.slice(g2.board.history.length).map(function (m) { return [m[0], m[1]]; });
  eq('pendingUndo == 实际撤销（人人）', pred, actual);

  // 人机模式：撤到人类回合（AI 一轮 + 我方一轮）
  var aiEngine = new A.AI('easy', 1);
  var g3 = new Game({
    black: new Player('玩家', 'human'),
    white: new Player('AI', 'ai', 'easy', aiEngine)
  });
  g3.place(9, 9); g3.endRound();
  g3.aiTurn();                       // AI 下完一轮 → 轮到人类
  ok('AI 走后轮到人类', g3.current === BLACK && g3.humanToMove());
  var movesBefore = g3.movesLog.length;
  var pred3 = g3.pendingUndo(true);
  var hist3 = g3.board.history.slice();
  g3.undoRound(true);
  var actual3 = hist3.slice(g3.board.history.length);
  eq('pendingUndo == 实际撤销（人机撤到人类）', pred3.map(function (m) { return [m.x, m.y, m.color]; }),
    actual3.map(function (m) { return [m[0], m[1], m[2]]; }));
  ok('人机悔棋后确实轮到我方', g3.humanToMove(), '撤前 ' + movesBefore + ' 手');

  // 终局 + 终局后悔棋
  var g4 = new Game({ black: new Player('甲'), white: new Player('乙') });
  var bp = [];
  for (var i = 0; i < 6; i++) bp.push([i, 0]);
  var wp = [];
  for (var j = 0; j < 8; j++) wp.push([j, 10]);
  var bi = 0;
  var wi = 0;
  for (var t = 0; t < 20 && !g4.finished; t++) {
    var pt = g4.current === BLACK ? bp[bi++] : wp[wi++];
    g4.place(pt[0], pt[1]);
    if (g4.finished || g4.stonesThisRound >= g4.maxStones) g4.endRound();
  }
  ok('构造出终局', g4.finished === true, g4.resultText());
  g4.undoRound(false);
  ok('终局后悔棋解除终局', g4.finished === false && g4.winner === null && !g4.winLine);

  // 五子棋变体：每轮 1 子
  var g5 = new Game({ variant: 'gomoku', black: new Player('甲'), white: new Player('乙') });
  ok('五子棋棋盘 15×15', g5.board.size === 15 && g5.board.winCount === 5);
  g5.place(7, 7);
  ok('五子棋每轮 1 子', g5.maxStones === 1 && g5.stonesThisRound === 1);
  var r5 = g5.place(8, 8);
  ok('五子棋本轮不能下第 2 子', r5.ok === false);
})();

// ---------------------------------------------------------------- ai
(function testAI() {
  // ① 一手成六必须立刻赢
  var b1 = new Board(19, 6);
  for (var i = 0; i < 5; i++) b1.place(i, 5, BLACK);
  var ai1 = new A.AI('medium', 7);
  var mv1 = ai1.getMove(b1, BLACK, 1);
  ok('AI 一手成六（左端）', (mv1[0][0] === 5 && mv1[0][1] === 5),
    JSON.stringify(mv1));

  // 中间空一个的补位成六
  var b2 = new Board(19, 6);
  b2.place(0, 5, BLACK); b2.place(1, 5, BLACK); b2.place(2, 5, BLACK);
  b2.place(4, 5, BLACK); b2.place(5, 5, BLACK);
  var ai2 = new A.AI('medium', 7);
  var mv2 = ai2.getMove(b2, BLACK, 1);
  ok('AI 会补中间缺口成六', (mv2[0][0] === 3 && mv2[0][1] === 5), JSON.stringify(mv2));

  // ② 对手差一子成六，必须封堵
  var b3 = new Board(19, 6);
  for (var k = 0; k < 5; k++) b3.place(k, 8, WHITE);
  var ai3 = new A.AI('medium', 11);
  var mv3 = ai3.getMove(b3, BLACK, 1);
  ok('AI 会封堵对手冲六点', (mv3[0][0] === 5 && mv3[0][1] === 8), JSON.stringify(mv3));

  // ③ 对手活五（两端都能成六）时，两子模式应两端各堵一个
  var b4 = new Board(19, 6);
  for (var m = 1; m <= 5; m++) b4.place(m, 8, WHITE);
  var ai4 = new A.AI('medium', 13);
  var mv4 = ai4.getMove(b4, BLACK, 2);
  var got = mv4.map(function (p) { return p[0] + ',' + p[1]; }).sort().join(' ');
  ok('AI 两端各堵一子（或至少堵住一端）',
    mv4.length === 2 && mv4.every(function (p) { return p[1] === 8; }),
    JSON.stringify(mv4) + ' -> ' + got);

  // ④ AI 落子必须合法（不占位、不越界）
  var b5 = new Board(19, 6);
  b5.place(9, 9, BLACK); b5.place(10, 10, WHITE);
  for (var d = 0; d < 3; d++) {
    var aiD = new A.AI(['easy', 'medium', 'hard'][d], 100 + d);
    var mvd = aiD.getMove(b5, BLACK, 2);
    var allLegal = mvd.length >= 1 && mvd.every(function (p) {
      return b5.isValid(p[0], p[1]) && b5.isEmpty(p[0], p[1]);
    });
    var distinct = mvd.length < 2 || (mvd[0][0] !== mvd[1][0] || mvd[0][1] !== mvd[1][1]);
    ok('难度 ' + ['easy', 'medium', 'hard'][d] + ' 落子合法且不重复', allLegal && distinct,
      JSON.stringify(mvd));
  }

  // ⑤ 引擎不会污染真实棋盘（搜索全程在快照上）
  var b6 = new Board(19, 6);
  b6.place(9, 9, BLACK);
  b6.place(10, 9, WHITE);
  var before = JSON.stringify(b6.grid);
  var aiB = new A.AI('hard', 5);
  aiB.getMove(b6, BLACK, 2);
  ok('AI 搜索不污染真实棋盘', JSON.stringify(b6.grid) === before);

  // ⑥ 评估函数方向性：己方大优必须高于对方大优
  var ev1 = new Board(19, 6);
  for (var e = 0; e < 4; e++) ev1.place(e, 0, BLACK);
  var s1 = A._internal.evaluate(ev1, BLACK);
  var s2 = A._internal.evaluate(ev1, WHITE);
  ok('评估对行棋方有利（黑视角 > 白视角）', s1 > s2, '黑视角=' + s1 + ' 白视角=' + s2);

  // ⑦ 对手"差一子即胜"时，AI 必须封堵（这是最要紧的防漏着）
  //    六子棋的强制胜形态：4 连两端开放（活四）→ 补一头成"活五"，
  //    活五两端都是成六点，对手一子堵不完 → 必胜。
  //    对引擎的要求分两层：① 自己的成六点能认出来 ② 对手的成六点必须去堵。
  var b7 = new Board(19, 6);
  for (var x7 = 1; x7 <= 4; x7++) b7.place(x7, 5, WHITE);   // 白活四：两端 (0,5)/(5,5)
  var ai7 = new A.AI('medium', 21);
  var mv7 = ai7.getMove(b7, BLACK, 1);
  // 白方在活四状态下的成六点应当为空（还没补成五）
  ok('活四本身没有成六点（须补一手才是威胁）',
    A._internal.winPoints(b7, WHITE).length === 0);
  // 模拟白补一头成"活五"，此时白有两个成六点 → AI 必须去堵其中之一
  var threatBoard = b7.snapshot();
  threatBoard.place(5, 5, WHITE);
  var whiteWins = A._internal.winPoints(threatBoard, WHITE);
  ok('白补成活五后有两个成六点（堵不完 → 已必胜形态）',
    whiteWins.length >= 2, JSON.stringify(whiteWins));
  var ai7b = new A.AI('medium', 21);
  var mvBlock = ai7b.getMove(threatBoard, BLACK, 1);
  var blocked = whiteWins.some(function (p) {
    return p[0] === mvBlock[0][0] && p[1] === mvBlock[0][1];
  });
  ok('AI 会去堵对手的成六点', blocked,
    'AI=' + JSON.stringify(mvBlock) + ' 白的成六点=' + JSON.stringify(whiteWins));

  // ⑧ 五子棋模式：四连必须补成五（不同 winCount 下分值档位要跟着平移）
  var b8 = new Board(15, 5);
  for (var x8 = 3; x8 < 7; x8++) b8.place(x8, 7, WHITE);
  var ai8 = new A.AI('medium', 33);
  var mv8 = ai8.getMove(b8, WHITE, 1);
  var wins = (mv8[0][0] === 2 || mv8[0][0] === 7) && mv8[0][1] === 7;
  ok('五子棋 AI 会补成五', wins, JSON.stringify(mv8));
})();

console.log('\n合计：' + passed + ' passed, ' + failed + ' failed');
if (failed) {
  console.log('失败项：' + fails.join('、'));
  process.exit(1);
}
