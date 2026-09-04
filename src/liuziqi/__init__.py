# -*- coding: utf-8 -*-
"""
liuziqi —— 六子棋（Connect6）核心逻辑包

模块划分：
    board        : 棋盘状态（落子 / 撤销 / 胜负判定 / 候选点）
    ai           : 本地 AI（极大极小 + Alpha-Beta 剪枝 + 置换表 + 迭代加深）
    llm_ai       : 大模型（LLM）对战引擎（DeepSeek / 千问）
    game         : 对局流程状态机（轮次 / 计时 / 悔棋 / 棋谱）
    paths        : 资源路径解析（开发 / PyInstaller 打包通用）
"""
