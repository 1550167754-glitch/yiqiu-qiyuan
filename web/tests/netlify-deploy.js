/**
 * netlify-deploy.js —— 用 CDP 在"已登录的 Edge"里把网页版部署到 Netlify
 *
 *   node web/tests/netlify-deploy.js [siteName] [cdpPort]
 *
 * 为什么要这么绕：Netlify 的网页上传控件需要真实用户操作（文件选择框/拖拽），
 * 自动化脚本碰不到。但通过 CDP 可以在页面里**构造** File 对象塞进 <input type=file>，
 * 走的仍是官方上传通道，不需要 token、也不弹任何对话框。
 *
 * 全程只做三件事：① 打开 Netlify 并把文件塞进上传控件 ② 等部署完成
 * ③ 把最终网址与部署结果打印出来（并回执验证资源是否 200）。
 */

var fs = require('fs');
var path = require('path');

var SITE_NAME = process.argv[2] || '';
var PORT = process.argv[3] || 9460;
var SITE_DIR = path.join(__dirname, '..', 'dist', 'site');

var FILES = ['index.html', 'style.css', 'app.js', 'engine.bundle.js', 'favicon.svg', '.nojekyll'];
// 上传时不要 .nojekyll（那是给 GitHub Pages 的，Netlify 无意义且可能被拒）
var UPLOAD = ['index.html', 'style.css', 'app.js', 'engine.bundle.js', 'favicon.svg'];

function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

async function main() {
  // 读取要上传的文件内容（base64，便于安全地塞进页面）
  var payload = UPLOAD.map(function (name) {
    var p = path.join(SITE_DIR, name);
    if (!fs.existsSync(p)) throw new Error('缺少发布文件: ' + p);
    return { name: name, b64: fs.readFileSync(p).toString('base64') };
  });
  console.log('待上传：' + payload.map(function (f) {
    return f.name + '(' + Math.round(f.b64.length * 3 / 4 / 1024) + 'KB)';
  }).join(', '));

  var page = await (await fetch('http://127.0.0.1:' + PORT + '/json/new?' +
    encodeURIComponent('https://app.netlify.com/'), { method: 'PUT' })).json();
  var ws = new WebSocket(page.webSocketDebuggerUrl);
  var id = 0, pending = {};
  function send(m, p) {
    return new Promise(function (res) {
      var mid = ++id; pending[mid] = res;
      ws.send(JSON.stringify({ id: mid, method: m, params: p || {} }));
    });
  }
  ws.addEventListener('message', function (ev) {
    var m = JSON.parse(ev.data);
    if (m.id && pending[m.id]) { pending[m.id](m); delete pending[m.id]; }
  });
  await new Promise(function (r) { ws.addEventListener('open', r); });
  await send('Runtime.enable');
  await send('Page.enable');
  await send('Emulation.setDeviceMetricsOverride', {
    width: 1440, height: 900, deviceScaleFactor: 1, mobile: false
  });

  async function goto(url) {
    await send('Page.navigate', { url: url });
    await sleep(2500);
  }
  async function evaluate(expr) {
    var r = await send('Runtime.evaluate', {
      expression: expr, returnByValue: true, awaitPromise: true
    });
    // 【坑】CDP 的返回结构是 {id, result:{result:{type,value}, exceptionDetails?}}。
    // 之前写成去看 r.result.exceptionDetails，且把异常描述取成 r.exceptionDetails.exception.description，
    // 结果出错时只拿到 undefined，完全看不出发生了什么。
    var inner = r && r.result ? r.result : {};
    if (inner.exceptionDetails) {
      var ed = inner.exceptionDetails;
      return {
        error: (ed.exception && (ed.exception.description || ed.exception.value)) ||
          ed.text || JSON.stringify(ed).slice(0, 200)
      };
    }
    return { value: inner.result ? inner.result.value : undefined };
  }
  async function snapshot(label) {
    var r = await evaluate('JSON.stringify({url:location.href, title:document.title, body:(document.body?document.body.innerText:"").replace(/\\s+/g," ").slice(0,300)})');
    console.log('  [' + label + '] ' + (r.value !== undefined ? r.value : ('ERR: ' + r.error)));
  }

  // ---------- 1) 登录态 ----------
  await goto('https://app.netlify.com/');
  await snapshot('首页');

  // ---------- 2) 找到目标站点（或确定需要新建）----------
  await goto('https://app.netlify.com/teams');
  await sleep(1500);
  var teams = await evaluate(
    'JSON.stringify(Array.from(document.querySelectorAll(\'a[href*="/team/"]\')).map(function(a){return a.getAttribute("href")}).filter(function(v,i,s){return v&&s.indexOf(v)===i}).slice(0,8))');
  console.log('  团队链接：' + (teams.value !== undefined ? teams.value : ('ERR: ' + teams.error)));

  ws.close();
  process.exit(0);
}

main().catch(function (e) {
  console.error('失败：' + e.message);
  process.exit(2);
});
