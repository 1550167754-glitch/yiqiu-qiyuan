# 弈趣棋苑 网页版 · UI 重设计规格（ui-redesign-spec）

> 产出：文策渊（design-strategist） · 供 art-director 直接实施
> 范围：`web/index.html`、`web/style.css`、`web/app.js` 三文件外壳层。
> **本文档是唯一设计决策来源，实施者按条执行，无需再做设计判断。**
> 版本：v1.0

---

## 0. 不动区清单（先读，红线）

以下内容**保持原样，本规格任何条目均不得涉及**。它们负责棋盘内的所有动画，且被 app.js 动画状态机（`anim` / `playBirth` / `playSlide` / `doUndo`）依赖：

| 文件 | 不动内容 |
|---|---|
| `web/engine/boardview.js` | 连珠类棋盘渲染：落子出生动画（缩放+过冲）、悔棋倒退动画（上浮+缩小+淡出+涟漪）、棋子涟漪、胜利连线（winLine）绘制、last 落点标记、选点虚线预览 |
| `web/engine/xqview.js` | 象棋渲染：走子滑动动画（含被吃子淡出）、悔棋倒退幽灵动画、将军红圈标记、悬停高亮、绿环/红圈可走可吃提示、棋盘翻转坐标换算 |
| `web/app.js` 内部逻辑 | `anim` 状态机结构、`aiGen` 代数令牌、Worker 探测与回退链路、`Haptic`/`Feedback`/`Sfx` 模块的**函数签名**（只允许按 §4/§5 调整参数值与新增触发点，不得重构模块） |

**重要边界**：fxLayer（`#fxLayer`，DOM 叠加层）不属于引擎，本规格 §3 中所有"全板闪光/边缘光晕"都走这一层或纯 CSS，与引擎绘制互不重叠（fxLayer 是 inset 阴影光晕，不画棋子）。

---

## 1. 设计基调（一切效果的判定尺）

金墨质感：**深底（#171B24→#1F2430）为墨，金（--c-accent #E8B34B）为光**。所有新效果逐条对照：

- ✅ 光要"晕"不要"闪"：一律用 box-shadow / radial-gradient 的缓入缓出，**禁止** opacity 在 0↔1 间直切、禁止亮白高光、禁止频闪（任何循环动画周期 ≥ 1.4s，且幅度小）。
- ✅ 动要"落"不要"弹"：位移类用 `cubic-bezier(.2,.7,.3,1)`（--ease-move），回弹系数 ≤ 1.25，只允许 banner/replay 面板入场用一次。
- ✅ 颜色语义恒定：金=交互/胜利，绿（--c-ok）=落子/成功，红（--c-danger）=将军/危险，灰=失败/禁用。全站不得混用。
- ✅ 所有新动画包进 `@media (prefers-reduced-motion: no-preference)`，reduce 分支按 style.css 现有兜底方式追加选择器（保留 opacity 切换）。
- ✅ hover 效果全部包在 `@media (hover: hover)` 内（触屏不触发）。

---

## 2. 信息架构与分区

### 2.1 现状问题

三张卡片视觉权重相同、内容性质混杂：「对局设置」把**对局条件**（棋种/模式/执子/难度）、**外观偏好**（主题/材质/音效）、**开新局动作**压成一摞；「对局状态」里状态展示与操作按钮混排；高频操作（落子/悔棋）与低频危险操作（认输）视觉同级。

### 2.2 收纳原则

- **操作类最靠近手**：状态 + 操作合并为侧栏第一卡（用户视线从棋盘移到侧栏第一眼就是"该谁走、点什么"）。
- **设置类分两级**：对局条件（每局都可能改）留在卡片明面上；外观偏好（改一次管很久）默认折叠进「外观」子区。
- **记录类垫底**：棋谱卡维持最后，默认收起为最近几手。
- **危险操作降级**：认输、清空战绩一律 `btn small danger` 弱化样式，且清空已有二次确认（保留）。

### 2.3 结构树（对局页）

