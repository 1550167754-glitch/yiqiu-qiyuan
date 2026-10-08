# -*- coding: utf-8 -*-
"""
llm_ai.py —— 大模型（LLM）对战引擎

功能：
    把当前棋盘以文本形式发给大模型（千问等 OpenAI 兼容接口），
    由模型给出落子建议；程序解析并校验后落子。

健壮性设计（重点）：
    1. 模型输出的坐标必须通过"合法性校验"（范围内 / 空点 / 数量 1~2 / 不重复），
       任何一步不合格即视为无效；
    2. 无效或调用失败时，自动回退到本地 Alpha-Beta AI（medium）顶替本轮，
       观战永不中断；
    3. 调用失败原因记录在 last_reason，界面状态栏可见。

零第三方依赖：HTTP 请求使用标准库 urllib。

安全提示：API Key 保存在 config/llm.ini，请勿分享该文件或上传公开仓库。
"""
from __future__ import annotations

import configparser
import json
import os
import urllib.request
import urllib.error

from .board import Board, BLACK, WHITE, OPPOSITE, COLOR_NAMES
from .ai import AI
from .paths import resource

# 缺省配置路径：外部可写优先（exe 同目录 config/llm.ini）
DEFAULT_CONFIG = resource("config", "llm.ini", writable=True)

# 供应方标识 -> (配置节名, 中文显示名)
PROVIDERS = {
    # 注：DeepSeek 已下线（引擎棋力不足观感差），如需恢复请同时恢复
    # xiangqi_gui 的 dsds 模式与 ds_xiangqi.py，并在此登记 provider。
    "qwen": ("qwen", "千问"),
}


def coord_to_xy(text: str) -> tuple[int, int] | None:
    """把 "K10" 形式坐标转为 (x, y)；非法返回 None。

    列 A~S（不区分大小写），行 1~19。
    """
    text = text.strip().upper()
    if len(text) < 2:
        return None
    col_ch, row_s = text[0], text[1:]
    if not ("A" <= col_ch <= "S"):
        return None
    if not row_s.isdigit():
        return None
    x = ord(col_ch) - ord("A")
    y = int(row_s) - 1
    if not (0 <= x < 19):
        return None
    if not (0 <= y < 19):
        return None
    return (x, y)


def parse_moves_json(text: str) -> tuple[list[str], str] | None:
    """从模型回复中解析 {"moves": [...], "reason": "..."}。

    兼容模型可能输出的 ```json 围栏；解析失败返回 None。
    """
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    moves = data.get("moves", [])
    reason = str(data.get("reason", ""))
    if isinstance(moves, list) and all(isinstance(m, str) for m in moves):
        return (moves, reason)
    return None


