/**
 * build.js —— 把引擎层打包成浏览器可直接用的单文件（零依赖，不需要 npm 装东西）
 *
 *   node web/build.js
 *
 * 做法：把 engine/*.js 原样塞进一个模块注册表（CommonJS 的 require 语义），
 * 浏览器里通过全局 `E` 取用，例如 E.board / E.game / E.ai / E.boardview。
 *
 * 【为什么不用 webpack/vite】这个项目要保持"零依赖、拿到就能跑"：
 * 引擎文件本身没有任何 import 语法魔法，只要给个 require 实现即可，
 * 一个 60 行的打包脚本比引入整个构建链更可靠、也不需要联网装包。
 */

var fs = require('fs');
var path = require('path');

var ROOT = __dirname;
var ENGINE = path.join(ROOT, 'engine');
var OUT = path.join(ROOT, 'dist');

// 依赖顺序无关紧要：模块在 require 时惰性求值
var FILES = ['board.js', 'game.js', 'ai.js', 'boardview.js', 'xiaqi.js', 'xqview.js', 'store.js'];

function read(f) {
  return fs.readFileSync(path.join(ENGINE, f), 'utf8');
}

var parts = [];
parts.push('/* 自动生成，请勿手改 —— 源文件在 web/engine/，改完跑 node web/build.js */');
parts.push('(function (root) {');
parts.push('  var __mods = {};');
parts.push('  var __cache = {};');
parts.push('  function __req(name) {');
parts.push('    if (__cache[name]) return __cache[name].exports;');
parts.push('    var m = { exports: {} };');
parts.push('    __cache[name] = m;');
parts.push('    if (!__mods[name]) throw new Error("模块未打包: " + name);');
parts.push('    __mods[name](m, m.exports, __req);');
parts.push('    return m.exports;');
parts.push('  }');

FILES.forEach(function (f) {
  var key = './' + f;
  var src = read(f);
  parts.push('  __mods[' + JSON.stringify(key) + '] = function (module, exports, require) {');
  parts.push(src);
  parts.push('  };');
});

// 各模块的 require('./x.js') 会被原样调用，键名一致即可
parts.push('  var E = {');
parts.push('    board: __req("./board.js"),');
parts.push('    game: __req("./game.js"),');
parts.push('    ai: __req("./ai.js"),');
parts.push('    boardview: __req("./boardview.js"),');
parts.push('    xiaqi: __req("./xiaqi.js"),');
parts.push('    xqview: __req("./xqview.js"),');
parts.push('    store: __req("./store.js"),');
parts.push('    require: __req');
parts.push('  };');
// 双环境出口：浏览器挂到全局（window.E），Node 里走 module.exports 以便自检/测试
parts.push('  root.E = E;');
parts.push('  if (typeof module !== "undefined" && module.exports) module.exports = E;');
parts.push('})(typeof globalThis !== "undefined" ? globalThis : this);');

if (!fs.existsSync(OUT)) fs.mkdirSync(OUT, { recursive: true });
var outFile = path.join(OUT, 'engine.bundle.js');
fs.writeFileSync(outFile, parts.join('\n'), 'utf8');
console.log('已生成 ' + outFile + '（' + (fs.statSync(outFile).size / 1024).toFixed(1) + ' KB）');

// ------------------------------------------------------------------ 发布目录
// 静态托管只认"根目录下有 index.html"，而本项目的网页版在 web/ 子目录里，
// 直接整仓部署会 404。所以这里把发布所需文件复制成一个自包含目录 web/dist/site/。
//
// 【务必保持"零子目录"】曾经把 bundle 放在 site/dist/ 下，结果用拖拽上传时
// **子目录整个丢了**（Netlify 上只有根目录那几个文件，/dist/engine.bundle.js 404），
// 站点打开是白屏（缺引擎）。现在所有文件都平铺在 site/ 根目录，
// 怎么传都不会漏；文件名加前缀区分用途。
var SITE = path.join(OUT, 'site');
if (fs.existsSync(SITE)) fs.rmSync(SITE, { recursive: true, force: true });
fs.mkdirSync(SITE, { recursive: true });

var PUBLISH = [
  ['index.html', 'index.html'],
  ['style.css', 'style.css'],
  ['app.js', 'app.js'],
  ['favicon.svg', 'favicon.svg'],
  [path.join('dist', 'engine.bundle.js'), 'engine.bundle.js']   // 平铺，不放子目录
];
var copied = [];
PUBLISH.forEach(function (pair) {
  var src = path.join(ROOT, pair[0]);
  var dst = path.join(SITE, pair[1]);
  if (!fs.existsSync(src)) {
    if (pair[0] === 'favicon.svg') return;      // 可选文件
    throw new Error('发布文件缺失: ' + src);
  }
  fs.copyFileSync(src, dst);
  copied.push(pair[1] + '（' + (fs.statSync(dst).size / 1024).toFixed(1) + ' KB）');
});
// 静态托管常需要它来关闭 Jekyll 处理（GitHub Pages 尤其）
fs.writeFileSync(path.join(SITE, '.nojekyll'), '', 'utf8');

