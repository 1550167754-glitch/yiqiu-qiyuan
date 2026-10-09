# -*- coding: utf-8 -*-
"""运行测试.py —— 不依赖 pytest 的测试跑手（本机 venv 里没装 pytest）。

用法（项目根目录）：
    <venv>\\Scripts\\python.exe scripts\\运行测试.py

发现 `tests/test_*.py` 里所有 `test_*` 函数并执行，逐条打印 PASS/FAIL，
末尾给出合计与退出码（有失败则退出码 1，可直接接进 CI / 批处理）。
正式回归仍然以 pytest 为准（见 pyproject.toml 的 testpaths / pythonpath）；
本脚本只是"没装 pytest 时也能跑一遍"的兜底。
"""
from __future__ import annotations

import importlib.util
import os
import sys
import traceback

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
TESTS = os.path.join(ROOT, "tests")

# 与 pyproject.toml 的 pythonpath=["src"] 保持一致
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, TESTS)


def _load(path: str):
    name = os.path.splitext(os.path.basename(path))[0]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    if not os.path.isdir(TESTS):
        print(f"[错误] 找不到测试目录：{TESTS}")
        return 2
    files = sorted(f for f in os.listdir(TESTS)
                   if f.startswith("test_") and f.endswith(".py"))
    if not files:
        print("[错误] tests/ 下没有 test_*.py")
        return 2

    passed = failed = 0
    failures = []
    for fname in files:
        modname = os.path.splitext(fname)[0]
        try:
            mod = _load(os.path.join(TESTS, fname))
        except Exception as exc:
            failed += 1
            failures.append(f"{modname}（导入失败：{type(exc).__name__}: {exc}）")
            print(f"FAIL {modname} 导入失败：{type(exc).__name__}: {exc}")
            traceback.print_exc()
            continue
        for name in sorted(dir(mod)):
            if not name.startswith("test_"):
                continue
            fn = getattr(mod, name)
            if not callable(fn):
                continue
            try:
                fn()
            except Exception as exc:
                failed += 1
                failures.append(f"{modname}.{name}")
                print(f"FAIL {modname}.{name}: {type(exc).__name__}: {exc}")
                traceback.print_exc()
            else:
                passed += 1
                print(f"PASS {modname}.{name}")

    print(f"\n合计：{passed} passed, {failed} failed")
    if failures:
        print("失败项：" + "、".join(failures))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
