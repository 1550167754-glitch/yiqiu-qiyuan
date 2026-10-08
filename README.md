# 六子棋 Connect6（计算机博弈）

面向计算机博弈比赛的六子棋游戏，含**本地 AI**（极大极小 + Alpha-Beta + PVS +
置换表 + 走法排序 + 迭代加深 + 威胁搜索）、**大模型引擎**（DeepSeek / 千问）、
三种对局模式、PostgreSQL 战绩存档（可选）。

> 本公开仓库只含源码、开源字体与音效。运行时所需的无损背景音乐与真实 API
> 密钥**不包含**（见下方"仓库说明"），clone 后可直接编译运行，功能完整。

---

## 一、标准分层目录

```
六子棋源代码/
├─ run.py               统一入口（打包 / 源码运行），失败自动降级文字菜单
├─ 启动六子棋.bat        源码运行（需 venv）
├─ build_exe.bat        一键打包（资源全部内嵌，自包含）
├─ setup_dev.bat        一键建 venv + 装依赖
├─ requirements.txt
├─ src/                 代码库（标准 src 布局，纯 .py，无缓存）
│   └─ liuziqi/         业务/引擎包（15 个模块 + main.py）
│       ├─ board.py     棋盘：落子/悔棋/连六判定/候选点
│       ├─ ai.py        本地 AI：Alpha-Beta+PVS+置换表+迭代加深+威胁搜索
│       ├─ llm_ai.py    大模型引擎（DeepSeek/千问），失败回退本地 AI
│       ├─ game.py      对局状态机（轮次/计时/悔棋/棋谱）
│       ├─ gui.py       图形界面：启动页+对战页+两步落子+胜率曲线+GlowButton
│       ├─ music.py     背景音乐（MCI），无损 WAV 支持，切歌释放设备
│       ├─ sounds.py    程序化合成音效
│       ├─ theme_boards.py  5 种棋盘皮肤
│       ├─ fonts.py     艺术字体私有注册（GDI）
│       ├─ winrate.py   本地胜率评估（sigmoid 映射）
│       ├─ database.py  PostgreSQL 战绩存档（可选）
│       ├─ pgcheck.py   DB 环境检测 / 启动
│       ├─ replay.py    棋谱回放窗口
│       └─ paths.py     资源路径解析（开发 / 打包通用）
├─ assets/              资源根
│   ├─ sounds/          音效（点击/落子/胜/负）
│   ├─ fonts/           艺术字体 TTF（Google Fonts 开源）
│   ├─ music/           背景音乐（本地放置，不入库）
│   ├─ icon.ico         窗口/程序图标
│   ├─ icon64.png
│   └─ logo.png
├─ engine/              第三方引擎（Pikafish NNUE，可执行文件 + 权重，不入库）
├─ scripts/             构建与安装脚本（build_exe.bat / setup_dev.bat 等）
├─ config/              实际配置（含密钥，已被 .gitignore 排除）
├─ config.example/      配置占位模板（database.ini / llm.ini，不含真实密钥）
├─ data/  logs/         运行期数据（回放/战绩）与日志，程序自动创建
└─ dist/  build/        打包产物（build_exe.bat 生成；已入库忽略，用时重建）
```

### 仓库说明

- **背景音乐 `assets/music/`（无损 WAV，约 273MB）不在仓库内**：体积过大且可能
  涉及音频版权。运行时该目录不存在会自动跳过，功能不受影响；如需音乐，把 WAV
  放入本地 `assets/music/` 即可。
- **`config/`（真实配置）不在仓库内**：含 PostgreSQL 口令与 LLM API Key，属敏感
  信息。请复制 `config.example/` 为 `config/` 并按需填写。

---

## 二、本次发布新增 / 修复

| 项 | 说明 |
| --- | --- |
| **UI 高清晰渲染** | Windows 下启用进程级 DPI 感知（per-monitor），按显示器真实 DPI 设置 tk 缩放；文字/棋盘锐利不模糊 |
| **两步落子** | 先点棋盘「选中位置」（虚线预览 + ✓），再点右侧栏「确认落子」正式落子；Enter=确认、Esc=取消；状态与按钮可用性实时反馈 |
| **右侧栏胜率曲线** | 新增「胜率曲线」实时折线小图：横轴手数、纵轴 0~100%，基线 50%，标注每子黑/白胜率%；黑方落 1 子、AI 落 2 子均逐子取点，全程与手数一一对应 |
| **音乐系统** | 无损 Hi-Fi WAV 统一放 `assets\music\`；播放前释放上一 MCI 设备避免切歌错乱 |
| **棋盘窗口缩放** | 按 `min(可用宽,可用高)` 等比居中重绘，始终完整显示、不变形 |
| **资源零丢失** | 打包时通过 `--add-data` 把 fonts/sounds/music/icon 全部内嵌，`dist\` 自包含 |

---

## 三、运行

- **源码运行**：双击 `启动六子棋.bat`（需已建 venv，见 setup_dev.bat）。
- **打包运行**：先跑 `build_exe.bat` 生成 `dist\六子棋\六子棋.exe`，双击即可。
- **命令行对弈**：`python -m src.liuziqi.main --cli`。

## 四、打包

```bat
build_exe.bat
```

- 产物：`dist\六子棋\六子棋.exe`（onedir，自包含全部资源）。
- 全部资源通过 `--add-data` 内嵌；同时复制一份到 exe 同目录 `assets\`、`config\`，
  便于用户放入自定义音乐或修改配置，二者以 exe 同目录为准。

## 五、技术要点

- 仅标准库 + tkinter；PostgreSQL / 大模型为可选，未就绪自动降级，不影响对弈。
- 默认不限时（休闲对弈）；AI 落子在工作线程计算，主线程保持流畅（16GB 内存友好）。
- 两步落子 + 胜率曲线均在 GUI 层实现，引擎层（board/ai/game）不受影响，可独立复用。