```
header.topbar
├── .brand（logo「弈」+ 弈趣棋苑 + 副标）
└── nav.tabs（对局 | 战绩 | 规则 + .tab-indicator 金条）

section#page-play .layout（grid: minmax(0,1fr) 320px）
├── .boardwrap#boardwrap（墨玉面板）
│   ├── canvas#board
│   ├── #fxLayer（全板闪光叠加层，不动结构）
│   ├── #overlay（AI 想棋徽标，右上角胶囊样式迁回 CSS，见 §3-E12）
│   └── #banner（终局横幅）
└── aside.sidebar（自上而下三卡）
    ├── 卡A「棋局」＝ 原对局状态卡 + 操作按钮（合并，优先级最高）
    │   ├── .status（轮到谁 / 本手进度 / 最后一手）
    │   ├── .actions（落子 | 结束回合 / 悔棋 | 翻转棋盘）
    │   ├── #btnResign（认输，占 actions 末位，danger small 视觉弱化）
    │   └── #hint（场景化一行提示）
    ├── 卡B「设置」＝ 原对局设置卡（重排）
    │   ├── 组1 对局条件：棋种 / 对弈方式 / 执子 / AI 难度
    │   ├── 组2 外观（默认折叠，点组标题展开）：棋盘主题 / 棋子材质 / 音效
    │   └── #btnNew「开新局」（primary，卡底通栏）
    └── 卡C「棋谱」＝ 原本局棋谱卡
        └── #moves（滚动区，默认 max-height 190px 保持）
```

### 2.4 布局示意（文字）

- **桌面（>860px）**：棋盘左、侧栏右，维持现 `grid-template-columns: minmax(0,1fr) 320px`。侧栏三卡依次为 棋局→设置→棋谱（即原第 2、1、3 卡换序）。
- **窄屏（≤860px）**：单列，顺序为 棋盘 → 卡A 棋局 → 卡B 设置 → 卡C 棋谱。
- **合并**：「对局状态」标题取消，与操作按钮同卡；音效从设置明面移入「外观」折叠组。
- **降级**：「认输」按钮从与悔棋同级降为 actions 网格末行小号 danger；「清空全部战绩」维持小号（已是）。
- **强调**：「开新局」（卡B 底部 primary 通栏）、「落子」（卡A actions 首位，ok 绿，可用态呼吸金光，见 §3-E8）。
- **折叠策略**：外观组用 `<details class="opts-group">` 或等价 class（`.opts-group.is-open`）实现；折叠头一行：「外观 ▾」，展开后为三行。折叠切换带 0.22s 高度过渡（复用 `.row.collapsed` 的过渡写法）。
- **战绩页/规则页**：结构不动，仅文案与卡片悬停微调（§3-E1、§3 文案表）。

---

## 3. 光效与反馈动画清单（重点）

实现层标注：**[CSS]** = 纯 CSS（keyframes/transition/box-shadow）；**[FX]** = `#fxLayer` DOM 叠加层（现有机制，class 触发）；**[不动]** = 引擎绘制，仅列出处以示边界。E 编号即验收编号。

### E1 卡片悬停 · [CSS]
`.card:hover`（包 `@media (hover:hover)`）：维持现状——border-color → `#414B60`、阴影加深。**不加拉起/缩放**（避免塑料感）。

### E2 卡片入场 · [CSS]
`.card` `cardIn` 错峰入场：维持现状（0.55s，延迟 0.07s/0.14s 递增）。

### E3 页签悬停与切换 · [CSS]
- `.tab:not(.is-on):hover`：文字变亮 + 7% 金底（现状保留）。
- `.tab-indicator` 金条滑动：维持 0.28s var(--ease-move)。
- **新增**：`.page.is-on` 入场淡入——`@keyframes pageIn { from { opacity:0; transform: translateY(4px); } to { opacity:1; transform:none; } }`，0.24s ease-out both，仅包在 no-preference 内。实现注意：`.page` 用 `display:none↔block` 切换，display 变化会自动重放动画，无需 JS。

### E4 通用按钮三态 · [CSS]
`.btn` hover（上浮 1px + 抬影）/ active（下沉 + inset 阴影）/ `::after` 涟漪（btnRipple 0.4s）：**全部维持现状**。

### E5 主按钮 hover · [CSS]
`.btn.primary:hover` 金色泛光（brightness 1.07 + 金影）：维持现状。

### E6 开新局三拍反馈 · [CSS]
`#btnNew` 的 loading（底部金流 btnFlow）→ success（btnSuccess 绿闪）→ 复位：结构维持。
**修改一处**：给 `#btnNew` 单独用金色成功态——新增 `.btn.primary.is-success { animation: btnSuccessGold .9s ease-out; }`，keyframes 与 btnSuccess 同节奏但颜色换 `rgba(232,179,75,…)`（30% 处 border-color: var(--c-accent); background-color: rgba(232,179,75,.14)）。绿色 success 保留给「落子」语义。reduce 分支追加 `.btn.primary.is-success` 到现有 animation:none 列表。

