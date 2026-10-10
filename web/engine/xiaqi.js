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

// ------------------------------------------------------------------ Zobrist 哈希
// 用确定性 LCG 生成 14 种（红/黑 × 7 种棋子）× 90 格的随机键 + 1 个"黑方走棋"键。
// 确定性是为了：主线程与 Worker 重建同一局面得到同一哈希（开局库/置换表口径一致）。
var ZOBRIST = (function () {
  var s = 0x1234ABCD >>> 0;
  function rnd() { s = (s * 1664525 + 1013904223) >>> 0; return s; }
  var n = 14 * (COLS * ROWS) + 1;      // 14 类棋子 × 90 格 + 1 个 side-to-move 键
  var table = new Array(n);
  for (var i = 0; i < n; i++) table[i] = rnd();
  return {
    table: table,
    BLACK_TO_MOVE: 14 * (COLS * ROWS)
  };
})();

// 棋子在 Zobrist 表中的基址：colorIdx(0/1) × 7 + kindIdx
var KIND_IDX = { K: 0, A: 1, E: 2, H: 3, R: 4, C: 5, P: 6 };
function zobBase(color, kind) {
  var ci = (color === RED) ? 0 : 1;
  return (ci * 7 + KIND_IDX[kind]) * (COLS * ROWS);
}
function zobAt(color, kind, square) {
  return ZOBRIST.table[zobBase(color, kind) + square];
}

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
  this.recomputeZobrist();
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
  return this.isAttacked(kp[0], kp[1], opp(color));
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
XiangqiBoard.prototype.isAttacked = function (tx, ty, byColor, gridOverride) {
  var g = gridOverride || this.grid;
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
  var orth = [[0, -1], [0, 1], [-1, 0], [1, 0]];
  for (var d = 0; d < 4; d++) {
    var dx = orth[d][0], dy = orth[d][1];

    // ---- (1) 车 / 将：第一个遇到的子是敌车或敌将 → 攻击 ----
    i = tx + dx; j = ty + dy;
    while (i >= 0 && i < COLS && j >= 0 && j < ROWS) {
      p = at(i, j);
      if (p) {
        if (p[0] === byColor && (p[1] === CHARIOT || p[1] === KING)) {
          if (TRACE) console.log('XQ 命中: 车/将 (' + i + ',' + j + ')');
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
  var horseSpots = [
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

  // 增量 Zobrist：撤掉被吃子、移走源、落下目标、翻转走棋方
  if (captured) this.zobrist ^= zobAt(captured[0], captured[1], ty * COLS + tx);
  this.zobrist ^= zobAt(moving[0], moving[1], fy * COLS + fx);
  this.zobrist ^= zobAt(moving[0], moving[1], ty * COLS + tx);
  this.zobrist ^= ZOBRIST.table[ZOBRIST.BLACK_TO_MOVE];

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
  if (!this.legalMoves(this.turn).length) {
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

  // 逆推 Zobrist（与 apply 的逆操作，XOR 自反）
  this.zobrist ^= ZOBRIST.table[ZOBRIST.BLACK_TO_MOVE];
  this.zobrist ^= zobAt(moving[0], moving[1], ty * COLS + tx);
  this.zobrist ^= zobAt(moving[0], moving[1], fy * COLS + fx);
  if (captured) this.zobrist ^= zobAt(captured[0], captured[1], ty * COLS + tx);

  this.grid[fy][fx] = moving;
  this.grid[ty][tx] = captured;
  this.turn = opp(this.turn);
  this.gameOver = false;
  this.winner = null;
  var prev = this.history.length ? this.history[this.history.length - 1] : null;
  this.lastMove = prev ? [prev[0], prev[1], prev[2], prev[3]] : null;
  this.checkFlag = this.inCheck(this.turn);
};

/** 从当前 grid/turn 重新算一遍 Zobrist（用于从快照重建的局面，如 Worker）。 */
XiangqiBoard.prototype.recomputeZobrist = function () {
  var h = 0;
  for (var y = 0; y < ROWS; y++) {
    for (var x = 0; x < COLS; x++) {
      var p = this.grid[y][x];
      if (!p) continue;
      h ^= zobAt(p[0], p[1], y * COLS + x);
    }
  }
  if (this.turn === BLACK) h ^= ZOBRIST.table[ZOBRIST.BLACK_TO_MOVE];
  this.zobrist = h;
};

/** 空着（null move）：只翻转走棋方，供空着裁剪使用。 */
XiangqiBoard.prototype.applyNullMove = function () {
  this.zobrist ^= ZOBRIST.table[ZOBRIST.BLACK_TO_MOVE];
  this.turn = opp(this.turn);
};
XiangqiBoard.prototype.undoNullMove = function () {
  this.zobrist ^= ZOBRIST.table[ZOBRIST.BLACK_TO_MOVE];
  this.turn = opp(this.turn);
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
 * 所以这里手写一个纯 JS 引擎，按**经典棋力配方**（参考 ElephantEye / cchess-engine
 * 的公开做法，属工程最佳实践而非某篇论文）：
 *   迭代加深 + 置换表(Zobrist) + 负极大值(negamax) + 主变例搜索(PVS) +
 *   空着裁剪(Null-Move) + Late Move Reductions + 将军/应将延伸 + 杀手/历史表 +
 *   走法排序(TT→MVV-LVA→杀手→历史) + 含应将的静态搜索(quiescence) +
 *   开局库（代码常量，零权重文件）+ 子力/位置表/机动性/将帅安全/车占线评估。
 */
var MATE = 30000;                     // 将死分值（与普通子力分拉开量级）
var INF = 1000000;                   // 正无穷（须 > MATE）
var R_NULL = 2;                      // 空着裁剪缩减深度
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
  var wx = (color === RED) ? x : (8 - x);
  return row[wx] || 0;
}

/** 将帅暴露度：被攻击 + 王宫周围被压制，越危险扣分越多（红方视角）。 */
function kingDanger(board, kp, byColor) {
  var danger = 0;
  if (board.isAttacked(kp[0], kp[1], byColor)) danger += 60;
  var neigh = [[0, 1], [0, -1], [1, 0], [-1, 0], [1, 1], [1, -1], [-1, 1], [-1, -1]];
  for (var i = 0; i < neigh.length; i++) {
    var nx = kp[0] + neigh[i][0], ny = kp[1] + neigh[i][1];
    if (nx < 0 || nx >= COLS || ny < 0 || ny >= ROWS) continue;
    if (board.isAttacked(nx, ny, byColor)) danger += 12;
  }
  return danger;
}

/** 车占开放/半开放线加分（红方视角）。 */
function rookFileBonus(board) {
  var grid = board.grid;
  var bonus = 0;
  for (var y = 0; y < ROWS; y++) {
    for (var x = 0; x < COLS; x++) {
      var p = grid[y][x];
      if (!p || p[1] !== CHARIOT) continue;
      var own = (p[0] === RED) ? 1 : -1;
      // 数该列上的"阻挡子"（除自己与将/帅外）
      var blockers = 0;
      for (var yy = 0; yy < ROWS; yy++) {
        if (yy === y) continue;
        var q = grid[yy][x];
        if (q && q[1] !== KING && q[1] !== CHARIOT) blockers++;
      }
      if (blockers === 0) bonus += 22 * own;
      else if (blockers === 1) bonus += 10 * own;
    }
  }
  return bonus;
}

/**
 * 局面评估（**红方视角**，返回值越大红方越好）。
 * 组成：子力 + 位置表 + 机动性 + 将帅安全 + 车占线。
 * 注意：实战里"谁走棋"会额外影响，搜索时用 negamax 交替取负处理。
 */
function xqEvaluate(board) {
  var grid = board.grid;
  var score = 0;
  var mobility = { r: 0, b: 0 };

  for (var y = 0; y < ROWS; y++) {
    for (var x = 0; x < COLS; x++) {
      var p = grid[y][x];
      if (!p) continue;
      var kind = p[1];
      var color = p[0];
      var v = PIECE_VALUE[kind] || 0;
      v += pstOf(kind, color, x, y);

      if (kind === CHARIOT || kind === CANNON || kind === HORSE) {
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
  score += rookFileBonus(board);

  // 将帅安全：被将军/周围受压扣分
  var redKing = board.findKing(RED);
  var blackKing = board.findKing(BLACK);
  if (redKing) score -= kingDanger(board, redKing, BLACK);
  if (blackKing) score += kingDanger(board, blackKing, RED);

  return score;
}

// ------------------------------------------------------------------ 走法排序
function moveKey(mv) { return ((mv[0] * 10 + mv[1]) * 100) + (mv[2] * 10 + mv[3]); }

// ------------------------------------------------------------------ 开局库（代码常量，零权重文件）
// 每条线是一串合法着法（红先、双方交替）；引擎在开局阶段（手数较少且实际对局
// 完全吻合某条线的前缀）时按库走，避免"开局乱走"。对手一旦偏离，前缀不匹配即
// 退回正常搜索。坐标是本引擎棋盘坐标（x∈[0,8], y∈[0,9]，红在下方）。
var OPENING_BOOK = [
  // 中炮对屏风马
  [[1,7,4,7],[7,2,4,2],[1,9,2,7],[7,0,6,2],[7,9,6,7],[1,0,2,2],[0,9,1,9],[8,0,7,0]],
  // 仙人指路（进兵）
  [[4,6,4,5],[4,3,4,4],[1,9,2,7],[7,0,6,2],[7,9,6,7],[1,0,2,2],[0,9,1,9],[8,0,7,0]],
  // 飞相局
  [[2,9,4,7],[6,0,4,2],[1,9,2,7],[7,0,6,2],[7,9,6,7],[1,0,2,2],[0,9,1,9],[8,0,7,0]],
  // 过宫炮
  [[1,7,3,7],[7,2,5,2],[1,9,2,7],[7,0,6,2],[7,9,6,7],[1,0,2,2],[0,9,1,9],[8,0,7,0]],
  // 右中炮（从右炮起）
  [[7,7,4,7],[1,2,4,2],[7,9,6,7],[1,0,2,2],[1,9,2,7],[7,0,6,2],[0,9,1,9],[8,0,7,0]],
  // 起马局（先跳马）
  [[1,9,2,7],[7,0,6,2],[1,7,4,7],[7,2,4,2],[7,9,6,7],[1,0,2,2],[0,9,1,9],[8,0,7,0]],
  // 进兵 + 中炮（过渡）
  [[4,6,4,5],[4,3,4,4],[1,7,4,7],[7,2,4,2],[1,9,2,7],[7,0,6,2],[0,9,1,9],[8,0,7,0]],
  // 进七兵起马
  [[0,6,0,5],[0,3,0,4],[1,9,2,7],[7,0,6,2],[1,7,4,7],[7,2,4,2],[7,9,6,7],[1,0,2,2]]
];

function moveEq(a, b) {
  return a[0] === b[0] && a[1] === b[1] && a[2] === b[2] && a[3] === b[3];
}
function bookMatches(line, hist) {
  if (line.length < hist.length + 1) return false;
  for (var k = 0; k < hist.length; k++) {
    if (!moveEq([hist[k][0], hist[k][1], hist[k][2], hist[k][3]], line[k])) return false;
  }
  return true;
}

function XqAI(level, seed) {
  this.level = level || 'medium';
  // 三档：深度上限 + 时限(ms) + 是否开启静态搜索
  // hard 档加深（配合空着裁剪/LMR，实际搜索深度远超 6 层）且不超时（受 deadline 保护）
  var prof = {
    easy:   { depth: 2, time: 400,  quiesce: true, rand: true },
    medium: { depth: 6, time: 1800, quiesce: true, rand: false },
    hard:   { depth: 10, time: 5000, quiesce: true, rand: false }
  }[this.level] || { depth: 6, time: 1800, quiesce: true, rand: false };
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
  this.useBook = true;            // 是否启用开局库（测试/纯搜索时可关）
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
  return board.movesOf(color);
};

/** 走法排序分：吃子(MVV-LVA, 赢子更优) > 杀手 > 历史 > 其他。 */
XqAI.prototype.scoreMove = function (board, mv, color, ply) {
  var target = board.grid[mv[3]][mv[2]];
  var s = 0;
  if (target) {
    var victim = PIECE_VALUE[target[1]] || 0;
    var attacker = PIECE_VALUE[(board.grid[mv[1]][mv[0]] || [0, 'P'])[1]] || 0;
    var win = victim >= attacker;
    // 赢子（吃相等或更大子）优先；其次按 MVV-LVA
    s = 1000000 + victim * 10 - attacker + (win ? 500000 : 0);
  } else {
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
  }
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

XqAI.prototype._moveToFront = function (moves, mv) {
  var out = [mv];
  for (var i = 0; i < moves.length; i++) {
    var m = moves[i];
    if (m[0] === mv[0] && m[1] === mv[1] && m[2] === mv[2] && m[3] === mv[3]) continue;
    out.push(m);
  }
  return out;
};

/** 当前方是否有"非兵非将"的棋子（避免空着裁剪在逼和/zugzwang 局面下误判）。 */
XqAI.prototype._hasNonPawn = function (board, color) {
  for (var y = 0; y < ROWS; y++) {
    for (var x = 0; x < COLS; x++) {
      var p = board.grid[y][x];
      if (p && p[0] === color && p[1] !== PAWN && p[1] !== KING) return true;
    }
  }
  return false;
};

XqAI.prototype._storeKiller = function (ply, mv) {
  var ks = this.killers[ply] || (this.killers[ply] = []);
  for (var i = 0; i < ks.length; i++) {
    if (ks[i][0] === mv[0] && ks[i][1] === mv[1] && ks[i][2] === mv[2] && ks[i][3] === mv[3]) return;
  }
  ks.unshift(mv);
  if (ks.length > 2) ks.length = 2;
};

/** 吃子/应将静态搜索：避免"地平线效应"把亏子看成不亏。 */
XqAI.prototype.quiesce = function (board, color, alpha, beta, qdepth) {
  if (this.stopFlag) return 0;
  if ((this.nodes++ & 511) === 0 && this._timeUp()) { this.stopFlag = true; return 0; }

  if (!board.findKing(color)) return -(MATE - 1);

  var checked = board.inCheck(color);

  // 被将军：搜全部应将着法（找杀/解将），否则即被将死
  if (checked) {
    if (qdepth <= -8) return xqEvaluate(board) * (color === RED ? 1 : -1);
    var ev = this.genMoves(board, color);
    var best = -INF;
    var any = 0;
    for (var e = 0; e < ev.length; e++) {
      var em = ev[e];
      board.apply([em[0], em[1]], [em[2], em[3]], false);
      if (board.inCheck(color)) { board.undo(); continue; }
      any++;
      var val = -this.quiesce(board, opp(color), -beta, -alpha, qdepth - 1);
      board.undo();
      if (this.stopFlag) return 0;
      if (val > best) best = val;
      if (val > alpha) alpha = val;
      if (alpha >= beta) break;
    }
    if (any === 0) return -(MATE - 50);   // 被将死（无应将）
    return best;
  }

  var stand = xqEvaluate(board) * (color === RED ? 1 : -1);
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
    var val = -this.quiesce(board, opp(color), -beta, -alpha, qdepth - 1);
    board.undo();
    if (this.stopFlag) return 0;
    if (val >= beta) return beta;
    if (val > alpha) alpha = val;
  }
  return alpha;
};

/**
 * 主搜索：negamax(负极大值) + PVS(主变例搜索) + 置换表 + 空着裁剪 +
 * Late Move Reductions + 将军/应将延伸。
 *
 * 置换表按 Zobrist(局面+行棋方) 存，深度单独比较（行业标准做法）：
 *   键 = 局面 + 行棋方（不含深度）；
 *   只有当"存下来的搜索深度 >= 当前需要的深度"时才允许直接返回。
 */
XqAI.prototype.search = function (board, color, depth, alpha, beta, ply) {
  if (this.stopFlag) return 0;
  if ((this.nodes++ & 255) === 0 && this._timeUp()) { this.stopFlag = true; return 0; }

  var checked = board.inCheck(color);

  // 将军延伸：被将军时把这一层再延伸一截，避免把杀棋推到地平线下
  if (checked && depth < 16) depth += 1;

  if (depth <= 0) {
    return this.useQuiesce
      ? this.quiesce(board, color, alpha, beta, 4)
      : xqEvaluate(board) * (color === RED ? 1 : -1);
  }

  // 置换表
  var key = board.zobrist;
  var hit = this.tt[key];
  var ttMove = null;
  if (hit) {
    ttMove = hit[3];
    if (hit[0] >= depth) {
      if (hit[1] === 0) return hit[2];
      else if (hit[1] === 1 && hit[2] >= beta) return hit[2];
      else if (hit[1] === 2 && hit[2] <= alpha) return hit[2];
    }
  }

  // 空着裁剪（Null-Move Pruning，R=2）：非将军、深度足够、且非逼和局面时，
  // 让对方"白走一步"若仍不劣于 beta，则本节点大概率已足够好，直接剪枝。
  if (!checked && depth >= 3 && this._hasNonPawn(board, color) && !ttMove) {
    board.applyNullMove();
    var nval = -this.search(board, opp(color), depth - 1 - R_NULL, -beta, -beta + 1, ply + 1);
    board.undoNullMove();
    if (this.stopFlag) return 0;
    if (nval >= beta) {
      // 验证搜索（防止空着裁剪误剪关键变化）：用稍大窗口再确认一次
      var vrf = -this.search(board, opp(color), depth - 1 - R_NULL, -beta, -alpha, ply + 1);
      if (this.stopFlag) return 0;
      if (vrf >= beta) return beta;
    }
  }

  var moves = this.orderMoves(board, this.genMoves(board, color), color, ply);
  if (ttMove) moves = this._moveToFront(moves, ttMove);

  var bestVal = -INF;
  var bestMove = null;
  var legalCount = 0;
  var alphaOrig = alpha;

  for (var i = 0; i < moves.length; i++) {
    var mv = moves[i];
    var captured = board.grid[mv[3]][mv[2]];
    var isCapture = !!captured;

    board.apply([mv[0], mv[1]], [mv[2], mv[3]], false);
    if (board.inCheck(color)) { board.undo(); continue; }    // 走完自己被将 → 非法
    legalCount += 1;

    var val;
    var isFirst = (legalCount === 1);
    // LMR：对非首着、非吃子的"后来着法"缩减深度（越靠后缩减越多）
    var sd = depth - 1;
    if (!isFirst && !isCapture && depth >= 3 && legalCount >= 3) {
      var red = 1 + Math.floor(Math.log(legalCount + 1));
      if (red > sd - 1) red = Math.max(0, sd - 1);
      if (red > 0) {
        val = -this.search(board, board.turn, sd - red, -alpha - 1, -alpha, ply + 1);
        if (val > alpha) {
          val = -this.search(board, board.turn, sd, -beta, -alpha, ply + 1);
        }
      } else {
        val = -this.search(board, board.turn, sd, -alpha - 1, -alpha, ply + 1);
        if (val > alpha && val < beta) val = -this.search(board, board.turn, sd, -beta, -alpha, ply + 1);
      }
    } else if (isFirst) {
      val = -this.search(board, board.turn, sd, -beta, -alpha, ply + 1);
    } else {
      // PVS 空窗：先用 [-alpha-1, -alpha] 试探，越界再全窗复搜
      val = -this.search(board, board.turn, sd, -alpha - 1, -alpha, ply + 1);
      if (val > alpha && val < beta) {
        val = -this.search(board, board.turn, sd, -beta, -alpha, ply + 1);
      }
    }
    board.undo();
    if (this.stopFlag) return (bestVal === -INF) ? 0 : bestVal;

    if (val > bestVal) { bestVal = val; bestMove = mv; }
    if (val > alpha) alpha = val;
    if (alpha >= beta) {
      if (!isCapture) {
        this._storeKiller(ply, mv);
        this.historyTbl[moveKey(mv)] = (this.historyTbl[moveKey(mv)] || 0) + depth * depth;
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

/** 对外：给当前行棋方选一手。返回 [fx,fy,tx,ty] 或 null。 */
XqAI.prototype.getMove = function (board) {
  this.nodes = 0;
  this.stopFlag = false;
  this.tt = {};               // 每次请求清表（单局面内迭代加深复用）
  this.killers = [];
  this.historyTbl = {};
  board.recomputeZobrist();
  this.deadline = Date.now() + this.timeLimit;
  var color = board.turn;

  var roots = board.legalMoves(color);
  if (!roots.length) return null;
  if (roots.length === 1) return roots[0];

  // 开局库：仅在前若干手且实际对局完全吻合某条线前缀时启用
  if (this.useBook && board.history.length <= 12 && this.level !== 'easy') {
    var bm = this._bookMove(board);
    if (bm) {
      for (var li = 0; li < roots.length; li++) {
        if (roots[li][0] === bm[0] && roots[li][1] === bm[1] &&
            roots[li][2] === bm[2] && roots[li][3] === bm[3]) {
          this.lastDepth = 1; this.lastScore = 0;
          return bm;
        }
      }
    }
  }

  // 简单档：只看一手吃子收益 + 少量随机，给玩家留活路
  if (this.level === 'easy') {
    var best = roots[0], bestV = -INF;
    for (var i = 0; i < roots.length; i++) {
      var mv = roots[i];
      var cap = board.grid[mv[3]][mv[2]];
      var v = cap ? (PIECE_VALUE[cap[1]] || 0) : 0;
      v += this._rng() * 30;                       // 随机扰动，别每局一样
      board.apply([mv[0], mv[1]], [mv[2], mv[3]]);
      if (board.inCheck(opp(color))) v += 40;
      board.undo();
      if (v > bestV) { bestV = v; best = mv; }
    }
    return best;
  }

  var bestMove = roots[0];
  var bestScore = -INF;
  var prevScore = 0;
  var ordered = this.orderMoves(board, roots, color, 0);

  // 迭代加深：逐层加深，每层先把上一层最好的着法排到最前（置换表/历史启发也起作用）
  for (var depth = 2; depth <= this.maxDepth; depth += 1) {
    var alpha = -INF, beta = INF;
    if (depth >= 4 && Math.abs(prevScore) < MATE - 1000) {
      // 渴望窗口（aspiration）：在上一手评分附近收口，提升剪枝效率；
      // 若越界则全窗复搜。
      var asp = 40 + depth * 4;
      alpha = Math.max(-INF, prevScore - asp);
      beta = Math.min(INF, prevScore + asp);
    }
    var alphaOrig = alpha;            // 留底，用于判断渴望窗口是否越界（不能用循环后被抬高的 alpha）
    var iterBest = null, iterScore = -INF;
    var localOrder = (bestMove && bestScore > -INF) ? this._moveToFront(ordered, bestMove) : ordered;
    var broken = false;

    for (var m = 0; m < localOrder.length; m++) {
      var mv2 = localOrder[m];
      board.apply([mv2[0], mv2[1]], [mv2[2], mv2[3]]);
      if (board.inCheck(color)) { board.undo(); continue; }
      var val;
      try {
        val = -this.search(board, board.turn, depth - 1, -beta, -alpha, 1);
      } finally {
        board.undo();
      }
      if (this.stopFlag) { broken = true; break; }
      if (val > iterScore) { iterScore = val; iterBest = mv2; }
      if (val > alpha) alpha = val;
    }

    // 渴望窗口越界：全窗复搜（仅当真正超出原窗口时才复搜，避免每层都白跑一遍）
    if (!broken && (iterScore <= alphaOrig || iterScore >= beta)) {
      alpha = -INF; beta = INF; iterBest = null; iterScore = -INF;
      for (var m2 = 0; m2 < localOrder.length; m2++) {
        var mv3 = localOrder[m2];
        board.apply([mv3[0], mv3[1]], [mv3[2], mv3[3]]);
        if (board.inCheck(color)) { board.undo(); continue; }
        var val2;
        try {
          val2 = -this.search(board, board.turn, depth - 1, -beta, -alpha, 1);
        } finally {
          board.undo();
        }
        if (this.stopFlag) { broken = true; break; }
        if (val2 > iterScore) { iterScore = val2; iterBest = mv3; }
        if (val2 > alpha) alpha = val2;
      }
    }

    if (!broken && iterBest) {
      bestMove = iterBest;
      bestScore = iterScore;
      this.lastDepth = depth;
      this.lastScore = iterScore;
    }
    if (broken) break;                             // 超时：沿用上一层的结果
    if (bestScore >= MATE - 100) break;            // 已经算到将死，不用更深
    if (this._timeUp()) break;
    prevScore = bestScore;
  }
  return bestMove;
};

XqAI.prototype._isInitial = function (board) {
  var g0 = initialGrid();
  for (var y = 0; y < ROWS; y++) {
    for (var x = 0; x < COLS; x++) {
      var a = board.grid[y][x], b = g0[y][x];
      if (!a && !b) continue;
      if (!a || !b) return false;
      if (a[0] !== b[0] || a[1] !== b[1]) return false;
    }
  }
  return true;
};

XqAI.prototype._bookMove = function (board) {
  var hist = board.history;
  // 空历史时只在本局面确实是"开局起始局面"才走库（否则单元测试里构造的非开局局面
  // 会因"空前缀匹配所有开局线"而被误用开局着法）。有历史时由 bookMatches 严格校验。
  if (hist.length === 0 && !this._isInitial(board)) return null;
  var cands = [];
  for (var i = 0; i < OPENING_BOOK.length; i++) {
    var line = OPENING_BOOK[i];
    if (bookMatches(line, hist)) cands.push(line[hist.length]);
  }
  if (!cands.length) return null;
  return cands[Math.floor(this._rng() * cands.length)];
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
  var fx = (from.length !== undefined) ? from[0] : from.x;
  var fy = (from.length !== undefined) ? from[1] : from.y;
  var side = this.board.turn;
  return this.board.legalMoves(side).filter(function (m) {
    return m[0] === fx && m[1] === fy;
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
  OPENING_BOOK: OPENING_BOOK,
  evaluate: xqEvaluate
};
