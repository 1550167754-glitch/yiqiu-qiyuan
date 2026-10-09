/**
 * store.js —— 存档/战绩的存储适配层（平台无关）
 *
 * 网页版用 localStorage，微信小程序用 wx.setStorageSync —— 引擎只认下面这组接口，
 * 由调用方在启动时注入具体实现（setBackend）。
 *
 * 数据模型（与桌面版 PostgreSQL 的三张表同构，便于将来对接服务端）：
 *   players: { name, kind, wins, losses, draws }
 *   games  : { id, variant, black, white, result, reason, moveCount, moves, endedAt }
 * 只保留最近 N 局明细，避免 localStorage 爆掉（浏览器通常 5MB）。
 */

var MAX_GAMES = 60;

var backend = null;          // { get(key), set(key,value) }

function setBackend(b) {
  backend = b;
}

/** 默认后端：浏览器 localStorage；没有就退化成内存（Node 测试用）。 */
function defaultBackend() {
  if (backend) return backend;
  try {
    if (typeof localStorage !== 'undefined' && localStorage) {
      return {
        get: function (k) {
          var v = localStorage.getItem(k);
          return v ? JSON.parse(v) : null;
        },
        set: function (k, v) {
          localStorage.setItem(k, JSON.stringify(v));
        }
      };
    }
  } catch (e) { /* 隐私模式等，忽略 */ }
  var mem = {};
  return {
    get: function (k) { return mem[k] === undefined ? null : mem[k]; },
    set: function (k, v) { mem[k] = v; }
  };
}

var K_PLAYERS = 'yiqiu.players';
var K_GAMES = 'yiqiu.games';
var K_SETTINGS = 'yiqiu.settings';
var K_SEQ = 'yiqiu.seq';

function b() { return defaultBackend(); }

function getPlayers() { return b().get(K_PLAYERS) || {}; }
function getGames() { return b().get(K_GAMES) || []; }

function getSettings() { return b().get(K_SETTINGS) || null; }
function saveSettings(s) { b().set(K_SETTINGS, s); }

/**
 * 保存一局：更新双方胜负统计 + 追加对局明细。
 * record 为 game.toRecord() 的产物（variant/black/white/result/reason/moves）。
 * 返回该局 id。
 */
function saveGame(record) {
  var players = getPlayers();
  var games = getGames();
  var seq = b().get(K_SEQ) || 0;
  seq += 1;

  function ensure(name, kind) {
    if (!players[name]) players[name] = { name: name, kind: kind || 'human', wins: 0, losses: 0, draws: 0 };
    else if (kind) players[name].kind = kind;
  }
  ensure(record.black, record.blackKind);
  ensure(record.white, record.whiteKind);

  if (record.result === 'BLACK') {
    players[record.black].wins += 1;
    players[record.white].losses += 1;
  } else if (record.result === 'WHITE') {
    players[record.white].wins += 1;
    players[record.black].losses += 1;
  } else if (record.result === 'DRAW') {
    players[record.black].draws += 1;
    players[record.white].draws += 1;
  }

  var entry = {
    id: seq,
    variant: record.variant,
    black: record.black,
    white: record.white,
    blackKind: record.blackKind,
    whiteKind: record.whiteKind,
    result: record.result,
    reason: record.reason,
    moveCount: record.moves.length,
    moves: record.moves,
    endedAt: Date.now()
  };
  games.unshift(entry);
  if (games.length > MAX_GAMES) games = games.slice(0, MAX_GAMES);

  b().set(K_PLAYERS, players);
  b().set(K_GAMES, games);
  b().set(K_SEQ, seq);
  return seq;
}

/** 战绩列表（按胜场降序）。 */
function stats() {
  var players = getPlayers();
  var list = Object.keys(players).map(function (k) { return players[k]; });
  list.sort(function (a, c) {
    return (c.wins - a.wins) || a.name.localeCompare(c.name);
  });
  return list;
}

/** 最近对局列表（已按时间倒序）。 */
function recentGames(limit) {
  var games = getGames();
  return limit ? games.slice(0, limit) : games;
}

function clearAll() {
  b().set(K_PLAYERS, {});
  b().set(K_GAMES, []);
  b().set(K_SEQ, 0);
}

module.exports = {
  setBackend: setBackend,
  saveGame: saveGame,
  stats: stats,
  recentGames: recentGames,
  getSettings: getSettings,
  saveSettings: saveSettings,
  clearAll: clearAll,
  MAX_GAMES: MAX_GAMES
};