### E7 落子确认（选点→落定） · [CSS] + [不动]
- **新增 E7a**：`#btnConfirm:not(:disabled)` 可用态呼吸——`@keyframes okBreath { 0%,100% { box-shadow: 0 0 0 0 rgba(62,187,107,0); } 50% { box-shadow: 0 0 10px 1px rgba(62,187,107,.35); } }`，2.4s ease-in-out infinite（周期 ≥1.4s，克制动效）。禁用/终局态由 `:disabled` 的 opacity .42 覆盖，无需处理。
- E7b 点击涟漪：走 E4 现有 `.btn.ok:active::after`。
- E7c 落子入场动画：引擎 birth（[不动]）。

### E8 吃子 · [FX] + [CSS] + 震动
维持现有组合，不加重：`fx-layer.is-capture`（金色 inset 泛光 0.42s）+ `.boardwrap.shake-m`（0.34s）+ `Haptic.capture()`（§5）。金光色值 `rgba(232,179,75,.55)` 保持。

### E9 将军警示 · [FX] + [CSS] + 震动
- E9a `fx-layer.is-check` 红色 inset 泛光 0.55s + `shake-m`：维持。
- **新增 E9b**：状态行将军着色——`#lblTurn.is-check { color: #E8766F; text-shadow: 0 0 8px rgba(217,83,79,.5); }`，app.js 在 `bd.checkFlag` 为真且未终局时给 `#lblTurn` 加 `is-check`，终局/换局时移除。将军瞬间的强提示仍以 [FX] 红光为主，状态行只是常驻着色，不另加循环动画。

### E10 胜负终局 · [FX] + [CSS] + 震动
- E10a `fx-layer.is-win`（绿）/ `.is-lose`（灰）泛光 0.7s + `shake-l`：维持。
- E10b 将死补刀 `fx-layer.is-checkmate`（强红 0.9s）：维持。
- E10c `#banner` bannerPop 入场（scale .82→1.04→1）：维持。
- **新增 E10d（胜局限定）**：banner 顶部一道金光扫过——`.banner.is-win::before { content:''; position:absolute; left:0; right:0; top:0; height:2px; border-radius:2px; background: linear-gradient(90deg, transparent, var(--c-accent), transparent); animation: bannerSheen 1s ease-out .25s both; }`，`@keyframes bannerSheen { from { transform: translateX(-60%); opacity:0; } 30% { opacity:1; } to { transform: translateX(60%); opacity:0; } }`。app.js 生成 banner 时按胜负给 `#banner` 追加 `is-win`/`is-lose` class（is-lose 无 ::before 效果，仅占位）。banner 需补 `overflow:hidden`。

### E11 悔棋 · [CSS] + [不动] + 震动
- E11a `#btnUndo.is-loading`（底部金流 + 置灰）：维持现状。
- E11b 棋子倒退动画（上浮+缩小+淡出+涟漪）：引擎绘制，[不动]。
- E11c 无棋可悔 `flashBtnError`（红边 + btnErr 左右抖 0.4s）：维持。

### E12 AI 想棋徽标 · [CSS]（迁移）
现状：app.js `showOverlay` 用**内联样式**把 `#overlay` 改成右上角胶囊。实施时把这套样式迁回 style.css：新增 `.overlay.badge` 类（top:10px; right:10px; inset 其余 auto; width/height auto; background: rgba(24,28,36,.86); color:#F2E8D5; border-radius:999px; padding:5px 14px; font-size:13px; box-shadow:0 2px 10px rgba(0,0,0,.35); pointer-events:none），app.js 改为 `overlay.classList.add('badge')`。行为等价、无视觉变化，纯工程收编；如实施者评估改动 app.js 风险大，可保留内联（本条不影响验收）。`.ai-progress` 不确定进度金流与 `.spinner` 维持。
- E12b `.boardwrap.locked` 锁盘脉冲（lockPulse 1.4s 金边呼吸）：维持。

### E13 翻转棋盘 / 换主题 / 换材质 · [CSS]
`#board.theme-pulse` 亮度呼吸 0.22s：维持现状。

### E14 换棋种过渡 · [CSS]
`.boardwrap.swap-out` 淡出 → `swap-in` 淡入（0.18s / 0.32s）：维持现状。

### E15 下拉与复选 · [CSS]
`.row select:hover` 金边、`:focus-visible` 金环、checkbox hover 放大 1.12：全部维持。

