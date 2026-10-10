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

    // ---- (1) 车 / 将：第一个遇到的子是敌车或敌将 → 攻击 ----
    //
    // 【为什么把敌方 KING 也算进车射线——飞将（将帅照面）规则】
    // 双王同列且中间无子时，将/帅可以直接互吃（飞将），这本身就是一种攻击。
    // 若不把敌方 KING 计入射线，isAttacked 就检测不到照面 → inCheck 判不出
    // → legalMoves 不会过滤"移开挡子送将"的着法 → 玩家能走出违规棋，
    //   将死/困毙的终局判定也会失真。
    //
    // 【安全性论证：不会产生横向误判】红王只会在 y∈[7,9]、黑王只会在 y∈[0,2]
    // （见 inPalace），双方九宫永不共行。而 isAttacked 的实战调用点
    // （inCheck、评估的将帅安全项）目标格永远是某方的将/帅，因此横向射线上
    // 第一颗子绝不可能是敌方王，横向不会误判；纵向命中恰好就是照面语义。
    // 其余子力判定不受影响——只是把"第一个遇到的子"的合法身份多认一种。
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

/** 供界面取"当前选中棋子能走哪儿"。
 *  入参兼容两种形态：[fx,fy] 数组（引擎内部）与 {x,y} 对象（app.js 的 selected）。
 *  【曾踩坑】只按下标 from[0]/from[1] 取值，而界面传的是对象 → undefined 永远
 *  匹配不上任何着法 → 可走点提示恒为空（"绿点=可走"从未显示过）。 */
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
  evaluate: xqEvaluate
};
