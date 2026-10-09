/**
 * serve.js —— 零依赖本地静态服务器（开发/预览用）
 *
 *   node web/serve.js                     # 默认 5178，服务 web/（开发目录）
 *   node web/serve.js 8080                # 指定端口
 *   node web/serve.js 8080 web/dist/site  # 指定要服务的目录（用于验证发布产物）
 *
 * 只用 Node 内置模块，不装任何包。启动后自动打开浏览器。
 * 正式发布不需要它：整个目录是纯静态文件，直接丢到任意静态托管即可。
 */

var http = require('http');
var fs = require('fs');
var path = require('path');
var url = require('url');
var child_process = require('child_process');

var PORT = parseInt(process.argv[2], 10) || 5178;
// 要服务的目录：默认是脚本所在目录；可用第 3 个参数指定（例如发布产物目录）
var ROOT = process.argv[3]
  ? path.resolve(process.cwd(), process.argv[3])
  : __dirname;

var MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
  '.woff2': 'font/woff2',
  '.wav': 'audio/wav',
  '.mp3': 'audio/mpeg'
};

var server = http.createServer(function (req, res) {
  var pathname = decodeURIComponent(url.parse(req.url).pathname);
  if (pathname === '/') pathname = '/index.html';
  // 防目录穿越
  var filePath = path.normalize(path.join(ROOT, pathname));
  if (filePath.indexOf(ROOT) !== 0) {
    res.writeHead(403); res.end('403'); return;
  }
  fs.stat(filePath, function (err, st) {
    if (err || !st.isFile()) {
      res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
      res.end('404 找不到：' + pathname);
      return;
    }
    var ext = path.extname(filePath).toLowerCase();
    res.writeHead(200, {
      'Content-Type': MIME[ext] || 'application/octet-stream',
      'Cache-Control': 'no-cache'
    });
    fs.createReadStream(filePath).pipe(res);
  });
});

server.listen(PORT, '127.0.0.1', function () {
  var urlStr = 'http://127.0.0.1:' + PORT + '/';
  console.log('弈趣棋苑 网页版已启动：' + urlStr);
  console.log('（按 Ctrl+C 停止）');
  try {
    // Windows / macOS 都支持；失败就手动打开
    if (process.platform === 'win32') {
      child_process.exec('start "" "' + urlStr + '"');
    } else if (process.platform === 'darwin') {
      child_process.exec('open "' + urlStr + '"');
    } else {
      child_process.exec('xdg-open "' + urlStr + '"');
    }
  } catch (e) { /* 忽略：用户可以自己打开 */ }
});

server.on('error', function (e) {
  if (e.code === 'EADDRINUSE') {
    console.error('端口 ' + PORT + ' 已被占用，换一个：node web/serve.js 5180');
  } else {
    console.error('启动失败：' + e.message);
  }
  process.exit(1);
});