### E16 弹窗（复盘）入场与遮罩 · [CSS]
- E16a `.replay-panel` replayPop（上浮+缩放 0.35s）：维持。
- **新增 E16b**：`.replay-modal` 遮罩淡入 `@keyframes fadeIn { from { opacity:0; } to { opacity:1; } }` 0.2s ease-out both；关闭不做退场动画（直接隐藏，克制）。

### E17 战绩列表项悬停 · [CSS]
**新增**：`@media (hover:hover) { .game-item:hover { border-color: var(--c-accent-d); transform: translateY(-1px); box-shadow: 0 4px 10px rgba(0,0,0,.18); } }`，`.game-item` 补 `transition: border-color .18s ease, transform .18s ease, box-shadow .18s ease`。

### E18 状态行轮到你脉冲 · [CSS]
`.status .line.pulse` turnPulse（金光文字呼吸 1.8s）：维持现状。

### 明确不做（负清单）
- 棋盘内涟漪/出生/连线光效 → 引擎已做，[不动]，DOM 层**不得**再叠加同位光点（会重影）。
- 禁止：卡片 hover 放大、按钮常亮循环动画、金色频闪边框、终局彩带/粒子雨、页面切换横滑。
- banner 每次显示只允许一次入场动画 + （胜局）一道金光，不加循环光效。

---

## 4. 震动反馈方案（navigator.vibrate）

桌面端无振动马达自动 no-op（现有 `Haptic` 已 try/catch 判空，无需额外处理），移动端按下表执行。**只改参数值与按下表新增两个触发点，不改 Haptic 模块结构。**

| 事件 | 触发点（app.js） | 现值 (ms) | **规格值 (ms)** | 说明 |
|---|---|---|---|---|
| 选点/选子 | 连珠选点、象棋选中（现无触感）→ 新增 `Haptic.select()` 于 `onBoardClick` 选点成功处与 `onXiangqiClick` 的 `r.select` 分支（与 `Sfx.play('select')` 同位） | — | `8` | 极轻确认 |
| 落子 | `Haptic.move()`（playSlide 无吃子分支、playBirth 每枚） | 8 | `12` | 短促"嗒" |
| 吃子 | `Haptic.capture()` | [16,10,22] | `[12,45,18]` | 短-顿-短重 |
| 将军 | `Haptic.check()`（玩家/ AI 造成将军两处） | [30,18,30,18,40] | `[25,60,25]` | 双拍警示，原五连拍过碎 |
| 胜 | `Haptic.win()` | [40,30,40,30,70] | `[35,45,35,45,90]` | 庆祝三连升 |
| 负 | `Haptic.lose()` | [70,40,120] | `[60,60,160]` | 沉底长震 |
| 悔棋 | 新增 `Haptic.undo()` = `18`，在 doUndo / doUndoXiangqi 确认 `removed` 后调用（与 is-loading 同步） | — | `18` | 轻回抽 |
| 终局横幅 | 不单独加：已由胜/负/将死路径覆盖 | — | — | 避免同帧双震 |

同帧去重约束：将死时会先走 win/lose 再补 check（finishGame 现逻辑），规格值下总时长可接受；若实测同帧连续调用被浏览器合并属正常行为，不做补偿。

---

## 5. 回放录像弹窗精修要点

弹窗 DOM 由 app.js `ensureReplayDom` 动态生成，类名结构不变，以下为样式与交互规格：

1. **控件排布**（一行化，减少三行折叠感）：
   - 头部 `.replay-head` 不动（标题+副标 左，关闭 右）。
   - 控制区合并为一行两段：`.replay-row`（上一步 | 播放/暂停 | 下一步）保持，进度条 `.replay-seek` 独占其下一整行（现状），速度档移到与进度条**同排右端**：`.replay-row` 改为 flex，`<input type="range">` `flex:1`，`.replay-speed` 组（含「速度」标签）`flex:0 0 auto` 靠右。窄屏 ≤520px 时速度组换行到下一行左对齐（现媒体查询微调即可）。
2. **进度条质感**：`#replaySeek` 自绘——
   - 轨道：`height:6px; border-radius:999px; background: linear-gradient(180deg, rgba(255,255,255,.06), rgba(255,255,255,.02)); border:1px solid var(--c-border);`
   - 滑块：`::-webkit-slider-thumb { appearance:none; width:14px; height:14px; border-radius:50%; background: linear-gradient(145deg, var(--c-accent), var(--c-accent-d)); box-shadow: 0 0 6px rgba(232,179,75,.5); border:none; }`，Firefox 用 `::-moz-range-thumb` 同值。
   - 已播段不着色（range 原生限制），以滑块金点为进度锚点即可，不做 JS 填色。
