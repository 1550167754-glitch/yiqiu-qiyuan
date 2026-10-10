/**
 * xqstrength.js —— 象棋引擎棋力抽检
 *
 *   node web/tests/xqstrength.js
 *
 * 用几个"有名字的杀法/战术局面"检查引擎是否具备相应棋力。
 * 这类测试比"随便走几步看看"可靠得多：每一题都有唯一的正确解法。
 */

var path = require('path');
var X = require(path.join(__dirname, '..', 'engine', 'xiaqi.js'));

var passed = 0, failed = 0, fails = [];
function ok(name, cond, extra) {
  if (cond) { passed++; console.log('PASS ' + name + (extra ? '  ' + extra : '')); }
  else { failed++; fails.push(name); console.log('FAIL ' + name + (extra ? '  ' + extra : '')); }
}

/** 造一个只有指定棋子的局面。kings: {red:[x,y], black:[x,y]} */
function pos(pieces, redKing, blackKing, turn) {
  var b = new X.XiangqiBoard();
  b.grid = [];
  for (var y = 0; y < X.ROWS; y++) {
    var row = [];
    for (var x = 0; x < X.COLS; x++) row.push(null);
    b.grid.push(row);
  }
  b.grid[blackKing[1]][blackKing[0]] = [X.BLACK, X.KING];
  b.grid[redKing[1]][redKing[0]] = [X.RED, X.KING];
  pieces.forEach(function (p) {
    b.grid[p[3]][p[2]] = [p[0], p[1]];
  });
  b.turn = turn || X.RED;
  return b;
}

function mvStr(m) { return m ? '(' + m[0] + ',' + m[1] + ')->(' + m[2] + ',' + m[3] + ')' : 'null'; }

// ---------------------------------------------------------------- 1. 一步杀：白脸将
// 红车在 (4,3)，黑将在 (4,0)，红帅在 (4,9)：同列中间无子 → 飞将照面，红车进底线即杀？
// 换成更明确的：黑将在 (4,0)，红车在 (0,0) 横线，红炮在 (4,5) 作炮架 →
// 红车横扫底线直接吃将。这里用最直白的"车吃无保护将"。
(function () {
  var b = pos([[X.RED, X.CHARIOT, 0, 0]], [4, 9], [4, 0], X.RED);
  // 把黑将放到车能一步吃到的位置
  b.grid[0][4] = null;
  b.grid[0][4] = [X.BLACK, X.KING];
  b.grid[0][0] = [X.RED, X.CHARIOT];
  // 黑将在 (4,0)，红车在 (0,0)，中间 (1,0)(2,0)(3,0) 为空 → 车一步吃将
  var ai = new X.XqAI('medium', 11);
  var mv = ai.getMove(b);
  // 接受"吃将"的任一手：红车 (0,0)->(4,0) 或 飞将（红帅 (4,9)->(4,0) 同列无遮拦吃将）。
  var eats = mv && mv[2] === 4 && mv[3] === 0;
  ok('一步吃将（车横扫/飞将均可）', eats, '着法=' + mvStr(mv));
})();

// ---------------------------------------------------------------- 2. 一步杀：马后炮
// 黑将 (4,0)；红炮 (4,2) 与黑将同列、中间 (4,1) 为红马（炮架）；
// 红马跳到 (3,1) 或 (5,1) 附近形成"马后炮"杀 —— 检查引擎能否走出将军且必胜的着法
(function () {
  var b = pos([
    [X.RED, X.CANNON, 4, 2],
    [X.RED, X.HORSE, 4, 1],
    [X.RED, X.CHARIOT, 0, 3]
  ], [4, 9], [4, 0], X.RED);
  var ai = new X.XqAI('hard', 12);
  var mv = ai.getMove(b);
  // 走出后应至少能将军（inCheck 黑方）
  var b2 = b;
  b2.apply([mv[0], mv[1]], [mv[2], mv[3]], false);
  var givesCheck = b2.inCheck(X.BLACK);
  b2.undo();
  ok('马后炮局面能走出将军', givesCheck, '着法=' + mvStr(mv) + ' 将军=' + givesCheck);
})();

