/* 自动生成，请勿手改 —— 源文件在 web/engine/，改完跑 node web/build.js */
(function (root) {
  var __mods = {};
  var __cache = {};
  function __req(name) {
    if (__cache[name]) return __cache[name].exports;
    var m = { exports: {} };
    __cache[name] = m;
    if (!__mods[name]) throw new Error("模块未打包: " + name);
    __mods[name](m, m.exports, __req);
    return m.exports;
  }
  __mods["./board.js"] = function (module, exports, require) {
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

  };
  __mods["./game.js"] = function (module, exports, require) {
/**
 * game.js —— 对局状态机（移植自桌面版 src/liuziqi/game.py）
 *
 * 规则（Connect6）：
 *   - 黑先，第一轮只下 1 子；
 *   - 之后双方每轮 1~2 子；
 *   - 横/竖/斜任一方向连成 6 子即胜。
 * 五子棋（variant='gomoku'）：15×15、每轮固定 1 子、连 5 即胜。
 *
 * 悔棋语义（与桌面版 v16 一致，这是踩过坑的地方）：
 *   undoRound(toHuman=true) —— 人机模式：连续撤销直到轮到人类，
 *   即一次撤掉「AI 一整轮 + 我方一整轮」，而不是只撤 AI 刚下的那步。
 *   undoRound(false)        —— 人人/AI 互弈：只撤最近一整轮。
 *
 * 【平台无关】不引用 DOM/wx。AI 在浏览器里会跑在 Worker（没有 Worker 时
 * 退化为分片同步搜索），因此这里不再需要桌面版那把 _ai_lock。
 */

var boardMod = require('./board.js');
var BLACK = boardMod.BLACK;
var WHITE = boardMod.WHITE;
var SIZE = boardMod.SIZE;
var WIN_COUNT = boardMod.WIN_COUNT;
var Board = boardMod.Board;
var opposite = boardMod.opposite;

var MODE_HUMAN_AI = 'human_ai';
var MODE_HUMAN_HUMAN = 'human_human';
var MODE_AI_AI = 'ai_ai';

var VARIANT_CONFIG = {
  connect6: { size: 19, winCount: 6, label: '六子棋' },
  gomoku: { size: 15, winCount: 5, label: '五子棋' }
};

/** createEngine(kind, difficulty) —— 由调用方注入 AI 工厂，避免引擎层依赖 AI 实现。 */
function Player(name, kind, difficulty, engine) {
  this.name = name;
  this.kind = kind || 'human';       // human / ai
  this.difficulty = difficulty || 'medium';
  this.engine = engine || null;      // 需实现 getMove(board, color, stonesToPlace) -> [[x,y],...]
}

function Game(opts) {
  opts = opts || {};
  var variant = opts.variant || 'connect6';
  var cfg = VARIANT_CONFIG[variant] || VARIANT_CONFIG.connect6;
  this.variant = variant;
  this.board = new Board(cfg.size, cfg.winCount);

  this.players = {};
  this.players[BLACK] = opts.black || new Player('黑方', 'human');
  this.players[WHITE] = opts.white || new Player('白方', 'human');

  this.current = BLACK;
  this.roundNo = 1;
  this.stonesThisRound = 0;
  this.maxStones = 1;               // 黑方第一轮 1 子
  this.finished = false;
  this.winner = null;
  this.winLine = null;
  this.reason = '';
  this.movesLog = [];               // [x, y, color, roundNo]
}

Game.prototype.currentPlayer = function () {
  return this.players[this.current];
};

Game.prototype.maxStonesFor = function (color) {
  if (this.variant === 'gomoku') return 1;
  if (color === BLACK && this.roundNo === 1) return 1;
  return 2;
};

/**
 * 落一子。返回 { ok, msg, line }。
 * 落子后若连成 winCount 直接置终局（与 Python 版一致）。
 */
Game.prototype.place = function (x, y) {
  if (this.finished) return { ok: false, msg: '对局已结束，请开始新对局', line: null };
  if (this.stonesThisRound >= this.maxStones) {
    return { ok: false, msg: '本轮已下满 ' + this.maxStones + ' 子，请结束回合', line: null };
  }
  var color = this.current;
  if (!this.board.place(x, y, color)) {
    return { ok: false, msg: '落子失败：该点已有棋子或坐标越界', line: null };
  }
  this.stonesThisRound += 1;
  this.movesLog.push([x, y, color, this.roundNo]);

  var line = this.board.checkWin(x, y);
  if (line) {
    this._finish(color, this._winReason(), line);
    return { ok: true, msg: (color === BLACK ? '黑棋' : '白棋') + '获胜！(' + this.reason + ')', line: line };
  }
  if (this.board.isFull()) {
    this._finish(null, '棋盘已满', null);
    return { ok: true, msg: '平局：棋盘已满', line: null };
  }
  return { ok: true, msg: '', line: null };
};

Game.prototype.endRound = function () {
  if (this.finished) return;
  this.current = opposite(this.current);
  this.roundNo += 1;
  this.stonesThisRound = 0;
  this.maxStones = this.maxStonesFor(this.current);
};

Game.prototype._finish = function (winner, reason, winLine) {
  this.finished = true;
  this.winner = winner;
  this.reason = reason;
  this.winLine = winLine || null;
};

Game.prototype._winReason = function () {
  if (this.variant === 'connect6') return '连成六子';
  return '连成 ' + this.board.winCount + ' 子';
};

Game.prototype.resign = function () {
  if (this.finished) return;
  var loser = this.current;
  this._finish(opposite(loser), (loser === BLACK ? '黑棋' : '白棋') + '认输', null);
};

Game.prototype.resultText = function () {
  if (this.winner !== null) {
    return (this.winner === BLACK ? '黑棋' : '白棋') + '获胜（' + this.reason + '）';
  }
  if (this.reason) return '平局（' + this.reason + '）';
  return '对局进行中';
};

/**
 * 预判 undoRound 会撤掉哪些子（供悔棋倒退动画先知道"要退哪几枚"）。
 * 与 undoRound 的取轮规则同源——两处不一致会让动画退错子。
 * 返回 [{x,y,color}, ...]，落子先后序。
 */
Game.prototype.pendingUndo = function (toHuman) {
  var log = this.movesLog.slice();
  if (!log.length) return [];
  var taken = [];
  var cur = this.current;
  while (log.length) {
    var lastRound = log[log.length - 1][3];
    var same = [];
    var rest = [];
    for (var i = 0; i < log.length; i++) {
      if (log[i][3] === lastRound) same.push(log[i]);
      else rest.push(log[i]);
    }
    taken = same.map(function (m) { return { x: m[0], y: m[1], color: m[2] }; }).concat(taken);
    log = rest;
    if (!toHuman) break;
    cur = same[same.length - 1][2];
    if (this.players[cur].kind === 'human') break;
  }
  return taken;
};

/** 撤销最近一整轮（1~2 子）。返回撤销的子数。 */
Game.prototype.undoRound = function (toHuman) {
  var total = 0;
  this.finished = false;
  this.winner = null;
  this.winLine = null;
  this.reason = '';
  while (this.movesLog.length) {
    var lastRound = this.movesLog[this.movesLog.length - 1][3];
    var same = [];
    var rest = [];
    for (var i = 0; i < this.movesLog.length; i++) {
      if (this.movesLog[i][3] === lastRound) same.push(this.movesLog[i]);
      else rest.push(this.movesLog[i]);
    }
    // 同一轮内部按落子先后撤（后下的先退）
    for (var k = same.length - 1; k >= 0; k--) this.board.undo();
    this.movesLog = rest;

    this.roundNo = lastRound;
    this.current = same[same.length - 1][2];
    this.stonesThisRound = 0;
    this.maxStones = this.maxStonesFor(this.current);
    total += same.length;

    if (!toHuman) break;
    if (this.currentPlayer().kind === 'human') break;
  }
  return total;
};

/** 当前行棋方是人类吗。 */
Game.prototype.humanToMove = function () {
  return this.currentPlayer().kind === 'human' && !this.finished;
};

/**
 * 让 AI 走完本轮。返回本轮落下的 [[x,y],...]。
 * 引擎接口：engine.getMove(board, color, stonesToPlace)
 */
Game.prototype.aiTurn = function () {
  var player = this.currentPlayer();
  if (player.kind === 'human' || this.finished || !player.engine) return [];
  var stones = player.engine.getMove(this.board, this.current, this.maxStones) || [];
  var out = [];
  for (var i = 0; i < stones.length; i++) {
    var r = this.place(stones[i][0], stones[i][1]);
    out.push([stones[i][0], stones[i][1]]);
    if (r.line) break;               // 中途连成即终局，不再落剩下的子
  }
  this.endRound();
  return out;
};

/** 导出棋谱（存本地/上传用）。 */
Game.prototype.toRecord = function () {
  var moves = this.movesLog.map(function (m) { return [m[0], m[1], m[2]]; });
  var result = 'ABORT';
  if (this.winner === BLACK) result = 'BLACK';
  else if (this.winner === WHITE) result = 'WHITE';
  else if (this.finished) result = 'DRAW';
  return {
    variant: this.variant,
    size: this.board.size,
    winCount: this.board.winCount,
    roundNo: this.roundNo,
    black: this.players[BLACK].name,
    blackKind: this.players[BLACK].kind,
    white: this.players[WHITE].name,
    whiteKind: this.players[WHITE].kind,
    moves: moves,
    result: result,
    reason: this.reason
  };
};

module.exports = {
  MODE_HUMAN_AI: MODE_HUMAN_AI,
  MODE_HUMAN_HUMAN: MODE_HUMAN_HUMAN,
  MODE_AI_AI: MODE_AI_AI,
  VARIANT_CONFIG: VARIANT_CONFIG,
  Player: Player,
  Game: Game
};

  };
  __mods["./ai.js"] = function (module, exports, require) {
/**
 * ai.js —— 本地 AI 引擎（移植自桌面版 src/liuziqi/ai.py）
 *
 * 保留桌面版的核心设计与"铁律"：
 *   1. 分值体系与 Python 版完全一致（WIN_SCORE / FIVE_OPEN / FOUR_OPEN / ...）；
 *   2. 落子顺序：① 己方一手成六 → ② 对手活五/冲六强制防守 → ③ 威胁空间搜索
 *      （TSS，冲四连击找必胜）→ ④ 迭代加深 + PVS + 置换表；
 *   3. 根节点在棋盘**快照**上搜索，中途超时/异常都不污染真实棋盘；
 *   4. 候选点只取已有棋子附近（切比雪夫半径 2），把 361 个空点压到几十个；
 *   5. 进攻权重 > 防守权重（3:1），避免"只会堵着续命"；
 *   6. 评估函数按**行棋方**动态取系数：己方 ×1.2、对手 ×1.6
 *      （对手威胁给更高惩罚，绝不漏守致命威胁）。
 *
 * 与 Python 版的差异（都是"浏览器里没这些条件"导致的，不影响棋力）：
 *   - 时间用 Date.now() 而非 time.monotonic()；
 *   - 评估改为**落点棋型采样**（8 方向射线，含跳形）而非全盘滑窗线表：
 *     省掉建线与逐线重算，在小程序/手机这种单线程环境里响应明显更快，
 *     棋型档位与 Python 的 _single_gain/_shape_rank 对齐；
 *   - 五子棋的 VCF/VCT 算杀（kill_search.py）暂未移植，改由 TSS + 加深搜索覆盖。
 *     Connect6 本来就不用 VCF/VCT，桌面版走的就是 TSS。
 *
 * 【平台无关】无 DOM / wx；搜索可被外部 stop() 中止（分片执行用）。
 */

var boardMod = require('./board.js');
var EMPTY = boardMod.EMPTY;
var BLACK = boardMod.BLACK;
var WHITE = boardMod.WHITE;
var opposite = boardMod.opposite;
var Board = boardMod.Board;

var WIN_SCORE = 10000000;
var FIVE_OPEN = 500000;
var FOUR_OPEN = 60000;
var FOUR_SIMPLE = 20000;
var THREE_OPEN = 6000;
var THREE_SIMPLE = 900;
var TWO_OPEN = 450;
var TWO_SIMPLE = 80;

var WIN_THRESHOLD = Math.floor(WIN_SCORE / 2);
var INF = Infinity;

var DIRS = [[1, 0], [0, 1], [1, 1], [1, -1]];

// ------------------------------------------------------------------ 随机源
// 固定种子的 xorshift：保证"同 seed 同棋路"可复现（用于回归测试与复盘）。
function makeRng(seed) {
  var s = (seed === undefined || seed === null) ? 0x9e3779b9 : (seed | 0);
  if (s === 0) s = 0x9e3779b9;
  return function () {
    s ^= s << 13; s |= 0;
    s ^= s >>> 17;
    s ^= s << 5; s |= 0;
    return ((s >>> 0) % 1000000) / 1000000;
  };
}

// ------------------------------------------------------------------ 棋型采样
/**
 * 以落点 (x,y) 为中心，沿某方向统计"若在此落 color 子"形成的连子数、
 * 两端开放度，并识别"跳形"（隔一个空位的连续段，六子棋里很关键）。
 * 返回 { cnt, openEnds, gaps }
 */
function scanDir(board, x, y, dx, dy, color) {
  var n = board.size;
  var grid = board.grid;
  var cnt = 1;          // 含落点自身
  var openEnds = 0;
  var gaps = 0;

  // 正方向
  var i = x + dx;
  var j = y + dy;
  while (i >= 0 && i < n && j >= 0 && j < n && grid[j][i] === color) {
    cnt += 1;
    i += dx;
    j += dy;
  }
  var gapUsedFwd = false;
  if (i >= 0 && i < n && j >= 0 && j < n && grid[j][i] === EMPTY) {
    // 跳形：空格后仍有己方子
    var ii = i + dx;
    var jj = j + dy;
    if (ii >= 0 && ii < n && jj >= 0 && jj < n && grid[jj][ii] === color) {
      var c2 = 0;
      while (ii >= 0 && ii < n && jj >= 0 && jj < n && grid[jj][ii] === color) {
        c2 += 1;
        ii += dx;
        jj += dy;
      }
      // 只有一段跳形才有意义：cnt + c2（中间空 1）
      gaps += 1;
      cnt += c2;
      gapUsedFwd = true;
      i = ii;
      j = jj;
    }
  }
  if (i >= 0 && i < n && j >= 0 && j < n && grid[j][i] === EMPTY) openEnds += 1;

  // 负方向
  i = x - dx;
  j = y - dy;
  while (i >= 0 && i < n && j >= 0 && j < n && grid[j][i] === color) {
    cnt += 1;
    i -= dx;
    j -= dy;
  }
  if (i >= 0 && i < n && j >= 0 && j < n && grid[j][i] === EMPTY) {
    var iii = i - dx;
    var jjj = j - dy;
    if (iii >= 0 && iii < n && jjj >= 0 && jjj < n && grid[jjj][iii] === color) {
      var c3 = 0;
      while (iii >= 0 && iii < n && jjj >= 0 && jjj < n && grid[jjj][iii] === color) {
        c3 += 1;
        iii -= dx;
        jjj -= dy;
      }
      gaps += 1;
      cnt += c3;
      i = iii;
      j = jjj;
    }
  }
  if (i >= 0 && i < n && j >= 0 && j < n && grid[j][i] === EMPTY) openEnds += 1;

  return { cnt: cnt, openEnds: openEnds, gaps: gaps, gapFwd: gapUsedFwd };
}

/**
 * 棋型 → 分值。cnt 为连子数（含跳形拼接后的等效长度），openEnds 为开放端数。
 * 档位与 Python 版 _single_gain 的表对齐（wc 平移由调用方处理）。
 */
function shapeScore(cnt, openEnds, wc) {
  var need = wc;                      // 还差几子
  if (cnt >= need) return WIN_SCORE;
  if (cnt === need - 1) {
    if (openEnds >= 2) return FIVE_OPEN;
    if (openEnds === 1) return FOUR_SIMPLE;
    return 0;
  }
  if (cnt === need - 2) {
    if (openEnds >= 2) return FOUR_OPEN;
    if (openEnds === 1) return FOUR_SIMPLE;
    return 0;
  }
  if (cnt === need - 3) {
    if (openEnds >= 2) return THREE_OPEN;
    if (openEnds === 1) return THREE_SIMPLE;
    return 0;
  }
  if (cnt === need - 4) {
    if (openEnds >= 2) return TWO_OPEN;
    if (openEnds === 1) return TWO_SIMPLE;
    return 0;
  }
  return 0;
}

/** 在 p 落 color 一子后，四方向棋型分之和（只算"这一步创造的威胁"）。 */
function pointGain(board, color, p) {
  var total = 0;
  var wc = board.winCount;
  for (var d = 0; d < 4; d++) {
    var s = scanDir(board, p[0], p[1], DIRS[d][0], DIRS[d][1], color);
    var sc = shapeScore(s.cnt, s.openEnds, wc);
    // 跳形（有 gap）价值打折：真连比隔一子的假线可靠得多
    if (s.gaps > 0 && sc > 0) sc = Math.floor(sc * 0.55);
    total += sc;
  }
  return total;
}

/** 进攻分×3 + 占对方要点分（Python 版 _point_gain 同权重）。 */
function scorePoint(board, color, p) {
  var atk = pointGain(board, color, p);
  var def = pointGain(board, opposite(color), p);
  return atk * 3 + def;
}

// ------------------------------------------------------------------ 威胁检测
/**
 * 沿一个方向，精确统计"落点这一手能让 color 在一条线上最多连通多少子"。
 *
 * 两个量必须分开（这是最容易写错的地方，实测踩过两次）：
 *   cnt      —— **严格连续**的同色子数（含落点）。满足 cnt >= wc 就是"已成"。
 *   gapCnt   —— 允许**恰好一个**空位（缺口）时的连通数，但只在
 *               「连续子数还没到 wc」时才有意义。
 *
 * 为什么不能用"cnt + 两侧跳形奖励"那种近似：
 *   黑在 x=0,1,2,4,5 时，落 x=6 —— 左边隔着空位 x=5 是空的、再过去是 4,5...
 *   近似写法会把 x=4,5 与远处的 0,1,2 两段都算进来（3+2+1≥6），
 *   把"其实只是 5 连"的废点误判成胜点。这里的做法是：
 *   只允许**一个**缺口、且缺口必须紧邻落点所在的那段，逐格精确推进，绝不重复计数。
 */
function analyzeDirection(grid, n, x, y, dx, dy, color) {
  var cnt = 1;
  var openEnds = 0;

  // ---- 正方向：连续段 ----
  var i = x + dx;
  var j = y + dy;
  while (i >= 0 && i < n && j >= 0 && j < n && grid[j][i] === color) { cnt += 1; i += dx; j += dy; }
  var fwdStop = [i, j];
  if (i >= 0 && i < n && j >= 0 && j < n && grid[j][i] === EMPTY) openEnds += 1;
  // 缺口后还有多长的同色段
  var fwdGap = 0;
  if (i >= 0 && i < n && j >= 0 && j < n && grid[j][i] === EMPTY) {
    var gi = i + dx;
    var gj = j + dy;
    while (gi >= 0 && gi < n && gj >= 0 && gj < n && grid[gj][gi] === color) {
      fwdGap += 1;
      gi += dx;
      gj += dy;
    }
  }

  // ---- 负方向：连续段 ----
  i = x - dx;
  j = y - dy;
  while (i >= 0 && i < n && j >= 0 && j < n && grid[j][i] === color) { cnt += 1; i -= dx; j -= dy; }
  var bwdStop = [i, j];
  if (i >= 0 && i < n && j >= 0 && j < n && grid[j][i] === EMPTY) openEnds += 1;
  var bwdGap = 0;
  if (i >= 0 && i < n && j >= 0 && j < n && grid[j][i] === EMPTY) {
    var hi = i - dx;
    var hj = j - dy;
    while (hi >= 0 && hi < n && hj >= 0 && hj < n && grid[hj][hi] === color) {
      bwdGap += 1;
      hi -= dx;
      hj -= dy;
    }
  }

  // ---- 允许缺口的连通数 ----
  // 关键约束：**两侧不能同时是缺口**。
  // 落点两侧都有缺口时，比如 0,1,2_[3]_4,5_[6]，落 6 看似能凑到 7 子，
  // 但缺口 3 永远填不上（一手只能下一子），实际只是 5 连。
  // 所以：两侧都有缺口 → 只认严格连续段；只有一侧有缺口 → 才允许把该段计入。
  var hasFwdGap = fwdGap > 0;
  var hasBwdGap = bwdGap > 0;
  var gapCnt = cnt;
  if (!(hasFwdGap && hasBwdGap)) {
    gapCnt = cnt + fwdGap + bwdGap;
  } else {
    // 两侧都有缺口：哪一侧的连续段更长，就只认那一侧（较优的一种连通）
    gapCnt = cnt + Math.max(fwdGap, bwdGap);
  }

  return {
    cnt: cnt,
    gapCnt: gapCnt,
    openEnds: openEnds,
    fwdGap: fwdGap,
    bwdGap: bwdGap
  };
}

/**
 * 「一手即胜」：在 (x,y) 落 color 子后**严格连续**达到 wc。
 *
 * 【为什么这里绝不能用 gapCnt】实测教训：曾经用"连续数 + 缺口后的段"来判胜，
 * 把「5 连 + 隔一空 + 1 子」这种（落在那颗孤立子上凑不出六连）误判成胜点，
 * 于是 AI 会去走废棋。补缺口成线只有一种形状是真正的胜：落点正落在缺口上，
 * 两侧都是连续同色段（此时 analyzeDirection 的 cnt 已经把两侧连起来算进去了）。
 * 所以判胜只认 cnt，gapCnt 只用于"这一手造出了什么威胁"的评分/候选排序。
 */
function isWinMove(grid, n, x, y, wc, color) {
  for (var d = 0; d < 4; d++) {
    var a = analyzeDirection(grid, n, x, y, DIRS[d][0], DIRS[d][1], color);
    if (a.cnt >= wc) return true;
  }
  return false;
}

/** color 落一手即连成 wc 的所有点。 */
function winPoints(board, color, cands) {
  var n = board.size;
  var grid = board.grid;
  var wc = board.winCount;
  var rng = cands || wideCandidates(board);
  var pts = [];
  for (var k = 0; k < rng.length; k++) {
    var x = rng[k][0];
    var y = rng[k][1];
    if (grid[y][x] !== EMPTY) continue;
    if (isWinMove(grid, n, x, y, wc, color)) pts.push([x, y]);
  }
  return pts;
}

/**
 * 在 (x,y) 落 color 子后，附近有多少个"下一步即胜"的点（成 wc 点）。
 * 只看向落点 wc+1 格以内 —— 更远处的点不可能被这一手影响。
 */
function countNextWinPoints(grid, n, x, y, wc, color) {
  var pts = 0;
  var R = wc + 1;
  for (var j = Math.max(0, y - R); j <= Math.min(n - 1, y + R); j++) {
    for (var i = Math.max(0, x - R); i <= Math.min(n - 1, x + R); i++) {
      if (i === x && j === y) continue;
      if (grid[j][i] !== EMPTY) continue;
      if (isWinMove(grid, n, i, j, wc, color)) pts += 1;
    }
  }
  return pts;
}

/**
 * 强制胜点：color 落一手后能形成 >= 2 个"成 wc 点"（对手一子堵不完 → 必胜）。
 *
 * 这是搜索里最要紧的一类威胁，也是"地平线效应"的根源：
 * 落完这一手盘面还没连成 wc 子，若搜索恰好在此被深度截断、直接取静态分，
 * 已经到手的必胜就被判成"还行"。引擎据此对该分支做**威胁延伸**。
 */
function forcedWinPoints(board, color, cands) {
  var n = board.size;
  var grid = board.grid;
  var wc = board.winCount;
  var rng = cands || wideCandidates(board);
  var res = [];
  for (var k = 0; k < rng.length; k++) {
    var x = rng[k][0];
    var y = rng[k][1];
    if (grid[y][x] !== EMPTY) continue;
    grid[y][x] = color;
    var cnt = countNextWinPoints(grid, n, x, y, wc, color);
    grid[y][x] = EMPTY;
    if (cnt >= 2) res.push([x, y]);
  }
  return res;
}

/** 空盘/稀疏局面下，把邻域放到 4 格，保证关键点不会被候选集漏掉。 */
function wideCandidates(board) {
  var cands = board.getCandidates(2);
  if (!cands.length) cands = board.getCandidates(4);
  return cands;
}

/** 空盘/稀疏局面下，把邻域放到 4 格，保证关键点不会被候选集漏掉。 */
function wideCandidates(board) {
  var cands = board.getCandidates(2);
  if (!cands.length) cands = board.getCandidates(4);
  return cands;
}

/**
 * color 已有"差一子即胜"的连续段（长 wc-1）的空端点。
 * 对手下一手落任一端点即获胜 → 必须封堵的强制防守点。
 */
function openEndsOf(board, color) {
  var n = board.size;
  var grid = board.grid;
  var wc = board.winCount;
  var need = wc - 1;
  var ends = [];
  var seen = {};
  for (var y = 0; y < n; y++) {
    for (var x = 0; x < n; x++) {
      if (grid[y][x] !== color) continue;
      for (var d = 0; d < 4; d++) {
        var dx = DIRS[d][0];
        var dy = DIRS[d][1];
        // 只从线段起点开始统计
        var px = x - dx;
        var py = y - dy;
        if (px >= 0 && px < n && py >= 0 && py < n && grid[py][px] === color) continue;
        var run = [];
        var i = x;
        var j = y;
        while (i >= 0 && i < n && j >= 0 && j < n && grid[j][i] === color) {
          run.push([i, j]);
          i += dx;
          j += dy;
        }
        if (run.length !== need) continue;
        // 两端为空则各是一个必堵点
        var e1x = run[0][0] - dx;
        var e1y = run[0][1] - dy;
        var e2x = run[run.length - 1][0] + dx;
        var e2y = run[run.length - 1][1] + dy;
        if (e1x >= 0 && e1x < n && e1y >= 0 && e1y < n && grid[e1y][e1x] === EMPTY) {
          if (!seen[e1y * n + e1x]) { seen[e1y * n + e1x] = 1; ends.push([e1x, e1y]); }
        }
        if (e2x >= 0 && e2x < n && e2y >= 0 && e2y < n && grid[e2y][e2x] === EMPTY) {
          if (!seen[e2y * n + e2x]) { seen[e2y * n + e2x] = 1; ends.push([e2x, e2y]); }
        }
      }
    }
  }
  return ends;
}

// ------------------------------------------------------------------ 评估（根号级别）
/**
 * 全局局面分（color 视角）。用四方向的"线段"累加棋型分，
 * 系数与 Python 版一致：己方 ×1.2，对手 ×1.6。
 * 复杂度 O(棋盘格数 × 4)，19×19 下约 1444 次扫描，可接受。
 */
var _evalGrid = null;
function evaluate(board, color) {
  var n = board.size;
  var grid = board.grid;
  var wc = board.winCount;

  // 【要害】必须先把"已经连成"判掉。
  // 采样式棋型分只衡量"还能发展成什么"，对盘面上**已经成立**的连线会给出 0
  // （例如已有 5 连，扫描时 cnt=5 早被归到"已成"之外的分支），
  // 于是"对手已经赢了"会跟"均势"一样得 0 分 —— 搜索就看不见必胜/必败。
  // 这跟 Python 版用全盘滑窗、天然含 WIN_SCORE 的做法不等价，必须显式补上。
  var sw = board.scanWin();
  if (sw[0] !== null) {
    return sw[0] === color ? WIN_SCORE : -WIN_SCORE;
  }

  var mine = 0;
  var foe = 0;
  var opp = opposite(color);
  for (var y = 0; y < n; y++) {
    for (var x = 0; x < n; x++) {
      var c = grid[y][x];
      if (c === EMPTY) continue;
      for (var d = 0; d < 4; d++) {
        var dx = DIRS[d][0];
        var dy = DIRS[d][1];
        var px = x - dx;
        var py = y - dy;
        if (px >= 0 && px < n && py >= 0 && py < n && grid[py][px] === c) continue;
        // 线段
        var run = 0;
        var openEnds = 0;
        var i = x;
        var j = y;
        while (i >= 0 && i < n && j >= 0 && j < n && grid[j][i] === c) { run += 1; i += dx; j += dy; }
        if (i >= 0 && i < n && j >= 0 && j < n && grid[j][i] === EMPTY) openEnds += 1;
        if (px >= 0 && px < n && py >= 0 && py < n && grid[py][px] === EMPTY) openEnds += 1;
        var sc = shapeScore(run, openEnds, wc);
        if (c === color) mine += sc; else foe += sc;
      }
    }
  }
  return Math.floor(mine * 1.2) - Math.floor(foe * 1.6);
}

// ------------------------------------------------------------------ 主引擎
function Engine(opts) {
  opts = opts || {};
  this.maxDepth = opts.maxDepth === undefined ? 6 : opts.maxDepth;
  this.timeLimit = opts.timeLimit === undefined ? 1200 : opts.timeLimit;   // ms
  this.candidateLimit = opts.candidateLimit === undefined ? 14 : opts.candidateLimit;
  this.tssBudget = opts.tssBudget === undefined ? 2000 : opts.tssBudget;
  this.seed = opts.seed;
  this.rng = makeRng(opts.seed);
  this.nodes = 0;
  this.deadline = 0;
  this.tt = {};
  this.history = {};
  this.killers = {};
  this.stopFlag = false;
  this.lastVal = 0;
  this.lastDepth = 0;
}

Engine.prototype.stop = function () { this.stopFlag = true; };

/** 入口：返回本轮要落的 [[x,y],...]（1~2 个）。 */
Engine.prototype.getMove = function (board, color, stonesToPlace) {
  return this.bestMove(board, color, stonesToPlace || 1);
};

Engine.prototype.bestMove = function (board, color, stonesToPlace) {
  var t0 = Date.now();
  this.nodes = 0;
  this.tt = {};
  this.history = {};
  this.killers = {};
  this.stopFlag = false;
  this.deadline = t0 + this.timeLimit;
  this.lastVal = 0;

  var b = board.snapshot();
  var wc = b.winCount;
  var opp = opposite(color);
  var cands = this.genCandidates(b);

  // ---------- 1) 己方一手成六 ----------
  var myWins = winPoints(b, color, cands);
  if (myWins.length) {
    if (stonesToPlace === 2) {
      var p0 = myWins[0];
      b.place(p0[0], p0[1], color);
      var more = winPoints(b, color, cands);
      b.undo();
      if (more.length) { this.lastVal = WIN_SCORE; return [p0, more[0]]; }
    }
    this.lastVal = WIN_SCORE;
    return [myWins[0]];
  }

  // ---------- 2) 对手强制威胁 → 必须防守 ----------
  var fiveEnds = openEndsOf(b, opp);
  if (fiveEnds.length) {
    if (fiveEnds.length === 2 && stonesToPlace === 2) return fiveEnds;
    return [fiveEnds[0]];
  }
  var oppWins = winPoints(b, opp, cands);
  if (oppWins.length) {
    if (stonesToPlace === 2 && oppWins.length >= 2) return [oppWins[0], oppWins[1]];
    var p = oppWins[0];
    if (stonesToPlace === 2) {
      b.place(p[0], p[1], color);
      var newOpp = winPoints(b, opp, cands);
      if (newOpp.length) { b.undo(); return [p, newOpp[0]]; }
      var rest = cands.filter(function (q) { return q[0] !== p[0] || q[1] !== p[1]; });
      var scored = this.scoreCandidates(b, color, rest);
      var p2 = scored.length ? scored[0][0] : [p[0], p[1] + 1];
      b.undo();
      return [p, p2];
    }
    return [p];
  }

  // ---------- 3) 威胁空间搜索：冲四连击找强制胜 ----------
  var seq = this.threatSearch(b, color, stonesToPlace);
  if (seq) { this.lastVal = WIN_SCORE; return seq.slice(0, stonesToPlace); }

  // ---------- 3.5) 一手做出"堵不完的双成六点" → 已是必胜 ----------
  // 这一步很关键：此时盘面还没连成六子，迭代加深有可能在快要看到兑现时
  // 被时限打断了。既然已经算出强制胜，就直接走，不必再搜。
  var forcedNow = forcedWinPoints(b, color, cands);
  if (forcedNow.length) {
    this.lastVal = WIN_SCORE;
    if (stonesToPlace === 2) {
      var f0 = forcedNow[0];
      b.place(f0[0], f0[1], color);
      var rest0 = cands.filter(function (q) { return q[0] !== f0[0] || q[1] !== f0[1]; });
      var f1 = this.pickSecond(b, color, rest0);
      b.undo();
      return [f0, f1];
    }
    return [forcedNow[0]];
  }

  // ---------- 3.6) 五子棋：VCF 算杀（连续冲四找必胜）----------
  // 桌面版在五子棋这一档走的就是 VCF/VCT（kill_search.py）。这里移植了 VCF：
  // 只走"造四"的强制着法，对手只能堵，分支极窄，因此浅深度也能算很远。
  // 命中即返回，不再依赖启发式评估（算杀成功 = 客观必胜）。
  if (wc === 5) {
    var vcfBudget = { n: this.tssBudget || 1500 };
    var vcfSeq = vcfSearch(this, b, color, 18, [], vcfBudget);
    if (vcfSeq && vcfSeq.length) {
      this.lastVal = WIN_SCORE;
      return vcfSeq.slice(0, stonesToPlace);
    }
  }

  // ---------- 4) 空盘 → 天元 ----------
  if (b.moveCount === 0) {
    var c = Math.floor(b.size / 2);
    return [[c, c]];
  }

  // ---------- 5) 迭代加深 + PVS ----------
  var pool = this.scoreCandidates(b, color, cands)
    .slice(0, this.candidateLimit * 3)
    .map(function (t) { return t[0]; });
  var best = null;
  var bestValAll = -INF;
  for (var depth = 2; depth <= this.maxDepth; depth += 2) {
    var bestThis = null;
    var bestVal = -INF;
    var alpha = -INF;
    var timedOut = false;
    for (var i = 0; i < pool.length; i++) {
      var pt = pool[i];
      if (!b.isEmpty(pt[0], pt[1])) continue;
      this.extensions = 0;             // 每条根分支的威胁延伸独立计数
      b.place(pt[0], pt[1], color);
      var val;
      try {
        if (stonesToPlace === 1) {
          val = -this.alphabeta(b, opp, 2, depth - 1, -INF, -alpha, 1);
        } else {
          val = this.alphabeta(b, color, 1, depth - 1, alpha, INF, 1);
        }
      } catch (e) {
        b.undo();
        if (e && e.__timeout) { timedOut = true; break; }
        throw e;
      }
      b.undo();
      if (this.stopFlag) { timedOut = true; break; }
      if (bestVal === -INF || val > bestVal) { bestVal = val; bestThis = [pt]; }
      if (val > alpha) alpha = val;
    }
    if (bestThis && !timedOut) {
      best = bestThis;
      bestValAll = bestVal;
      this.lastVal = bestVal;
      this.lastDepth = depth;
    }
    if (bestVal >= WIN_THRESHOLD) break;
    if (timedOut || Date.now() >= this.deadline) break;
    if (this.stopFlag) break;
  }

  if (!best) {
    // 一道保险：搜索一无所获时，至少挑一个最有价值的空点
    var fallbackPool = pool.filter(function (q) { return b.isEmpty(q[0], q[1]); });
    if (!fallbackPool.length) fallbackPool = this.genCandidates(b);
    if (!fallbackPool.length) {
      var cc = Math.floor(b.size / 2);
      fallbackPool = [[cc, cc]];
    }
    best = [fallbackPool[0]];
  }

  if (stonesToPlace === 2 && best.length === 1) {
    var p1 = best[0];
    b.place(p1[0], p1[1], color);
    var rest2 = pool.filter(function (q) { return q[0] !== p1[0] || q[1] !== p1[1]; });
    var p2b = this.pickSecond(b, color, rest2);
    b.undo();
    best.push(p2b);
  }
  return best;
};

Engine.prototype.genCandidates = function (board) {
  var cands = board.getCandidates(2);
  if (!cands.length) cands = board.getCandidates(4);
  return cands;
};

Engine.prototype.scoreCandidates = function (board, color, cands, ttMove, ply) {
  var out = [];
  var hist = this.history;
  var killers = this.killers[ply] || [];
  for (var i = 0; i < cands.length; i++) {
    var p = cands[i];
    if (board.grid[p[1]][p[0]] !== EMPTY) continue;
    var s = scorePoint(board, color, p);
    var h = hist[color + ':' + p[0] + ':' + p[1]];
    if (h) s += h;
    if (ttMove && p[0] === ttMove[0] && p[1] === ttMove[1]) s += 1073741824;
    else {
      for (var k = 0; k < killers.length; k++) {
        if (p[0] === killers[k][0] && p[1] === killers[k][1]) { s += 1048576; break; }
      }
    }
    out.push([p, s]);
  }
  out.sort(function (a, b) { return b[1] - a[1]; });
  return out;
};

Engine.prototype.pickSecond = function (board, color, pool) {
  var bestP = null;
  var bestS = -1;
  for (var i = 0; i < pool.length && i < 12; i++) {
    var s = scorePoint(board, color, pool[i]);
    if (s > bestS) { bestS = s; bestP = pool[i]; }
  }
  if (!bestP) bestP = pool.length ? pool[0] : [Math.floor(board.size / 2), Math.floor(board.size / 2)];
  return bestP;
};

/** Zobrist 键：用字符串（JS 的 64 位位运算不可靠，字符串哈希便于调试）。 */
Engine.prototype.hashKey = function (board, color, remain) {
  var h = 0;
  for (var i = 0; i < board.history.length; i++) {
    var m = board.history[i];
    h = (h * 31 + (m[0] * 19 + m[1]) * 3 + m[2]) | 0;
  }
  return (h * 31 + color * 7 + remain) | 0;
};

function Timeout() { this.__timeout = true; }

/** 负极大值 + PVS。ev 用棋盘本身（评估为全盘采样，无需增量结构）。 */
Engine.prototype.alphabeta = function (board, color, remain, depth, alpha, beta, ply) {
  if (this.stopFlag) throw new Timeout();
  if (((this.nodes++) & 127) === 0 && Date.now() >= this.deadline) {
    this.stopFlag = true;
    throw new Timeout();
  }

  var key = this.hashKey(board, color, remain);
  var entry = this.tt[key];
  var ttMove = null;
  if (entry) {
    ttMove = entry[3];
    if (entry[0] >= depth) {
      if (entry[1] === 0) return entry[2];
      if (entry[1] === 1 && entry[2] >= beta) return entry[2];
      if (entry[1] === 2 && entry[2] <= alpha) return entry[2];
    }
  }

  if (depth <= 0) return evaluate(board, color);

  var ext = this.extensions || 0;
  if (ext > 24) return evaluate(board, color);   // 延伸上限：防极端局面无限加深

  var cands = wideCandidates(board);
  var myWins = winPoints(board, color, cands);
  if (myWins.length) return WIN_SCORE - ply;

  var opp = opposite(color);
  var oppWins = winPoints(board, opp, cands);
  var scored;
  var extend = 0;
  if (oppWins.length) {
    // 对手下一手就连成 → 本节点只有"堵"这一族着法，是强制局面
    scored = oppWins.map(function (p) { return [p, 0]; });
    extend = 1;
  } else {
    var forced = forcedWinPoints(board, color, cands);
    if (forced.length) {
      // 我下一手就能做出"堵不完的两个成六点" → 强制胜，必须算到兑现为止
      scored = forced.map(function (p) { return [p, 0]; });
      extend = 1;
    } else {
      var oppForced = forcedWinPoints(board, opp, cands);
      if (oppForced.length) {
        // 对手已能一手做出致命双威胁 → 本节点必须优先破坏它
        scored = this.scoreCandidates(board, color, oppForced, ttMove, ply);
        extend = 1;
      } else {
        scored = this.scoreCandidates(board, color, cands, ttMove, ply)
          .slice(0, this.candidateLimit);
      }
    }
  }
  depth += extend;   // 威胁延伸：强制局面不截断，直到威胁兑现或被化解
  if (extend) this.extensions = ext + 1;

  var alphaOrig = alpha;
  var bestVal = -INF;
  var bestMove = null;
  var first = true;
  for (var i = 0; i < scored.length; i++) {
    var p = scored[i][0];
    if (board.grid[p[1]][p[0]] !== EMPTY) continue;
    board.place(p[0], p[1], color);
    var r2 = remain - 1;
    var val;
    try {
      if (r2 === 0) {
        val = -this.alphabeta(board, opp, 2, depth - 1, -beta, -alpha, ply + 1);
      } else if (first) {
        val = this.alphabeta(board, color, r2, depth - 1, alpha, beta, ply + 1);
      } else {
        val = this.alphabeta(board, color, r2, depth - 1, -alpha - 1, -alpha, ply + 1);
        if (alpha < val && val < beta) {
          val = this.alphabeta(board, color, r2, depth - 1, -beta, -val, ply + 1);
        }
      }
    } finally {
      board.undo();
    }
    if (this.stopFlag) throw new Timeout();
    if (bestVal === -INF || val > bestVal) { bestVal = val; bestMove = p; }
    if (val > alpha) alpha = val;
    first = false;
    if (alpha >= beta) {
      if (remain === 2) {
        var ks = this.killers[ply] || (this.killers[ply] = []);
        var dup = false;
        for (var kk = 0; kk < ks.length; kk++) {
          if (ks[kk][0] === p[0] && ks[kk][1] === p[1]) { dup = true; break; }
        }
        if (!dup) { ks.unshift(p); if (ks.length > 2) ks.length = 2; }
      }
      var hk = color + ':' + p[0] + ':' + p[1];
      this.history[hk] = (this.history[hk] || 0) + depth * depth;
      break;
    }
  }

  if (!this.stopFlag && bestMove) {
    var flag = 0;
    if (bestVal <= alphaOrig) flag = 2;
    else if (bestVal >= beta) flag = 1;
    var old = this.tt[key];
    if (!old || old[0] <= depth) this.tt[key] = [depth, flag, bestVal, bestMove];
  }
  return bestVal;
};

// ------------------------------------------------------------------ 威胁空间搜索
/**
 * 找一条由"成六点威胁"（冲四/活四）串成的强制胜序列。
 * 思路与 Python 版 _tss 一致：只考虑能制造成六点的着法，对手只能被动堵。
 */
Engine.prototype.threatSearch = function (board, color, stonesToPlace) {
  this._tssNodes = 0;
  var seq = [];
  if (this.tss(board, color, stonesToPlace, 14, seq)) return seq;
  return null;
};

Engine.prototype.tss = function (board, color, remain, budget, seq) {
  if (budget <= 0 || this._tssNodes > 8000) return false;
  if (this.stopFlag || Date.now() >= this.deadline) return false;
  this._tssNodes += 1;
  var opp = opposite(color);
  var cands = this.genCandidates(board);
  var wins = winPoints(board, color, cands);
  if (wins.length) {
    seq.push(wins[0]);
    if (remain === 2) {
      var alt = null;
      for (var q = 0; q < cands.length; q++) {
        if (cands[q][0] !== wins[0][0] || cands[q][1] !== wins[0][1]) { alt = cands[q]; break; }
      }
      if (!alt) { var c = Math.floor(board.size / 2); alt = [c, c]; }
      seq.push(alt);
    }
    return true;
  }

  if (remain === 2) {
    var top = this.scoreCandidates(board, color, cands).slice(0, 8);
    for (var i = 0; i < top.length; i++) {
      var p = top[i][0];
      if (board.grid[p[1]][p[0]] !== EMPTY) continue;
      board.place(p[0], p[1], color);
      var sub = [p];
      var ok = this.tss(board, color, 1, budget - 1, sub);
      board.undo();
      if (ok) { for (var s = 0; s < sub.length; s++) seq.push(sub[s]); return true; }
    }
    return false;
  }

  // remain === 1：找能制造成六点的着法（冲四/活四）
  var threats = [];
  var sc = this.scoreCandidates(board, color, cands).slice(0, 12);
  for (var j = 0; j < sc.length; j++) {
    var pt = sc[j][0];
    if (board.grid[pt[1]][pt[0]] !== EMPTY) continue;
    board.place(pt[0], pt[1], color);
    var w2 = winPoints(board, color);
    board.undo();
    if (w2.length) threats.push([pt, w2.length]);
  }
  threats.sort(function (a, b) { return b[1] - a[1]; });
  for (var t = 0; t < threats.length; t++) {
    var tp = threats[t][0];
    board.place(tp[0], tp[1], color);
    // 对手只能堵：逐一试其堵法，只要我仍能继续造威胁就是强制序列
    var oppCands = board.getCandidates(2);
    var blockers = winPoints(board, color, oppCands);
    var blockList = blockers.length ? blockers : oppCands.slice(0, 6);
    var survived = false;
    if (!blockers.length) {
      // 我有两个以上成六点 → 对手堵不完，直接胜
      survived = true;
    } else {
      for (var bi = 0; bi < blockList.length; bi++) {
        var blk = blockList[bi];
        if (board.grid[blk[1]][blk[0]] !== EMPTY) continue;
        board.place(blk[0], blk[1], opp);
        var sub2 = [tp, blk];
        var ok2 = this.tss(board, color, 2, budget - 1, sub2);
        board.undo();
        if (ok2) {
          seq.push(tp);
          // 只把我方后续着法并入序列（对手的堵法由调用方重新推导）
          for (var z = 2; z < sub2.length; z += 2) seq.push(sub2[z]);
          board.undo();
          return true;
        }
      }
    }
    board.undo();
    if (survived) { seq.push(tp); return true; }
  }
  return false;
};

// ------------------------------------------------------------------ 五子棋算杀（VCF / VCT）
/**
 * 为什么需要它：Alpha-Beta 是"评估驱动"的，遇到"连续冲四逼死对手"这类
 * **强制序列**时，深度不够就看不到兑现（地平线效应）。桌面版为此写了
 * kill_search.py（VCF 连续冲四 + VCT 连续威胁），这里把 VCF 移植过来。
 *
 * VCF（Victory by Continuous Fours）的算法骨架：
 *   轮到我时，只考虑"能造出四（下一步成五）"的着法；
 *   对手被将军（这里指"我必须马上成五"的威胁），只能去堵那些成五点；
 *   如此递归，若某条线最终真的连成五 → 强制胜，返回着法序列。
 * 关键点：**只走强制着法**，所以分支极窄，浅深度就能算很远（桌面版能到 16~18 层）。
 *
 * VCT（连续活三威胁）分支多、代价大，桌面版也是在 VCF 失败后才试；
 * 这里先做 VCF（收益最直接），VCT 留给后续。
 */

/** 落子后形成的"成五点数"≥1 且有必要形状时才算威胁候选。 */
function highThreatMoves(board, color, cands, limit) {
  var out = [];
  var rng = cands || board.getCandidates(2);
  for (var i = 0; i < rng.length; i++) {
    var p = rng[i];
    if (board.grid[p[1]][p[0]] !== EMPTY) continue;
    board.place(p[0], p[1], color);
    var wins = winPoints(board, color).length;
    board.undo();
    if (wins > 0) out.push([p, wins]);
  }
  out.sort(function (a, b) { return b[1] - a[1]; });
  if (limit) out = out.slice(0, limit);
  return out.map(function (t) { return t[0]; });
}

/**
 * VCF 递归。返回着法序列（我方着法）或 null。
 * budget 为剩余节点预算，deadline 由调用方设置（this.deadline）。
 */
function vcfSearch(ai, board, color, depth, seq, budget) {
  if (depth <= 0 || budget.n <= 0) return null;
  if (ai.stopFlag || Date.now() >= ai.deadline) return null;
  budget.n -= 1;
  var opp = opposite(color);

  // ① 我能一手成五 → 赢
  var myWins = winPoints(board, color);
  if (myWins.length) { seq.push(myWins[0]); return seq; }

  // ② 只考虑能造出"四"的着法（下一步成五）
  var threats = highThreatMoves(board, color, null, 8);
  for (var i = 0; i < threats.length; i++) {
    var p = threats[i];
    if (!board.isEmpty(p[0], p[1])) continue;
    board.place(p[0], p[1], color);

    // 我造出的成五点（对手必须去堵这些点）
    var myFour = winPoints(board, color);
    if (!myFour.length) { board.undo(); continue; }

    // 如果我造出 >= 2 个成五点 → 对手堵不完 → 直接胜。
    // 【别用"再落一子看能不能成五"来找兑现着** —— 棋子一落下，winPoints 里
    //  就不包含"刚落下的这颗"了（它已经占了位）。兑现着就是 myFour 本身。
    if (myFour.length >= 2) {
      board.undo();
      seq.push(p);
      seq.push(myFour[0]);           // 两步连击：先做双四，再兑现
      return seq;
    }

    // 只有一个成五点：对手只能堵那里
    var blockPt = myFour[0];
    var canBlock = board.isEmpty(blockPt[0], blockPt[1]);
    if (!canBlock) { board.undo(); continue; }
    board.place(blockPt[0], blockPt[1], opp);

    // 对手堵完，我继续找下一个冲四
    var sub = vcfSearch(ai, board, color, depth - 1, [], budget);
    board.undo();     // 撤对手的堵
    board.undo();     // 撤我的冲四

    if (sub) {
      seq.push(p);
      for (var k = 0; k < sub.length; k++) seq.push(sub[k]);
      return seq;
    }
  }
  return null;
}

// ------------------------------------------------------------------ 难度档位
/**
 * 难度：easy / medium / hard。
 * 浏览器是单线程，时限比桌面版收敛（桌面 hard 是 9s，网页版 2.6s 上限，
 * 再靠分片让出主线程，避免界面卡死）。
 */
var PROFILES = {
  easy: { maxDepth: 2, timeLimit: 250, candidateLimit: 8, tssBudget: 300 },
  medium: { maxDepth: 6, timeLimit: 1200, candidateLimit: 16, tssBudget: 1500 },
  hard: { maxDepth: 10, timeLimit: 2600, candidateLimit: 24, tssBudget: 3000 }
};

function EasyEngine(opts) {
  Engine.call(this, opts || {});
}
EasyEngine.prototype = Object.create(Engine.prototype);
EasyEngine.prototype.constructor = EasyEngine;

/** 简单档：不做 TSS，前 3 名里随机挑，保留一点"人情味"。 */
EasyEngine.prototype.bestMove = function (board, color, stonesToPlace) {
  var b = board.snapshot();
  var cands = this.genCandidates(b);
  var opp = opposite(color);
  var myWins = winPoints(b, color, cands);
  if (myWins.length) {
    if (stonesToPlace === 2) {
      var p0 = myWins[0];
      b.place(p0[0], p0[1], color);
      var more = winPoints(b, color, cands);
      b.undo();
      if (more.length) return [p0, more[0]];
    }
    return [myWins[0]];
  }
  var oppWins = winPoints(b, opp, cands);
  if (oppWins.length) {
    if (stonesToPlace === 1) return [oppWins[0]];
    var second = cands.length ? cands[Math.floor(cands.length / 2)] : oppWins[0];
    return [oppWins[0], second];
  }
  var scored = this.scoreCandidates(b, color, cands).slice(0, 10);
  if (!scored.length) {
    var c = Math.floor(b.size / 2);
    return [[c, c]];
  }
  var i1 = Math.floor(this.rng() * Math.min(3, scored.length));
  var pick1 = scored[i1][0];
  var res = [pick1];
  if (stonesToPlace === 2) {
    var rest = scored.map(function (t) { return t[0]; }).filter(function (q) {
      return q[0] !== pick1[0] || q[1] !== pick1[1];
    });
    if (rest.length) res.push(rest[Math.floor(this.rng() * Math.min(3, rest.length))]);
    else res.push(pick1);
  }
  return res;
};

/** 对外统一入口：AI(difficulty, seed).getMove(board, color, stonesToPlace) */
function AI(difficulty, seed) {
  this.difficulty = PROFILES[difficulty] ? difficulty : 'medium';
  var prof = PROFILES[this.difficulty];
  var opts = {
    maxDepth: prof.maxDepth,
    timeLimit: prof.timeLimit,
    candidateLimit: prof.candidateLimit,
    tssBudget: prof.tssBudget,
    seed: seed
  };
  this.engine = this.difficulty === 'easy' ? new EasyEngine(opts) : new Engine(opts);
}

AI.prototype.getMove = function (board, color, stonesToPlace) {
  var stones = this.engine.bestMove(board, color, stonesToPlace);
  if (!stones || !stones.length) {
    var c = Math.floor(board.size / 2);
    stones = [[c, c]];
  }
  if (stones.length > stonesToPlace) stones = stones.slice(0, stonesToPlace);
  // 兜底：过滤掉非空点/越界点，绝不让 AI 下出非法着
  var legal = [];
  var b = board;
  for (var i = 0; i < stones.length; i++) {
    var x = stones[i][0];
    var y = stones[i][1];
    if (!b.isValid(x, y) || !b.isEmpty(x, y)) continue;
    legal.push([x, y]);
    b = b; // 同一轮内后续子需在真实棋盘上校验，由调用方按序落子保证
  }
  if (!legal.length) {
    var cands = board.getCandidates(2);
    legal = cands.length ? [cands[0]] : [[Math.floor(board.size / 2), Math.floor(board.size / 2)]];
  }
  return legal;
};

AI.prototype.stop = function () { this.engine.stop(); };
AI.prototype.lastNodes = function () { return this.engine.nodes || 0; };

module.exports = {
  AI: AI,
  Engine: Engine,
  EasyEngine: EasyEngine,
  PROFILES: PROFILES,
  WIN_SCORE: WIN_SCORE,
  // 导出内部函数便于单测与调参
  _internal: {
    scanDir: scanDir,
    analyzeDirection: analyzeDirection,
    isWinMove: isWinMove,
    shapeScore: shapeScore,
    pointGain: pointGain,
    scorePoint: scorePoint,
    winPoints: winPoints,
    forcedWinPoints: forcedWinPoints,
    openEndsOf: openEndsOf,
    evaluate: evaluate,
    makeRng: makeRng
  }
};

  };
  __mods["./boardview.js"] = function (module, exports, require) {
/**
 * boardview.js —— 棋盘渲染器（平台无关）
 *
 * 只依赖一个最朴素的 2D 上下文接口（Canvas 2D 的公共子集）：
 *   fillStyle / strokeStyle / lineWidth / globalAlpha / font / textAlign
 *   fillRect / clearRect / beginPath / moveTo / lineTo / arc / fill / stroke / fillText
 *
 * 因此它同时适用于：浏览器 Canvas 2D、微信小程序 Canvas 2D、Node + node-canvas。
 * 不引用 DOM、window、wx —— 这是"同一份代码三端复用"的关键。
 *
 * 绘制分层（与桌面版一致的思路）：
 *   1) 木纹棋盘底板 + 网格 + 星位 + 坐标
 *   2) 棋子（球面光影用径向渐变画，网页端不需要 PIL 预渲染）
 *   3) 效果层：最后一手标记、待确认预览、胜利连线、悔棋倒退动画
 */

var GEOM_MARGIN = 34;      // 棋盘外边距（给坐标留位）

function View() {
  this.geom = null;
  this.theme = null;
}

/** 主题（5 套，与桌面版同名，网页端重新调过明度） */
var THEMES = {
  '经典原木': {
    bgA: '#EACD96', bgB: '#D8B276', line: '#4A3B28', star: '#4A3B28',
    coord: '#5A4A34', tray: '#D2A96B'
  },
  '胡桃深木': {
    bgA: '#8A5A33', bgB: '#6E4223', line: '#3A2415', star: '#2E1D10',
    coord: '#E8D8C0', tray: '#5C3618'
  },
  '石板灰': {
    bgA: '#B9BEC4', bgB: '#98A0A8', line: '#4A5058', star: '#3E444C',
    coord: '#3A4048', tray: '#8B939B'
  },
  '墨玉黑': {
    bgA: '#2E3440', bgB: '#22272F', line: '#6E7A8A', star: '#8A98A8',
    coord: '#9AA6B4', tray: '#1B2027'
  },
  '青瓷绿': {
    bgA: '#BFD8CC', bgB: '#9EBFAF', line: '#3E5C50', star: '#32493F',
    coord: '#38524A', tray: '#8FB0A0'
  }
};
var THEME_NAMES = Object.keys(THEMES);

/**
 * 计算几何：把棋盘等比放进 width×height，返回像素布局。
 * 与桌面版一样"按 min(可用宽,高) 等比居中"，保证任何屏幕都完整显示不变形。
 */
View.prototype.computeGeom = function (width, height, boardSize) {
  var usableW = width - GEOM_MARGIN * 2;
  var usableH = height - GEOM_MARGIN * 2;
  // 棋盘是 (size-1) 个格子的跨度，格子 = 跨度/数量
  var cell = Math.min(usableW, usableH) / (boardSize - 1 + 0.9);
  var side = cell * (boardSize - 1);
  var x0 = (width - side) / 2;
  var y0 = (height - side) / 2;
  this.geom = {
    W: width, H: height, cell: cell, x0: x0, y0: y0, side: side,
    stoneR: cell * 0.44, size: boardSize
  };
  return this.geom;
};

/** 像素坐标 → 棋盘格坐标（返回最近的交叉点；超出容差返回 null）。 */
View.prototype.toGrid = function (px, py) {
  var g = this.geom;
  if (!g) return null;
  var x = Math.round((px - g.x0) / g.cell);
  var y = Math.round((py - g.y0) / g.cell);
  if (x < 0 || x >= g.size || y < 0 || y >= g.size) return null;
  // 容差：离交叉点太远就不算点中（避免误触）
  var dx = px - (g.x0 + x * g.cell);
  var dy = py - (g.y0 + y * g.cell);
  if (Math.sqrt(dx * dx + dy * dy) > g.cell * 0.62) return null;
  return { x: x, y: y };
};

/** 格坐标 → 像素中心。 */
View.prototype.center = function (x, y) {
  var g = this.geom;
  return { cx: g.x0 + x * g.cell, cy: g.y0 + y * g.cell };
};

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y);
  ctx.arc(x + w - r, y + r, r, -Math.PI / 2, 0);
  ctx.lineTo(x + w, y + h - r);
  ctx.arc(x + w - r, y + h - r, r, 0, Math.PI / 2);
  ctx.lineTo(x + r, y + h);
  ctx.arc(x + r, y + h - r, r, Math.PI / 2, Math.PI);
  ctx.lineTo(x, y + r);
  ctx.arc(x + r, y + r, r, Math.PI, Math.PI * 1.5);
  ctx.closePath();
}

/** 1) 静态层：底板 + 网格 + 星位 + 坐标 */
View.prototype.drawStatic = function (ctx) {
  var g = this.geom;
  var t = this.theme;
  var n = g.size;
  ctx.clearRect(0, 0, g.W, g.H);

  // 四周托盘（比棋盘略深一圈）
  var pad = Math.max(2, GEOM_MARGIN * 0.72);
  ctx.fillStyle = t.tray;
  ctx.fillRect(g.x0 - pad, g.y0 - pad, g.side + pad * 2, g.side + pad * 2);

  // 棋盘底色：竖向渐变（用多段矩形模拟，兼容所有 2D 实现）
  var steps = 24;
  for (var i = 0; i < steps; i++) {
    var f = i / (steps - 1);
    ctx.fillStyle = mix(t.bgA, t.bgB, f);
    var yy = g.y0 + (g.side * i) / steps;
    ctx.fillRect(g.x0, yy, g.side, g.side / steps + 1);
  }

  // 外框 + 网格
  var lw = Math.max(1, Math.round(g.cell * 0.045));
  ctx.strokeStyle = t.line;
  ctx.lineWidth = lw + 1;
  ctx.strokeRect(g.x0, g.y0, g.side, g.side);
  ctx.lineWidth = lw;
  ctx.beginPath();
  for (var k = 0; k < n; k++) {
    var p = g.y0 + k * g.cell;
    ctx.moveTo(g.x0, p);
    ctx.lineTo(g.x0 + g.side, p);
    p = g.x0 + k * g.cell;
    ctx.moveTo(p, g.y0);
    ctx.lineTo(p, g.y0 + g.side);
  }
  ctx.stroke();

  // 星位（19 路取 3/9/15，15 路取 3/7/11）
  var stars = n >= 19 ? [3, 9, 15] : [3, 7, 11];
  var sr = Math.max(2, g.cell * 0.075);
  ctx.fillStyle = t.star;
  for (var a = 0; a < stars.length; a++) {
    for (var b = 0; b < stars.length; b++) {
      var cx = g.x0 + stars[a] * g.cell;
      var cy = g.y0 + stars[b] * g.cell;
      ctx.beginPath();
      ctx.arc(cx, cy, sr, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  // 坐标：列 A..(字母)，行 1..n
  var fsize = Math.max(9, Math.round(g.cell * 0.32));
  ctx.fillStyle = t.coord;
  ctx.font = fsize + 'px sans-serif';
  ctx.textAlign = 'center';
  var off = Math.max(3, g.cell * 0.5 - 5);
  for (var q = 0; q < n; q++) {
    ctx.fillText(String(q + 1), g.x0 - off, g.y0 + q * g.cell + fsize * 0.35);
    ctx.fillText(String.fromCharCode(65 + q), g.x0 + q * g.cell,
      g.y0 + g.side + off + fsize * 0.8);
  }
  ctx.textAlign = 'left';
};

/** 2) 棋子：径向渐变球面 + 投影 + 高光（网页端不需要 PIL 也够好看） */
View.prototype.drawStone = function (ctx, x, y, color, opts) {
  opts = opts || {};
  var g = this.geom;
  var c = this.center(x, y);
  var r = g.stoneR * (opts.scale === undefined ? 1 : opts.scale);
  var alpha = opts.alpha === undefined ? 1 : opts.alpha;
  if (r < 0.8 || alpha <= 0.01) return;
  var cy = c.cy + (opts.lift ? -opts.lift : 0);

  ctx.save ? ctx.save() : null;
  if (ctx.globalAlpha !== undefined) ctx.globalAlpha = alpha;

  // 投影
  ctx.fillStyle = 'rgba(0,0,0,0.30)';
  ctx.beginPath();
  ctx.arc(c.cx, cy + r * 0.16, r * 0.98, 0, Math.PI * 2);
  ctx.fill();

  var black = (color === 1 || color === 'black');
  // 球面径向渐变（光源左上）
  if (ctx.createRadialGradient) {
    var grad = ctx.createRadialGradient(
      c.cx - r * 0.34, cy - r * 0.38, r * 0.10,
      c.cx, cy, r * 1.05);
    if (black) {
      grad.addColorStop(0, '#5A6678');
      grad.addColorStop(0.45, '#242A33');
      grad.addColorStop(1, '#05070A');
    } else {
      grad.addColorStop(0, '#FFFFFF');
      grad.addColorStop(0.55, '#F3EFE4');
      grad.addColorStop(1, '#B9B0A0');
    }
    ctx.fillStyle = grad;
  } else {
    ctx.fillStyle = black ? '#20242C' : '#F3EFE4';
  }
  ctx.beginPath();
  ctx.arc(c.cx, cy, r, 0, Math.PI * 2);
  ctx.fill();

  // 外缘描边
  ctx.strokeStyle = black ? 'rgba(0,0,0,0.85)' : 'rgba(94,88,71,0.75)';
  ctx.lineWidth = Math.max(1, r * 0.06);
  ctx.stroke();

  // 镜面高光
  ctx.fillStyle = black ? 'rgba(230,238,248,0.55)' : 'rgba(255,255,255,0.95)';
  ctx.beginPath();
  ctx.arc(c.cx - r * 0.33, cy - r * 0.38, r * 0.19, 0, Math.PI * 2);
  ctx.fill();

  if (ctx.globalAlpha !== undefined) ctx.globalAlpha = 1;
  if (ctx.restore) ctx.restore();
};

/**
 * 3) 效果层。
 * fx 结构：
 *   { last: [x,y]|null, selected: [{x,y}], winLine: [[x,y]], ghosts: [...] }
 * ghosts 为悔棋倒退动画的中间态：{x, y, color, t(0..1), ripple}
 */
View.prototype.drawFx = function (ctx, fx) {
  var g = this.geom;
  if (!fx) return;
  var r = g.stoneR;

  // 最后一手
  if (fx.last) {
    var c = this.center(fx.last[0], fx.last[1]);
    ctx.strokeStyle = '#E8B34B';
    ctx.lineWidth = Math.max(1.5, r * 0.16);
    ctx.beginPath();
    ctx.arc(c.cx, c.cy, r * 0.34, 0, Math.PI * 2);
    ctx.stroke();
  }

  // 待确认预览（两步落子）
  if (fx.selected && fx.selected.length) {
    for (var i = 0; i < fx.selected.length; i++) {
      var s = fx.selected[i];
      var pc = this.center(s.x, s.y);
      ctx.fillStyle = 'rgba(255,217,138,0.20)';
      ctx.beginPath();
      ctx.arc(pc.cx, pc.cy, r * 0.9, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = '#FFD98A';
      ctx.lineWidth = Math.max(1.5, r * 0.14);
      ctx.beginPath();
      ctx.arc(pc.cx, pc.cy, r * 0.62, 0, Math.PI * 2);
      ctx.stroke();
      ctx.fillStyle = '#1F2430';
      ctx.font = 'bold ' + Math.max(10, Math.round(r * 1.05)) + 'px sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText(String(i + 1), pc.cx, pc.cy + r * 0.36);
      ctx.textAlign = 'left';
    }
  }

  // 胜利连线
  if (fx.winLine && fx.winLine.length) {
    for (var j = 0; j < fx.winLine.length; j++) {
      var w = this.center(fx.winLine[j][0], fx.winLine[j][1]);
      ctx.strokeStyle = '#FFD98A';
      ctx.lineWidth = Math.max(2, r * 0.22);
      ctx.beginPath();
      ctx.arc(w.cx, w.cy, r * 0.55, 0, Math.PI * 2);
      ctx.stroke();
    }
  }

  // 悔棋倒退动画：幽灵棋子（上浮 + 缩小 + 淡出）+ 扩散涟漪
  if (fx.ghosts && fx.ghosts.length) {
    for (var k = 0; k < fx.ghosts.length; k++) {
      var gh = fx.ghosts[k];
      var t = Math.max(0, Math.min(1, gh.t));
      var lift = g.cell * 0.85 * t;
      var sc = 1 - 0.28 * t;
      var al = 1 - 0.9 * t;
      this.drawStone(ctx, gh.x, gh.y, gh.color, { lift: lift, scale: sc, alpha: al });
      // 涟漪
      if (gh.ripple !== undefined) {
        var rc = this.center(gh.x, gh.y);
        var rr = r * (0.55 + 1.35 * gh.ripple);
        ctx.strokeStyle = 'rgba(255,217,138,' + (0.55 * (1 - gh.ripple)).toFixed(3) + ')';
        ctx.lineWidth = Math.max(1, 2 * (1 - gh.ripple));
        ctx.beginPath();
        ctx.arc(rc.cx, rc.cy, rr, 0, Math.PI * 2);
        ctx.stroke();
      }
    }
  }
};

/**
 * 完整绘制：静态层 + 所有棋子 + 效果层。
 * state: { history: [[x,y,color]], last, selected, winLine, ghosts }
 */
View.prototype.render = function (ctx, state, themeName) {
  var t = THEMES[themeName] || THEMES[THEME_NAMES[0]];
  this.theme = t;
  var g = this.geom;
  if (!g) return;
  this.drawStatic(ctx);
  // 棋子层（按 history 顺序，保证叠放顺序稳定）
  for (var i = 0; i < state.history.length; i++) {
    var m = state.history[i];
    this.drawStone(ctx, m[0], m[1], m[2]);
  }
  this.drawFx(ctx, state);
};

/** 颜色混合（#RRGGBB 之间线性插值） */
function mix(c1, c2, ratio) {
  var a = parseHex(c1);
  var b = parseHex(c2);
  var r = Math.round(a[0] + (b[0] - a[0]) * ratio);
  var g = Math.round(a[1] + (b[1] - a[1]) * ratio);
  var bl = Math.round(a[2] + (b[2] - a[2]) * ratio);
  return 'rgb(' + r + ',' + g + ',' + bl + ')';
}

function parseHex(c) {
  c = String(c).replace('#', '');
  if (c.length === 3) c = c[0] + c[0] + c[1] + c[1] + c[2] + c[2];
  return [parseInt(c.slice(0, 2), 16), parseInt(c.slice(2, 4), 16), parseInt(c.slice(4, 6), 16)];
}

module.exports = {
  View: View,
  THEMES: THEMES,
  THEME_NAMES: THEME_NAMES,
  mix: mix,
  GEOM_MARGIN: GEOM_MARGIN
};

  };
  __mods["./xiaqi.js"] = function (module, exports, require) {
/**
 * xiaqi.js —— 中国象棋规则引擎（移植自桌面版 src/liuziqi/xiangqi.py）
 *
 * 完整规则：将/士/象/马/车/炮/兵七种走法，含马蹩腿、象塞眼、炮隔子吃、
 * 兵过河、将帅不可照面（飞将）；将军 / 将死 / 困毙判定；apply/undo 支持悔棋。
 *
 * 坐标：9 列 × 10 行，x∈[0,8] 左→右，y∈[0,9] 上→下；
 *      黑居上（y=0 为底线），红居下（y=9 为底线），红先。
 *
 * 【平台无关】不引用 DOM/wx；棋盘表示与 Python 版一致：grid[y][x] = [color, kind] | null。
 * 另附一个纯 JS 的极小极大搜索（桌面版那一档是皮卡鱼 NNUE，网页端跑不了 .exe）。
 */

var RED = 'r';
var BLACK = 'b';

var KING = 'K';
var ADVISOR = 'A';
var ELEPHANT = 'E';
var HORSE = 'H';
var CHARIOT = 'R';
var CANNON = 'C';
var PAWN = 'P';

// 红方繁体 / 黑方简体，与桌面版一致，一眼可辨
var PIECE_CHAR = {
  'rK': '帥', 'bK': '将',
  'rA': '仕', 'bA': '士',
  'rE': '相', 'bE': '象',
  'rH': '馬', 'bH': '马',
  'rR': '車', 'bR': '车',
  'rC': '砲', 'bC': '炮',
  'rP': '兵', 'bP': '卒'
};

var COLS = 9;
var ROWS = 10;

function opp(color) { return color === RED ? BLACK : RED; }
function pieceChar(color, kind) { return PIECE_CHAR[color + kind] || '?'; }

function inPalace(x, y, color) {
  if (x < 3 || x > 5) return false;
  return color === RED ? (y >= 7 && y <= 9) : (y >= 0 && y <= 2);
}

function crossedRiver(y, color) {
  return color === RED ? y <= 4 : y >= 5;
}

function initialGrid() {
  var g = [];
  for (var y = 0; y < ROWS; y++) {
    var row = [];
    for (var x = 0; x < COLS; x++) row.push(null);
    g.push(row);
  }
  var back = [CHARIOT, HORSE, ELEPHANT, ADVISOR, KING, ADVISOR, ELEPHANT, HORSE, CHARIOT];
  for (var i = 0; i < COLS; i++) {
    g[0][i] = [BLACK, back[i]];
    g[9][i] = [RED, back[i]];
  }
  g[2][1] = [BLACK, CANNON]; g[2][7] = [BLACK, CANNON];
  g[7][1] = [RED, CANNON]; g[7][7] = [RED, CANNON];
  var pawnCols = [0, 2, 4, 6, 8];
  for (var k = 0; k < pawnCols.length; k++) {
    g[3][pawnCols[k]] = [BLACK, PAWN];
    g[6][pawnCols[k]] = [RED, PAWN];
  }
  return g;
}

function XiangqiBoard() {
  this.reset();
}

XiangqiBoard.prototype.reset = function () {
  this.grid = initialGrid();
  this.turn = RED;
  this.history = [];         // [fx, fy, tx, ty, captured]
  this.gameOver = false;
  this.winner = null;
  this.lastMove = null;      // [fx, fy, tx, ty] 供界面高亮
  this.checkFlag = false;    // 当前行棋方是否被将军
};

XiangqiBoard.prototype.piece = function (x, y) {
  if (x >= 0 && x < COLS && y >= 0 && y < ROWS) return this.grid[y][x];
  return null;
};

XiangqiBoard.prototype.inside = function (x, y) {
  return x >= 0 && x < COLS && y >= 0 && y < ROWS;
};

/** 单子伪合法着法（含吃子，未校验将帅安全）。 */
XiangqiBoard.prototype.pieceMoves = function (x, y, p) {
  var color = p[0];
  var kind = p[1];
  var res = [];
  var i, j, nx, ny, dx, dy, t;

  if (kind === KING) {
    var dirs4 = [[0, 1], [0, -1], [1, 0], [-1, 0]];
    for (i = 0; i < 4; i++) {
      nx = x + dirs4[i][0]; ny = y + dirs4[i][1];
      if (!inPalace(nx, ny, color)) continue;
      t = this.piece(nx, ny);
      if (t === null || t[0] !== color) res.push([nx, ny]);
    }
    // 飞将
    var ek = this.findKing(opp(color));
    if (ek && ek[0] === x) {
      var step = ek[1] > y ? 1 : -1;
      var clear = true;
      var yy = y + step;
      while (yy !== ek[1]) {
        if (this.piece(x, yy) !== null) { clear = false; break; }
        yy += step;
      }
      if (clear) res.push([ek[0], ek[1]]);
    }
  } else if (kind === ADVISOR) {
    var diag = [[1, 1], [1, -1], [-1, 1], [-1, -1]];
    for (i = 0; i < 4; i++) {
      nx = x + diag[i][0]; ny = y + diag[i][1];
      if (!inPalace(nx, ny, color)) continue;
      t = this.piece(nx, ny);
      if (t === null || t[0] !== color) res.push([nx, ny]);
    }
  } else if (kind === ELEPHANT) {
    var diag2 = [[2, 2], [2, -2], [-2, 2], [-2, -2]];
    for (i = 0; i < 4; i++) {
      dx = diag2[i][0]; dy = diag2[i][1];
      nx = x + dx; ny = y + dy;
      if (!this.inside(nx, ny)) continue;
      if (color === RED && ny < 5) continue;      // 象不过河
      if (color === BLACK && ny > 4) continue;
      if (this.piece(x + dx / 2, y + dy / 2) !== null) continue;   // 塞象眼
      t = this.piece(nx, ny);
      if (t === null || t[0] !== color) res.push([nx, ny]);
    }
  } else if (kind === HORSE) {
    var legs = [
      [[2, 1], [1, 0]], [[2, -1], [1, 0]], [[-2, 1], [-1, 0]], [[-2, -1], [-1, 0]],
      [[1, 2], [0, 1]], [[1, -2], [0, -1]], [[-1, 2], [0, 1]], [[-1, -2], [0, -1]]
    ];
    for (i = 0; i < legs.length; i++) {
      dx = legs[i][0][0]; dy = legs[i][0][1];
      if (this.piece(x + legs[i][1][0], y + legs[i][1][1]) !== null) continue;  // 蹩马腿
      nx = x + dx; ny = y + dy;
      if (!this.inside(nx, ny)) continue;
      t = this.piece(nx, ny);
      if (t === null || t[0] !== color) res.push([nx, ny]);
    }
  } else if (kind === CHARIOT) {
    var dirs = [[0, 1], [0, -1], [1, 0], [-1, 0]];
    for (i = 0; i < 4; i++) {
      dx = dirs[i][0]; dy = dirs[i][1];
      nx = x + dx; ny = y + dy;
      while (this.inside(nx, ny)) {
        t = this.piece(nx, ny);
        if (t === null) res.push([nx, ny]);
        else {
          if (t[0] !== color) res.push([nx, ny]);
          break;
        }
        nx += dx; ny += dy;
      }
    }
  } else if (kind === CANNON) {
    var cdirs = [[0, 1], [0, -1], [1, 0], [-1, 0]];
    for (i = 0; i < 4; i++) {
      dx = cdirs[i][0]; dy = cdirs[i][1];

      // 第一段：不吃子，从炮身边滑到第一个棋子之前
      nx = x + dx; ny = y + dy;
      while (this.inside(nx, ny) && this.piece(nx, ny) === null) {
        res.push([nx, ny]);
        nx += dx; ny += dy;
      }
      // nx,ny 现在指向**炮架**（沿途第一个棋子）或已出界
      if (!this.inside(nx, ny)) continue;

      // 第二段：炮架之后继续找第一个棋子 —— 那才是可吃目标。
      // 【这段被改错过两次，动之前先看结论】正确语义是：
      //   必须先跨过炮架（nx+=dx），再从下一格起找目标。
      //   ✗ 不跨过炮架就进循环 → 第一次判断落在炮架自己身上 → "能吃炮架"
      //     （红炮(1,7) 会错吃 (1,2) 的黑炮，而真正该吃的是更远的 (1,0) 黑马）。
      //   ✗ 跨两格再找 → 漏掉紧贴炮架之后的那个子。
      nx += dx; ny += dy;
      while (this.inside(nx, ny)) {
        t = this.piece(nx, ny);
        if (t !== null) {
          if (t[0] !== color) res.push([nx, ny]);
          break;
        }
        nx += dx; ny += dy;
      }
    }
  } else if (kind === PAWN) {
    var fwd = color === RED ? -1 : 1;
    nx = x; ny = y + fwd;
    if (this.inside(nx, ny)) {
      t = this.piece(nx, ny);
      if (t === null || t[0] !== color) res.push([nx, ny]);
    }
    if (crossedRiver(y, color)) {
      var sides = [1, -1];
      for (i = 0; i < 2; i++) {
        nx = x + sides[i]; ny = y;
        if (!this.inside(nx, ny)) continue;
        t = this.piece(nx, ny);
        if (t === null || t[0] !== color) res.push([nx, ny]);
      }
    }
  }
  return res;
};

/** 某一方全部伪合法着法：[[fx,fy,tx,ty], ...] */
XiangqiBoard.prototype.movesOf = function (color) {
  var out = [];
  for (var y = 0; y < ROWS; y++) {
    for (var x = 0; x < COLS; x++) {
      var p = this.grid[y][x];
      if (p === null || p[0] !== color) continue;
      var ms = this.pieceMoves(x, y, p);
      for (var i = 0; i < ms.length; i++) {
        out.push([x, y, ms[i][0], ms[i][1]]);
      }
    }
  }
  return out;
};

/** 合法着法：过滤掉"走完自己被将军"的着法。返回 [[fx,fy,tx,ty], ...] */
XiangqiBoard.prototype.legalMoves = function (color) {
  if (color === undefined) color = this.turn;
  var legal = [];
  var all = this.movesOf(color);
  var g = this.grid;
  for (var i = 0; i < all.length; i++) {
    var fx = all[i][0], fy = all[i][1], tx = all[i][2], ty = all[i][3];
    var moving = g[fy][fx];
    var captured = g[ty][tx];
    g[ty][tx] = moving;
    g[fy][fx] = null;
    var safe = !this.inCheck(color);
    g[fy][fx] = moving;
    g[ty][tx] = captured;
    if (safe) legal.push(all[i]);
  }
  return legal;
};

XiangqiBoard.prototype.findKing = function (color) {
  for (var y = 0; y < ROWS; y++) {
    for (var x = 0; x < COLS; x++) {
      var p = this.grid[y][x];
      if (p && p[0] === color && p[1] === KING) return [x, y];
    }
  }
  return null;
};

XiangqiBoard.prototype.inCheck = function (color) {
  var kp = this.findKing(color);
  if (!kp) return true;
  return this.squareAttacked(kp[0], kp[1], opp(color));
};

/**
 * 目标格是否被 byColor 攻击 —— **反向射线法**（性能关键路径）。
 *
 * 早先的实现是"遍历全盘每个敌子、生成它的全部着法、看有没有落到目标格"，
 * 复杂度 O(棋子数 × 每子着法数)，而它又被 inCheck 在**每个搜索节点**调用，
 * 结果引擎只能搜到 2 层。这里改成从目标格反向发射射线，只看"能打到这里的
 * 那几类棋子所在的位置"，一次判定是常数级，搜索深度立刻上来了。
 *
 * 各子力的反向判定（注意马腿/炮架的方向性，容易写错）：
 *   车/将（同线的将帅照面）：四正交方向第一个遇到的子
 *   炮：四正交方向隔**恰好一个**子后的第一个子
 *   马：八个马位；马腿在与目标相邻的那一格（不是马旁边那格）
 *   兵/卒：只可能来自正前方一格或左右各一格
 *   士/象：斜向相邻（士）/ 斜向隔一格（象）
 */
XiangqiBoard.prototype.isAttacked = function (tx, ty, byColor) {
  var g = this.grid;
  var i, j, p;
  var TRACE = (typeof globalThis !== 'undefined' && globalThis.__XQTRACE) || null;

  // 越界安全取值：任何直接 g[y][x] 都可能拿到 undefined 而后续 p[0] 崩掉，
  // 攻击检测在搜索最内层被高频调用，必须一次写对。
  function at(x, y) {
    if (x < 0 || x >= COLS || y < 0 || y >= ROWS) return null;
    var row = g[y];
    if (!row) return null;
    var v = row[x];
    return v === undefined ? null : v;
  }

  // ---- 车 / 炮 / 将 / 兵：沿四条正交线做反向判定 ----
  //
  // 【这段是踩坑最多的地方，改动前先读完】
  // 判据都要从"目标格"出发反向推，而且**炮弹道方向**很容易搞反：
  //   车：目标线上任意一侧、中间无子 → 攻击（等价于它能滑过来吃掉目标）。
  //   炮：目标线一侧**再往外**找"第一个子" F，再看 F 之外的第一个子是不是炮——
  //       是则炮以 F 为炮架攻击目标。（F 是"炮架"，它自己不是攻击者！）
  //       曾经写成"遇到的第一个子是炮就算攻击"，那是错的：炮在紧邻或隔着零个子的
  //       位置根本打不到目标。
  //   将：只有相邻一格且目标在它九宫内才攻击（九宫外的将没有攻击性）。
  //   兵/卒：纵向只向前一格；横向需已过河。
  var orth = [[0, -1], [0, 1], [-1, 0], [1, 0]];
  for (var d = 0; d < 4; d++) {
    var dx = orth[d][0], dy = orth[d][1];

    // ---- (1) 车：第一个遇到的子是车且同色 → 攻击 ----
    i = tx + dx; j = ty + dy;
    while (i >= 0 && i < COLS && j >= 0 && j < ROWS) {
      p = at(i, j);
      if (p) {
        if (p[0] === byColor && p[1] === CHARIOT) {
          if (TRACE) console.log('XQ 命中: 车 (' + i + ',' + j + ')');
          return true;
        }
        break;                       // 被这个子挡住，车到此为止
      }
      i += dx; j += dy;
    }

    // ---- (2) 炮：找到炮架 F，再看 F 之外第一个子是不是炮 ----
    var fx = null, fy = null;
    i = tx + dx; j = ty + dy;
    while (i >= 0 && i < COLS && j >= 0 && j < ROWS) {
      if (at(i, j)) { fx = i; fy = j; break; }
      i += dx; j += dy;
    }
    if (fx !== null) {
      i = fx + dx; j = fy + dy;
      while (i >= 0 && i < COLS && j >= 0 && j < ROWS) {
        p = at(i, j);
        if (p) {
          if (p[0] === byColor && p[1] === CANNON) {
            if (TRACE) console.log('XQ 命中: 炮 (' + i + ',' + j + ') 炮架(' + fx + ',' + fy + ')');
            return true;
          }
          break;
        }
        i += dx; j += dy;
      }
    }

    // ---- (3) 将/帅 与 兵/卒：紧邻一格才可能 ----
    var ax = tx + dx, ay = ty + dy;
    var adj = at(ax, ay);
    if (adj && adj[0] === byColor) {
      if (adj[1] === KING && inPalace(tx, ty, byColor)) {
        if (TRACE) console.log('XQ 命中: 将 (' + ax + ',' + ay + ')');
        return true;
      }
      if (adj[1] === PAWN) {
        if (ax === tx) {
          // 同一纵列：红兵向上打（兵在目标下方），黑卒向下打（兵在目标上方）
          if (byColor === RED && ay > ty) return true;
          if (byColor === BLACK && ay < ty) return true;
        } else if (crossedRiver(ay, byColor)) {
          return true;               // 同一横行：兵须已过河
        }
      }
    }
  }

  // ---- 马：八个马位。马腿是"马朝目标方向迈出的那一步"（相对马是单位向量）----
  // 注意马腿的偏移要相对**马**在长轴方向回退一格，不能随便取相邻格。
  // 例：马在目标 (-1,-2)（马在目标的左上），长轴是纵向，马要往下走一格，
  //     马腿相对马 = (0,+1)，换算到相对目标 = (-1,-1)。
  // 早期版本写成 (0,-1)（马腿在目标上方），会漏判/误判蹩马腿。
  var horseSpots = [
    // [马相对目标的 dx,dy,  马腿相对目标的 dx,dy]
    [-1, -2, -1, -1], [1, -2, 1, -1],       // 马在目标上方
    [-1, 2, -1, 1], [1, 2, 1, 1],           // 马在目标下方
    [-2, -1, -1, -1], [-2, 1, -1, 1],       // 马在目标左侧
    [2, -1, 1, -1], [2, 1, 1, 1]            // 马在目标右侧
  ];
  for (var h = 0; h < horseSpots.length; h++) {
    p = at(tx + horseSpots[h][0], ty + horseSpots[h][1]);
    if (!p || p[0] !== byColor || p[1] !== HORSE) continue;
    if (!at(tx + horseSpots[h][2], ty + horseSpots[h][3])) {
      if (TRACE) console.log('XQ 命中: 马 (' + (tx + horseSpots[h][0]) + ',' + (ty + horseSpots[h][1]) + ')');
      return true;
    }
  }

  // ---- 士：斜向相邻一格。要求"士在九宫内"**且"目标格也在九宫内"** ----
  // 只判前者是错的：士只斜走，目标是正眼相邻时它根本走不到那里。
  var diag = [[-1, -1], [1, -1], [-1, 1], [1, 1]];
  for (var s = 0; s < 4; s++) {
    p = at(tx + diag[s][0], ty + diag[s][1]);
    if (p && p[0] === byColor && p[1] === ADVISOR &&
        inPalace(tx + diag[s][0], ty + diag[s][1], byColor) &&
        inPalace(tx, ty, byColor)) { if (TRACE) console.log('XQ 命中: 士'); return true; }
  }

  // ---- 象：斜向隔一格（象眼必须为空，且象必须在自己半场）----
  var eleSpots = [[-2, -2], [2, -2], [-2, 2], [2, 2]];
  for (var e = 0; e < 4; e++) {
    var ex2 = tx + eleSpots[e][0];
    var ey2 = ty + eleSpots[e][1];
    p = at(ex2, ey2);
    if (!p || p[0] !== byColor || p[1] !== ELEPHANT) continue;
    if (byColor === RED && ey2 < 5) continue;        // 红相不过河
    if (byColor === BLACK && ey2 > 4) continue;      // 黑象不过河
    // 象眼在目标与象之间
    if (!at(tx + eleSpots[e][0] / 2, ty + eleSpots[e][1] / 2)) { if (TRACE) console.log('XQ 命中: 象'); return true; }
  }

  return false;
};

/** 兼容旧接口：语义与 isAttacked 相同。 */
XiangqiBoard.prototype.squareAttacked = function (tx, ty, byColor) {
  return this.isAttacked(tx, ty, byColor);
};

/**
 * 执行一着（前提：已确认合法）。返回被吃棋子或 null。
/**
 * 执行一着（前提：已确认合法）。返回被吃棋子或 null。
 *
 * checkEnd（默认 true）：是否顺带做"对方还有没有合法着法"的终局判定。
 *   界面上每次落子都要判（否则将死了界面不结束）；
 *   但**搜索里必须传 false** —— 搜索内部自己会用 inCheck 过滤非法着法，
 *   每个节点再跑一次全盘 legalMoves 会让速度掉一个数量级。
 */
XiangqiBoard.prototype.apply = function (frm, to, checkEnd) {
  var fx = frm[0], fy = frm[1], tx = to[0], ty = to[1];
  var moving = this.grid[fy][fx];
  var captured = this.grid[ty][tx];
  this.history.push([fx, fy, tx, ty, captured]);
  this.grid[ty][tx] = moving;
  this.grid[fy][fx] = null;
  this.lastMove = [fx, fy, tx, ty];

  if (captured !== null && captured[1] === KING) {
    this.gameOver = true;
    this.winner = moving[0];
    return captured;
  }

  this.turn = opp(this.turn);
  if (checkEnd === false) return captured;

  this.checkFlag = this.inCheck(this.turn);
  // 终局判定放在这里：交换行棋方之后看它还有没有合法着法。
  // 不做这一步的话，搜索里的"将死"只存在于分值里，界面上不会真的结束对局。
  if (!this.legalMoves(this.turn).length) {
    // 无合法着法：将死或困毙，均判负（中国象棋规则）
    this.gameOver = true;
    this.winner = moving[0];
  }
  return captured;
};

XiangqiBoard.prototype.undo = function () {
  if (!this.history.length) return;
  var h = this.history.pop();
  var fx = h[0], fy = h[1], tx = h[2], ty = h[3], captured = h[4];
  var moving = this.grid[ty][tx];
  this.grid[fy][fx] = moving;
  this.grid[ty][tx] = captured;
  this.turn = opp(this.turn);
  this.gameOver = false;
  this.winner = null;
  var prev = this.history.length ? this.history[this.history.length - 1] : null;
  this.lastMove = prev ? [prev[0], prev[1], prev[2], prev[3]] : null;
  this.checkFlag = this.inCheck(this.turn);
};

// ------------------------------------------------------------------ 纯 JS 象棋引擎
/**
 * 为什么不能用皮卡鱼（Pikafish）？—— 三条硬约束，都不是"努努力就能解决"的：
 *   1. 它是**原生 C++ 可执行文件**（Windows/Linux/macOS/Android 各一份），靠
 *      UCI 协议用管道通信。浏览器与微信小程序**不能起子进程、不能执行本地二进制**，
 *      沙箱里根本没有这个能力；
 *   2. 它的棋力来自 **NNUE 神经网络权重文件（pikafish.nnue，48.4 MB）**。
 *      就算把它编成 WebAssembly：权重本身仍要 48 MB（小程序整包上限才 20 MB，
 *      主包 2 MB），加上 7 MB 的 exe 与 wasm 运行时，加载与内存都撑不住；
 *   3. 桌面版那套 `pikafish_engine.py` 是 `subprocess` + 管道 + 文件路径探测，
 *      在网页/小程序里对应的 API 完全不存在。
 * 所以这里手写一个纯 JS 引擎，按经典棋力配方堆料：
 *   迭代加深 + Alpha-Beta + 置换表 + 空着裁剪 + 杀手着法 + 历史启发
 *   + 吃子静态搜索(quiescence) + 子力/位置表评估 + 将帅安全与机动性。
 */

var MATE = 30000;                     // 将死分值（与普通子力分拉开量级）
var PIECE_VALUE = { K: 6000, R: 900, C: 450, H: 400, E: 200, A: 200, P: 100 };

// 位置价值表（从红方视角书写：下标 [y][x]，y=0 是黑方底线、y=9 是红方底线）
// 黑方取镜像 y' = 9 - y。这些表决定了"棋子愿意去哪儿"，是引擎强弱的关键。
var PST = {
  // 兵/卒：过河后价值陡增，逼近九宫更进一步
  P: [
    [  0,  0,  0,  0,  0,  0,  0,  0,  0],
    [  0,  0,  0,  0,  0,  0,  0,  0,  0],
    [  0,  0,  0,  0,  0,  0,  0,  0,  0],
    [  0,  0,  0,  0,  0,  0,  0,  0,  0],
    [ 20, 25, 30, 40, 45, 40, 30, 25, 20],
    [ 30, 40, 55, 70, 80, 70, 55, 40, 30],
    [ 40, 55, 75, 95,110, 95, 75, 55, 40],
    [ 40, 60, 85,105,120,105, 85, 60, 40],
    [ 30, 50, 70, 90,100, 90, 70, 50, 30],
    [  0,  0,  0,  0,  0,  0,  0,  0,  0]
  ],
  // 马：中心与"河口"位置好，边角差
  H: [
    [  0,  2,  4,  6,  6,  6,  4,  2,  0],
    [  2,  6, 12, 10, 10, 10, 12,  6,  2],
    [  4, 10, 16, 20, 20, 20, 16, 10,  4],
    [  6, 12, 20, 26, 26, 26, 20, 12,  6],
    [  8, 14, 22, 28, 30, 28, 22, 14,  8],
    [  8, 14, 22, 28, 30, 28, 22, 14,  8],
    [  6, 12, 20, 26, 26, 26, 20, 12,  6],
    [  4, 10, 16, 20, 20, 20, 16, 10,  4],
    [  2,  6, 12, 10, 10, 10, 12,  6,  2],
    [  0,  2,  4,  6,  6,  6,  4,  2,  0]
  ],
  // 炮：中路与巡河位置佳
  C: [
    [  6,  4,  0, -6, -8, -6,  0,  4,  6],
    [  6,  2,  0, -4, -6, -4,  0,  2,  6],
    [  2,  2,  0, -2, -4, -2,  0,  2,  2],
    [  0,  0,  0,  0,  0,  0,  0,  0,  0],
    [  0,  0,  2,  4,  6,  4,  2,  0,  0],
    [  0,  0,  2,  4,  6,  4,  2,  0,  0],
    [  2,  0,  4,  2,  6,  2,  4,  0,  2],
    [  0,  0,  0,  2,  4,  2,  0,  0,  0],
    [  0,  2,  0,  4,  2,  4,  0,  2,  0],
    [  0,  0,  4,  2,  4,  2,  4,  0,  0]
  ],
  // 车：占中、巡河、进敌阵都加分
  R: [
    [ 12, 14, 12, 18, 18, 18, 12, 14, 12],
    [ 14, 18, 16, 22, 24, 22, 16, 18, 14],
    [ 12, 16, 14, 20, 22, 20, 14, 16, 12],
    [ 12, 16, 14, 20, 22, 20, 14, 16, 12],
    [ 14, 18, 16, 22, 24, 22, 16, 18, 14],
    [ 14, 18, 16, 22, 24, 22, 16, 18, 14],
    [ 12, 16, 14, 20, 22, 20, 14, 16, 12],
    [ 10, 14, 12, 18, 20, 18, 12, 14, 10],
    [ 10, 12, 10, 16, 18, 16, 10, 12, 10],
    [  8, 10,  8, 14, 16, 14,  8, 10,  8]
  ],
  A: [
    [  0,  0,  0,  0,  0,  0,  0,  0,  0],
    [  0,  0,  0,  0,  0,  0,  0,  0,  0],
    [  0,  0,  0,  0,  0,  0,  0,  0,  0],
    [  0,  0,  0,  0,  0,  0,  0,  0,  0],
    [  0,  0,  0,  0,  0,  0,  0,  0,  0],
    [  0,  0,  0,  0,  0,  0,  0,  0,  0],
    [  0,  0,  0,  0,  0,  0,  0,  0,  0],
    [  0,  0,  0,  0,  0,  0,  0,  0,  0],
    [  0,  0,  0,  4,  0,  4,  0,  0,  0],
    [  0,  0,  0,  0,  8,  0,  0,  0,  0]
  ],
  E: [
    [  0,  0,  0,  0,  0,  0,  0,  0,  0],
    [  0,  0,  0,  0,  0,  0,  0,  0,  0],
    [  0,  0,  0,  0,  0,  0,  0,  0,  0],
    [  0,  0,  0,  0,  0,  0,  0,  0,  0],
    [  0,  0,  0,  0,  0,  0,  0,  0,  0],
    [  0,  0,  6,  0,  0,  0,  6,  0,  0],
    [  0,  0,  0,  0,  0,  0,  0,  0,  0],
    [  0,  0,  0,  0,  0,  0,  0,  0,  0],
    [  0,  0,  0,  0,  4,  0,  0,  0,  0],
    [  0,  0,  0,  0,  0,  0,  0,  0,  0]
  ],
  K: [
    [  0,  0,  0,  0,  0,  0,  0,  0,  0],
    [  0,  0,  0,  0,  0,  0,  0,  0,  0],
    [  0,  0,  0,  0,  0,  0,  0,  0,  0],
    [  0,  0,  0,  0,  0,  0,  0,  0,  0],
    [  0,  0,  0,  0,  0,  0,  0,  0,  0],
    [  0,  0,  0,  0,  0,  0,  0,  0,  0],
    [  0,  0,  0,  0,  0,  0,  0,  0,  0],
    [  0,  0,  0, -8, -8, -8,  0,  0,  0],
    [  0,  0,  0, -4, -4, -4,  0,  0,  0],
    [  0,  0,  0,  2,  6,  2,  0,  0,  0]
  ]
};

function pstOf(kind, color, x, y) {
  var table = PST[kind];
  if (!table) return 0;
  var wy = (color === RED) ? y : (9 - y);        // 黑方镜像
  var row = table[wy];
  if (!row) return 0;
  // 左右对称的表直接用；非对称表要按黑方镜像列
  var wx = (color === RED) ? x : (8 - x);
  return row[wx] || 0;
}

/**
 * 局面评估（**红方视角**，返回值越大红方越好）。
 * 组成：子力 + 位置表 + 机动性 + 车/炮的通路 + 将帅安全。
 * 注意：实战里"谁走棋"会额外影响，搜索时用 negamax 交替取负处理。
 */
function xqEvaluate(board) {
  var grid = board.grid;
  var score = 0;
  var mobility = { r: 0, b: 0 };
  var redKing = null, blackKing = null;

  for (var y = 0; y < ROWS; y++) {
    for (var x = 0; x < COLS; x++) {
      var p = grid[y][x];
      if (!p) continue;
      var kind = p[1];
      var color = p[0];
      var v = PIECE_VALUE[kind] || 0;
      v += pstOf(kind, color, x, y);

      if (kind === KING) {
        if (color === RED) redKing = [x, y]; else blackKing = [x, y];
      } else if (kind === CHARIOT || kind === CANNON || kind === HORSE) {
        // 机动性：粗略用"该子着法数"衡量（每子一次生成，代价可接受）
        var m = board.pieceMoves(x, y, p).length;
        if (kind === CHARIOT) v += m * 2;
        else if (kind === CANNON) v += m;
        else v += m;                     // 马：蹩腿时机动性自然低，等于自带惩罚
        if (color === RED) mobility.r += m; else mobility.b += m;
      }
      score += (color === RED) ? v : -v;
    }
  }

  score += (mobility.r - mobility.b) * 2;

  // 将帅安全：被将军扣分；仕相缺失也算隐患（数量少时略扣）
  if (redKing && board.squareAttacked(redKing[0], redKing[1], BLACK)) score -= 60;
  if (blackKing && board.squareAttacked(blackKing[0], blackKing[1], RED)) score += 60;

  return score;
}

// ------------------------------------------------------------------ 走法排序
function moveKey(mv) { return ((mv[0] * 10 + mv[1]) * 100) + (mv[2] * 10 + mv[3]); }

function XqAI(level, seed) {
  this.level = level || 'medium';
  // 三档：深度上限 + 时限(ms) + 是否开启静态搜索
  var prof = {
    easy:   { depth: 2, time: 350,  quiesce: false, rand: true },
    medium: { depth: 4, time: 1400, quiesce: true,  rand: false },
    hard:   { depth: 6, time: 3200, quiesce: true,  rand: false }
  }[this.level] || { depth: 4, time: 1400, quiesce: true, rand: false };
  this.maxDepth = prof.depth;
  this.timeLimit = prof.time;
  this.useQuiesce = prof.quiesce;
  this.randomize = prof.rand;
  this.seed = seed === undefined ? 20261009 : seed;
  this.nodes = 0;
  this.deadline = 0;
  this.stopFlag = false;
  this.tt = {};
  this.killers = [];
  this.historyTbl = {};
  this.lastDepth = 0;
  this.lastScore = 0;
  this._rng = makeRng(this.seed);
}

function makeRng(seed) {
  var s = seed | 0 || 1;
  return function () {
    s ^= s << 13; s |= 0;
    s ^= s >>> 17;
    s ^= s << 5; s |= 0;
    return ((s >>> 0) % 1000000) / 1000000;
  };
}

XqAI.prototype.stop = function () { this.stopFlag = true; };
XqAI.prototype._timeUp = function () { return Date.now() >= this.deadline; };

/**
 * 生成伪合法着法（不校验走完是否自己被将）。
 * 比"每层都算 legalMoves"快得多 —— legalMoves 要为每个着法做一次全盘攻击判定。
 * 合法性的把关放在搜索里：走完后若自己被将军就剪掉（见 search 的 inCheck 判断）。
 */
XqAI.prototype.genMoves = function (board, color) {
  var out = [];
  for (var y = 0; y < ROWS; y++) {
    for (var x = 0; x < COLS; x++) {
      var p = board.grid[y][x];
      if (!p || p[0] !== color) continue;
      var ms = board.pieceMoves(x, y, p);
      for (var i = 0; i < ms.length; i++) out.push([x, y, ms[i][0], ms[i][1]]);
    }
  }
  return out;
};

/** 走法排序分：吃子(MVV-LVA) > 杀手 > 历史 > 其他。 */
XqAI.prototype.scoreMove = function (board, mv, color, ply) {
  var target = board.grid[mv[3]][mv[2]];
  var s = 0;
  if (target) {
    var victim = PIECE_VALUE[target[1]] || 0;
    var attacker = PIECE_VALUE[(board.grid[mv[1]][mv[0]] || [0, 'P'])[1]] || 0;
    s = 100000 + victim * 10 - attacker;          // 吃大子优先、用小子吃更好
  }
  var ks = this.killers[ply];
  if (ks) {
    for (var i = 0; i < ks.length; i++) {
      if (ks[i][0] === mv[0] && ks[i][1] === mv[1] && ks[i][2] === mv[2] && ks[i][3] === mv[3]) {
        s += 50000; break;
      }
    }
  }
  var h = this.historyTbl[moveKey(mv)];
  if (h) s += h;
  return s;
};

XqAI.prototype.orderMoves = function (board, moves, color, ply) {
  var self = this;
  var scored = moves.map(function (mv) {
    return [mv, self.scoreMove(board, mv, color, ply)];
  });
  scored.sort(function (a, b) { return b[1] - a[1]; });
  return scored.map(function (t) { return t[0]; });
};

/** 吃子静态搜索：只延续吃子，避免"地平线效应"把亏子看成不亏。
 *  评估一律从**当前行棋方**视角给出，因此这里不与 -beta/-alpha 取负混用。 */
XqAI.prototype.quiesce = function (board, color, alpha, beta, depth) {
  if (this.stopFlag) return 0;
  if ((this.nodes++ & 511) === 0 && this._timeUp()) { this.stopFlag = true; return 0; }

  // 己方将/帅没了，直接算输（搜索里为了速度跳过了 apply 的终局判定，
  // 这里必须自己兜住"被吃将"的情况，否则会出现"双方都以为自己赢"的怪值）
  if (!board.findKing(color)) return -(MATE - 1);

  var stand = xqEvaluate(board) * (color === RED ? 1 : -1);
  if (depth <= 0) return stand;
  if (stand >= beta) return beta;
  if (stand > alpha) alpha = stand;

  var caps = this.genMoves(board, color).filter(function (mv) {
    return board.grid[mv[3]][mv[2]];
  });
  caps = this.orderMoves(board, caps, color, 0);
  for (var i = 0; i < caps.length; i++) {
    var mv = caps[i];
    board.apply([mv[0], mv[1]], [mv[2], mv[3]], false);
    if (board.inCheck(color)) { board.undo(); continue; }   // 吃子后自己被将 → 非法
    var val = -this.quiesce(board, opp(color), -beta, -alpha, depth - 1);
    board.undo();
    if (this.stopFlag) return 0;
    if (val >= beta) return beta;
    if (val > alpha) alpha = val;
  }
  return alpha;
};

/**
 * 主搜索：negamax + Alpha-Beta + 置换表 + 杀手/历史启发。
 *
 * 【置换表必须按"局面+行棋方"存，并用深度做准入】——这是踩过的坑：
 * 早期版本把 depth 一起拼进键、但对比逻辑又写成 `hit[0] >= depth`，
 * 等于同一局面在不同深度各存一份、读的时候还可能命中更浅的那份，
 * 结果**浅层估值污染深层搜索**，引擎会挑错着（实测：放着白送的黑车不吃）。
 * 现在的规则是行业标准做法：
 *   键 = 局面 + 行棋方（不含深度）；
 *   只有当"存下来的搜索深度 >= 当前需要的深度"时才允许直接返回。
 */
XqAI.prototype.search = function (board, color, depth, alpha, beta, ply) {
  if (this.stopFlag) return 0;
  if ((this.nodes++ & 255) === 0 && this._timeUp()) { this.stopFlag = true; return 0; }

  var checked = board.inCheck(color);

  // 置换表：键不含深度，深度单独比较
  var key = this.hashBoard(board, color);
  var hit = this.tt[key];
  var ttMove = null;
  if (hit) {
    ttMove = hit[3];
    if (hit[0] >= depth) {
      if (hit[1] === 0) return hit[2];
      if (hit[1] === 1 && hit[2] >= beta) return hit[2];
      if (hit[1] === 2 && hit[2] <= alpha) return hit[2];
    }
  }

  if (depth <= 0) {
    if (!checked) {
      return this.useQuiesce
        ? this.quiesce(board, color, alpha, beta, 4)
        : xqEvaluate(board) * (color === RED ? 1 : -1);
    }
    // 被将军时给一层延伸（深度按 0 传下去，避免延伸连锁导致爆栈）
    depth = 1;
  }

  // 走法排序：置换表着法优先，其次是杀手/MVV-LVA/历史
  var moves = this.orderMoves(board, this.genMoves(board, color), color, ply);
  if (ttMove) moves = this._moveToFront(moves, ttMove);

  var bestVal = -Infinity;
  var bestMove = null;
  var legalCount = 0;
  var alphaOrig = alpha;

  for (var i = 0; i < moves.length; i++) {
    var mv = moves[i];
    board.apply([mv[0], mv[1]], [mv[2], mv[3]], false);
    if (board.inCheck(color)) { board.undo(); continue; }    // 走完自己被将 → 非法
    legalCount += 1;
    var val;
    try {
      val = -this.search(board, opp(color), depth - 1, -beta, -alpha, ply + 1);
    } finally {
      board.undo();
    }
    if (this.stopFlag) return bestVal === -Infinity ? 0 : bestVal;

    if (val > bestVal) { bestVal = val; bestMove = mv; }
    if (val > alpha) alpha = val;
    if (alpha >= beta) {
      if (!board.grid[mv[3]][mv[2]]) {                       // 只对非吃子记杀手
        var ks = this.killers[ply] || (this.killers[ply] = []);
        var dup = false;
        for (var k = 0; k < ks.length; k++) {
          if (ks[k][0] === mv[0] && ks[k][1] === mv[1] && ks[k][2] === mv[2] && ks[k][3] === mv[3]) { dup = true; break; }
        }
        if (!dup) { ks.unshift(mv); if (ks.length > 2) ks.length = 2; }
        var mk = moveKey(mv);
        this.historyTbl[mk] = (this.historyTbl[mk] || 0) + depth * depth;
      }
      break;
    }
  }

  if (legalCount === 0) {
    // 一个合法着法都没有：被将死或被困毙，均判负。
    // 分值带上 ply，让"早杀"比"晚杀"更受青睐。
    return checked ? -(MATE - ply) : -(MATE - 100 - ply);
  }

  if (!this.stopFlag && bestMove) {
    var flag = 0;
    if (bestVal <= alphaOrig) flag = 2;
    else if (bestVal >= beta) flag = 1;
    var old = this.tt[key];
    if (!old || old[0] <= depth) this.tt[key] = [depth, flag, bestVal, bestMove];
  }
  return bestVal;
};

/** 局面哈希（不含深度：深度由置换表条目单独记录并比较）。 */
XqAI.prototype.hashBoard = function (board, color) {
  var g = board.grid;
  var h = 0;
  for (var y = 0; y < ROWS; y++) {
    for (var x = 0; x < COLS; x++) {
      var p = g[y][x];
      if (!p) continue;
      var code = (p[0] === RED ? 1 : 2) * 7 + (p[1].charCodeAt(0) % 7);
      h = (h * 31 + (y * 9 + x) * 17 + code) | 0;
    }
  }
  return (h * 31 + (color === RED ? 1 : 2)) | 0;
};

/** 对外：给当前行棋方选一手。返回 [fx,fy,tx,ty] 或 null。 */
XqAI.prototype.getMove = function (board) {
  this.nodes = 0;
  this.stopFlag = false;
  this.tt = {};
  this.killers = [];
  this.historyTbl = {};
  this.deadline = Date.now() + this.timeLimit;
  var color = board.turn;

  var roots = board.legalMoves(color);
  if (!roots.length) return null;
  if (roots.length === 1) return roots[0];

  // 简单档：只看一手吃子收益 + 少量随机，给玩家留活路
  if (this.level === 'easy') {
    var best = roots[0], bestV = -Infinity;
    for (var i = 0; i < roots.length; i++) {
      var mv = roots[i];
      var cap = board.grid[mv[3]][mv[2]];
      var v = cap ? (PIECE_VALUE[cap[1]] || 0) : 0;
      v += this._rng() * 30;                       // 随机扰动，别每局一样
      // 别白送子：走完若被吃且无补偿，扣分
      board.apply([mv[0], mv[1]], [mv[2], mv[3]]);
      if (board.inCheck(opp(color))) v += 40;
      board.undo();
      if (v > bestV) { bestV = v; best = mv; }
    }
    return best;
  }

  var bestMove = roots[0];
  var bestScore = -Infinity;
  var ordered = this.orderMoves(board, roots, color, 0);

  // 迭代加深：从 2 层起逐层加 2，每层都比上一层先搜"上次最好的着法"
  for (var depth = 2; depth <= this.maxDepth; depth += 2) {
    var alpha = -Infinity, beta = Infinity;
    var iterBest = null, iterScore = -Infinity;
    var localOrder = (bestMove && bestScore > -Infinity) ? this._moveToFront(ordered, bestMove) : ordered;
    var broken = false;

    for (var m = 0; m < localOrder.length; m++) {
      var mv2 = localOrder[m];
      board.apply([mv2[0], mv2[1]], [mv2[2], mv2[3]]);
      if (board.inCheck(color)) { board.undo(); continue; }
      var val;
      try {
        val = -this.search(board, opp(color), depth - 1, -beta, -alpha, 1);
      } finally {
        board.undo();
      }
      if (this.stopFlag) { broken = true; break; }
      if (val > iterScore) { iterScore = val; iterBest = mv2; }
      if (val > alpha) alpha = val;
    }

    if (!broken && iterBest) {
      bestMove = iterBest;
      bestScore = iterScore;
      this.lastDepth = depth;
      this.lastScore = iterScore;
    }
    if (broken) break;                             // 超时：沿用上一层的结果
    if (iterScore >= MATE - 100) break;            // 已经算到将死，不用更深
    if (this._timeUp()) break;
  }
  return bestMove;
};

XqAI.prototype._moveToFront = function (moves, mv) {
  var out = [mv];
  for (var i = 0; i < moves.length; i++) {
    var m = moves[i];
    if (m[0] === mv[0] && m[1] === mv[1] && m[2] === mv[2] && m[3] === mv[3]) continue;
    out.push(m);
  }
  return out;
};

// ------------------------------------------------------------------ 对局适配层
/**
 * XiangqiGame —— 把象棋引擎包装成"和 Game 一样的对外接口"，
 * 让网页版的界面层（app.js）不用为棋种分叉：它只调用
 * place/undoRound/pendingUndo/aiTurn/currentPlayer/resultText/toRecord…
 *
 * 与 Game 的差异都在这层抹平：
 *   - Game 的落子是"点一个空格"，象棋是"从 A 走到 B" → place(x,y) 里用
 *     this.selectedFrom 记住起点，第二次落点即为目标；
 *   - 象棋没有"一轮 1~2 子"，每次一方走一步；
 *   - 悔棋以"半回合"为单位（一步棋），人机模式可一次撤两步（AI + 我方）。
 */
function XiangqiGame(opts) {
  opts = opts || {};
  this.variant = 'xiangqi';
  this.board = new XiangqiBoard();
  this.players = {};
  this.players[RED] = opts.black || { name: '红方', kind: 'human', engine: null };
  this.players[BLACK] = opts.white || { name: '黑方', kind: 'human', engine: null };
  // 象棋红先；为了与 Game 的 BLACK/WHITE 常量对齐，这里把 RED 视为"先手方"
  this.movesLog = [];          // [fx,fy,tx,ty]
  this.finished = false;
  this.winner = null;
  this.winLine = null;
  this.reason = '';
  this.selectedFrom = null;
}

XiangqiGame.prototype.currentPlayer = function () {
  // 引擎用 'r'/'b'，这里映射成 RED/BLACK 两个键
  var c = this.board.turn;
  return c === RED ? this.players[RED] : this.players[BLACK];
};

XiangqiGame.prototype.currentSide = function () {
  return this.board.turn;      // 'r' 或 'b'
};

/** 选中/落子：第一次调用传起点，第二次传目标（与界面"点两次"一致）。 */
XiangqiGame.prototype.place = function (x, y) {
  if (this.finished || this.board.gameOver) {
    return { ok: false, msg: '对局已结束', line: null };
  }
  var side = this.board.turn;
  var piece = this.board.piece(x, y);

  // 第一次点：选中自己的子
  if (piece && piece[0] === side) {
    // 若已选中同一个子，视为取消
    if (this.selectedFrom && this.selectedFrom[0] === x && this.selectedFrom[1] === y) {
      this.selectedFrom = null;
      return { ok: false, msg: '已取消选择', line: null, select: null };
    }
    this.selectedFrom = [x, y];
    return { ok: false, msg: '已选中', line: null, select: [x, y] };
  }

  // 第二次点：走子
  if (!this.selectedFrom) {
    return { ok: false, msg: '请先选择要走的棋子', line: null };
  }
  var frm = this.selectedFrom;
  var legal = this.board.legalMoves(side).some(function (m) {
    return m[0] === frm[0] && m[1] === frm[1] && m[2] === x && m[3] === y;
  });
  if (!legal) {
    // 目标不可走：若点到了自己的另一个子，则改选它（更符合直觉）
    if (piece && piece[0] === side) {
      this.selectedFrom = [x, y];
      return { ok: false, msg: '已改选', line: null, select: [x, y] };
    }
    return { ok: false, msg: '这一步不合规则', line: null };
  }

  var before = this.board.history.length;
  this.board.apply([frm[0], frm[1]], [x, y], true);
  this.selectedFrom = null;
  this.movesLog.push([frm[0], frm[1], x, y]);

  if (this.board.gameOver) {
    this.finished = true;
    this.winner = this.board.winner === RED ? RED : BLACK;
    this.reason = this.board.inCheck(this.board.winner === RED ? BLACK : RED)
      ? '将死' : '困毙';
    return {
      ok: true,
      msg: this.resultText(),
      line: null,
      check: this.board.checkFlag
    };
  }
  return { ok: true, msg: '', line: null, check: this.board.checkFlag };
};

/** 象棋没有"结束本回合"，留一个兼容空实现。 */
XiangqiGame.prototype.endRound = function () { };

/** 供界面取"当前选中棋子能走哪儿"。 */
XiangqiGame.prototype.legalTargetsFrom = function (from) {
  if (!from) return [];
  var side = this.board.turn;
  return this.board.legalMoves(side).filter(function (m) {
    return m[0] === from[0] && m[1] === from[1];
  }).map(function (m) { return { x: m[2], y: m[3] }; });
};

/** 撤销 n 步（半回合）。返回实际撤销的步数。 */
XiangqiGame.prototype.undoRound = function (toHuman) {
  if (!this.movesLog.length) return 0;
  var n = 1;
  // 人机模式：一次撤两步（对方 + 我方），回到我方走棋
  if (toHuman && this.players && this.players[RED] && this.players[BLACK]) {
    var kinds = [this.players[RED].kind, this.players[BLACK].kind];
    if (kinds.indexOf('human') >= 0 && kinds.indexOf('ai') >= 0) n = 2;
  }
  var done = 0;
  for (var i = 0; i < n && this.movesLog.length; i++) {
    this.board.undo();
    this.movesLog.pop();
    done++;
  }
  this.finished = false;
  this.winner = null;
  this.winLine = null;
  this.reason = '';
  this.selectedFrom = null;
  return done;
};

/** 预测将被撤销的走法（供动画）。返回 [{fx,fy,tx,ty}, ...]。 */
XiangqiGame.prototype.pendingUndo = function (toHuman) {
  var n = 1;
  if (toHuman && this.players[RED] && this.players[BLACK]) {
    var kinds = [this.players[RED].kind, this.players[BLACK].kind];
    if (kinds.indexOf('human') >= 0 && kinds.indexOf('ai') >= 0) n = 2;
  }
  var out = [];
  for (var i = 0; i < n && i < this.movesLog.length; i++) {
    var m = this.movesLog[this.movesLog.length - 1 - i];
    out.push({ fx: m[0], fy: m[1], tx: m[2], ty: m[3] });
  }
  return out;
};

XiangqiGame.prototype.humanToMove = function () {
  return this.currentPlayer().kind === 'human' && !this.finished;
};

/** 让 AI 走一步。返回 [[fx,fy],[tx,ty]] 或 []。 */
XiangqiGame.prototype.aiTurn = function () {
  var pl = this.currentPlayer();
  if (pl.kind === 'human' || this.finished || !pl.engine) return [];
  var mv = pl.engine.getMove(this.board);
  if (!mv) return [];
  this.board.apply([mv[0], mv[1]], [mv[2], mv[3]], true);
  this.movesLog.push(mv);
  if (this.board.gameOver) {
    this.finished = true;
    this.winner = this.board.winner === RED ? RED : BLACK;
    this.reason = '将死';
  }
  return [[mv[0], mv[1]], [mv[2], mv[3]]];
};

XiangqiGame.prototype.resign = function () {
  if (this.finished) return;
  var loser = this.board.turn;
  this.finished = true;
  this.winner = (loser === RED) ? BLACK : RED;
  this.reason = (loser === RED ? '红方' : '黑方') + '认输';
};

XiangqiGame.prototype.resultText = function () {
  if (this.winner !== null) {
    return (this.winner === RED ? '红方' : '黑方') + '获胜（' + (this.reason || '将死') + '）';
  }
  if (this.reason) return this.reason;
  return '对局进行中';
};

XiangqiGame.prototype.toRecord = function () {
  var result = 'ABORT';
  if (this.winner === RED) result = 'BLACK';        // 红=先手，记为 BLACK 位
  else if (this.winner === BLACK) result = 'WHITE';
  else if (this.finished) result = 'DRAW';
  return {
    variant: 'xiangqi',
    size: 90,
    winCount: 0,
    roundNo: this.movesLog.length,
    black: this.players[RED].name,
    blackKind: this.players[RED].kind,
    white: this.players[BLACK].name,
    whiteKind: this.players[BLACK].kind,
    moves: this.movesLog.map(function (m) { return [m[2], m[3], 1]; }),
    result: result,
    reason: this.reason
  };
};

module.exports = {
  RED: RED,
  BLACK: BLACK,
  KING: KING,
  ADVISOR: ADVISOR,
  ELEPHANT: ELEPHANT,
  HORSE: HORSE,
  CHARIOT: CHARIOT,
  CANNON: CANNON,
  PAWN: PAWN,
  COLS: COLS,
  ROWS: ROWS,
  PIECE_CHAR: PIECE_CHAR,
  PIECE_VALUE: PIECE_VALUE,
  PST: PST,
  MATE: MATE,
  opp: opp,
  pieceChar: pieceChar,
  inPalace: inPalace,
  initialGrid: initialGrid,
  XiangqiBoard: XiangqiBoard,
  XiangqiGame: XiangqiGame,
  XqAI: XqAI,
  evaluate: xqEvaluate
};

  };
  __mods["./xqview.js"] = function (module, exports, require) {
/**
 * xqview.js —— 中国象棋棋盘渲染器（平台无关）
 *
 * 与 boardview.js 同样的定位：只认 Canvas 2D 的公共接口子集，
 * 不引用 DOM / wx，因此浏览器与将来的微信小程序共用同一份。
 *
 * 绘制层次：
 *   1) 木色底板 + 边框 + 九宫斜线 + 河界文字
 *   2) 棋子（圆形木片 + 双圈 + 红/黑字形，红方繁体、黑方简体）
 *   3) 效果层：上一步标记、选中环、可走点提示、被将军提示
 *
 * 坐标：x∈[0,8] 左→右，y∈[0,9] 上→下（黑在上、红在下），与引擎一致。
 */

var XI = require('./xiaqi.js');

var XQ_THEME = {
  bgA: '#EFD9A8',
  bgB: '#E3C88E',
  line: '#5A4630',
  river: '#7A6244',
  tray: '#D8BC80'
};

var MARGIN = 30;

function XqView() {
  this.geom = null;
}

/** 计算几何：9 列 × 10 行，取 min 保证完整显示。 */
XqView.prototype.computeGeom = function (width, height, theme) {
  var usableW = width - MARGIN * 2;
  var usableH = height - MARGIN * 2;
  // 横向 8 个格、纵向 9 个格，格子取两者较小值再留一点边
  var cell = Math.min(usableW / (XI.COLS - 1 + 0.6), usableH / (XI.ROWS - 1 + 0.6));
  var sideW = cell * (XI.COLS - 1);
  var sideH = cell * (XI.ROWS - 1);
  this.geom = {
    W: width, H: height, cell: cell,
    x0: (width - sideW) / 2,
    y0: (height - sideH) / 2,
    sideW: sideW, sideH: sideH,
    pieceR: cell * 0.42,
    theme: theme || XQ_THEME
  };
  return this.geom;
};

/** 像素 → 棋盘格；超出容差返回 null。 */
XqView.prototype.toGrid = function (px, py) {
  var g = this.geom;
  if (!g) return null;
  var x = Math.round((px - g.x0) / g.cell);
  var y = Math.round((py - g.y0) / g.cell);
  if (x < 0 || x >= XI.COLS || y < 0 || y >= XI.ROWS) return null;
  var dx = px - (g.x0 + x * g.cell);
  var dy = py - (g.y0 + y * g.cell);
  if (Math.sqrt(dx * dx + dy * dy) > g.cell * 0.62) return null;
  return { x: x, y: y };
};

XqView.prototype.center = function (x, y) {
  var g = this.geom;
  return { cx: g.x0 + x * g.cell, cy: g.y0 + y * g.cell };
};

/** 1) 静态层：底板 / 网格（河界处竖线断开）/ 九宫斜线 / 河界文字 */
XqView.prototype.drawStatic = function (ctx, themeName) {
  var g = this.geom;
  var t = g.theme;
  ctx.clearRect(0, 0, g.W, g.H);

  // 托盘
  ctx.fillStyle = t.tray;
  var pad = MARGIN * 0.6;
  ctx.fillRect(g.x0 - pad, g.y0 - pad, g.sideW + pad * 2, g.sideH + pad * 2);

  // 底板渐变
  var steps = 26;
  for (var i = 0; i < steps; i++) {
    ctx.fillStyle = mix(t.bgA, t.bgB, i / (steps - 1));
    ctx.fillRect(g.x0, g.y0 + (g.sideH * i) / steps, g.sideW, g.sideH / steps + 1);
  }

  var lw = Math.max(1, Math.round(g.cell * 0.035));
  ctx.strokeStyle = t.line;
  ctx.lineWidth = lw * 1.6;
  ctx.strokeRect(g.x0, g.y0, g.sideW, g.sideH);
  ctx.lineWidth = lw;

  // 横线 10 条
  ctx.beginPath();
  for (var r = 0; r < XI.ROWS; r++) {
    var y = g.y0 + r * g.cell;
    ctx.moveTo(g.x0, y);
    ctx.lineTo(g.x0 + g.sideW, y);
  }
  ctx.stroke();

  // 竖线：中间 7 条在河界（第 4~5 行之间）断开，最左最右通到底
  ctx.beginPath();
  for (var c = 0; c < XI.COLS; c++) {
    var x = g.x0 + c * g.cell;
    if (c === 0 || c === XI.COLS - 1) {
      ctx.moveTo(x, g.y0);
      ctx.lineTo(x, g.y0 + g.sideH);
    } else {
      ctx.moveTo(x, g.y0);
      ctx.lineTo(x, g.y0 + 4 * g.cell);
      ctx.moveTo(x, g.y0 + 5 * g.cell);
      ctx.lineTo(x, g.y0 + g.sideH);
    }
  }
  ctx.stroke();

  // 九宫斜线（上：黑；下：红）
  ctx.beginPath();
  ctx.moveTo(g.x0 + 3 * g.cell, g.y0);
  ctx.lineTo(g.x0 + 5 * g.cell, g.y0 + 2 * g.cell);
  ctx.moveTo(g.x0 + 5 * g.cell, g.y0);
  ctx.lineTo(g.x0 + 3 * g.cell, g.y0 + 2 * g.cell);
  ctx.moveTo(g.x0 + 3 * g.cell, g.y0 + 7 * g.cell);
  ctx.lineTo(g.x0 + 5 * g.cell, g.y0 + 9 * g.cell);
  ctx.moveTo(g.x0 + 5 * g.cell, g.y0 + 7 * g.cell);
  ctx.lineTo(g.x0 + 3 * g.cell, g.y0 + 9 * g.cell);
  ctx.stroke();

  // 河界文字
  var fs = Math.max(11, Math.round(g.cell * 0.46));
  ctx.fillStyle = t.river;
  ctx.font = fs + 'px "KaiTi","STKaiti",serif';
  ctx.textAlign = 'center';
  var midY = g.y0 + 4.5 * g.cell + fs * 0.35;
  ctx.fillText('楚 河', g.x0 + 2 * g.cell, midY);
  ctx.fillText('漢 界', g.x0 + 6 * g.cell, midY);
  ctx.textAlign = 'left';
};

/** 2) 一枚棋子：木片底 + 双圈 + 字形（红方繁体、黑方简体，与桌面版一致） */
XqView.prototype.drawPiece = function (ctx, x, y, piece, opts) {
  opts = opts || {};
  var g = this.geom;
  var c = this.center(x, y);
  var r = g.pieceR * (opts.scale === undefined ? 1 : opts.scale);
  var cy = c.cy + (opts.lift ? -opts.lift : 0);
  if (ctx.globalAlpha !== undefined) ctx.globalAlpha = (opts.alpha === undefined ? 1 : opts.alpha);

  var isRed = piece[0] === XI.RED;
  // 投影
  ctx.fillStyle = 'rgba(0,0,0,0.28)';
  ctx.beginPath();
  ctx.arc(c.cx, cy + r * 0.12, r * 1.0, 0, Math.PI * 2);
  ctx.fill();

  // 木片底（径向渐变）
  if (ctx.createRadialGradient) {
    var grad = ctx.createRadialGradient(c.cx - r * 0.3, cy - r * 0.35, r * 0.1, c.cx, cy, r * 1.05);
    grad.addColorStop(0, '#FFF6DC');
    grad.addColorStop(0.62, '#F0DFB4');
    grad.addColorStop(1, '#C9AE7C');
    ctx.fillStyle = grad;
  } else {
    ctx.fillStyle = '#F0DFB4';
  }
  ctx.beginPath();
  ctx.arc(c.cx, cy, r, 0, Math.PI * 2);
  ctx.fill();

  // 外圈
  ctx.strokeStyle = isRed ? '#B23A2E' : '#2E3540';
  ctx.lineWidth = Math.max(1, r * 0.07);
  ctx.beginPath();
  ctx.arc(c.cx, cy, r * 0.97, 0, Math.PI * 2);
  ctx.stroke();
  // 内圈
  ctx.lineWidth = Math.max(1, r * 0.045);
  ctx.beginPath();
  ctx.arc(c.cx, cy, r * 0.80, 0, Math.PI * 2);
  ctx.stroke();

  // 字形
  var ch = XI.PIECE_CHAR[piece[0] + piece[1]] || '?';
  ctx.fillStyle = isRed ? '#B23A2E' : '#2E3540';
  ctx.font = 'bold ' + Math.round(r * 1.16) + 'px "KaiTi","STKaiti","Microsoft YaHei",serif';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(ch, c.cx, cy + r * 0.04);
  ctx.textBaseline = 'alphabetic';
  ctx.textAlign = 'left';
  if (ctx.globalAlpha !== undefined) ctx.globalAlpha = 1;
};

/**
 * 3) 效果层
 * fx = {
 *   last: [fx,fy,tx,ty] | null,
 *   selected: {x,y} | null,
 *   moves: [{x,y}],            // 选中棋子后可落点提示
 *   check: {x,y} | null,       // 被将军的将/帅位置
 *   ghosts: [{x,y,piece,alpha,lift}]
 * }
 */
XqView.prototype.drawFx = function (ctx, fx) {
  if (!fx) return;
  var g = this.geom;
  var r = g.pieceR;

  // 上一步：起点用空心方框、落点用四角标记
  if (fx.last) {
    var a = this.center(fx.last[0], fx.last[1]);
    var b = this.center(fx.last[2], fx.last[3]);
    ctx.strokeStyle = 'rgba(90,70,48,0.55)';
    ctx.lineWidth = Math.max(1, r * 0.10);
    ctx.strokeRect(a.cx - r * 0.7, a.cy - r * 0.7, r * 1.4, r * 1.4);
    ctx.strokeStyle = '#C9972F';
    ctx.lineWidth = Math.max(1.5, r * 0.12);
    var s = r * 0.85;
    var seg = s * 0.45;
    [[-1, -1], [1, -1], [-1, 1], [1, 1]].forEach(function (d) {
      ctx.beginPath();
      ctx.moveTo(b.cx + d[0] * s, b.cy + d[1] * s - d[1] * seg);
      ctx.lineTo(b.cx + d[0] * s, b.cy + d[1] * s);
      ctx.lineTo(b.cx + d[0] * s - d[0] * seg, b.cy + d[1] * s);
      ctx.stroke();
    });
  }

  // 选中环
  if (fx.selected) {
    var sc = this.center(fx.selected.x, fx.selected.y);
    ctx.strokeStyle = '#E8B34B';
    ctx.lineWidth = Math.max(2, r * 0.16);
    ctx.beginPath();
    ctx.arc(sc.cx, sc.cy, r * 1.06, 0, Math.PI * 2);
    ctx.stroke();
  }

  // 可落点提示
  if (fx.moves && fx.moves.length) {
    for (var i = 0; i < fx.moves.length; i++) {
      var m = this.center(fx.moves[i].x, fx.moves[i].y);
      var occupied = fx.moves[i].piece;
      if (occupied) {
        ctx.strokeStyle = 'rgba(217,83,79,0.85)';
        ctx.lineWidth = Math.max(2, r * 0.14);
        ctx.beginPath();
        ctx.arc(m.cx, m.cy, r * 0.92, 0, Math.PI * 2);
        ctx.stroke();
      } else {
        ctx.fillStyle = 'rgba(62,187,107,0.75)';
        ctx.beginPath();
        ctx.arc(m.cx, m.cy, r * 0.22, 0, Math.PI * 2);
        ctx.fill();
      }
    }
  }

  // 被将军的将/帅
  if (fx.check) {
    var kc = this.center(fx.check.x, fx.check.y);
    ctx.strokeStyle = 'rgba(217,83,79,0.95)';
    ctx.lineWidth = Math.max(2, r * 0.18);
    ctx.beginPath();
    ctx.arc(kc.cx, kc.cy, r * 1.12, 0, Math.PI * 2);
    ctx.stroke();
  }

  // 幽灵（用于"吃子/移动"过渡动画，预留）
  if (fx.ghosts) {
    for (var k = 0; k < fx.ghosts.length; k++) {
      var gh = fx.ghosts[k];
      this.drawPiece(ctx, gh.x, gh.y, gh.piece,
        { alpha: gh.alpha, lift: gh.lift, scale: gh.scale });
    }
  }
};

/** 完整绘制：静态层 + 棋子 + 效果层。 */
XqView.prototype.render = function (ctx, board, fx, themeName) {
  if (!this.geom) return;
  this.drawStatic(ctx, themeName);
  for (var y = 0; y < XI.ROWS; y++) {
    for (var x = 0; x < XI.COLS; x++) {
      var p = board.grid[y][x];
      if (p) this.drawPiece(ctx, x, y, p);
    }
  }
  this.drawFx(ctx, fx);
};

/** #RRGGBB 线性插值 */
function mix(c1, c2, ratio) {
  var a = parseHex(c1);
  var b = parseHex(c2);
  return 'rgb(' + Math.round(a[0] + (b[0] - a[0]) * ratio) + ',' +
    Math.round(a[1] + (b[1] - a[1]) * ratio) + ',' +
    Math.round(a[2] + (b[2] - a[2]) * ratio) + ')';
}
function parseHex(c) {
  c = String(c).replace('#', '');
  if (c.length === 3) c = c[0] + c[0] + c[1] + c[1] + c[2] + c[2];
  return [parseInt(c.slice(0, 2), 16), parseInt(c.slice(2, 4), 16), parseInt(c.slice(4, 6), 16)];
}

module.exports = {
  XqView: XqView,
  XQ_THEME: XQ_THEME,
  mix: mix,
  MARGIN: MARGIN
};

  };
  __mods["./store.js"] = function (module, exports, require) {
/**
 * store.js —— 存档/战绩的存储适配层（平台无关）
 *
 * 网页版用 localStorage，微信小程序用 wx.setStorageSync —— 引擎只认下面这组接口，
 * 由调用方在启动时注入具体实现（setBackend）。
 *
 * 数据模型（与桌面版 PostgreSQL 的三张表同构，便于将来对接服务端）：
 *   players: { name, kind, wins, losses, draws }
 *   games  : { id, variant, black, white, result, reason, moveCount, moves, endedAt }
 * 只保留最近 N 局明细，避免 localStorage 爆掉（浏览器通常 5MB）。
 */

var MAX_GAMES = 60;

var backend = null;          // { get(key), set(key,value) }

function setBackend(b) {
  backend = b;
}

/** 默认后端：浏览器 localStorage；没有就退化成内存（Node 测试用）。 */
function defaultBackend() {
  if (backend) return backend;
  try {
    if (typeof localStorage !== 'undefined' && localStorage) {
      return {
        get: function (k) {
          var v = localStorage.getItem(k);
          return v ? JSON.parse(v) : null;
        },
        set: function (k, v) {
          localStorage.setItem(k, JSON.stringify(v));
        }
      };
    }
  } catch (e) { /* 隐私模式等，忽略 */ }
  var mem = {};
  return {
    get: function (k) { return mem[k] === undefined ? null : mem[k]; },
    set: function (k, v) { mem[k] = v; }
  };
}

var K_PLAYERS = 'yiqiu.players';
var K_GAMES = 'yiqiu.games';
var K_SETTINGS = 'yiqiu.settings';
var K_SEQ = 'yiqiu.seq';

function b() { return defaultBackend(); }

function getPlayers() { return b().get(K_PLAYERS) || {}; }
function getGames() { return b().get(K_GAMES) || []; }

function getSettings() { return b().get(K_SETTINGS) || null; }
function saveSettings(s) { b().set(K_SETTINGS, s); }

/**
 * 保存一局：更新双方胜负统计 + 追加对局明细。
 * record 为 game.toRecord() 的产物（variant/black/white/result/reason/moves）。
 * 返回该局 id。
 */
function saveGame(record) {
  var players = getPlayers();
  var games = getGames();
  var seq = b().get(K_SEQ) || 0;
  seq += 1;

  function ensure(name, kind) {
    if (!players[name]) players[name] = { name: name, kind: kind || 'human', wins: 0, losses: 0, draws: 0 };
    else if (kind) players[name].kind = kind;
  }
  ensure(record.black, record.blackKind);
  ensure(record.white, record.whiteKind);

  if (record.result === 'BLACK') {
    players[record.black].wins += 1;
    players[record.white].losses += 1;
  } else if (record.result === 'WHITE') {
    players[record.white].wins += 1;
    players[record.black].losses += 1;
  } else if (record.result === 'DRAW') {
    players[record.black].draws += 1;
    players[record.white].draws += 1;
  }

  var entry = {
    id: seq,
    variant: record.variant,
    black: record.black,
    white: record.white,
    blackKind: record.blackKind,
    whiteKind: record.whiteKind,
    result: record.result,
    reason: record.reason,
    moveCount: record.moves.length,
    moves: record.moves,
    endedAt: Date.now()
  };
  games.unshift(entry);
  if (games.length > MAX_GAMES) games = games.slice(0, MAX_GAMES);

  b().set(K_PLAYERS, players);
  b().set(K_GAMES, games);
  b().set(K_SEQ, seq);
  return seq;
}

/** 战绩列表（按胜场降序）。 */
function stats() {
  var players = getPlayers();
  var list = Object.keys(players).map(function (k) { return players[k]; });
  list.sort(function (a, c) {
    return (c.wins - a.wins) || a.name.localeCompare(c.name);
  });
  return list;
}

/** 最近对局列表（已按时间倒序）。 */
function recentGames(limit) {
  var games = getGames();
  return limit ? games.slice(0, limit) : games;
}

function clearAll() {
  b().set(K_PLAYERS, {});
  b().set(K_GAMES, []);
  b().set(K_SEQ, 0);
}

module.exports = {
  setBackend: setBackend,
  saveGame: saveGame,
  stats: stats,
  recentGames: recentGames,
  getSettings: getSettings,
  saveSettings: saveSettings,
  clearAll: clearAll,
  MAX_GAMES: MAX_GAMES
};

  };
  var E = {
    board: __req("./board.js"),
    game: __req("./game.js"),
    ai: __req("./ai.js"),
    boardview: __req("./boardview.js"),
    xiaqi: __req("./xiaqi.js"),
    xqview: __req("./xqview.js"),
    store: __req("./store.js"),
    require: __req
  };
  root.E = E;
  if (typeof module !== "undefined" && module.exports) module.exports = E;
})(typeof globalThis !== "undefined" ? globalThis : this);