3. **速度档交互**：改为**分段控件**——`.replay-speed` 容器 `display:inline-flex; border:1px solid var(--c-border); border-radius:9px; overflow:hidden;`，四钮（慢/中/快/极快）去独立边框（`border:0; border-radius:0;`），相邻钮间 `border-left:1px solid var(--c-border)`；选中态 `.is-on`：`background: rgba(232,179,75,.18); color: var(--c-text); font-weight:700; box-shadow: inset 0 0 0 1px var(--c-accent);`。「速度」标签保留在组左侧。点击换挡立即生效（现逻辑已支持，播放中切换会重启节奏，保留）。
4. **视觉细节**：
   - `.replay-panel` 背景加一道与侧栏卡片一致的顶部暖光（复用 `.card` 的第一层 `linear-gradient(180deg, rgba(232,179,75,.040), transparent 58px)` 叠加）。
   - `.replay-boardwrap` 内加 `box-shadow: inset 0 0 24px rgba(0,0,0,.25);`（棋盘沉入感）。
   - `.replay-title` 用楷体题签（同 `.card h2` 的 font-family），前置一枚 `.card h2::before` 同款小金印点（用伪元素）。
   - 播放中 `#replayPlay`（is-on 由文字切换为「暂停」表达，现状保留），按钮 hover/active 复用 §3-E4。
5. **键盘**（新增，轻量）：弹窗打开时 ←/→ 单步、空格 播放/暂停（在现有 keydown 监听处补分支，注意 `e.target` 为 range 时方向键不劫持）。Esc 关闭已有。
6. **文案**：见 §6-P 组。控件文案（上一步/播放/暂停/下一步/速度/关闭/复盘录像）全部保留现词，仅副标格式微调。

---

## 6. 文案全量替换清单

**全站统一用语表**（先定词，后逐条替换）：

| 概念 | 统一词 | 弃用词 |
|---|---|---|
| 开新对局 | 开新局（按钮）/ 再来一盘（终局语） | 开始新对局、再来一局 |
| 确认落子 | 落子（按钮）；长句里用"落定" | 确认落子 |
| 本轮只下一枚后换手 | 结束回合 | 结束本回合 |
| AI 计算中 | 对手想棋中 | AI 正在思考、AI 思考中 |
| 计量：连珠类 | 手（全局）/ 枚（棋子） | 子（与象棋"步"混淆时） |
| 计量：象棋 | 步 | — |
| 无人可悔/无记录 | 还没… 句式 | 尚未…、暂无（列表空态除外） |

下表**原文→新文案**逐条可粘贴。「保留」= 措辞已自然，不动。定位列给出 文件 · 元素/选择器（app.js 动态串给出函数名）。

### 6-A 全局与元信息（4 条）

| # | 位置 | 原文 | 新文案 |
|---|---|---|---|
| A1 | index.html `<title>` | 弈趣棋苑 · 六子棋 / 五子棋 / 中国象棋 | 弈趣棋苑 — 六子棋 · 五子棋 · 中国象棋 |
| A2 | index.html head（**新增行**，title 之后） | （无） | `<meta name="description" content="弈趣棋苑：打开就能下的六子棋、五子棋、中国象棋，可人机对弈或同屏双人，无需注册。">` |
| A3 | index.html footer 左 span | 弈趣棋苑 · 网页版 | 保留 |
| A4 | index.html footer 右 span | 纯前端运行，无需服务器；棋谱与战绩保存在本机 | 打开即玩，数据都存在你这台设备上 |

### 6-B 顶部导航（5 条）

| # | 位置 | 原文 | 新文案 |
|---|---|---|---|
| B1 | .brand h1 | 弈趣棋苑 | 保留 |
| B2 | .brand p | 六子棋 · 五子棋 · 中国象棋 | 保留 |
| B3 | .tab[data-page=play] | 对局 | 保留 |
| B4 | .tab[data-page=records] | 战绩 | 保留 |
| B5 | .tab[data-page=help] | 规则 | 保留 |

### 6-C 设置卡（卡B，17 条）