// 发布版 index.html 里的资源引用要"压平"：源码结构是 web/index.html + web/dist/engine.bundle.js，
// 而发布目录把所有文件都放在一层。这里直接把引用改写掉，避免线上 404。
var siteIndex = path.join(SITE, 'index.html');
var siteHtml = fs.readFileSync(siteIndex, 'utf8')
  .replace(/dist\/engine\.bundle\.js/g, 'engine.bundle.js');
fs.writeFileSync(siteIndex, siteHtml, 'utf8');

// 自检：发布目录里 index.html 引用的每个本地资源都必须存在，
// 否则上线后才白屏（这次就是吃了这个亏，所以加一道自动检查）
var html = fs.readFileSync(siteIndex, 'utf8');
var refs = [];
html.replace(/(?:src|href)="([^"]+)"/g, function (m, u) {
  if (/^(https?:)?\/\//.test(u) || u.charAt(0) === '#') return m;
  refs.push(u);
  return m;
});
var missing = refs.filter(function (u) {
  return !fs.existsSync(path.join(SITE, u.replace(/^\//, '')));
});
if (missing.length) {
  throw new Error('发布目录缺少 index.html 引用的资源: ' + missing.join(', '));
}
var subs = [];
(function walk(dir) {
  fs.readdirSync(dir).forEach(function (n) {
    var p = path.join(dir, n);
    if (fs.statSync(p).isDirectory()) { subs.push(n); walk(p); }
  });
})(SITE);
if (subs.length) throw new Error('发布目录不该有子目录（拖拽上传会漏）: ' + subs.join(', '));

console.log('已生成发布目录 ' + SITE + '（零子目录）：');
copied.forEach(function (c) { console.log('   ' + c); });
console.log('   引用的本地资源全部就位：' + refs.join(' / '));

// ------------------------------------------------------------------ GitHub Pages 载体
// GitHub Pages 只能从"仓库根目录"或"仓库里的 docs/ 目录"发布，不能指定 /web。
// 而且不能指定更深的子目录（没有 docs/pages 这种选项），所以网页产物直接平铺进 docs/。
//
// ⚠ docs/ 里本来就有项目的《开发日志.md》（仓库原有内容），绝不能整个清空。
//   这里只覆盖/新增"网页产物这几个固定文件名"，其余文件一律不碰。
var DOCS = path.join(ROOT, '..', 'docs');
if (!fs.existsSync(DOCS)) fs.mkdirSync(DOCS, { recursive: true });
var PAGE_FILES = ['index.html', 'style.css', 'app.js', 'engine.bundle.js', 'favicon.svg', '.nojekyll'];
PAGE_FILES.forEach(function (name) {
  var src = path.join(SITE, name);
  if (fs.existsSync(src)) fs.copyFileSync(src, path.join(DOCS, name));
});
// 旧的 docs/pages/ 产物清掉（改布局后不再需要，避免仓库里留两套）
var OLD_PAGES = path.join(DOCS, 'pages');
if (fs.existsSync(OLD_PAGES)) fs.rmSync(OLD_PAGES, { recursive: true, force: true });
console.log('已铺好 GitHub Pages 载体 docs/（Pages 源选 main /docs）');
console.log('   注意：docs/开发日志.md 等项目文档未被触碰');

// 顺手做一次语法自检：在 Node 里加载打包产物，确认模块键名与导出都对得上
try {
  delete require.cache[require.resolve(outFile)];
  var E = require(outFile);
  var need = ['board', 'game', 'ai', 'boardview', 'xiaqi', 'xqview', 'store'];
  var missing = need.filter(function (k) { return !E[k]; });
  if (missing.length) throw new Error('缺少导出: ' + missing.join(','));
  var b = new E.board.Board(19, 6);
  b.place(9, 9, 1);
  if (b.moveCount !== 1) throw new Error('打包后引擎不可用');
  var xq = new E.xiaqi.XiangqiBoard();
  if (xq.legalMoves(E.xiaqi.RED).length !== 44) throw new Error('打包后象棋引擎不可用');
  console.log('打包产物自检通过：' + need.join(' / '));
} catch (e) {
  console.error('打包产物自检失败：' + e.message);
  process.exit(1);
}
