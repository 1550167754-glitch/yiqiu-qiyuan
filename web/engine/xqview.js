/**
 * xqview.js —— 中国象棋棋盘渲染器（平台无关）
 *
 * 与 boardview.js 同样的定位：只认 Canvas 2D 的公共接口子集，
 * 不引用 DOM / wx，因此浏览器与将来的微信小程序共用同一份。
 *
 * 绘制层次：
 *   1) 木色底板 + 边框 + 九宫斜线 + 河界文字 + 炮位/兵位传统折角标记
 *   2) 棋子（多层木片质感：径向渐变 + 边缘暗角 + 倒角受光 + 刻字阴影）
 *   3) 效果层：上一步标记、选中环、可走点提示、被将军提示、走子滑动动画
 *
 * 坐标：x∈[0,8] 左→右，y∈[0,9] 上→下（黑在上、红在下），与引擎一致。
 * 翻转：this.flipped = true 时显示坐标系上下翻转（我执黑时让己方在下方），
 *       所有「棋盘坐标 → 像素」的换算都经过 disp()，输入命中 toGrid 做反变换。
 */

var XI = require('./xiaqi.js');

/**
 * 5 套主题，键名与 boardview.THEMES 对齐（下拉框直接联动）。
 * 每套包含：棋盘四色 + 棋子面色三档（径向渐变）+ 红/黑字色。
 * 深色棋盘（墨玉黑）配浅木棋子，对比清晰；红黑字色在深浅底上都可读。
 */
var XQ_THEMES = {
  '经典原木': {
    bgA: '#EFD9A8', bgB: '#E3C88E', line: '#5A4630', river: '#7A6244', tray: '#D8BC80',
    faceA: '#FFF6DC', faceB: '#F0DFB4', faceC: '#C9AE7C',
    red: '#B23A2E', black: '#2E3540'
  },
  '胡桃深木': {
    bgA: '#D2AC6C', bgB: '#BE9350', line: '#503418', river: '#6E5230', tray: '#96702F',
    faceA: '#FFF3D6', faceB: '#EFDCB0', faceC: '#C2A170',
    red: '#A02C22', black: '#3A3226'
  },
  '石板灰': {
    bgA: '#C6CBCF', bgB: '#A8B0B6', line: '#474E56', river: '#5C646C', tray: '#8B939B',
    faceA: '#FBF7EA', faceB: '#E9E2CC', faceC: '#B9AE90',
    red: '#AE3A30', black: '#2C333E'
  },
  '墨玉黑': {
    bgA: '#39404C', bgB: '#2A303A', line: '#9AA6B4', river: '#8A96A6', tray: '#1D222A',
    faceA: '#F8F0D8', faceB: '#E8DCBB', faceC: '#B4A47E',
    red: '#C4483A', black: '#3E4854'
  },
  '青瓷绿': {
    bgA: '#CBDCCF', bgB: '#AEC6B2', line: '#3E5C50', river: '#4E6E60', tray: '#8FB0A0',
    faceA: '#FCF6E4', faceB: '#EFDFBC', faceC: '#C2AF88',
    red: '#A8362C', black: '#31463C'
  }
};
var DEFAULT_THEME = '经典原木';
// 兼容旧引用（xqshot.js 等只取 MARGIN）
var XQ_THEME = XQ_THEMES[DEFAULT_THEME];

var MARGIN = 30;

function XqView() {
  this.geom = null;
  this.flipped = false;        // true：显示时上下翻转（执黑方便）
}

/** 棋盘坐标 → 显示坐标（翻转的唯一入口，绘制与命中都必须经过它）。 */
XqView.prototype.disp = function (x, y) {
  return this.flipped ? { x: XI.COLS - 1 - x, y: XI.ROWS - 1 - y } : { x: x, y: y };
};

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

/** 像素 → 棋盘格；超出容差返回 null（翻转时做反变换）。 */
XqView.prototype.toGrid = function (px, py) {
  var g = this.geom;
  if (!g) return null;
  var dx = Math.round((px - g.x0) / g.cell);
  var dy = Math.round((py - g.y0) / g.cell);
  if (dx < 0 || dx >= XI.COLS || dy < 0 || dy >= XI.ROWS) return null;
  var ex = px - (g.x0 + dx * g.cell);
  var ey = py - (g.y0 + dy * g.cell);
  if (Math.sqrt(ex * ex + ey * ey) > g.cell * 0.62) return null;
  return this.flipped
    ? { x: XI.COLS - 1 - dx, y: XI.ROWS - 1 - dy }
    : { x: dx, y: dy };
};