class LLMAI:
    """大模型对战引擎。

    用法：
        ai = LLMAI("qwen")
        stones = ai.get_move(board, WHITE, stones_to_place=2)
    与本地 AI (ai.AI) 保持相同接口 get_move(board, color, stones_to_place)，
    可直接放入 Player(kind='llm') 由对局状态机驱动。
    """

    def __init__(
        self,
        provider: str = "qwen",
        config_path: str = DEFAULT_CONFIG,
        fallback_difficulty: str = "medium",
    ):
        if provider not in PROVIDERS:
            raise ValueError(f"未知 LLM 供应方：{provider}，可选 {list(PROVIDERS)}")
        self.provider = provider
        self.display_name = PROVIDERS[provider][1]
        self.config_path = config_path
        self.last_reason = ""
        self.last_nodes = 0
        # 本地兜底引擎
        self.fallback = AI(difficulty=fallback_difficulty, seed=None)
        try:
            cfg = self._load_config()
            self.api_key, self.base_url = cfg["api_key"], cfg["base_url"]
            self.model, self.timeout = cfg["model"], cfg["timeout"]
            self.ok = True
        except Exception as exc:
            self.ok = False
            self.last_reason = f"配置读取失败：{exc}"

    def _load_config(self) -> dict:
        cp = configparser.ConfigParser()
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"LLM 配置文件不存在：{self.config_path}")
        cp.read(self.config_path, encoding="utf-8")
        section = PROVIDERS[self.provider][0]
        if section not in cp:
            raise KeyError(f"llm.ini 缺少 [{section}] 配置节")
        d = cp[section]
        api_key = d["api_key"].strip()
        # 允许用环境变量提供密钥（DASHSCOPE_API_KEY），优先于明文配置文件，
        # 减少真实密钥在 config/llm.ini 中落盘的风险。
        env_key = os.environ.get("DASHSCOPE_API_KEY")
        if env_key:
            api_key = env_key
        return dict(
            api_key=api_key,
            base_url=d["base_url"].strip(),
            model=d["model"].strip(),
            timeout=int(d.get("timeout", 40)),
        )

    def get_move(self, board: Board, color: int, stones_to_place: int = 2) -> list[tuple[int, int]]:
        """让 LLM 出招；失败自动回退本地 AI。返回 1~2 个落点。"""
        if board.move_count == 0:
            # 第一手占天元
            c = board.size // 2
            self.last_reason = "第一手占天元"
            return [(c, c)]
        if not self.ok:
            return self._fallback(board, color, stones_to_place, "配置不可用")
        try:
            reply = self._chat(self._build_prompt(board, color, stones_to_place))
            parsed = parse_moves_json(reply)
            if parsed is None:
                return self._fallback(board, color, stones_to_place, "回复格式无法解析")
            raw_moves, self.last_reason = parsed
            moves = self._validate(raw_moves, board, stones_to_place)
            if moves:
                return moves
            return self._fallback(board, color, stones_to_place, "落子非法")
        except Exception as exc:
            return self._fallback(board, color, stones_to_place, f"API 错误：{exc}")

    def _validate(self, raw_moves: list[str], board: Board, stones_to_place: int) -> list[tuple[int, int]]:
        """把模型输出的坐标列表校验为合法落点（1~stones_to_place 个）。"""
        if not (1 <= len(raw_moves) <= max(1, stones_to_place)):
            return []
        pts: list[tuple[int, int]] = []
        for m in raw_moves:
            xy = coord_to_xy(m)
            if xy is None or not board.is_empty(xy[0], xy[1]) or xy in pts:
                return []
            pts.append(xy)
        return pts

    def _fallback(self, board: Board, color: int, stones_to_place: int, why: str) -> list[tuple[int, int]]:
        """本地 AI 兜底：记录原因，观战不中断。"""
        self.last_reason = f"{self.display_name} {why}，本轮由本地AI(medium)顶替"
        return self.fallback.get_move(board, color, stones_to_place)

    def _build_prompt(self, board: Board, color: int, stones_to_place: int) -> str:
        """构造对局提示词（规则 + 棋盘 + 最近落子 + 输出格式约束）。"""
        opp = OPPOSITE[color]
        recent = board.history[-8:]
        recent_text = (
            "、".join(
                f"{chr(ord('A') + x)}{y + 1}({'黑' if c == BLACK else '白'})"
                for (x, y, c) in recent
            )
            if recent else "（开局）"
        )
        return (
            "你是一名六子棋（Connect6）职业选手，请根据局面给出本轮落子。\n\n"
            "【规则】19×19 棋盘；列 A-S 从左到右，行 1-19 从上到下；黑棋X先行，"
            "第一手 1 子，此后每方每轮下 1 或 2 子；横、竖、斜任一方向连成 6 子即获胜。\n\n"
            f"【你的执子】{COLOR_NAMES[color]}（{'X' if color == BLACK else 'O'}），本轮最多下 {stones_to_place} 子。\n"
            f"【对手】{COLOR_NAMES[opp]}（{'X' if opp == BLACK else 'O'}）\n\n"
            "【棋盘】（. 为空；左侧是行号 1-19，第一行是列号 A-S）\n"
            f"{board.display()}\n\n"
            f"【最近落子】{recent_text}\n\n"
            "【思考要点】1) 你有一步连六的点必下；2) 对手即将连六的点必堵；"
            "3) 制造活四/冲四等威胁；4) 两子尽量互相配合（连线或双威胁）。\n\n"
            "只输出如下 JSON，不要输出任何其他文字：\n"
            '{"moves": ["列行", "列行"], "reason": "20字以内理由"}\n'
            '示例：{"moves": ["K10", "K11"], "reason": "构建纵向威胁"}\n'
            "只下一子时 moves 数组给 1 个元素即可。"
        )

    def _chat(self, prompt: str) -> str:
        """调用 OpenAI 兼容 chat/completions 接口，返回模型文本。"""
        url = self.base_url.rstrip("/") + "/chat/completions"
        body = json.dumps(
            {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "你是精通六子棋(Connect6)的博弈引擎，只输出被要求的 JSON。"},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.2,
                "max_tokens": 300,
                "stream": False,
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"]

    def __repr__(self) -> str:
        return f"LLMAI(provider={self.provider!r}, model={self.model!r})"