| # | 位置 | 原文 | 新文案 |
|---|---|---|---|
| C1 | 卡B h2（原「对局设置」） | 对局设置 | 设置 |
| C2 | 折叠组头（**新增**，见 §2.4） | （无） | 外观 ▾ |
| C3 | #variant 选项1 | 六子棋（19×19 连六） | 六子棋（19 路 · 连六） |
| C4 | #variant 选项2 | 五子棋（15×15 连五） | 五子棋（15 路 · 连五） |
| C5 | #variant 选项3 | 中国象棋（9×10） | 中国象棋（9×10 盘） |
| C6 | 行标签 棋种 | 棋种 | 保留 |
| C7 | 行标签 模式 | 模式 | 对弈方式 |
| C8 | #mode 选项1 | 人机对战 | 人机对弈 |
| C9 | #mode 选项2 | 本地双人 | 同屏双人 |
| C10 | 行标签 我执 | 我执 | 执子 |
| C11 | #side 默认两选项（index.html） | 黑（先手）/ 白（后手） | 保留 |
| C12 | #difficulty 三选项 | 简单/中等/困难 | 保留 |
| C13 | 行标签 AI 难度 | AI 难度 | 保留 |
| C14 | 行标签 棋盘主题 | 棋盘主题 | 保留 |
| C15 | 行标签 棋子材质 | 棋子材质 | 保留 |
| C16 | 行标签 音效 | 音效 | 保留 |
| C17 | #btnNew | 开始新对局 | 开新局 |

### 6-D 棋局卡（卡A，原「对局状态」，16 条）

| # | 位置 | 原文 | 新文案 |
|---|---|---|---|
| D1 | 卡A h2 | 对局状态 | 棋局 |
| D2 | #btnConfirm | 确认落子 | 落子 |
| D3 | #btnPass | 结束本回合 | 结束回合 |
| D4 | #btnUndo | 悔棋 | 保留 |
| D5 | #btnResign | 认输 | 保留 |
| D6 | #btnFlip | 翻转棋盘 | 保留 |
| D7 | index.html 静态 #hint | 在棋盘上点选落点，选满后自动落下；本回合只想走一枚时，可点「结束本回合」。 | 点棋盘选位，选满自动落定；只想下一枚，就点「结束回合」。 |
| D8 | app.js refreshButtons 连珠提示 | 点击棋盘选点（最多 X 个），选满自动落子；也可选 1 子后点「结束本回合」。 | 点棋盘选位（最多 X 枚），选满自动落定；只想下一枚就点「结束回合」。 |
| D9 | app.js refreshButtons 象棋提示 | 点自己的棋子选中（绿环=可走，红圈=可吃），再点目标即可走子；Esc 取消选中。 | 点己方棋子选中（绿圈能走、红圈能吃），再点目标位置落子；按 Esc 取消。 |
| D10 | app.js refreshButtons 终局提示 | 本局已结束，点「开始新对局」继续。 | 这局下完了，点「开新局」再来一盘。 |
| D11 | app.js refreshButtons AI 思考 | AI 正在思考，请稍候… | 对手想棋中… |
| D12 | app.js updateStatus lblTurn 人机 | 轮到你 | 保留 |
| D13 | app.js updateStatus lblTurn（思考中后缀） | （思考中） | （想棋中） |
| D14 | app.js updateStatus lblStep 连珠进行中 | 本轮已下 X/Y 子，还可下 Z 子 | 本手已下 X/Y，还能下 Z 枚 |
| D15 | app.js updateStatus lblMove 连珠空局 | 尚未落子 | 还没落子 |
| D16 | app.js updateStatus lblMove 象棋空局 | 尚未行棋 | 还没走子 |

（D 组补充约定：`lblStep` 象棋「轮到红方/黑方（被将军！）」→ 改为「红方行棋，将军！」/「黑方行棋」；「共 X 步」「共 X 手」「上一步：」「最后一手：」格式保留；连珠将军无此行。）

### 6-E 棋谱卡（2 条）

| # | 位置 | 原文 | 新文案 |
|---|---|---|---|
| E1 | 卡C h2 | 本局棋谱 | 棋谱 |
| E2 | app.js renderMoves 空态 | （暂无） | 保留 |

### 6-F 棋盘浮层（overlay / banner，7 条）

| # | 位置 | 原文 | 新文案 |
|---|---|---|---|
| F1 | index.html #overlayText 默认 | AI 思考中… | 对手想棋中… |
| F2 | app.js showOverlay 默认参 | AI 思考中… | 对手想棋中… |
| F3 | app.js maybeAiTurn 调用 | AI 思考中（中等）… | 对手想棋中（中等）…（括号内为难度名） |
| F4 | app.js finishGame banner 按钮 | 再来一局 | 再来一盘 |
| F5 | app.js finishGame banner 按钮 | 复盘录像 | 保留 |
| F6 | app.js finishGame sub 格式 | 共 X 步 · {原因} / 共 X 手 · {原因} | 保留 |
| F7 | banner 主行 game.resultText() | 引擎串 | 见 6-M 引擎侧标注 |

