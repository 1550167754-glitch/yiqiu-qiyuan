/**
 * app.js —— 网页版主控制器（只在浏览器里跑；引擎逻辑全在 dist/engine.bundle.js）
 *
 * 职责：
 *   1. 画布初始化：设备像素比适配（高分屏不模糊）+ 自适应缩放
 *   2. 输入：点击/触摸选点 → 两步落子（确认 / 取消 / 结束本回合）
 *   3. AI 调度：显示"思考中"后再同步计算（避免界面先卡住、看不到反馈）
 *   4. 悔棋：与桌面版一致的"倒退动画"（上浮 + 缩小 + 淡出 + 涟漪）
 *   5. 终局存档与战绩（localStorage）
 */

/* global E */
(function () {
  'use strict';

  var B = E.board;
  var G = E.game;
  var A = E.ai;
  var V = E.boardview;
  var X = E.xiaqi;
  var XV = E.xqview;
  var Store = E.store;

  var BLACK = B.BLACK;
  var WHITE = B.WHITE;
  var XQ_RED = X.RED;
  var XQ_BLACK = X.BLACK;

  // 统一的"棋种"判定：xiangqi 的界面与交互与连珠类不同，但都用同一套外壳
  function isXiangqi() { return variant === 'xiangqi'; }

  // ---------------------------------------------------------------- DOM
  function $(id) { return document.getElementById(id); }

  var canvas = $('board');
  var ctx = canvas.getContext('2d');
  var overlay = $('overlay');
  var overlayText = $('overlayText');
  var banner = $('banner');

  // ---------------------------------------------------------------- 状态
  var view = new V.View();
  var xqView = new XV.XqView();
  var game = null;
  var humanSide = BLACK;          // 人机模式下我方执色（象棋用 'r'/'b'）
  var variant = 'connect6';
  var mode = 'human_ai';
  var difficulty = 'medium';
  var themeName = V.THEME_NAMES[0];
  var selected = [];              // 连珠类：待确认落点；象棋：至多一项（选中的子）
  var thinking = false;
  var aiGen = 0;                  // AI 代数：悔棋/重开后作废旧结果
  var anim = null;                // 悔棋动画状态
  var dpr = 1;

  function isHumanTurn() {
    if (!game || game.finished) return false;
    return game.currentPlayer().kind === 'human';
  }

  // ---------------------------------------------------------------- 画布尺寸
  /** 当前棋种的"格数"（用于按几何比例算画布尺寸）。 */
  function gridSpan() {
    if (isXiangqi()) return { cols: X.COLS, rows: X.ROWS, margin: XV.MARGIN };
    var n = game ? game.board.size : 19;
    return { cols: n, rows: n, margin: V.GEOM_MARGIN };
  }

  function resize() {
    var wrap = canvas.parentElement;
    var cssW = Math.max(240, wrap.clientWidth - 16);
    var maxH = window.innerWidth > 860 ? Math.max(320, window.innerHeight - 200) : 1e9;
    var sp = gridSpan();

    // 先按宽度定格子大小，再看高度是否要收缩（保持棋盘完整不变形）
    var cellW = cssW / (sp.cols - 1 + 0.9);
    var cellH = maxH / (sp.rows - 1 + 0.9);
    var cell = Math.min(cellW, cellH);
    var w = cell * (sp.cols - 1) + sp.margin * 2;
    var h = cell * (sp.rows - 1) + sp.margin * 2;
    if (w > cssW) {               // 极端窄屏再压一次
      cell *= cssW / w;
      w = cell * (sp.cols - 1) + sp.margin * 2;
      h = cell * (sp.rows - 1) + sp.margin * 2;
    }

    dpr = Math.min(3, window.devicePixelRatio || 1);
    canvas.style.width = w + 'px';
    canvas.style.height = h + 'px';
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    if (isXiangqi()) xqView.computeGeom(w, h);
    else view.computeGeom(w, h, sp.cols);
    paint();
  }

  /** 像素坐标 → 棋盘格（按当前棋种选对应渲染器）。 */
  function hitGrid(px, py) {
    return isXiangqi() ? xqView.toGrid(px, py) : view.toGrid(px, py);
  }

  // ---------------------------------------------------------------- 绘制
  function paint(extraGhosts) {
    if (!game) return;
    try {
      if (isXiangqi()) {
        var bd = game.board;
        var side = bd.turn;
        var kind = bd.findKing(side);
        var fx = {
          last: bd.lastMove,
          selected: selected.length ? selected[0] : null,
          moves: bd.lastMove || selected.length ? null : null,
          check: null,
          ghosts: null
        };
        // 可落点提示：选中自己的子时显示
        if (selected.length) {
          fx.moves = game.legalTargetsFrom(selected[0]).map(function (t) {
            return { x: t.x, y: t.y, piece: bd.piece(t.x, t.y) };
          });
        }
        if (kind && bd.inCheck(side)) fx.check = { x: kind[0], y: kind[1] };
        xqView.render(ctx, bd, fx);
      } else {
        var st = {
          history: game.board.history,
          last: game.board.history.length ? game.board.history[game.board.history.length - 1] : null,
          selected: selected,
          winLine: game.winLine || null,
          ghosts: extraGhosts || (anim ? anim.ghosts : null)
        };
        view.render(ctx, st, themeName);
      }
    } catch (err) {
      console.error('render failed', err);
    }
  }

  // ---------------------------------------------------------------- 提示条
  function setBanner(html) {
    if (!html) { banner.classList.add('is-hidden'); banner.innerHTML = ''; return; }
    banner.innerHTML = html;
    banner.classList.remove('is-hidden');
  }

  // ---------------------------------------------------------------- 新对局
  function newGame() {
    cancelAnim();
    aiGen += 1;
    selected = [];
    thinking = false;
    setBanner('');
    hideOverlay();

    variant = $('variant').value;
    mode = $('mode').value;
    difficulty = $('difficulty').value;
    themeName = $('theme').value;

    // 象棋用 'r'/'b'，连珠类用 1/2 —— 由棋种决定"我方执色"的取值
    if (isXiangqi()) {
      humanSide = $('side').value === 'black' ? XQ_RED : XQ_BLACK;
      game = new X.XiangqiGame({
        black: mkXqPlayer(XQ_RED),
        white: mkXqPlayer(XQ_BLACK)
      });
    } else {
      humanSide = $('side').value === 'black' ? BLACK : WHITE;
      game = new G.Game({
        variant: variant,
        black: mkPlayer(BLACK),
        white: mkPlayer(WHITE)
      });
    }

    Store.saveSettings({
      variant: variant, mode: mode, difficulty: difficulty,
      side: $('side').value, theme: themeName
    });

    resize();
    updateStatus();
    refreshButtons();
    // 若开局轮到 AI（人机模式下我方执后手），立刻让它走
    maybeAiTurn();
  }

  function diffLabel(d) {
    return d === 'easy' ? '简单' : (d === 'hard' ? '困难' : '中等');
  }

  /** 连珠类棋手（1/2 执色）。 */
  function mkPlayer(side) {
    var mySide = (side === BLACK) ? 'black' : 'white';
    var mine = ($('side').value === mySide);
    var human = (mode === 'human_human') || mine;
    var name = human
      ? (mode === 'human_human' ? (side === BLACK ? '黑方（玩家1）' : '白方（玩家2）') : '我')
      : 'AI（' + diffLabel(difficulty) + '）';
    if (human) return new G.Player(name, 'human');
    return new G.Player(name, 'ai', difficulty, new A.AI(difficulty, Date.now() % 100000));
  }

  /** 象棋棋手（'r'/'b' 执色）。 */
  function mkXqPlayer(side) {
    var mySide = (side === XQ_RED) ? 'black' : 'white';   // 红=先手，界面上对应"黑（先手）"选项
    var mine = ($('side').value === mySide);
    var human = (mode === 'human_human') || mine;
    var name = human
      ? (mode === 'human_human' ? (side === XQ_RED ? '红方（玩家1）' : '黑方（玩家2）') : '我')
      : 'AI（' + diffLabel(difficulty) + '）';
    if (human) return { name: name, kind: 'human', engine: null };
    return { name: name, kind: 'ai', engine: new X.XqAI(difficulty, Date.now() % 100000) };
  }

  // ---------------------------------------------------------------- 状态显示
  function updateStatus() {
    if (!game) return;
    var cur = game.currentPlayer();
    var curName = cur.kind === 'human' ? '轮到你' : '轮到 ' + cur.name;
    $('lblTurn').textContent = game.finished
      ? game.resultText()
      : curName + (cur.kind === 'human' ? '' : '（思考中）');

    if (isXiangqi()) {
      var bd = game.board;
      $('lblStep').textContent = game.finished
        ? ('共 ' + game.movesLog.length + ' 步')
        : ('轮到' + (bd.turn === XQ_RED ? '红方' : '黑方') +
           (bd.checkFlag ? '（被将军！）' : ''));
      var lm = bd.lastMove;
      $('lblMove').textContent = lm
        ? ('上一步：' + xqName(lm[0], lm[1]) + ' → ' + xqName(lm[2], lm[3]))
        : '尚未行棋';
    } else {
      var left = game.maxStones - game.stonesThisRound;
      $('lblStep').textContent = game.finished
        ? ('共 ' + game.board.moveCount + ' 手')
        : ('本轮已下 ' + game.stonesThisRound + '/' + game.maxStones + ' 子，还可下 ' + left + ' 子');
      var last = game.board.history.length ? game.board.history[game.board.history.length - 1] : null;
      $('lblMove').textContent = last
        ? ('最后一手：' + coordName(last[0], last[1]) + '（' + (last[2] === BLACK ? '黑' : '白') + '）')
        : '尚未落子';
    }
    renderMoves();
  }

  function coordName(x, y) {
    return String.fromCharCode(65 + x) + (y + 1);
  }
  /** 象棋坐标：列 A-I、行 1-10（黑方底线为第 1 行，与棋盘显示一致）。 */
  function xqName(x, y) {
    return String.fromCharCode(65 + x) + (y + 1);
  }
  /** 取某格的棋子显示名（连珠类=黑/白，象棋=車馬砲…）。 */
  function pieceLabel(x, y) {
    if (isXiangqi()) {
      var p = game.board.piece(x, y);
      return p ? X.PIECE_CHAR[p[0] + p[1]] : '?';
    }
    var c = game.board.get(x, y);
    return c === BLACK ? '黑' : (c === WHITE ? '白' : '?');
  }

  function renderMoves() {
    var el = $('moves');
    if (!game) { el.textContent = '（暂无）'; return; }
    if (isXiangqi()) {
      var log = game.movesLog;
      if (!log.length) { el.textContent = '（暂无）'; return; }
      var html = '';
      for (var i = 0; i < log.length; i++) {
        var m = log[i];
        html += '<b>' + (i + 1) + '.</b> ' + xqName(m[0], m[1]) + '→' + xqName(m[2], m[3]) +
          (i % 5 === 4 ? '<br>' : '　');
      }
      el.innerHTML = html;
      return;
    }
    if (!game.movesLog.length) { el.textContent = '（暂无）'; return; }
    var html2 = '';
    for (var k = 0; k < game.movesLog.length; k++) {
      var mm = game.movesLog[k];
      html2 += '<b>' + (k + 1) + '.</b> ' + (mm[2] === BLACK ? '黑' : '白') + ' ' +
        coordName(mm[0], mm[1]) + (k % 6 === 5 ? '<br>' : '　');
    }
    el.innerHTML = html2;
  }

  function refreshButtons() {
    var human = isHumanTurn();
    $('btnResign').disabled = !game || game.finished;

    if (isXiangqi()) {
      // 象棋是"点子 → 点目标"两步走，没有"确认/结束本回合"
      $('btnConfirm').disabled = true;
      $('btnPass').disabled = true;
      var canUndoXq = !!game && game.movesLog.length > 0 && !anim && !thinking && human;
      $('btnUndo').disabled = !canUndoXq;
      $('hint').textContent = (game && game.finished)
        ? '本局已结束，点「开始新对局」继续。'
        : (human
          ? '点自己的棋子选中（绿点=可走，红圈=可吃），再点目标位置即可走子。'
          : 'AI 正在思考，请稍候…');
      return;
    }

    var canConfirm = human && selected.length > 0 &&
      selected.length <= game.maxStones &&
      game.stonesThisRound + selected.length <= game.maxStones;
    $('btnConfirm').disabled = !canConfirm;
    $('btnPass').disabled = !(human && game.stonesThisRound >= 1);
    // 悔棋只在"轮到我、且没有动画/AI 在跑"时可用：
    // 否则撤完立刻被 AI 的应对着补回来，玩家的操作看起来毫无效果。
    $('btnUndo').disabled = !game || game.board.moveCount === 0 || !!anim ||
      thinking || !human;
    $('hint').textContent = game && game.finished
      ? '本局已结束，点「开始新对局」继续。'
      : (human
        ? '点击棋盘选点（最多 ' + game.maxStones + ' 个），选满自动落子；也可选 1 子后点「结束本回合」。'
        : 'AI 正在思考，请稍候…');
  }

  // ---------------------------------------------------------------- 落子交互
  function canvasPos(ev) {
    var rect = canvas.getBoundingClientRect();
    var p = ev.touches && ev.touches[0] ? ev.touches[0] : ev;
    var g = isXiangqi() ? xqView.geom : view.geom;
    return {
      x: (p.clientX - rect.left) * (g.W / rect.width),
      y: (p.clientY - rect.top) * (g.H / rect.height)
    };
  }

  /** 象棋的点击：选子 / 走子。 */
  function onXiangqiClick(g) {
    var bd = game.board;
    var r = game.place(g.x, g.y);
    if (r.select) {
      selected = [{ x: r.select[0], y: r.select[1] }];
    } else if (r.ok) {
      selected = [];
    } else if (r.msg && r.msg !== '已取消选择') {
      $('hint').textContent = r.msg;
    }
    paint();
    updateStatus();
    refreshButtons();
    if (r.ok) {
      if (game.finished) { finishGame(); return; }
      maybeAiTurn();
    }
  }

  function onBoardClick(ev) {
    if (!game || game.finished || thinking || anim) return;
    if (!isHumanTurn()) return;
    ev.preventDefault();
    var pos = canvasPos(ev);
    var g = hitGrid(pos.x, pos.y);
    if (!g) return;

    if (isXiangqi()) { onXiangqiClick(g); return; }

    if (!game.board.isEmpty(g.x, g.y)) return;
    // 已选过就取消（再点同一点）
    for (var i = 0; i < selected.length; i++) {
      if (selected[i].x === g.x && selected[i].y === g.y) {
        selected.splice(i, 1);
        paint(); refreshButtons();
        return;
      }
    }
    if (game.stonesThisRound + selected.length >= game.maxStones) return;
    selected.push({ x: g.x, y: g.y });
    paint();
    refreshButtons();
    // 选满自动落子（落子体验更顺）
    if (game.stonesThisRound + selected.length >= game.maxStones) {
      setTimeout(confirmStones, 90);
    }
  }

  function confirmStones() {
    if (!game || !isHumanTurn() || !selected.length) return;
    var picks = selected.slice();
    selected = [];
    var placed = 0;
    for (var i = 0; i < picks.length; i++) {
      var r = game.place(picks[i].x, picks[i].y);
      if (!r.ok) break;
      placed += 1;
      if (r.line) break;
    }
    paint();
    updateStatus();
    refreshButtons();
    if (game.finished) { finishGame(); return; }
    // 本轮下满 → 结束回合，换手
    if (game.stonesThisRound >= game.maxStones) {
      game.endRound();
      updateStatus();
    }
    maybeAiTurn();
  }

  function passRound() {
    if (!game || !isHumanTurn() || game.stonesThisRound < 1) return;
    selected = [];
    game.endRound();
    paint();
    updateStatus();
    refreshButtons();
    maybeAiTurn();
  }

  // ---------------------------------------------------------------- AI
  function showOverlay(text) {
    overlayText.textContent = text || 'AI 思考中…';
    overlay.classList.remove('is-hidden');
  }
  function hideOverlay() { overlay.classList.add('is-hidden'); }

  function maybeAiTurn() {
    if (!game || game.finished) return;
    if (game.currentPlayer().kind === 'human') { refreshButtons(); return; }
    if (thinking) return;
    thinking = true;
    refreshButtons();
    showOverlay('AI 思考中（' + diffLabel(difficulty) + '）…');
    var gen = aiGen;
    var eng = game.currentPlayer().engine;
    // 先让浏览器画一帧（显示"思考中"），再同步搜索。
    // 搜索是纯计算的循环，无法中途让出主线程；先渲染可避免"界面像卡死"。
    requestAnimationFrame(function () {
      setTimeout(function () {
        // 【易错点】下面两条"作废返回"都必须先 refreshButtons()：
        // 否则 thinking 虽然清了，按钮与提示仍是"AI 思考中"的那一套，
        // 界面看起来永久卡住（实测踩过：悔棋打断 AI 后按钮再也不亮）。
        if (gen !== aiGen || !game || game.finished) {
          thinking = false;
          hideOverlay();
          if (game && !game.finished) { updateStatus(); }
          refreshButtons();
          return;
        }
        // 象棋走一步、连珠类走 1~2 子，分支处理（引擎接口本来就不同）
        var aiStones = null;
        if (isXiangqi()) {
          aiStones = game.aiTurn();
        } else {
          var stones = eng ? eng.getMove(game.board, game.current, game.maxStones) : [];
          for (var i = 0; i < stones.length; i++) {
            var r = game.place(stones[i][0], stones[i][1]);
            if (!r.ok) break;
            if (r.line) break;
          }
          game.endRound();     // 无论落子成败都要换手，否则会卡在"AI 该走却轮不到人"
          aiStones = stones;
        }
        thinking = false;
        hideOverlay();
        if (gen !== aiGen) {                    // 期间悔棋/重开了，结果作废
          updateStatus();
          refreshButtons();
          return;
        }
        if (isXiangqi() && (!aiStones || !aiStones.length)) {
          // 象棋 AI 无着可走（理论不该发生）：判终局，绝不卡死
          game.finished = true;
          game.reason = 'AI 无着可走';
        }
        paint();
        updateStatus();
        refreshButtons();
        if (game.finished) { finishGame(); return; }
        maybeAiTurn();                          // 连锁：下一个也是 AI（机机/观战）
      }, 40);
    });
  }

  // ---------------------------------------------------------------- 终局
  function finishGame() {
    paint();
    updateStatus();
    refreshButtons();
    var rec = game.toRecord();
    if (rec.result !== 'ABORT') {
      try { Store.saveGame(rec); } catch (e) { console.warn('存战绩失败', e); }
    }
    var sub = isXiangqi()
      ? ('共 ' + game.movesLog.length + ' 步 · ' + game.reason)
      : ('共 ' + game.board.moveCount + ' 手 · ' + game.reason);
    setBanner(
      '<div class="big">' + game.resultText() + '</div>' +
      '<div class="sub">' + sub + '</div>' +
      '<div class="row">' +
      '<button class="btn primary" id="bnAgain" style="width:auto">再来一局</button>' +
      '<button class="btn" id="bnUndoEnd" style="width:auto">悔棋看看</button>' +
      '</div>'
    );
    var a = $('bnAgain');
    var u = $('bnUndoEnd');
    if (a) a.onclick = function () { newGame(); };
    if (u) u.onclick = function () { setBanner(''); doUndo(); };
  }

  // ---------------------------------------------------------------- 悔棋 + 倒退动画
  function cancelAnim() {
    if (anim && anim.raf) cancelAnimationFrame(anim.raf);
    anim = null;
    hideOverlay();
  }

  function doUndo() {
    if (!game || anim) return;
    var toHuman = (mode === 'human_ai');

    if (isXiangqi()) { doUndoXiangqi(toHuman); return; }
    if (!game.board.moveCount) return;
    var pending = game.pendingUndo(toHuman);     // 先算出"要退哪几枚"
    if (!pending.length) return;

    aiGen += 1;                                   // 作废正在跑的 AI 结果
    thinking = false;
    selected = [];
    var removed = game.undoRound(toHuman);        // 规则层立即撤销
    if (!removed) return;

    paint();
    updateStatus();                               // 内含 renderMoves：棋谱面板要跟着撤
    refreshButtons();

    // 动画：后下的先退，每枚 上浮+缩小+淡出 + 一圈涟漪
    var order = pending.slice().reverse();
    anim = { order: order, idx: 0, t: 0, ghosts: [], raf: 0, started: performance.now() };
    var PER = 190;          // 每枚棋子时长(ms)
    var GAP = 40;           // 多枚之间的间隔
    var total = order.length * PER + (order.length - 1) * GAP;

    function tick(now) {
      if (!anim) return;
      var el = now - anim.started;
      var timePer = PER + GAP;
      var i = Math.min(order.length - 1, Math.floor(el / timePer));
      var local = Math.min(PER, el - i * timePer);
      var t = Math.max(0, local / PER);
      anim.ghosts = [];
      for (var k = 0; k < order.length; k++) {
        if (k < i) continue;                       // 已退完的不再画
        var st = (k === i) ? t : 0;                // 后面的还没开始
        anim.ghosts.push({
          x: order[k].x, y: order[k].y, color: order[k].color,
          t: st, ripple: st
        });
      }
      paint();
      if (el < total) {
        anim.raf = requestAnimationFrame(tick);
      } else {
        anim = null;
        paint();
        refreshButtons();
        maybeAiTurn();                             // 撤到 AI 轮则让它续走
      }
    }
    anim.raf = requestAnimationFrame(tick);
    refreshButtons();
  }

  /**
   * 象棋悔棋 + 倒退动画。
   * 与连珠类同一套观感：被撤的棋子原地"上浮 + 缩小 + 淡出 + 涟漪"。
   * 只是象棋的"子"是从 A 走到 B 的，所以幽灵要画在**落点**上
   * （那正是它现在待的地方），退场后原地就空了。
   */
  function doUndoXiangqi(toHuman) {
    if (!game.movesLog.length) return;
    var pending = game.pendingUndo(toHuman);
    if (!pending.length) return;

    var ghosts = [];
    for (var i = 0; i < pending.length; i++) {
      var m = pending[i];
      var p = game.board.piece(m.tx, m.ty);
      if (p) ghosts.push({ x: m.tx, y: m.ty, piece: p });
    }

    aiGen += 1;
    thinking = false;
    selected = [];
    var removed = game.undoRound(toHuman);
    if (!removed) return;

    paint();
    updateStatus();
    refreshButtons();

    if (!ghosts.length) { maybeAiTurn(); return; }

    anim = { order: ghosts, idx: 0, t: 0, ghosts: [], raf: 0, started: performance.now() };
    var PER = 240, GAP = 40;
    var total = ghosts.length * PER + (ghosts.length - 1) * GAP;

    function tick(now) {
      if (!anim) return;
      var el = now - anim.started;
      var timePer = PER + GAP;
      var idx = Math.min(ghosts.length - 1, Math.floor(el / timePer));
      var local = Math.min(PER, el - idx * timePer);
      var t = Math.max(0, local / PER);
      anim.ghosts = [];
      for (var k = 0; k < ghosts.length; k++) {
        if (k < idx) continue;
        var st = (k === idx) ? t : 0;
        anim.ghosts.push({
          x: ghosts[k].x, y: ghosts[k].y, piece: ghosts[k].piece,
          alpha: 1 - 0.9 * st,
          lift: XV.MARGIN * 0.85 * 0 + (xqView.geom ? xqView.geom.cell * 0.8 * st : 0),
          scale: 1 - 0.28 * st
        });
      }
      animateXiangqiGhosts();
      if (el < total) {
        anim.raf = requestAnimationFrame(tick);
      } else {
        anim = null;
        paint();
        refreshButtons();
        maybeAiTurn();
      }
    }
    anim.raf = requestAnimationFrame(tick);
    refreshButtons();
  }

  /** 单独绘制一帧：底色 + 棋盘 + 幽灵（象棋的 render 接口没有 ghosts 参数，这里补一层）。 */
  function animateXiangqiGhosts() {
    if (!game) return;
    var bd = game.board;
    xqView.render(ctx, bd, {
      last: anim && anim.ghosts.length ? null : bd.lastMove,
      selected: null,
      moves: null,
      check: null,
      ghosts: anim ? anim.ghosts : null
    });
  }

  // ---------------------------------------------------------------- 战绩页
  function renderRecords() {
    var list = Store.stats();
    var tbody = document.querySelector('#statTable tbody');
    tbody.innerHTML = '';
    if (!list.length) {
      tbody.innerHTML = '<tr><td colspan="5" class="empty">暂无战绩记录，先下几局吧。</td></tr>';
    } else {
      list.forEach(function (p) {
        var tr = document.createElement('tr');
        tr.innerHTML = '<td>' + esc(p.name) + '</td>' +
          '<td>' + (p.kind === 'ai' ? 'AI' : '玩家') + '</td>' +
          '<td>' + p.wins + '</td><td>' + p.losses + '</td><td>' + p.draws + '</td>';
        tbody.appendChild(tr);
      });
    }
    var games = Store.recentGames(20);
    var box = $('gameList');
    box.innerHTML = '';
    if (!games.length) {
      box.innerHTML = '<div class="empty">暂无对局记录。</div>';
      return;
    }
    games.forEach(function (g) {
      var res = g.result === 'BLACK' ? '黑胜' : (g.result === 'WHITE' ? '白胜' : '和棋');
      var d = new Date(g.endedAt);
      var pad = function (n) { return n < 10 ? '0' + n : '' + n; };
      var when = d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()) +
        ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes());
      var el = document.createElement('div');
      el.className = 'game-item';
      el.innerHTML = '<div class="t"><span><b>' + esc(g.black) + '</b> vs <b>' + esc(g.white) + '</b></span>' +
        '<span class="tag">' + res + '</span></div>' +
        '<div class="m">' + (g.variant === 'gomoku' ? '五子棋' : '六子棋') +
        ' · ' + g.moveCount + ' 手 · ' + esc(g.reason || '') + ' · ' + when + '</div>';
      box.appendChild(el);
    });
  }

  function esc(s) {
    return String(s === undefined || s === null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  // ---------------------------------------------------------------- 事件绑定
  /** 按棋种重设"我执"下拉的两项文案（红先/黑先的措辞不同）。 */
  function syncSideOptions() {
    var sel = $('side');
    var xq = $('variant').value === 'xiangqi';
    var keep = sel.value;
    sel.innerHTML = '';
    var opts = xq
      ? [['black', '红（先手）'], ['white', '黑（后手）']]
      : [['black', '黑（先手）'], ['white', '白（后手）']];
    opts.forEach(function (o) {
      var el = document.createElement('option');
      el.value = o[0];
      el.textContent = o[1];
      sel.appendChild(el);
    });
    sel.value = (keep === 'black' || keep === 'white') ? keep : 'black';
  }

  function switchPage(name) {
    ['play', 'records', 'help'].forEach(function (p) {
      $('page-' + p).classList.toggle('is-on', p === name);
    });
    Array.prototype.forEach.call(document.querySelectorAll('.tab'), function (t) {
      t.classList.toggle('is-on', t.getAttribute('data-page') === name);
    });
    if (name === 'records') renderRecords();
    if (name === 'play') resize();
  }

  function bind() {
    Array.prototype.forEach.call(document.querySelectorAll('.tab'), function (t) {
      t.onclick = function () { switchPage(t.getAttribute('data-page')); };
    });

    // 主题下拉
    var sel = $('theme');
    V.THEME_NAMES.forEach(function (n) {
      var o = document.createElement('option');
      o.value = n; o.textContent = n;
      sel.appendChild(o);
    });

    $('mode').onchange = function () {
      var human = $('mode').value === 'human_ai';
      $('rowSide').style.display = human ? '' : 'none';
      $('rowDiff').style.display = human ? '' : 'none';
    };
    // 棋种切换：重设"我执"的两个选项文案（象棋是红先、连珠类是黑先），
    // 然后开新局（棋盘尺寸/渲染器都要换）
    $('variant').onchange = function () {
      syncSideOptions();
      newGame();
    };
    $('theme').onchange = function () { themeName = $('theme').value; paint(); };

    $('btnNew').onclick = newGame;
    $('btnConfirm').onclick = confirmStones;
    $('btnPass').onclick = passRound;
    $('btnUndo').onclick = doUndo;
    $('btnResign').onclick = function () {
      if (!game || game.finished) return;
      game.resign();
      paint(); updateStatus(); refreshButtons(); finishGame();
    };
    $('btnClear').onclick = function () {
      if (confirm('确定清空全部战绩记录吗？此操作不可撤销。')) {
        Store.clearAll();
        renderRecords();
      }
    };

    canvas.addEventListener('click', onBoardClick);
    canvas.addEventListener('touchstart', function (e) { onBoardClick(e); }, { passive: false });

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { confirmStones(); }
      else if (e.key === 'Escape') { selected = []; paint(); refreshButtons(); }
    });

    window.addEventListener('resize', function () {
      clearTimeout(bind._t);
      bind._t = setTimeout(resize, 120);
    });
    window.addEventListener('orientationchange', function () {
      setTimeout(resize, 260);
    });
  }

  // ---------------------------------------------------------------- 启动
  function boot() {
    bind();
    // 读回上次设置
    var s = Store.getSettings();
    if (s) {
      if (s.variant) $('variant').value = s.variant;
      if (s.mode) $('mode').value = s.mode;
      if (s.difficulty) $('difficulty').value = s.difficulty;
      if (s.side) $('side').value = s.side;
      if (s.theme) $('theme').value = s.theme;
      themeName = $('theme').value;
    }
    $('mode').onchange();
    newGame();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
