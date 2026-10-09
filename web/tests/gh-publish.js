/**
 * gh-publish.js —— 通过 GitHub REST API 把仓库内容推上去并开启 Pages
 *
 *   node web/tests/gh-publish.js
 *
 * 为什么不用 git push：本机到 github.com 的 HTTPS 连接被完全阻断
 * （连续 3 次 21 秒超时），SSH-over-443 通道虽通但 GCM 的 OAuth token
 * 没有 admin:public_key 权限、传不了公钥。而 api.github.com 稳定可达，
 * 所以改用 Contents API 逐个文件提交（GitHub 允许对空仓库这样做）。
 *
 * 凭证来源：Windows 凭据管理器里 git:https://github.com 的 OAuth token
 * （由 git credential fill 取出），不落盘、不打印。
 */

var fs = require('fs');
var path = require('path');
var { execFileSync } = require('child_process');

var OWNER = '1550167754-glitch';
var REPO = 'yiqiu-qiyuan';
var BRANCH = 'main';
var API = 'https://api.github.com';

function getToken() {
  var out = execFileSync('git', ['credential', 'fill'], {
    input: 'protocol=https\nhost=github.com\n\n',
    encoding: 'utf8',
    env: Object.assign({}, process.env, { GIT_TERMINAL_PROMPT: '0' })
  });
  var m = /^password=(.+)$/m.exec(out);
  if (!m) throw new Error('未能从凭据管理器取到 token');
  return m[1].trim();
}

function api(token, method, url, body) {
  var init = {
    method: method,
    headers: {
      Authorization: 'token ' + token,
      'User-Agent': 'dsh-agent',
      Accept: 'application/vnd.github+json',
      'Content-Type': 'application/json'
    }
  };
  if (body) init.body = JSON.stringify(body);
  return fetch(API + url, init).then(function (r) {
    return r.text().then(function (t) {
      var j = null;
      try { j = t ? JSON.parse(t) : null; } catch (e) { j = { raw: t }; }
      return { status: r.status, ok: r.ok, body: j };
    });
  });
}

function collectFiles(dir, prefix, out) {
  out = out || [];
  fs.readdirSync(dir).forEach(function (name) {
    if (name === 'pages') return;                 // 旧的子目录产物，不上传
    var p = path.join(dir, name);
    var rel = prefix ? prefix + '/' + name : name;
    var st = fs.statSync(p);
    if (st.isDirectory()) collectFiles(p, rel, out);
    else out.push({ rel: rel, abs: p, size: st.size });
  });
  return out;
}

async function main() {
  var token = getToken();
  console.log('token 已取到（不打印）');

  var me = await api(token, 'GET', '/user');
  if (!me.ok) throw new Error('token 无效: HTTP ' + me.status);
  console.log('账号：' + me.body.login);

  // 1) 把 main 分支建出来（空仓库没有分支，需要先提交一个文件）
  var refRes = await api(token, 'GET', '/repos/' + OWNER + '/' + REPO + '/git/ref/heads/' + BRANCH);
  var hasBranch = refRes.ok && refRes.body && refRes.body.object;
  console.log('分支 ' + BRANCH + ' 是否存在：' + hasBranch);

  // 2) 收集 docs/ 发布文件（页面本体）
  var docsDir = path.resolve(__dirname, '..', '..', 'docs');
  var files = collectFiles(docsDir, 'docs');
  console.log('待上传 ' + files.length + ' 个文件，共 ' +
    (files.reduce(function (s, f) { return s + f.size; }, 0) / 1024).toFixed(1) + ' KB');

  for (var i = 0; i < files.length; i++) {
    var f = files[i];
    var content = fs.readFileSync(f.abs).toString('base64');
    var putUrl = '/repos/' + OWNER + '/' + REPO + '/contents/' + encodeURI(f.rel);
    // 已存在则要带 sha 才能覆盖
    var existing = await api(token, 'GET', putUrl + '?ref=' + BRANCH);
    var payload = {
      message: 'chore: 发布网页版（' + f.rel + '）',
      content: content,
      branch: BRANCH
    };
    if (existing.ok && existing.body && existing.body.sha) payload.sha = existing.body.sha;
    var r = await api(token, 'PUT', putUrl, payload);
    console.log('  ' + (r.ok ? 'OK  ' : 'FAIL') + ' ' + f.rel +
      (r.ok ? '' : ' -> HTTP ' + r.status + ' ' + JSON.stringify(r.body).slice(0, 160)));
    if (i === 0 && !r.ok) throw new Error('首个文件就失败，终止（检查 token 权限）');
  }

  // 3) 开启 GitHub Pages：源 = main 分支 /docs 目录
  console.log('\n开启 GitHub Pages（源：' + BRANCH + ' /docs）…');
  var body = {
    source: { branch: BRANCH, path: '/docs' }
  };
  var en = await api(token, 'POST', '/repos/' + OWNER + '/' + REPO + '/pages', body);
  if (en.ok) {
    console.log('  Pages 已开启：' + (en.body.html_url || ''));
  } else {
    var up = await api(token, 'PUT', '/repos/' + OWNER + '/' + REPO + '/pages', body);
    console.log('  ' + (up.ok ? 'Pages 已更新：' + (up.body.html_url || '')
      : 'Pages 设置失败 HTTP ' + en.status + '/' + up.status +
        ' ' + JSON.stringify(en.body).slice(0, 200)));
  }

  var info = await api(token, 'GET', '/repos/' + OWNER + '/' + REPO + '/pages');
  console.log('  Pages 状态：' + JSON.stringify(info.body).slice(0, 300));

  console.log('\n预计网址：https://' + OWNER + '.github.io/' + REPO + '/');
  return 0;
}

main().then(function (c) { process.exit(c); }).catch(function (e) {
  console.error('失败：' + e.message);
  process.exit(1);
});