### 6-G 战绩页（12 条）

| # | 位置 | 原文 | 新文案 |
|---|---|---|---|
| G1 | h2 | 棋手战绩 | 战绩 |
| G2 | 表头 ×5 | 棋手 / 类型 / 胜 / 负 / 平 | 保留 |
| G3 | 表格 类型值 | AI / 玩家 | 保留 |
| G4 | hint | 数据保存在本机浏览器（localStorage），不上传服务器。 | 战绩只存在你这台设备的浏览器里，不会上传。 |
| G5 | h2 | 最近对局 | 保留 |
| G6 | #btnClear | 清空全部战绩 | 清空战绩 |
| G7 | app.js btnClear confirm() | 确定清空全部战绩记录吗？此操作不可撤销。 | 清空后所有战绩都找不回来，确定全删吗？ |
| G8 | renderRecords 表格空态 | 暂无战绩记录，先下几局吧。 | 还没有战绩，下一局就开始攒。 |
| G9 | renderRecords 列表空态 | 暂无对局记录。 | 还没下过棋，去下一局吧。 |
| G10 | 列表结果 tag | 黑胜 / 白胜 / 和棋 | 保留 |
| G11 | 列表棋种名 | 五子棋 / 六子棋 | 保留 |
| G12 | 列表行格式 | {棋种} · X 手 · {原因} · {时间} | 保留（日期格式 YYYY-MM-DD HH:mm 不变） |

### 6-H 规则页（15 条）

| # | 位置 | 原文 | 新文案 |
|---|---|---|---|
| H1 | h2 | 六子棋 Connect6 | 六子棋 |
| H2 | 六子棋 规则1 | 19×19 棋盘，黑先；黑方第一轮只下 1 子，之后每轮双方各下 1~2 子。 | 19 路棋盘，黑棋先行。黑棋第一手只下 1 枚，之后双方每轮各下 1～2 枚。 |
| H3 | 六子棋 规则2 | 横、竖、斜任一方向连成 6 子即胜。 | 横、竖、斜任意方向连成 6 枚即胜。 |
| H4 | 六子棋 规则3 | 常见棋型：4 连两端开放（活四）→ 补一头成活五，两端都能成六，对手堵不完即必胜。 | 小提示：两头空的四连（活四）几乎必胜——补一头就是活五，对手堵不住两头。 |
| H5 | h2 | 五子棋 Gomoku | 五子棋 |
| H6 | 五子棋 规则1 | 15×15 棋盘，黑先；每轮双方各下 1 子；连成 5 子即胜。 | 15 路棋盘，轮流各下一枚，先连成 5 枚的一方胜。 |
| H7 | h2 | 中国象棋 Xiangqi | 中国象棋 |
| H8 | 象棋 规则1 | 红先。完整规则：马蹩腿、象塞眼、炮隔子吃、兵过河可平移、将帅不可照面。 | 红先黑后。马蹩腿、象塞眼、炮打隔子、过河兵能横走、将帅不能照面——和街边象棋一个下法。 |
| H9 | 象棋 规则2 | 将死或困毙（无合法着法）均判负。 | 被将死，或轮到自己却无棋可走，都算输。 |
| H10 | 象棋 规则3 | 点子走子：先点己方棋子（绿环=可走、红圈=可吃），再点目标格即可；Esc 取消选中。 | 点子走棋：先点自己的棋子（绿圈＝能走的点，红圈＝能吃的子），再点要去的位置；按 Esc 取消。 |
| H11 | 象棋 规则4 | 执黑时棋盘自动翻转（己方在下方），也可随时点「翻转棋盘」。 | 执黑时棋盘会自动翻过来，你的棋子始终在下方；也可以随时点「翻转棋盘」调头。 |
| H12 | h2 | 操作说明 | 怎么玩 |
| H13 | 操作 规则1 | 连珠类两步落子：先点棋盘选点（虚线预览），再点「确认落子」。 | 六子棋和五子棋落子分两步：先点棋盘选位（有虚线预览），再点「落子」确认。 |
| H14 | 操作 规则2 | 悔棋：人机模式一次撤掉「AI 一轮 + 我方一轮」，回到我方行棋；带倒退动画。 | 悔棋：人机模式下一次撤回对手和你各一手，回到你行棋，棋子带倒退动画。 |
| H15 | 操作 规则3/4 | 快捷键：Enter 确认落子（连珠类）、Esc 取消选择。／音效在设置里可开关，选择会自动记忆。 | 快捷键：Enter 落子（六子/五子），Esc 取消选择。音效在「设置 → 外观」里开关，选好会自动记住。 |

