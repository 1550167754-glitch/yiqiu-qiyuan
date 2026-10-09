/**
 * board.js —— 六子棋/五子棋棋盘（移植自桌面版 src/liuziqi/board.py）
 *
 * 【平台无关铁律】本文件不引用 DOM、window、wx、require 之外的任何东西。
 * 同一个文件被三处复用：Node 回归测试 / 浏览器网页版 / 将来的微信小程序。
 * 所以这里只用 CommonJS（module.exports），浏览器端由构建脚本转一层。
 *
 * 与 Python 版逐条对应：EMPTY/BLACK/WHITE、grid[y][x]、history 栈、
 * place/undo 非法输入返回 false/null 而不抛异常、checkWin 只看最后一手、
 * scanWin 全盘兜底、getCandidates 切比雪夫半径候选点。
 */

var EMPTY = 0;
var BLACK = 1;
var WHITE = 2;
var SIZE = 19;
var WIN_COUNT = 6;
var DIRECTIONS = [[1, 0], [0, 1], [1, 1], [1, -1]];
var COLOR_NAMES = { 1: '黑棋', 2: '白棋' };

function opposite(color) {
  return color === BLACK ? WHITE : BLACK;
}

function Board(size, winCount) {
  this.size = size || SIZE;
  this.winCount = winCount || WIN_COUNT;
  this.moveCount = 0;
  this.history = [];
  this.grid = [];
  for (var y = 0; y < this.size; y++) {
    var row = new Array(this.size);
    for (var x = 0; x < this.size; x++) row[x] = EMPTY;
    this.grid.push(row);
  }
}

Board.prototype.isValid = function (x, y) {
  return x >= 0 && x < this.size && y >= 0 && y < this.size;
};

Board.prototype.isEmpty = function (x, y) {
  return this.isValid(x, y) && this.grid[y][x] === EMPTY;
};

Board.prototype.get = function (x, y) {
  if (!this.isValid(x, y)) return EMPTY;
  return this.grid[y][x];
};

/** 深拷贝；AI 全程在快照上搜索，中途超时/异常都不会污染真实棋盘。 */
Board.prototype.snapshot = function () {
  var b = new Board(this.size, this.winCount);
  for (var y = 0; y < this.size; y++) {
    for (var x = 0; x < this.size; x++) b.grid[y][x] = this.grid[y][x];
  }
  b.moveCount = this.moveCount;
  b.history = this.history.slice();
  return b;
};

Board.prototype.isFull = function () {
  return this.moveCount >= this.size * this.size;
};

Board.prototype.place = function (x, y, color) {
  if (!this.isEmpty(x, y)) return false;
  if (color !== BLACK && color !== WHITE) return false;
  this.grid[y][x] = color;
  this.moveCount += 1;
  this.history.push([x, y, color]);
  return true;
};

Board.prototype.undo = function () {
  if (!this.history.length) return null;
  var last = this.history.pop();
  this.grid[last[1]][last[0]] = EMPTY;
  this.moveCount -= 1;
  return [last[0], last[1], last[2]];
};

/** 判定 (x,y) 处刚落下的子是否连成 winCount；返回整条连线或 null。 */
Board.prototype.checkWin = function (x, y) {
  var color = this.get(x, y);
  if (color === EMPTY) return null;
  var n = this.size;
  var wc = this.winCount;
  for (var d = 0; d < 4; d++) {
    var dx = DIRECTIONS[d][0];
    var dy = DIRECTIONS[d][1];
    var line = [[x, y]];
    var i = x + dx;
    var j = y + dy;
    while (i >= 0 && i < n && j >= 0 && j < n && this.grid[j][i] === color) {
      line.push([i, j]);
      i += dx;
      j += dy;
    }
    i = x - dx;
    j = y - dy;
    while (i >= 0 && i < n && j >= 0 && j < n && this.grid[j][i] === color) {
      line.unshift([i, j]);
      i -= dx;
      j -= dy;
    }
    if (line.length >= wc) return line;
  }
  return null;
};

/** 全盘扫描胜负（兜底）。返回 [winner, line]；无胜局 [null, null]。 */
Board.prototype.scanWin = function () {
  var n = this.size;
  var wc = this.winCount;
  for (var y = 0; y < n; y++) {
    for (var x = 0; x < n; x++) {
      var c = this.grid[y][x];
      if (c === EMPTY) continue;
      for (var d = 0; d < 4; d++) {
        var dx = DIRECTIONS[d][0];
        var dy = DIRECTIONS[d][1];
        var px = x - dx;
        var py = y - dy;
        if (px >= 0 && px < n && py >= 0 && py < n && this.grid[py][px] === c) continue;
        var line = [];
        var i = x;
        var j = y;
        while (i >= 0 && i < n && j >= 0 && j < n && this.grid[j][i] === c) {
          line.push([i, j]);
          i += dx;
          j += dy;
        }
        if (line.length >= wc) return [c, line];
      }
    }
  }
  return [null, null];
};

/**
 * 候选点：距任意已有棋子切比雪夫距离 <= radius 的空点，按 (y,x) 升序。
 * 空盘返回中心 3×3。这是把 361 个空点压到几十个的关键。
 */
Board.prototype.getCandidates = function (radius, limit) {
  var r = radius === undefined ? 2 : radius;
  var n = this.size;
  if (this.moveCount === 0) {
    var c = Math.floor(n / 2);
    var out = [];
    for (var y0 = c - 1; y0 <= c + 1; y0++) {
      for (var x0 = c - 1; x0 <= c + 1; x0++) {
        if (this.isEmpty(x0, y0)) out.push([x0, y0]);
      }
    }
    return out;
  }
  var seen = {};
  var cands = [];
  for (var y = 0; y < n; y++) {
    for (var x = 0; x < n; x++) {
      if (this.grid[y][x] === EMPTY) continue;
      for (var j = y - r; j <= y + r; j++) {
        for (var i = x - r; i <= x + r; i++) {
          if (!this.isEmpty(i, j)) continue;
          var k = j * n + i;
          if (seen[k]) continue;
          seen[k] = 1;
          cands.push([i, j]);
        }
      }
    }
  }
  cands.sort(function (a, b) {
    return (a[1] - b[1]) || (a[0] - b[0]);
  });
  if (limit !== undefined && limit !== null) return cands.slice(0, limit);
  return cands;
};

module.exports = {
  EMPTY: EMPTY,
  BLACK: BLACK,
  WHITE: WHITE,
  SIZE: SIZE,
  WIN_COUNT: WIN_COUNT,
  DIRECTIONS: DIRECTIONS,
  COLOR_NAMES: COLOR_NAMES,
  opposite: opposite,
  Board: Board
};
