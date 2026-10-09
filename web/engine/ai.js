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