### 6-I 复盘弹窗（11 条）

| # | 位置 | 原文 | 新文案 |
|---|---|---|---|
| I1 | aria-label / .replay-title | 复盘录像 | 保留 |
| I2 | #replayClose | 关闭 | 保留 |
| I3 | #replaySub 格式 | 第 X / Y 手 ／ 第 X / Y 手 · 轮到红方 | 保留 |
| I4 | #replayPrev | 上一步 | 保留 |
| I5 | #replayPlay | 播放 / 暂停 | 保留 |
| I6 | #replayNext | 下一步 | 保留 |
| I7 | .replay-speed-label | 速度 | 保留 |
| I8-I11 | 速度四档 | 慢 / 中 / 快 / 极快 | 保留 |

### 6-J 玩家命名（app.js 动态，6 条）

| # | 位置 | 原文 | 新文案 |
|---|---|---|---|
| J1 | mkPlayer 人机我方 | 我 | 保留 |
| J2 | mkPlayer AI | AI（简单/中等/困难） | 保留 |
| J3 | mkPlayer 双人连珠 | 黑方（玩家1）/ 白方（玩家2） | 玩家1 · 黑方 / 玩家2 · 白方 |
| J4 | mkXqPlayer 双人象棋 | 红方（玩家1）/ 黑方（玩家2） | 玩家1 · 红方 / 玩家2 · 黑方 |
| J5 | updateStatus 双人轮转 | 轮到 {名字} | 保留 |
| J6 | diffLabel | 简单/中等/困难 | 保留 |

### 6-K 终局原因串（app.js，4 条）

| # | 位置 | 原文 | 新文案 |
|---|---|---|---|
| K1 | applyFallbackXiangqiMove / reason | 将死 | 保留（术语准确） |
| K2 | reason 兜底 | AI 无着可走 | 对手无棋可走 |
| K3 | syncAiTurn/applyAiResult reason 兜底 | AI 无着可走 | 对手无棋可走 |
| K4 | 战绩/终局共用 reason 空值 | '' | 保留 |

### 6-L 合计

文案条目合计 **82 条**（保留 34 · 替换 47 · 新增 1）。替换项均为可直接粘贴的整句/整词。

### 6-M 引擎侧字符串（不在本规格改动范围，标注供知晓）

以下字符串位于引擎（`src/engine/…` → `dist/engine.bundle.js`），属 §0 不动区，本次**不改**；若后续引擎发版，建议同步：`game.resultText()` 的 黑方胜/白方胜/和棋/六子胜 系（banner 主行与战绩 tag 各有一套，现基本一致）；`game.place` 返回的用户提示（如「已取消选择」「此处不能落子」类）；reason「困毙」等。当前措辞自然，保留即可。

---

## 7. 实施顺序建议（给 art-director）

1. 文案全量替换（§6，纯字符串，零风险，先落）；
2. IA 重排（§2：卡A/卡B 换序合并 + 外观折叠组 + 认输降级）；
3. 新增动效（§3：E3 页面淡入、E6 金色 success、E7a 呼吸、E9b 将军着色、E10d banner 金光、E16b 遮罩淡入、E17 列表悬停、E12 样式收编）；
4. 复盘弹窗精修（§5）；
5. 震动参数与新增触发点（§4）。

每步独立可验收；任一步出问题可单独回退，不影响已落步骤。

## 8. 验收标准

- [ ] §6 中全部「替换/新增」条目在页面中逐条比对通过，全站无「确认落子/结束本回合/开始新对局/AI 思考中/尚未/暂无（表格空态除外）」残留；
- [ ] 同一动作全站用词一致（以 §6 开头用语表为准）；
- [ ] §3 所有新增动效在 Chrome（hover 设备与触屏各一）与 `prefers-reduced-motion: reduce` 下行为符合规格；
- [ ] §4 震动在 Android Chrome 实机触发正常，桌面端无报错；
- [ ] §5 复盘弹窗在 ≤520px 与桌面两种宽度下排布正确，四档速度点击即生效；
- [ ] `web/engine/boardview.js`、`web/engine/xqview.js` 与 app.js 的 `anim`/`Haptic`/`Feedback`/`Sfx` 模块结构零 diff（仅允许 §4/§5/§3-E9b/E10d/E12 指明的行级改动）。