// ---------------------------------------------------------------- 3. 物质判断：必吃送上门的大子
// 【踩坑教训·必留】测"吃送吃大子"极易假失败：红车落子时一旦能照将，引擎常能顺手走出
// 两步杀（这其实更聪明），断言"吃子"就落空。前几版用过"红车(0,6) 黑将(3,0)"，
// 红车走 (0,6)->(3,6) 将军即触发 mate-in-2，引擎弃吃子走杀着，断言失败。
// 可靠的局面必须满足：**红车没有任何一步将军/照面可走**，于是"吃子"是严格最优解。
// 本局面：红车(8,9)、红帅(4,9) 同在第 9 行、红帅恰好挡住红车沿第 9 行去黑将列(3)的路；
// 黑车挂在 (8,5) 同列(8) 送吃，黑将(3,0) 不在第 8 列，红车沿第 8 行被黑车本身挡住无法到第 8 行底，
// 因此红车**唯一**有收益的正解就是 (8,9)->(8,5) 吃掉黑车 (+900)，无将军可走、无速杀可抢。
(function () {
  var b = pos([
    [X.RED, X.CHARIOT, 8, 9],
    [X.BLACK, X.CHARIOT, 8, 5],
    [X.BLACK, X.PAWN, 1, 7]
  ], [4, 9], [3, 0], X.RED);
  var ai = new X.XqAI('hard', 13);
  var before = materialRed(b);
  var mv = ai.getMove(b);
  b.apply([mv[0], mv[1]], [mv[2], mv[3]], false);
  var after = materialRed(b);
  b.undo();
  // 吃到对方一个车 → 红方物质净增约 +900（车=900），>=400 即通过
  ok('物质上必吃送上门的大子（净增 >= 400）', after - before >= 400,
    '着法=' + mvStr(mv) + ' 物质变化=' + (after - before));
})();

/** 红方视角的物质总和（用于断言"赚了子"）。 */
function materialRed(b) {
  var s = 0;
  for (var y = 0; y < X.ROWS; y++) {
    for (var x = 0; x < X.COLS; x++) {
      var p = b.grid[y][x];
      if (!p) continue;
      var v = X.PIECE_VALUE[p[1]] || 0;
      s += (p[0] === X.RED ? v : -v);
    }
  }
  return s;
}

// ---------------------------------------------------------------- 4. 不白送子：有保护的子不该贪
// 黑车 (0,3) 被黑车 (0,1) 保着（同列相邻），红车吃 (0,3) 会被立刻打回 → 不应吃。
(function () {
  var b = pos([
    [X.RED, X.CHARIOT, 0, 6],
    [X.BLACK, X.CHARIOT, 0, 3],
    [X.BLACK, X.CHARIOT, 0, 1]
  ], [4, 9], [5, 0], X.RED);
  var ai = new X.XqAI('hard', 14);
  var mv = ai.getMove(b);
  var eats = mv && mv[2] === 0 && mv[3] === 3;
  ok('不白吃有保护的黑车（吃后被同列黑车打回）', !eats, '着法=' + mvStr(mv) + ' 吃车=' + eats);
})();

// ---------------------------------------------------------------- 5. 被将军必须应将
(function () {
  var b = pos([
    [X.RED, X.CHARIOT, 0, 5],
    [X.BLACK, X.CHARIOT, 4, 1]
  ], [4, 9], [5, 0], X.RED);
  // 黑车在 (4,1) 照将红帅 (4,9)（中间为空）
  var ai = new X.XqAI('medium', 15);
  var mv = ai.getMove(b);
  var b2 = b;
  b2.apply([mv[0], mv[1]], [mv[2], mv[3]], false);
  var safe = !b2.inCheck(X.RED);
  b2.undo();
  ok('被将时走出的着法能解将', safe, '着法=' + mvStr(mv));
})();

// ---------------------------------------------------------------- 6. 搜索深度/速度体检
(function () {
  var b = new X.XiangqiBoard();
  var ai = new X.XqAI('hard', 16);
  ai.useBook = false;            // 关掉开局库，纯粹测搜索深度（否则首着直接走库、深度记为 1）
  var t = Date.now();
  var mv = ai.getMove(b);
  var dt = Date.now() - t;
  ok('困难档能在时限内搜到 >= 4 层', ai.lastDepth >= 4,
    '深度=' + ai.lastDepth + ' 节点=' + ai.nodes + ' 耗时=' + dt + 'ms');
})();

// ---------------------------------------------------------------- 7. 自对弈不崩、能终局
(function () {
  var b = new X.XiangqiBoard();
  var aiR = new X.XqAI('easy', 21);
  var aiB = new X.XqAI('easy', 22);
  var moves = 0;
  var t = Date.now();
  while (!b.gameOver && moves < 120 && Date.now() - t < 20000) {
    var ai = (b.turn === X.RED) ? aiR : aiB;
    var mv = ai.getMove(b);
    if (!mv) break;
    b.apply([mv[0], mv[1]], [mv[2], mv[3]], true);
    moves++;
  }
  ok('快棋自对弈能正常推进', moves >= 20,
    '共 ' + moves + ' 手，终局=' + b.gameOver + ' 胜方=' + (b.winner || '未分'));
})();

console.log('\n合计：' + passed + ' passed, ' + failed + ' failed');
if (failed) { console.log('失败项：' + fails.join('、')); process.exit(1); }
process.exit(0);