XqView.prototype.center = function (x, y) {
  var g = this.geom;
  var d = this.disp(x, y);
  return { cx: g.x0 + d.x * g.cell, cy: g.y0 + d.y * g.cell };
};

/** 炮位/兵位的传统折角标记（显示坐标；翻转后点位集合与自身镜像重合，天然对齐）。 */
XqView.prototype._drawPosMarks = function (ctx) {
  var g = this.geom;
  var t = g.theme;
  var pts = [
    [1, 2], [7, 2], [1, 7], [7, 7],                       // 炮位
    [0, 3], [2, 3], [4, 3], [6, 3], [8, 3],               // 兵位（黑）
    [0, 6], [2, 6], [4, 6], [6, 6], [8, 6]                // 兵位（红）
  ];
  ctx.strokeStyle = t.line;
  ctx.globalAlpha = 0.55;
  ctx.lineWidth = Math.max(1, g.cell * 0.028);
  var gap = g.cell * 0.09;
  var len = g.cell * 0.17;
  for (var i = 0; i < pts.length; i++) {
    var d = this.disp(pts[i][0], pts[i][1]);
    var cx = g.x0 + d.x * g.cell;
    var cy = g.y0 + d.y * g.cell;
    // 四象限折角；贴边列只画内侧，避免伸出棋盘
    var quads = [[-1, -1], [1, -1], [-1, 1], [1, 1]];
    for (var q = 0; q < quads.length; q++) {
      var sx = quads[q][0], sy = quads[q][1];
      if (d.x === 0 && sx < 0) continue;
      if (d.x === XI.COLS - 1 && sx > 0) continue;
      ctx.beginPath();
      ctx.moveTo(cx + sx * gap, cy + sy * (gap + len));
      ctx.lineTo(cx + sx * gap, cy + sy * gap);
      ctx.lineTo(cx + sx * (gap + len), cy + sy * gap);
      ctx.stroke();
    }
  }
  ctx.globalAlpha = 1;
};

/** 1) 静态层：底板 / 网格（河界处竖线断开）/ 九宫斜线 / 河界文字 / 位标 */
XqView.prototype.drawStatic = function (ctx) {
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

  // 九宫斜线（上、下各一宫；几何对称，翻转无影响）
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

  // 炮位/兵位折角
  this._drawPosMarks(ctx);

  // 河界文字（用显示坐标：翻转后楚河/漢界自然对调）
  var fs = Math.max(11, Math.round(g.cell * 0.46));
  ctx.fillStyle = t.river;
  ctx.font = fs + 'px "KaiTi","STKaiti",serif';
  ctx.textAlign = 'center';
  var midY = g.y0 + 4.5 * g.cell + fs * 0.35;
  ctx.fillText('楚 河', g.x0 + 2 * g.cell, midY);
  ctx.fillText('漢 界', g.x0 + 6 * g.cell, midY);
  ctx.textAlign = 'left';
};

/** 2) 一枚棋子：多层木片质感 + 双圈 + 字形（红繁黑简，与桌面版一致）。
 *  opts: { scale, alpha, lift, at:{cx,cy} }  —— at 直接给像素中心（动画插值用） */
