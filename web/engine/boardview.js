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
