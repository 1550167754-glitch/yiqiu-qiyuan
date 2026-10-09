/**
 * wincheck.js —— 用"穷举对拍"证明 AI 引擎里的胜负判定与棋盘真值完全一致。
 *
 *   node web/tests/wincheck.js
 *
 * 做法：在一维线段上枚举 0/1/2（空/黑/白）的所有小组合，
 * 对每个候选落点分别用两套独立实现判断"落这一子是否成六"：
 *   A. board.checkWin()——基于真实落子的权威判定（用它当 ground truth）
 *   B. ai.isWinMove()  ——引擎里用于威胁检测的那套（含缺口/跳形的快速判定）
 * 两者必须**逐点一致**。这是唯一能确认"缺口、跳形、双侧缺口、跨界"都写对的办法，
 * 靠手写期望值很容易把自己写错的认知当成正确结果。
 */

var path = require('path');
var B = require(path.join(__dirname, '..', 'engine', 'board.js'));
var A = require(path.join(__dirname, '..', 'engine', 'ai.js'));

var BLACK = B.BLACK;
var WHITE = B.WHITE;
var EMPTY = B.EMPTY;

var SEQ = Math.pow(3, 11);      // 长度 11 的一维线段，3^11 = 177147 种组合
var mismatches = 0;
var checked = 0;
var winCount = 0;
var samples = [];

for (var code = 0; code < SEQ; code++) {
  // 解出线段内容（下标 0..10）
  var line = [];
  var v = code;
  for (var i = 0; i < 11; i++) {
    line.push(v % 3);
    v = Math.floor(v / 3);
  }
  // 全部落在中间行 y=5，x = i
  var bd = new B.Board(19, 6);
  for (var x = 0; x < 11; x++) {
    if (line[x] !== EMPTY) bd.place(x, 5, line[x]);
  }
  // 只考虑"落在 3..7"这些关键位置（两侧都有 3 格余地）
  for (var px = 3; px <= 7; px++) {
    if (line[px] !== EMPTY) continue;
    for (var who = 0; who < 2; who++) {
      var color = who === 0 ? BLACK : WHITE;
      // A：权威判定 —— 真落子后问 checkWin
      var snap = bd.snapshot();
      snap.place(px, 5, color);
      var truth = snap.checkWin(px, 5) !== null;
      // B：引擎判定
      var fast = A._internal.isWinMove(bd.grid, 19, px, 5, 6, color);
      checked += 1;
      if (truth) winCount += 1;
      if (truth !== fast) {
        mismatches += 1;
        if (samples.length < 8) {
          samples.push({
            line: line.join(''),
            place: px,
            color: color === BLACK ? '黑' : '白',
            truth: truth,
            fast: fast
          });
        }
      }
    }
  }
}

console.log('对拍组合数：' + checked + '（其中真值为"成六"的 ' + winCount + ' 个）');
if (mismatches) {
  console.log('不一致：' + mismatches + ' 处');
  samples.forEach(function (s) {
    console.log('  线段=' + s.line + ' 落点x=' + s.place + ' 执' + s.color +
      ' 真值=' + s.truth + ' 引擎=' + s.fast);
  });
  process.exit(1);
}
console.log('全部一致：isWinMove 与 board.checkWin 逐点吻合');
process.exit(0);
