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
