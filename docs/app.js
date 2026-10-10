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

  // ---------------------------------------------------------------- 音效（WebAudio 合成，零资源文件）
  // 木片落盘声 = 短噪声过带通（"嗒"）+ 低频正弦敲击（"咚"）；
  // 吃子更低沉响亮，将军/胜负用三音阶提示。全部运行时合成，不加载任何音频文件。
  var Sfx = (function () {
    var ac = null;
    function actx() {
      try {
        if (!ac) {
          var AC = window.AudioContext || window.webkitAudioContext;
          if (!AC) return null;
          ac = new AC();
        }
        if (ac.state === 'suspended') ac.resume();   // 浏览器自动播放策略：手势后恢复
        return ac;
      } catch (e) { return null; }
    }
    function muted() { var el = $('chkSound'); return el ? !el.checked : false; }
    function thump(c, t0, f0, f1, vol, dur) {
      var o = c.createOscillator(); o.type = 'sine';
      o.frequency.setValueAtTime(f0, t0);
      o.frequency.exponentialRampToValueAtTime(f1, t0 + dur * 0.8);
      var g = c.createGain();
      g.gain.setValueAtTime(vol, t0);
      g.gain.exponentialRampToValueAtTime(0.0008, t0 + dur);
      o.connect(g); g.connect(c.destination);
      o.start(t0); o.stop(t0 + dur + 0.02);
    }
    function knock(c, t0, freq, vol) {
      var n = Math.floor(c.sampleRate * 0.05);
      var buf = c.createBuffer(1, n, c.sampleRate);
      var d = buf.getChannelData(0);
      for (var i = 0; i < n; i++) d[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / n, 2.5);
      var src = c.createBufferSource(); src.buffer = buf;
      var bp = c.createBiquadFilter(); bp.type = 'bandpass';
      bp.frequency.value = freq; bp.Q.value = 1.1;
      var g = c.createGain(); g.gain.value = vol;
      src.connect(bp); bp.connect(g); g.connect(c.destination);
      src.start(t0);
    }
    function tone(c, t0, f, dur, vol) {
      var o = c.createOscillator(); o.type = 'triangle';
      o.frequency.value = f;
      var g = c.createGain();
      g.gain.setValueAtTime(0.0001, t0);
      g.gain.linearRampToValueAtTime(vol, t0 + 0.012);
      g.gain.exponentialRampToValueAtTime(0.0008, t0 + dur);
      o.connect(g); g.connect(c.destination);
      o.start(t0); o.stop(t0 + dur + 0.02);
    }
    // delayMs：延后触发（同轮两枚落子错峰用）。走 AudioContext 时钟调度，
    // 比 setTimeout 更准，且在合成器内部排队，不影响静音/无音频环境的分支。
    function play(kind, delayMs) {
      if (muted()) return;
      var c = actx(); if (!c) return;
      var t0 = c.currentTime + 0.01 + (delayMs ? delayMs / 1000 : 0);
      if (kind === 'move') { knock(c, t0, 1500, 0.32); thump(c, t0, 210, 85, 0.28, 0.10); }
      else if (kind === 'capture') { knock(c, t0, 950, 0.48); thump(c, t0, 165, 70, 0.40, 0.13); }
      else if (kind === 'select') { knock(c, t0, 2100, 0.14); }
      else if (kind === 'check') { tone(c, t0, 660, 0.12, 0.20); tone(c, t0 + 0.11, 880, 0.16, 0.20); }
      else if (kind === 'win') { tone(c, t0, 523, 0.14, 0.22); tone(c, t0 + 0.13, 659, 0.14, 0.22); tone(c, t0 + 0.26, 784, 0.22, 0.24); }
      else if (kind === 'lose') { tone(c, t0, 392, 0.16, 0.20); tone(c, t0 + 0.15, 330, 0.16, 0.20); tone(c, t0 + 0.30, 262, 0.26, 0.22); }
    }
    return { play: play };
  })();

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
  var anim = null;                // 动画状态：{type:'slide'|'undo', ...}
  var xqFlipped = false;          // 象棋棋盘翻转（执黑时自动开，可手动切换）
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
        if (anim && anim.type === 'slide') { paintSlideFrame(); return; }
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
        xqView.render(ctx, bd, fx, themeName);
      } else {
        // 出生动画期间：动画中的那几枚子从 history 层摘掉（它们已在盘上），
        // 改由 ghosts 层按 birth 进度画缩放入场，否则会出现"整子+缩放影子"重影。
        var hist = game.board.history;
        var skip = (anim && anim.type === 'birth' && anim.stones) ? anim.stones.length : 0;
        var st = {
          history: skip ? hist.slice(0, hist.length - skip) : hist,
          last: skip ? null : (hist.length ? hist[hist.length - 1] : null),
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
      // 我执黑（后手）时翻转棋盘，让己方永远在下方（与实体棋对坐习惯一致）
      xqFlipped = (mode === 'human_ai' && $('side').value === 'white');
      xqView.flipped = xqFlipped;
    } else {
      humanSide = $('side').value === 'black' ? BLACK : WHITE;
      game = new G.Game({
        variant: variant,
        black: mkPlayer(BLACK),
        white: mkPlayer(WHITE)
      });
    }

    // 棋谱面板与按钮可见性按棋种切换：
    // 象棋没有"确认/结束本回合"（点子→点目标直接走），但多一个"翻转棋盘"
    $('cardRecord').hidden = false;
    $('btnConfirm').style.display = isXiangqi() ? 'none' : '';
    $('btnPass').style.display = isXiangqi() ? 'none' : '';
    $('btnFlip').style.display = isXiangqi() ? '' : 'none';

    Store.saveSettings({
      variant: variant, mode: mode, difficulty: difficulty,
      side: $('side').value, theme: themeName,
      sound: $('chkSound').checked
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
    var seed = Date.now() % 100000;
    var p = new G.Player(name, 'ai', difficulty, new A.AI(difficulty, seed));
    p.seed = seed;                 // Worker 搜索要按同一把种子重建 AI
    return p;
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
    var seed2 = Date.now() % 100000;
    return { name: name, kind: 'ai', engine: new X.XqAI(difficulty, seed2), seed: seed2, difficulty: difficulty };
  }

  // ---------------------------------------------------------------- 状态显示
  function updateStatus() {
    if (!game) return;
    var cur = game.currentPlayer();
    // 双人模式下"轮到你"有歧义（分不清该谁），显示棋手名；人机模式才说"轮到你"
    var curName = (cur.kind === 'human' && mode !== 'human_human')
      ? '轮到你'
      : '轮到 ' + cur.name;
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
      // 象棋是"点子 → 点目标"两步走，没有"确认/结束本回合"（按钮已隐藏）
      $('btnConfirm').disabled = true;
      $('btnPass').disabled = true;
      var canUndoXq = !!game && game.movesLog.length > 0 && !anim && !thinking && human;
      $('btnUndo').disabled = !canUndoXq;
      $('hint').textContent = (game && game.finished)
        ? '本局已结束，点「开始新对局」继续。'
        : (human
          ? '点自己的棋子选中（绿环=可走，红圈=可吃），再点目标即可走子；Esc 取消选中。'
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

  /** 象棋的点击：选子 / 走子。走子带滑动动画，AI 连锁推迟到动画结束。 */
  function onXiangqiClick(g) {
    var bd = game.board;
    var r = game.place(g.x, g.y);
    if (r.select) {
      selected = [{ x: r.select[0], y: r.select[1] }];
      Sfx.play('select');
    } else if (r.ok) {
      selected = [];
    } else if (r.msg && r.msg !== '已取消选择') {
      $('hint').textContent = r.msg;
    }
    if (r.ok) {
      playSlide(function () {
        updateStatus();
        refreshButtons();
        if (game.finished) { finishGame(); return; }
        if (bd.checkFlag) Sfx.play('check');
        maybeAiTurn();
      });
    } else {
      paint();
      updateStatus();
      refreshButtons();
    }
  }

  /**
   * 走子滑动动画（玩家与 AI 通用）。
   * 数据取自 board.history 最后一手（apply 时已记录 captured），因此
   * 调用时机是"落子已生效之后"，动画纯做视觉过渡：
   *   行进子从起点滑到落点（easeOutCubic + 中途微抬），
   *   被吃子原地淡出。期间 onBoardClick 被 anim 拦截，不会误触。
   */
  function playSlide(done) {
    var bd = game.board;
    var h = bd.history[bd.history.length - 1];
    if (!h || !bd.piece(h[2], h[3])) { if (done) done(); return; }
    Sfx.play(h[4] ? 'capture' : 'move');
    anim = {
      type: 'slide', started: performance.now(), dur: 220,
      fx: h[0], fy: h[1], tx: h[2], ty: h[3],
      piece: bd.piece(h[2], h[3]), captured: h[4] || null,
      t: 0, raf: 0
    };
    function tick(now) {
      if (!anim || anim.type !== 'slide') return;
      var t = Math.min(1, (now - anim.started) / anim.dur);
      anim.t = t;
      paintSlideFrame();
      if (t < 1) {
        anim.raf = requestAnimationFrame(tick);
      } else {
        anim = null;
        paint();
        if (done) done();
      }
    }
    anim.raf = requestAnimationFrame(tick);
  }

  /** 滑动动画单帧：只画"滑动中"的画面（上一步标记等全部隐藏，避免视觉打架）。 */
  function paintSlideFrame() {
    if (!game || !anim || anim.type !== 'slide') return;
    xqView.render(ctx, game.board, {
      last: null, selected: null, moves: null, check: null,
      slide: {
        piece: anim.piece, fx: anim.fx, fy: anim.fy, tx: anim.tx, ty: anim.ty,
        t: anim.t, captured: anim.captured
      }
    }, themeName);
  }

  /**
   * 连珠类落子入场动画（玩家确认落子 / AI 落子通用）。
   * 调用时机同样是"落子已生效之后"：新子 150~180ms 缩放入场（0→1 带轻微过冲），
   * 同轮多枚按 85ms 错峰出生，音效同步错峰。期间输入被 anim 拦截，
   * 回调推迟到全部出生完毕（对齐象棋 slide 的做法）。
   * 绘制约定见 boardview.js drawFx 的 birth 形态；悔棋动画路径不受影响。
   */
  function playBirth(stones, done) {
    if (!stones || !stones.length) { paint(); if (done) done(); return; }
    for (var s = 0; s < stones.length; s++) Sfx.play('move', s * 85);
    var DUR = 170;          // 单枚入场时长
    var GAP = 85;           // 多枚错峰间隔（与音效一致）
    var total = stones.length * DUR + (stones.length - 1) * GAP;
    anim = {
      type: 'birth', stones: stones,
      started: performance.now(), dur: DUR, gap: GAP,
      ghosts: stones.map(function (p) {
        return { x: p.x, y: p.y, color: p.color, birth: 0 };
      }),
      raf: 0
    };
    function tick(now) {
      if (!anim || anim.type !== 'birth') return;
      var el = now - anim.started;
      for (var k = 0; k < stones.length; k++) {
        var local = el - k * GAP;
        anim.ghosts[k].birth = local <= 0 ? 0 : Math.min(1, local / DUR);
      }
      paint();
      if (el < total) {
        anim.raf = requestAnimationFrame(tick);
      } else {
        anim = null;
        paint();
        if (done) done();
      }
    }
    anim.raf = requestAnimationFrame(tick);
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
    if (!game || !isHumanTurn() || !selected.length || anim) return;
    var picks = selected.slice();
    selected = [];
    var color = game.current;
    var placed = [];
    for (var i = 0; i < picks.length; i++) {
      var r = game.place(picks[i].x, picks[i].y);
      if (!r.ok) break;              // 被拒不响（音效只在成功落子时播）
      placed.push({ x: picks[i].x, y: picks[i].y, color: color });
      if (r.line) break;
    }
    refreshButtons();                // 动画期间先禁掉确认/悔棋
    // 本轮下满 → 结束回合，换手（先换手再播动画，AI 调度推迟到动画结束）
    var endedRound = false;
    if (!game.finished && game.stonesThisRound >= game.maxStones) {
      game.endRound();
      endedRound = true;
    }
    playBirth(placed, function () {
      updateStatus();
      refreshButtons();
      if (game.finished) { finishGame(); return; }
      maybeAiTurn();                 // 动画结束才轮到 AI 调度
    });
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
  // 「思考中」从全屏遮罩改为棋盘右上角小型徽标：
  // 复用 overlay 元素与 id（apptest 假 DOM 只认现有 id），角落化完全靠内联样式
  // 覆盖 .overlay 的居中/半透明底（style.css / index.html 不动，见协作分工）。
  // display 不动内联——.is-hidden{display:none} 的隐藏开关必须继续生效。
  function showOverlay(text) {
    var s = overlay.style;
    s.top = '10px'; s.right = '10px'; s.bottom = 'auto'; s.left = 'auto';
    s.width = 'auto'; s.height = 'auto';
    s.background = 'rgba(24,28,36,0.86)';
    s.color = '#F2E8D5';
    s.borderRadius = '999px';
    s.padding = '5px 14px';
    s.fontSize = '13px';
    s.boxShadow = '0 2px 10px rgba(0,0,0,0.35)';
    s.pointerEvents = 'none';
    overlayText.textContent = text || 'AI 思考中…';
    overlay.classList.remove('is-hidden');
  }
  function hideOverlay() { overlay.classList.add('is-hidden'); }

  // ------------------------------------------------ Worker（后台搜索，失败自动回退同步）
  // 优先把 AI 搜索交给 Worker（不阻塞主线程，向 exe 版响应手感看齐）；
  // 探测失败（构造抛错 / onerror / 首次 ping 3s 无响应）→ 永久回退现有同步路径。
  // aiGen 代数令牌语义保持：结果回来时 gen 不符即丢弃；悔棋/重开作废在途结果。
  var worker = { w: null, broken: false, seq: 0, pending: null, pingTimer: null };

  function killWorker() {
    if (worker.pending && worker.pending.timer) clearTimeout(worker.pending.timer);
    worker.pending = null;
    if (worker.pingTimer) { clearTimeout(worker.pingTimer); worker.pingTimer = null; }
    if (worker.w) { try { worker.w.terminate(); } catch (e) { } worker.w = null; }
  }

  /** 组装一次 AI 求解请求（主线程快照局面，worker 里重建）。返回 null 表示无法用 worker。 */
  function buildWorkerRequest() {
    if (worker.broken || !game || game.finished) return null;
    var cur = game.currentPlayer();
    if (!cur || cur.kind !== 'ai') return null;
    var diff = cur.difficulty || difficulty;
    var seed = (typeof cur.seed === 'number') ? cur.seed : (Date.now() % 100000);
    if (isXiangqi()) {
      var bd = game.board;
      var grid = [];
      for (var y = 0; y < X.ROWS; y++) {
        var row = [];
        for (var x = 0; x < X.COLS; x++) {
          var p = bd.grid[y][x];
          row.push(p ? [p[0], p[1]] : null);
        }
        grid.push(row);
      }
      return { variant: 'xiangqi', difficulty: diff, seed: seed, payload: { grid: grid, turn: bd.turn } };
    }
    var b = game.board;
    return {
      variant: variant, difficulty: diff, seed: seed,
      payload: {
        size: b.size, winCount: b.winCount,
        moves: b.history.map(function (m) { return [m[0], m[1], m[2]]; }),
        maxStones: game.maxStones
      }
    };
  }

  function handleWorkerResult(msg) {
    var p = worker.pending;
    if (!p || p.id !== msg.id) return;   // 过期/已被悔棋作废的在途结果：直接丢弃
    worker.pending = null;
    if (p.timer) clearTimeout(p.timer);
    if (msg.error) {                     // worker 内部异常：永久回退同步，本次同步补算
      worker.broken = true;
      killWorker();
      p.cb(null);
      return;
    }
    p.cb(msg);
  }

  function failPending() {
    var p = worker.pending;
    if (!p) return;
    worker.pending = null;
    if (p.timer) clearTimeout(p.timer);
    p.cb(null);
  }

  /** 懒建 Worker：候选路径依次探测（源码 dist/ 结构、发布平铺结构），ping 3s 超时换下一个。 */
  function ensureWorker(cb) {
    if (worker.broken) { cb(null); return; }
    if (worker.w) { cb(worker.w); return; }
    if (typeof Worker === 'undefined') { worker.broken = true; cb(null); return; }
    var urls = ['dist/engine.worker.js', 'engine.worker.js'];
    var idx = 0;
    function dropCurrent(next) {
      if (worker.pingTimer) { clearTimeout(worker.pingTimer); worker.pingTimer = null; }
      if (worker.w) { try { worker.w.terminate(); } catch (e) { } worker.w = null; }
      if (next) next();
    }
    function tryNext() {
      if (idx >= urls.length) { worker.broken = true; cb(null); return; }
      var w;
      try { w = new Worker(urls[idx++]); } catch (e) { tryNext(); return; }
      worker.w = w;
      var settled = false;               // ping 是否已确认可用
      w.onerror = function () {
        if (worker.w !== w) return;
        if (!settled) { dropCurrent(tryNext); }          // 探测期：换下一个候选
        else { worker.broken = true; dropCurrent(null); failPending(); }
      };
      w.onmessage = function (ev) {
        var msg = ev.data || {};
        if (msg.id === 0) {                              // ping 应答
          if (settled) return;
          settled = true;
          if (worker.pingTimer) { clearTimeout(worker.pingTimer); worker.pingTimer = null; }
          cb(worker.w);
          return;
        }
        handleWorkerResult(msg);
      };
      try { w.postMessage({ id: 0, variant: 'ping' }); }
      catch (e2) { dropCurrent(tryNext); return; }
      worker.pingTimer = setTimeout(function () {
        worker.pingTimer = null;
        if (worker.w === w && !settled) dropCurrent(tryNext);   // 3s 无响应 → 换下一个
      }, 3000);
    }
    tryNext();
  }

  /** 把一次 AI 求解交给 worker。成功 cb({move}|{stones})，不可用/失败 cb(null) 走同步。 */
  function workerCompute(req, cb) {
    ensureWorker(function (w) {
      if (!w) { cb(null); return; }
      var id = ++worker.seq;
      worker.pending = {
        id: id, cb: cb,
        timer: setTimeout(function () {
          // 计算超时（难档长搜）：作废本次在途结果、同步补算；不销毁 worker，
          // 迟到的结果因 id 不符会被丢弃，绝不重复落子、绝不卡死。
          if (worker.pending && worker.pending.id === id) {
            worker.pending = null;
            cb(null);
          }
        }, 45000)
      };
      try {
        w.postMessage({ id: id, variant: req.variant, difficulty: req.difficulty, seed: req.seed, payload: req.payload });
      } catch (e) {
        worker.broken = true;
        killWorker();
        cb(null);
      }
    });
  }

  function maybeAiTurn() {
    if (!game || game.finished) return;
    if (game.currentPlayer().kind === 'human') { refreshButtons(); return; }
    if (thinking) return;
    thinking = true;
    refreshButtons();
    showOverlay('AI 思考中（' + diffLabel(difficulty) + '）…');
    var gen = aiGen;
    var req = buildWorkerRequest();

    if (req) {
      workerCompute(req, function (res) {
        // 【易错点】"作废返回"必须先 thinking=false、refreshButtons()：
        // 否则按钮与提示停留在"AI 思考中"那套，界面看起来永久卡住。
        if (gen !== aiGen || !game || game.finished) {
          thinking = false;
          hideOverlay();
          if (game && !game.finished) { updateStatus(); }
          refreshButtons();
          return;
        }
        if (res) { applyAiResult(req, res, gen); return; }
        // Worker 不可用：先让浏览器画一帧（徽标已显示），再走同步回退
        requestAnimationFrame(function () {
          setTimeout(function () { syncAiTurn(gen); }, 40);
        });
      });
    } else {
      // 无 Worker（环境不支持/已永久回退）：先渲染再同步搜索，避免"界面像卡死"
      requestAnimationFrame(function () {
        setTimeout(function () { syncAiTurn(gen); }, 40);
      });
    }
  }

  /** 同步回退路径（与 Worker 化之前行为完全一致），仅当 Worker 不可用时走到这里。 */
  function syncAiTurn(gen) {
    // 【易错点】下面这条"作废返回"必须先 refreshButtons()：
    // 否则 thinking 虽然清了，按钮与提示仍是"AI 思考中"的那一套，
    // 界面看起来永久卡住（实测踩过：悔棋打断 AI 后按钮再也不亮）。
    if (gen !== aiGen || !game || game.finished) {
      thinking = false;
      hideOverlay();
      if (game && !game.finished) { updateStatus(); }
      refreshButtons();
      return;
    }
    var aiStones = null;
    var aiPlaced = [];
    if (isXiangqi()) {
      aiStones = game.aiTurn();
    } else {
      var eng = game.currentPlayer().engine;
      var stones = eng ? eng.getMove(game.board, game.current, game.maxStones) : [];
      var color = game.current;
      for (var i = 0; i < stones.length; i++) {
        var r = game.place(stones[i][0], stones[i][1]);
        if (!r.ok) break;
        aiPlaced.push({ x: stones[i][0], y: stones[i][1], color: color });
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
    afterAiMoved(aiStones, aiPlaced, gen);
  }

  /** 把 worker 回传的着法应用到真实对局（gen 令牌保证局面自请求以来未被改动）。 */
  function applyAiResult(req, res, gen) {
    var aiStones = null;
    var aiPlaced = [];
    if (req.variant === 'xiangqi') {
      var mv = res.move;
      if (mv) {
        // 与 XiangqiGame.aiTurn 的应用逻辑逐行同源（apply → 记谱 → 判将死）
        game.board.apply([mv[0], mv[1]], [mv[2], mv[3]], true);
        game.movesLog.push(mv);
        if (game.board.gameOver) {
          game.finished = true;
          game.winner = game.board.winner === XQ_RED ? XQ_RED : XQ_BLACK;
          game.reason = '将死';
        }
        aiStones = [[mv[0], mv[1]], [mv[2], mv[3]]];
      }
    } else {
      var stones = res.stones || [];
      var color = game.current;
      for (var i = 0; i < stones.length; i++) {
        var r = game.place(stones[i][0], stones[i][1]);
        if (!r.ok) break;
        aiPlaced.push({ x: stones[i][0], y: stones[i][1], color: color });
        if (r.line) break;
      }
      game.endRound();
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
      game.finished = true;
      game.reason = 'AI 无着可走';
    }
    afterAiMoved(aiStones, aiPlaced, gen);
  }

  /** AI 已落子：象棋走滑动动画、连珠类走出生动画；动画结束后刷新状态并连锁下一步。 */
  function afterAiMoved(aiStones, aiPlaced, gen) {
    if (isXiangqi() && aiStones && aiStones.length) {
      playSlide(function () {
        if (gen !== aiGen) { updateStatus(); refreshButtons(); return; }
        paint();
        updateStatus();
        refreshButtons();
        if (game.finished) { finishGame(); return; }
        if (game.board.checkFlag) Sfx.play('check');
        maybeAiTurn();                        // 连锁：机机/观战模式
      });
      return;
    }
    playBirth(aiPlaced, function () {
      if (gen !== aiGen) { updateStatus(); refreshButtons(); return; }
      paint();
      updateStatus();
      refreshButtons();
      if (game.finished) { finishGame(); return; }
      maybeAiTurn();                          // 连锁：下一个也是 AI（机机/观战）
    });
  }

  // ---------------------------------------------------------------- 终局
  function finishGame() {
    paint();
    updateStatus();
    refreshButtons();
    // 胜负音效：只在人机模式且有明确胜者时响（双人模式不替玩家庆祝）
    if (mode === 'human_ai' && game.winner != null) {
      Sfx.play(game.winner === humanSide ? 'win' : 'lose');
    }
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

    anim = { type: 'undo', order: ghosts, idx: 0, t: 0, ghosts: [], raf: 0, started: performance.now() };
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
    $('btnFlip').onclick = function () {
      // 翻转棋盘（仅象棋）：坐标换算全部走 xqView.disp/toGrid，翻转即改标志位
      if (!isXiangqi()) return;
      xqFlipped = !xqFlipped;
      xqView.flipped = xqFlipped;
      paint();
    };
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
      else if (e.key === 'Escape') {
        selected = [];
        // 象棋的选中状态存在 game.selectedFrom 里，Esc 要一并取消
        if (isXiangqi() && game && game.selectedFrom) { game.selectedFrom = null; }
        paint(); refreshButtons();
      }
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
      if (s.sound === false) $('chkSound').checked = false;   // 音效开关记忆
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
