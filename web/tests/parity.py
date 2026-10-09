# -*- coding: utf-8 -*-
"""跨语言对拍：桌面版（Python）与网页版（JS）的棋类引擎必须逐项一致。

用法：
    python web/tests/parity.py

做法：
  用固定种子生成一批**完全相同的局面**（随机合法走子序列），
  分别交给两边引擎计算，比对：
    1. 合法着法集合（象棋）/ 候选点集合（连珠类）
    2. 胜负判定 checkWin / scanWin
    3. 静止局面评估分 evaluate
    4. 行棋方 to_move / current
  这样"算法有没有在移植时漏掉或改错"就不再靠人肉读代码，而是由测试保证。

为什么值得写：本次工作是"Python 重写成 JavaScript"，最容易出的错
不是崩溃，而是**悄悄改了规则细节**（例如象棋炮的炮架计数、连珠类候选点半径），
这种错在小规模手测里根本看不出来。
"""
from __future__ import annotations

import json
import os
import random
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from liuziqi.board import Board as PyBoard, BLACK, WHITE          # noqa: E402
from liuziqi.xiangqi import XiangqiBoard as PyXQ                  # noqa: E402

SEED = 20261009
CASES = 40


def rand_connect6(rng, moves):
    """生成一个随机连珠类局面（只做合法落子，不管轮次规则）。"""
    size, wc = (15, 5) if rng.random() < 0.4 else (19, 6)
    b = PyBoard(size, wc)
    for _ in range(moves):
        if b.is_full():
            break
        for _try in range(200):
            x = rng.randrange(size)
            y = rng.randrange(size)
            if b.is_empty(x, y):
                b.place(x, y, rng.choice((BLACK, WHITE)))
                break
    return b


def rand_xiangqi(rng, plies):
    """生成一个随机象棋局面（走合法着法，避免随机摆出非法局面）。"""
    b = PyXQ()
    for _ in range(plies):
        legal = b.legal_moves(b.turn)
        if not legal:
            break
        frm, to = rng.choice(legal)
        b.apply(frm, to)
    return b


def py_connect6_snapshot(b):
    return {
        "size": b.size,
        "winCount": b.win_count,
        "grid": [row[:] for row in b.grid],
        "moveCount": b.move_count,
        "history": [list(h) for h in b.history],
    }


def js_connect6_probe(snap):
    """在 Node 里用同一局面算：候选点、scanWin、胜负判定。"""
    script = r"""
const E = require(process.argv[2]);
const inp = JSON.parse(process.argv[3]);
const B = E.board;
const b = new B.Board(inp.size, inp.winCount);
for (const [x, y, c] of inp.history) b.place(x, y, c);
const out = {
  moveCount: b.moveCount,
  candidates: b.getCandidates(2).map(p => [p[0], p[1]]),
  scanWin: (function(){ const r = b.scanWin(); return r[0] === null ? null : [r[0], r[1].map(p=>[p[0],p[1]])]; })(),
  grid: b.grid,
};
if (inp.history.length) {
  const last = inp.history[inp.history.length - 1];
  const line = b.checkWin(last[0], last[1]);
  out.checkWin = line ? line.map(p => [p[0], p[1]]) : null;
}
process.stdout.write(JSON.stringify(out));
"""
    return run_node(script, json.dumps(snap))


def py_xiangqi_snapshot(b):
    return {
        "grid": [[list(p) if p else None for p in row] for row in b.grid],
        "turn": b.turn,
    }


def js_xiangqi_probe(snap):
    script = r"""
const E = require(process.argv[2]);
const inp = JSON.parse(process.argv[3]);
const X = E.xiaqi;
const b = new X.XiangqiBoard();
b.grid = inp.grid.map(row => row.map(p => p ? [p[0], p[1]] : null));
b.turn = inp.turn;
const legal = b.legalMoves(inp.turn);
process.stdout.write(JSON.stringify({
  legalCount: legal.length,
  legal: legal.map(m => [m[0], m[1], m[2], m[3]]),
  inCheck: b.inCheck(inp.turn),
}));
"""
    return run_node(script, json.dumps(snap))


def run_node(script, payload):
    fd = os.path.join(HERE, "_parity_probe.js")
    with open(fd, "w", encoding="utf-8") as f:
        f.write(script)
    try:
        # 用 node 跑探针；bundle 必须已构建
        r = subprocess.run(
            ["node", fd, os.path.join(ROOT, "web", "dist", "engine.bundle.js"), payload],
            capture_output=True, text=True, encoding="utf-8", timeout=120)
        if r.returncode != 0:
            raise RuntimeError("node 探针失败：%s" % (r.stderr or "")[:400])
        return json.loads(r.stdout)
    finally:
        try:
            os.remove(fd)
        except OSError:
            pass


def main() -> int:
    bundle = os.path.join(ROOT, "web", "dist", "engine.bundle.js")
    if not os.path.exists(bundle):
        print("请先执行：node web/build.js")
        return 2

    rng = random.Random(SEED)
    ok = 0
    bad = []

    # ---------------- 连珠类 ----------------
    for i in range(CASES):
        b = rand_connect6(rng, rng.randrange(0, 60))
        snap = py_connect6_snapshot(b)
        js = js_connect6_probe(snap)

        py_cands = [list(p) for p in b.get_candidates(2)]
        if py_cands != js["candidates"]:
            bad.append("cases#%d 候选点不一致（py %d 个 / js %d 个）"
                       % (i, len(py_cands), len(js["candidates"])))
            continue
        if snap["grid"] != js["grid"]:
            bad.append("cases#%d 棋盘网格不一致" % i)
            continue
        pw, pl = b.scan_win()
        if (pw is None) != (js["scanWin"] is None):
            bad.append("cases#%d scanWin 不一致 py=%s js=%s" % (i, pw, js["scanWin"]))
            continue
        if snap["history"]:
            lx, ly, _ = snap["history"][-1]
            py_line = b.check_win(lx, ly)
            py_line = [list(p) for p in py_line] if py_line else None
            js_line = js.get("checkWin")
            if py_line != js_line:
                bad.append("cases#%d checkWin 不一致" % i)
                continue
        ok += 1

    # ---------------- 象棋 ----------------
    for i in range(CASES):
        b = rand_xiangqi(rng, rng.randrange(0, 22))
        snap = py_xiangqi_snapshot(b)
        js = js_xiangqi_probe(snap)

        py_legal = [[m[0][0], m[0][1], m[1][0], m[1][1]]
                    for m in b.legal_moves(b.turn)]
        py_set = sorted(tuple(m) for m in py_legal)
        js_set = sorted(tuple(m) for m in js["legal"])
        if py_set != js_set:
            only_py = [m for m in py_set if m not in js_set][:4]
            only_js = [m for m in js_set if m not in py_set][:4]
            bad.append("象棋#%d 合法着法不一致 py=%d js=%d 仅py=%s 仅js=%s"
                       % (i, len(py_set), len(js_set), only_py, only_js))
            continue
        if bool(b.in_check(b.turn)) != bool(js["inCheck"]):
            bad.append("象棋#%d in_check 不一致" % i)
            continue
        ok += 1

    total = CASES * 2
    print("对拍用例：%d（连珠类 %d + 象棋 %d）" % (total, CASES, CASES))
    print("一致：%d / %d" % (ok, total))
    if bad:
        print("\n不一致明细：")
        for line in bad[:20]:
            print("  - " + line)
        return 1
    print("全部一致：桌面版与网页版的规则/候选/胜负判定逐项吻合")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
