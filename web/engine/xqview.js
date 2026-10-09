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
