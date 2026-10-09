/**
 * netlify-push.js —— 自动把 web/dist/site 部署到 Netlify（借助已打开的 Edge，无需 token）
 *
 *   node web/tests/netlify-push.js [cdpPort]
 *
 * 原理：Netlify Drop 页面上有一个隐藏的 <input type=file id="drop-hero-folder">，
 * 官方就是用它接收"拖进来的文件夹"。我们通过 CDP 在页面里：
 *   ① 用 base64 还原出各个 File 对象（带 webkitRelativePath，模拟文件夹结构）
 *   ② 用 DataTransfer 塞进那个 input，并派发 change 事件
 * 这样走的是 Netlify 自己的上传通道，不弹文件选择框、不需要任何权限、不需要 token。
 */

var fs = require('fs');
var path = require('path');

var PORT = process.argv[2] || 9460;
var SITE_DIR = path.join(__dirname, '..', 'dist', 'site');
var FILES = ['index.html', 'style.css', 'app.js', 'engine.bundle.js', 'favicon.svg'];

function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

async function main() {
  var payload = FILES.map(function (name) {
    var p = path.join(SITE_DIR, name);
    if (!fs.existsSync(p)) throw new Error('缺少发布文件: ' + p);
    return { n: name, b: fs.readFileSync(p).toString('base64') };
  });
  console.log('待部署 ' + payload.length + ' 个文件，共 ' +
    (payload.reduce(function (s, f) { return s + f.b.length * 3 / 4; }, 0) / 1024).toFixed(1) + ' KB');

  var page = await (await fetch('http://127.0.0.1:' + PORT + '/json/new?' +
    encodeURIComponent('https://app.netlify.com/drop'), { method: 'PUT' })).json();
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
  await send('Runtime.enable'); await send('Page.enable');
  await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });
  await send('Page.navigate', { url: 'https://app.netlify.com/drop' });
  await sleep(6000);

  async function ev(expr, awaitPromise) {
    var r = await send('Runtime.evaluate', {
      expression: expr, returnByValue: true, awaitPromise: awaitPromise !== false
    });
    var inner = r && r.result ? r.result : {};
    if (inner.exceptionDetails) {
      var ed = inner.exceptionDetails;
      return 'ERR: ' + ((ed.exception && (ed.exception.description || ed.exception.value)) || ed.text);
    }
    return inner.result ? inner.result.value : undefined;
  }

  console.log('页面：' + await ev('location.href + " | " + document.title'));

  // ---------- 把文件塞进 Netlify 的文件夹上传控件 ----------
  var inject = [
    '(function(){',
    '  var PAYLOAD = ' + JSON.stringify(payload) + ';',
    '  var input = document.getElementById("drop-hero-folder");',
    '  if (!input) return "找不到上传控件 drop-hero-folder";',
    '  function b64ToBlob(b64){',
    '    var bin = atob(b64);',
    '    var len = bin.length;',
    '    var buf = new Uint8Array(len);',
    '    for (var i=0;i<len;i++) buf[i] = bin.charCodeAt(i);',
    '    return new Blob([buf], {type: "application/octet-stream"});',
    '  }',
    '  var dt = new DataTransfer();',
    '  PAYLOAD.forEach(function(f){',
    '    var file = new File([b64ToBlob(f.b)], f.n, {type:"application/octet-stream"});',
    '    try { Object.defineProperty(file, "webkitRelativePath", {value: "site/" + f.n}); } catch(e){}',
    '    dt.items.add(file);',
    '  });',
    '  try { input.files = dt.files; } catch (e) { return "无法赋值 input.files: " + e.message; }',
    '  var n = input.files ? input.files.length : -1;',
    '  input.dispatchEvent(new Event("change", {bubbles:true}));',
    '  return "已注入 " + n + " 个文件：" + Array.from(input.files).map(function(x){return x.name;}).join(",");',
    '})()'
  ].join('\n');
  console.log('注入结果：' + await ev(inject));

  // ---------- 等部署完成，抓最终网址 ----------
  var url = null;
  for (var i = 0; i < 40; i++) {
    await sleep(1500);
    var info = await ev('JSON.stringify({u:location.href, t:document.title, body:(document.body?document.body.innerText:"").replace(/\\s+/g," ").slice(0,300)})');
    if (i % 4 === 0) console.log('  等待中 ' + ((i + 1) * 1.5).toFixed(0) + 's：' + String(info).slice(0, 180));
    var m = /https:\/\/[a-z0-9-]+\.netlify\.app/.exec(String(info));
    if (m) { url = m[0]; break; }
    if (String(info).indexOf('ERR:') === 0) { console.log('  出错：' + info); break; }
  }

  console.log('\n部署结果：' + (url || '（未在页面上捕获到 netlify.app 网址，请看上面最后一条状态）'));
  if (url) {
    for (var k = 0; k < FILES.length; k++) {
      try {
        var r = await fetch(url + '/' + FILES[k], { method: 'HEAD' });
        console.log('  ' + FILES[k] + ' -> HTTP ' + r.status);
      } catch (e) { console.log('  ' + FILES[k] + ' -> 探测失败'); }
    }
  }
  ws.close();
  process.exit(url ? 0 : 1);
}

main().catch(function (e) { console.error('失败：' + e.message); process.exit(2); });