XqView.prototype.drawPiece = function (ctx, x, y, piece, opts) {
  opts = opts || {};
  var g = this.geom;
  var t = g.theme;
  var c;
  if (opts.at) {
    c = { cx: opts.at.cx, cy: opts.at.cy };
  } else {
    c = this.center(x, y);
  }
  var r = g.pieceR * (opts.scale === undefined ? 1 : opts.scale);
  var cy = c.cy + (opts.lift ? -opts.lift : 0);
  var cx = c.cx;
  if (ctx.globalAlpha !== undefined) ctx.globalAlpha = (opts.alpha === undefined ? 1 : opts.alpha);

  var isRed = piece[0] === XI.RED;

  // 落影：宽软影 + 紧贴深影（两层，避免死黑一片）
  ctx.fillStyle = 'rgba(0,0,0,0.16)';
  ctx.beginPath();
  ctx.arc(cx, cy + r * 0.18, r * 1.04, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = 'rgba(0,0,0,0.20)';
  ctx.beginPath();
  ctx.arc(cx, cy + r * 0.10, r * 0.99, 0, Math.PI * 2);
  ctx.fill();

  // 木片底（径向渐变：高光偏左上 → 边缘压暗）
  if (ctx.createRadialGradient) {
    var grad = ctx.createRadialGradient(cx - r * 0.32, cy - r * 0.38, r * 0.1, cx, cy, r * 1.05);
    grad.addColorStop(0, t.faceA);
    grad.addColorStop(0.58, t.faceB);
    grad.addColorStop(1, t.faceC);
    ctx.fillStyle = grad;
  } else {
    ctx.fillStyle = t.faceB;
  }
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, Math.PI * 2);
  ctx.fill();

  // 边缘暗角（内圈一圈淡淡的压暗，增强厚度感）
  ctx.strokeStyle = 'rgba(0,0,0,0.10)';
  ctx.lineWidth = r * 0.14;
  ctx.beginPath();
  ctx.arc(cx, cy, r * 0.93, 0, Math.PI * 2);
  ctx.stroke();

  // 倒角受光：左上一段弧（各向异性，不是塑料 hotspot）
  ctx.strokeStyle = 'rgba(255,252,240,0.55)';
  ctx.lineWidth = Math.max(1, r * 0.05);
  ctx.beginPath();
  ctx.arc(cx, cy, r * 0.90, Math.PI * 1.05, Math.PI * 1.62);
  ctx.stroke();

  // 外圈（色随行棋方）+ 内圈
  ctx.strokeStyle = isRed ? t.red : t.black;
  ctx.lineWidth = Math.max(1, r * 0.07);
  ctx.beginPath();
  ctx.arc(cx, cy, r * 0.97, 0, Math.PI * 2);
  ctx.stroke();
  ctx.globalAlpha *= 0.65;
  ctx.lineWidth = Math.max(1, r * 0.04);
  ctx.beginPath();
  ctx.arc(cx, cy, r * 0.80, 0, Math.PI * 2);
  ctx.stroke();
  ctx.globalAlpha = (opts.alpha === undefined ? 1 : opts.alpha);

  // 字形（红繁黑简）：先压一层极淡的偏移暗字做"刻痕"，再画正字
  var ch = XI.PIECE_CHAR[piece[0] + piece[1]] || '?';
  var fpx = Math.round(r * 1.16);
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.font = 'bold ' + fpx + 'px "KaiTi","STKaiti","Microsoft YaHei",serif';
  ctx.fillStyle = 'rgba(0,0,0,0.16)';
  ctx.fillText(ch, cx + r * 0.02, cy + r * 0.06);
  ctx.fillStyle = isRed ? t.red : t.black;
  ctx.fillText(ch, cx, cy + r * 0.04);
  ctx.textBaseline = 'alphabetic';
  ctx.textAlign = 'left';
  if (ctx.globalAlpha !== undefined) ctx.globalAlpha = 1;
};

/**
 * 3) 效果层
 * fx = {
 *   last: [fx,fy,tx,ty] | null,
 *   selected: {x,y} | null,
 *   moves: [{x,y,piece}],      // 选中棋子后可落点提示（piece=该格棋子，有则画"可吃"）
 *   check: {x,y} | null,       // 被将军的将/帅位置
 *   ghosts: [{x,y,piece,alpha,lift,scale}],
 *   slide: {piece,fx,fy,tx,ty,t,captured}   // 走子滑动动画（t∈[0,1]）
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

  // 选中环：金环 + 外圈淡光晕
  if (fx.selected) {
    var sc = this.center(fx.selected.x, fx.selected.y);
    ctx.strokeStyle = 'rgba(232,179,75,0.30)';
    ctx.lineWidth = Math.max(3, r * 0.26);
    ctx.beginPath();
    ctx.arc(sc.cx, sc.cy, r * 1.10, 0, Math.PI * 2);
    ctx.stroke();
    ctx.strokeStyle = '#E8B34B';
    ctx.lineWidth = Math.max(2, r * 0.13);
    ctx.beginPath();
    ctx.arc(sc.cx, sc.cy, r * 1.06, 0, Math.PI * 2);
    ctx.stroke();
  }

  // 可落点提示：空点=空心绿环，可吃=红圈+四角
  if (fx.moves && fx.moves.length) {
    for (var i = 0; i < fx.moves.length; i++) {
      var m = this.center(fx.moves[i].x, fx.moves[i].y);
      var occupied = fx.moves[i].piece;
      if (occupied) {
        ctx.strokeStyle = 'rgba(217,83,79,0.85)';
        ctx.lineWidth = Math.max(2, r * 0.12);
        ctx.beginPath();
        ctx.arc(m.cx, m.cy, r * 0.94, 0, Math.PI * 2);
        ctx.stroke();
        ctx.lineWidth = Math.max(1.5, r * 0.09);
        var ks = r * 1.02, kseg = ks * 0.38;
        [[-1, -1], [1, -1], [-1, 1], [1, 1]].forEach(function (d2) {
          ctx.beginPath();
          ctx.moveTo(m.cx + d2[0] * ks, m.cy + d2[1] * ks - d2[1] * kseg);
          ctx.lineTo(m.cx + d2[0] * ks, m.cy + d2[1] * ks);
          ctx.lineTo(m.cx + d2[0] * ks - d2[0] * kseg, m.cy + d2[1] * ks);
          ctx.stroke();
        });
      } else {
        ctx.strokeStyle = 'rgba(62,187,107,0.85)';
        ctx.lineWidth = Math.max(1.5, r * 0.07);
        ctx.beginPath();
        ctx.arc(m.cx, m.cy, r * 0.24, 0, Math.PI * 2);
        ctx.stroke();
        ctx.fillStyle = 'rgba(62,187,107,0.30)';
        ctx.beginPath();
        ctx.arc(m.cx, m.cy, r * 0.10, 0, Math.PI * 2);
        ctx.fill();
      }
    }
  }

  // 被将军的将/帅：双圈红环（内圈虚一点，警示感更强）
  if (fx.check) {
    var kc = this.center(fx.check.x, fx.check.y);
    ctx.strokeStyle = 'rgba(217,83,79,0.95)';
    ctx.lineWidth = Math.max(2, r * 0.16);
    ctx.beginPath();
    ctx.arc(kc.cx, kc.cy, r * 1.14, 0, Math.PI * 2);
    ctx.stroke();
    ctx.strokeStyle = 'rgba(217,83,79,0.55)';
    ctx.lineWidth = Math.max(1.5, r * 0.09);
    ctx.beginPath();
    ctx.arc(kc.cx, kc.cy, r * 0.98, 0, Math.PI * 2);
    ctx.stroke();
  }

  // 幽灵（悔棋倒退动画用）
  if (fx.ghosts) {
    for (var k = 0; k < fx.ghosts.length; k++) {
      var gh = fx.ghosts[k];
      this.drawPiece(ctx, gh.x, gh.y, gh.piece,
        { alpha: gh.alpha, lift: gh.lift, scale: gh.scale });
    }
  }

  // 走子滑动动画：被吃子原地淡出，行进子沿弧线滑入落点
  if (fx.slide) {
    var sl = fx.slide;
    var et = 1 - Math.pow(1 - Math.min(1, Math.max(0, sl.t)), 3);   // easeOutCubic
    if (sl.captured) {
      this.drawPiece(ctx, sl.tx, sl.ty, sl.captured, {
        alpha: Math.max(0, 1 - sl.t * 1.7),
        scale: 1 - 0.10 * sl.t
      });
    }
    var ix = sl.fx + (sl.tx - sl.fx) * et;
    var iy = sl.fy + (sl.ty - sl.fy) * et;
    var cc = this.center(ix, iy);
    var arc = Math.sin(Math.PI * Math.min(1, sl.t));               // 中途微微抬起
    this.drawPiece(ctx, sl.tx, sl.ty, sl.piece, {
      at: { cx: cc.cx, cy: cc.cy - r * 0.16 * arc },
      scale: 1 + 0.05 * arc
    });
  }
};

/** 完整绘制：静态层 + 棋子 + 效果层（themeName 与主题下拉联动）。 */
XqView.prototype.render = function (ctx, board, fx, themeName) {
  if (!this.geom) return;
  this.geom.theme = XQ_THEMES[themeName] || XQ_THEMES[DEFAULT_THEME];
  this.drawStatic(ctx);
  var slide = fx && fx.slide;
  for (var y = 0; y < XI.ROWS; y++) {
    for (var x = 0; x < XI.COLS; x++) {
      // 滑动动画中的行进子在 fx 层单独画，这里跳过落点
      if (slide && x === slide.tx && y === slide.ty) continue;
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
  XQ_THEMES: XQ_THEMES,
  DEFAULT_THEME: DEFAULT_THEME,
  mix: mix,
  MARGIN: MARGIN
};
