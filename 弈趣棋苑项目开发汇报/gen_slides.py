# -*- coding: utf-8 -*-
# 生成《弈趣棋苑项目开发汇报》64 页 SlideDSL 源文件（低模块 / 去 AI 腔 / 版式多变）
import os

OUT = r"C:\Users\ASUS\Desktop\六子棋源代码\弈趣棋苑项目开发汇报\slides"
TOTAL = 64
PROJECT = "弈趣棋苑 · 项目开发汇报"

PAPER = "#F5E3BE"; INK = "#2A2118"; WOOD = "#8C5A2B"; CIN = "#B3271E"
SERIF = '"' + "'Songti SC', 'STSong', 'SimSun', serif" + '"'
SANS = '"' + "'PingFang SC', 'Microsoft YaHei', sans-serif" + '"'

# ---------- 基础构件 ----------
def A(title, sub="", h=96):
    return ('''  <Box style={{ width: "100%", height: ''' + str(h) + ''', flexDirection: "column", justifyContent: "center" }}>
    <Text style={{ fontSize: 34, fontWeight: "bold", color: "''' + INK + '''", fontFamily: ''' + SERIF + ''' }}>''' + title + '''</Text>
    <Box style={{ width: 56, height: 2, background: "''' + CIN + '''", marginTop: 10 }} />
''' + sub + '''
  </Box>''')

def C(page):
    return ('''  <Box style={{ width: "100%", height: 48, flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
    <Text style={{ fontSize: 14, color: "rgba(42,33,24,0.55)", fontFamily: ''' + SANS + ''' }}>''' + PROJECT + '''</Text>
    <Text style={{ fontSize: 14, color: "rgba(42,33,24,0.55)", fontFamily: ''' + SANS + ''' }}>''' + page + ''' / ''' + str(TOTAL) + '''</Text>
  </Box>''')

def content(title, body, page, sub=None, tail=None):
    """正文页：标题区 + 副标（可选）+ 内容区 + 页脚。"""
    subhtml = ""
    h = 96
    if sub:
        subhtml = ('''    <Text style={{ fontSize: 16, lineHeight: 1.5, color: "rgba(42,33,24,0.62)", fontFamily: ''' + SANS + ''', marginTop: 8 }}>''' + sub + '''</Text>''')
        h = 122
    if tail:
        body = '''  <Box style={{ width: "100%", height: "100%", flexDirection: "column" }}>
''' + body + '''
''' + takeaway(tail) + '''
  </Box>'''
    return ('''<Slide style={{ width: 1280, height: 720, padding: "20px 72px", background: "''' + PAPER + '''", flexDirection: "column" }}>
''' + A(title, sub=subhtml, h=h) + '''
  <Box style={{ width: "100%", height: ''' + str(720 - 40 - h - 48) + ''', flexDirection: "column" }}>
''' + body + '''
  </Box>
''' + C(page) + '''
</Slide>''')

def section(num, title, subtitle):
    return ('''<Slide style={{ width: 1280, height: 720, position: "relative", padding: "0px", background: "''' + INK + '''", overflow: "hidden" }}>
  <Image src="assets/wood_panel.jpg" style={{ position: "absolute", top: 0, left: 0, width: 1280, height: 720, objectFit: "cover", opacity: 0.22 }} />
  <Box style={{ position: "absolute", top: 0, left: 0, width: 1280, height: 720, background: "linear-gradient(160deg, #2A2118 0%, #3E2E1E 55%, #8C5A2B 100%)", opacity: 0.55 }} />
  <Box style={{ position: "absolute", right: 84, top: 48, flexDirection: "column", alignItems: "flex-end" }}>
    <Text style={{ fontSize: 210, fontWeight: "bold", lineHeight: 1.0, color: "rgba(179,39,30,0.85)", fontFamily: ''' + SERIF + ''' }}>''' + num + '''</Text>
  </Box>
  <Box style={{ position: "relative", zIndex: 2, width: 1280, height: 720, padding: "0px 96px", flexDirection: "column", justifyContent: "center" }}>
    <Text style={{ fontSize: 22, color: "rgba(245,227,190,0.7)", fontFamily: ''' + SANS + ''', letterSpacing: 6 }}>第 ''' + num + ''' 章</Text>
    <Text style={{ fontSize: 62, fontWeight: "bold", color: "''' + PAPER + '''", fontFamily: ''' + SERIF + ''', marginTop: 12 }}>''' + title + '''</Text>
    <Box style={{ width: 70, height: 3, background: "''' + CIN + '''", marginTop: 20 }} />
    <Text style={{ fontSize: 22, fontStyle: "italic", color: "rgba(245,227,190,0.82)", fontFamily: ''' + SANS + ''', marginTop: 20 }}>''' + subtitle + '''</Text>
  </Box>
  <Box style={{ position: "absolute", right: 60, bottom: 50, width: 52, height: 52, borderRadius: 6, background: "''' + CIN + '''", justifyContent: "center", alignItems: "center" }}>
    <Text style={{ fontSize: 28, fontWeight: "bold", color: "''' + PAPER + '''", fontFamily: ''' + SERIF + ''' }}>弈</Text>
  </Box>
</Slide>''')

def cover():
    return ('''<Slide style={{ width: 1280, height: 720, position: "relative", padding: "0px", background: "''' + INK + '''", overflow: "hidden" }}>
  <Image src="assets/wood_dark.jpg" style={{ position: "absolute", top: 0, left: 0, width: 1280, height: 720, objectFit: "cover" }} />
  <Box style={{ position: "absolute", top: 0, left: 0, width: 1280, height: 720, background: "linear-gradient(90deg, rgba(42,33,24,0.95) 0%, rgba(42,33,24,0.80) 42%, rgba(42,33,24,0.34) 72%, rgba(42,33,24,0.10) 100%)" }} />
  <svg width="360" height="360" viewBox="0 0 360 360" style={{ position: "absolute", right: 54, bottom: 46 }} opacity="0.20">
    <g stroke="''' + PAPER + '''" strokeWidth="1" fill="none">
      <line x1="40" y1="0" x2="40" y2="360" /><line x1="120" y1="0" x2="120" y2="360" /><line x1="200" y1="0" x2="200" y2="360" /><line x1="280" y1="0" x2="280" y2="360" /><line x1="360" y1="0" x2="360" y2="360" />
      <line x1="0" y1="40" x2="360" y2="40" /><line x1="0" y1="120" x2="360" y2="120" /><line x1="0" y1="200" x2="360" y2="200" /><line x1="0" y1="280" x2="360" y2="280" /><line x1="0" y1="360" x2="360" y2="360" />
    </g>
    <circle cx="200" cy="200" r="13" fill="''' + CIN + '''" opacity="0.85" /><circle cx="120" cy="120" r="13" fill="''' + PAPER + '''" opacity="0.75" /><circle cx="280" cy="280" r="13" fill="''' + PAPER + '''" opacity="0.55" />
  </svg>
  <Box style={{ position: "relative", zIndex: 2, width: 1280, height: 720, padding: "0px 0px 0px 96px", flexDirection: "column", justifyContent: "center" }}>
    <Box style={{ flexDirection: "row", alignItems: "center", gap: 14, marginBottom: 26 }}>
      <Box style={{ width: 46, height: 3, background: "''' + CIN + '''" }} />
      <Text style={{ fontSize: 19, color: "rgba(245,227,190,0.72)", fontFamily: ''' + SANS + ''', letterSpacing: 3 }}>个人独立开发 · 项目开发汇报</Text>
    </Box>
    <Text style={{ fontSize: 74, fontWeight: "bold", lineHeight: 1.15, color: "''' + PAPER + '''", fontFamily: ''' + SERIF + ''', letterSpacing: 8 }}>弈趣棋苑</Text>
    <Text style={{ fontSize: 24, color: "rgba(245,227,190,0.86)", fontFamily: ''' + SANS + ''', letterSpacing: 2, marginTop: 20 }}>Connect6 · Gomoku · 中国象棋</Text>
    <Text style={{ fontSize: 21, lineHeight: 1.7, color: "rgba(245,227,190,0.62)", fontFamily: ''' + SANS + ''', marginTop: 34, width: 640 }}>
      一份从「能跑」走到「可交付」的棋类合集开发纪实——把每一个决定拆开讲清楚：为什么这么画、为什么这么响、为什么这么搜。</Text>
  </Box>
  <Box style={{ position: "absolute", left: 96, bottom: 54, flexDirection: "row", alignItems: "center", gap: 16 }}>
    <Box style={{ width: 46, height: 46, borderRadius: 6, background: "''' + CIN + '''", justifyContent: "center", alignItems: "center" }}>
      <Text style={{ fontSize: 24, fontWeight: "bold", color: "''' + PAPER + '''", fontFamily: ''' + SERIF + ''' }}>弈</Text>
    </Box>
    <Box style={{ flexDirection: "column", gap: 4 }}>
      <Text style={{ fontSize: 16, color: "rgba(245,227,190,0.80)", fontFamily: ''' + SANS + ''' }}>''' + PROJECT + '''</Text>
      <Text style={{ fontSize: 14, color: "rgba(245,227,190,0.48)", fontFamily: ''' + SANS + ''' }}>个人独立开发 · 20+ 模块 · ''' + str(TOTAL) + ''' 页</Text>
    </Box>
  </Box>
</Slide>''')

def ending():
    return ('''<Slide style={{ width: 1280, height: 720, position: "relative", padding: "0px", background: "''' + INK + '''", overflow: "hidden" }}>
  <Image src="assets/wood_dark_flip.jpg" style={{ position: "absolute", top: 0, left: 0, width: 1280, height: 720, objectFit: "cover" }} />
  <Box style={{ position: "absolute", top: 0, left: 0, width: 1280, height: 720, background: "linear-gradient(270deg, rgba(42,33,24,0.95) 0%, rgba(42,33,24,0.78) 46%, rgba(42,33,24,0.22) 76%, rgba(42,33,24,0.08) 100%)" }} />
  <Box style={{ position: "absolute", left: 96, top: 0, height: 720, flexDirection: "column", justifyContent: "center", gap: 26 }}>
    <Box style={{ width: 46, height: 3, background: "''' + CIN + '''" }} />
    <Text style={{ fontSize: 60, fontWeight: "bold", lineHeight: 1.25, color: "''' + PAPER + '''", fontFamily: ''' + SERIF + ''' }}>棋盘上每一步都可回退，<br />工程上每一个决定都要留下依据。</Text>
    <Text style={{ fontSize: 22, color: "rgba(245,227,190,0.78)", fontFamily: ''' + SANS + ''', letterSpacing: 2 }}>谢 谢 观 看</Text>
  </Box>
  <Box style={{ position: "absolute", right: 70, bottom: 54, flexDirection: "row", alignItems: "center", gap: 16 }}>
    <Box style={{ flexDirection: "column", gap: 4, alignItems: "flex-end" }}>
      <Text style={{ fontSize: 16, color: "rgba(245,227,190,0.80)", fontFamily: ''' + SANS + ''' }}>''' + PROJECT + '''</Text>
      <Text style={{ fontSize: 14, color: "rgba(245,227,190,0.48)", fontFamily: ''' + SANS + ''' }}>个人独立开发 · 2026</Text>
    </Box>
    <Box style={{ width: 46, height: 46, borderRadius: 6, background: "''' + CIN + '''", justifyContent: "center", alignItems: "center" }}>
      <Text style={{ fontSize: 24, fontWeight: "bold", color: "''' + PAPER + '''", fontFamily: ''' + SERIF + ''' }}>弈</Text>
    </Box>
  </Box>
</Slide>''')

# ---------- 内嵌构件 ----------
def img(path, w, h, cap):
    return ('''    <Box style={{ flexDirection: "column", gap: 10 }}>
      <Image src="''' + path + '''" style={{ width: ''' + str(w) + ''', height: ''' + str(h) + ''', objectFit: "cover", borderRadius: 8, border: "1px solid rgba(140,90,43,0.30)" }} />
      <Text style={{ fontSize: 15, color: "''' + WOOD + '''", fontWeight: "bold", fontFamily: ''' + SANS + ''' }}>''' + cap + '''</Text>
    </Box>''')

def para(text, size=17, color=INK, gap=11):
    return ('''    <Text style={{ fontSize: ''' + str(size) + ''', lineHeight: 1.68, color: "''' + color + '''", fontFamily: ''' + SANS + ''', marginBottom: ''' + str(gap) + ''' }}>''' + text + '''</Text>''')

def bullet(text, size=16, color="rgba(42,33,24,0.82)", gap=11):
    """带朱砂方点的要点行，用于加密信息、替代长段落。"""
    return ('''    <Box style={{ flexDirection: "row", alignItems: "flex-start", gap: 12, marginBottom: ''' + str(gap) + ''' }}>
      <Box style={{ width: 7, height: 7, borderRadius: 2, background: "''' + CIN + '''", marginTop: 9 }} />
      <Text style={{ fontSize: ''' + str(size) + ''', lineHeight: 1.64, color: "''' + color + '''", fontFamily: ''' + SANS + ''', flex: 1 }}>''' + text + '''</Text>
    </Box>''')

def takeaway(text):
    """页底结论条：深底朱砂边，收束本页核心判断。"""
    return ('''  <Box style={{ width: "100%", background: "rgba(42,33,24,0.94)", borderLeft: "5px solid ''' + CIN + '''", borderRadius: 6, padding: "10px 20px", marginTop: 4 }}>
    <Text style={{ fontSize: 15, lineHeight: 1.45, color: "rgba(245,227,190,0.92)", fontFamily: ''' + SANS + ''' }}>''' + text + '''</Text>
  </Box>''')

def narrative(title, paras, page, sub=None, points=None, tail=None):
    """左栏长叙述 + 可选要点 + 页底结论。"""
    parts = "\n".join([para(p) for p in paras])
    if points:
        parts += "\n" + "\n".join([bullet(p) for p in points])
    if tail:
        parts += "\n" + takeaway(tail)
    return content(title, '''  <Box style={{ width: "100%", height: "100%", flexDirection: "column", justifyContent: "center" }}>
''' + parts + '''
  </Box>''', page, sub=sub)

def split_img(title, imgpath, w, h, cap, paras, page, side="left", sub=None, points=None, tail=None, imgvalign="center"):
    imgbox = img(imgpath, w, h, cap)
    parts = "\n".join([para(p) for p in paras])
    if points:
        parts += "\n" + "\n".join([bullet(p) for p in points])
    txtbox = '''  <Box style={{ flex: 1, flexDirection: "column", justifyContent: "center" }}>
''' + parts + '''
  </Box>'''
    if side == "left":
        row = "      " + imgbox + "\n      " + txtbox
    else:
        row = "      " + txtbox + "\n      " + imgbox
    rowbox = '''  <Box style={{ flexDirection: "row", width: "100%", height: "100%", gap: 36, overflow: "hidden" }}>''' + row + '''
  </Box>'''
    if tail:
        body = '''  <Box style={{ width: "100%", height: "100%", flexDirection: "column", gap: 8 }}>
''' + rowbox + '''
''' + takeaway(tail) + '''
  </Box>'''
    else:
        body = rowbox
    return content(title, body, page, sub=sub)

def flow(title, labels, page, sub=None, notes=None, tail=None):
    boxes = []
    n = len(labels)
    bw = 158 if n >= 5 else 186
    for i, l in enumerate(labels):
        boxes.append('''<Box style={{ width: ''' + str(bw) + ''', background: "rgba(140,90,43,0.10)", borderLeft: "4px solid ''' + WOOD + '''", borderRadius: 6, padding: "12px 11px", flexDirection: "column", gap: 4 }}>
        <Text style={{ fontSize: 14, fontWeight: "bold", color: "''' + INK + '''", fontFamily: ''' + SERIF + ''' }}>''' + str(i+1) + ". " + l["t"] + '''</Text>
        <Text style={{ fontSize: 12, lineHeight: 1.45, color: "rgba(42,33,24,0.72)", fontFamily: ''' + SANS + ''' }}>''' + l["d"] + '''</Text>
      </Box>''')
        if i < len(labels) - 1:
            boxes.append('''<Text style={{ fontSize: 20, color: "''' + CIN + '''", fontFamily: ''' + SERIF + ''', alignSelf: "center" }}>→</Text>''')
    row = "\n      ".join(boxes)
    mid = '''  <Box style={{ flexDirection: "row", alignItems: "stretch", justifyContent: "center", gap: 8 }}>
''' + row + '''
  </Box>'''
    if notes or tail:
        # 下方用「说明 + 结论」两栏，压缩竖向高度
        rightcol = ""
        if notes:
            rightcol = '''\n'''.join([bullet(x, 15, "rgba(42,33,24,0.78)", 8) for x in notes])
        lower = '''    <Box style={{ width: "100%", flexDirection: "column", gap: 8 }}>
''' + rightcol + (("\n" + takeaway(tail)) if tail else "") + '''
    </Box>'''
        body = '''  <Box style={{ width: "100%", height: "100%", flexDirection: "column", justifyContent: "center", gap: 14 }}>
''' + mid + '''
''' + lower + '''
  </Box>'''
    else:
        body = '''  <Box style={{ width: "100%", height: "100%", flexDirection: "column", justifyContent: "center" }}>
''' + mid + '''
  </Box>'''
    return content(title, body, page, sub=sub)

def bigstat_row(num, color, sub, desc):
    return '''    <Box style={{ flexDirection: "row", alignItems: "flex-end", gap: 28 }}>
      <Text style={{ fontSize: 92, fontWeight: "bold", lineHeight: 1.0, color: "''' + color + '''", fontFamily: ''' + SERIF + ''', width: 200 }}>''' + num + '''</Text>
      <Box style={{ flex: 1, flexDirection: "column", gap: 8, paddingBottom: 10 }}>
        <Text style={{ fontSize: 21, fontWeight: "bold", color: "''' + INK + '''", fontFamily: ''' + SERIF + ''' }}>''' + sub + '''</Text>
        <Text style={{ fontSize: 16, lineHeight: 1.7, color: "rgba(42,33,24,0.75)", fontFamily: ''' + SANS + ''' }}>''' + desc + '''</Text>
      </Box>
    </Box>'''

def datapage(title, stats, page, sub=None, tail=None):
    rows = "\n".join([bigstat_row(s[0], s[1], s[2], s[3]) for s in stats])
    body = '''  <Box style={{ flexDirection: "column", height: "100%", justifyContent: "center", gap: 18 }}>
''' + rows + '''
  </Box>'''
    if tail:
        body = '''  <Box style={{ flexDirection: "column", height: "100%", justifyContent: "center", gap: 18 }}>
''' + rows + '''
''' + takeaway(tail) + '''
  </Box>'''
    return content(title, body, page, sub=sub)

def compare(title, b_title, b_text, a_title, a_text, page, sub=None, tail=None):
    left = '''    <Box style={{ flex: 1, height: "100%", background: "rgba(140,90,43,0.06)", border: "1px solid rgba(140,90,43,0.2)", borderRadius: 8, padding: "22px 24px", flexDirection: "column", gap: 12 }}>
      <Text style={{ fontSize: 18, fontWeight: "bold", color: "rgba(42,33,24,0.5)", fontFamily: ''' + SERIF + ''' }}>''' + b_title + '''</Text>
      <Text style={{ fontSize: 17, lineHeight: 1.78, color: "rgba(42,33,24,0.78)", fontFamily: ''' + SANS + ''' }}>''' + b_text + '''</Text>
    </Box>'''
    right = '''    <Box style={{ flex: 1, height: "100%", background: "rgba(179,39,30,0.06)", border: "1px solid rgba(179,39,30,0.28)", borderRadius: 8, padding: "22px 24px", flexDirection: "column", gap: 12 }}>
      <Text style={{ fontSize: 18, fontWeight: "bold", color: "''' + CIN + '''", fontFamily: ''' + SERIF + ''' }}>''' + a_title + '''</Text>
      <Text style={{ fontSize: 17, lineHeight: 1.78, color: "rgba(42,33,24,0.84)", fontFamily: ''' + SANS + ''' }}>''' + a_text + '''</Text>
    </Box>'''
    body = '''  <Box style={{ flexDirection: "row", height: "100%", gap: 24, alignItems: "stretch" }}>
''' + left + "\n" + right + '''
  </Box>'''
    if tail:
        body = '''  <Box style={{ width: "100%", height: "100%", flexDirection: "column", gap: 14 }}>
''' + body + '''
''' + takeaway(tail) + '''
  </Box>'''
    return content(title, body, page, sub=sub)

def diagram(title, svg, cap, page, sub=None, notes=None, tail=None):
    """图 + 说明。有 notes 时改为左右两栏（图左、文字右），避免竖向堆叠溢出。
    SVG 若过宽，用 maxWidth 约束在栏内。"""
    caphtml = '''      <Text style={{ fontSize: 14, lineHeight: 1.4, color: "rgba(42,33,24,0.6)", fontFamily: ''' + SANS + ''' }}>''' + cap + '''</Text>'''
    if not notes and not tail:
        body = '''  <Box style={{ flexDirection: "column", height: "100%", justifyContent: "center", alignItems: "center", gap: 10 }}>
''' + svg + '''
''' + caphtml + '''
  </Box>'''
        return content(title, body, page, sub=sub)
    # 左栏：图 + 图注（限制在 520px 内，SVG 用 maxWidth 自适应）
    left = '''    <Box style={{ width: 520, flexDirection: "column", justifyContent: "center", gap: 10, alignItems: "center" }}>
''' + svg + '''
''' + caphtml + '''
    </Box>'''
    right_items = ""
    if notes:
        right_items += "\n".join([bullet(x, 16, "rgba(42,33,24,0.8)", 13) for x in notes])
    right = '''    <Box style={{ flex: 1, flexDirection: "column", justifyContent: "center", gap: 6 }}>
''' + right_items + '''
    </Box>'''
    row = '''  <Box style={{ flexDirection: "row", height: "100%", gap: 30, alignItems: "center" }}>
''' + left + "\n" + right + '''
  </Box>'''
    if tail:
        body = '''  <Box style={{ width: "100%", height: "100%", flexDirection: "column" }}>
''' + row + '''
''' + takeaway(tail) + '''
  </Box>'''
    else:
        body = row
    return content(title, body, page, sub=sub)

def steps_list(title, steps, page):
    items = "\n".join(['''    <Box style={{ flexDirection: "row", alignItems: "flex-start", gap: 14, marginBottom: 14 }}>
      <Box style={{ width: 30, height: 30, borderRadius: 15, background: "''' + CIN + '''", justifyContent: "center", alignItems: "center" }}>
        <Text style={{ fontSize: 15, fontWeight: "bold", color: "''' + PAPER + '''", fontFamily: ''' + SANS + ''' }}>''' + str(i+1) + '''</Text>
      </Box>
      <Text style={{ fontSize: 17, lineHeight: 1.6, color: "rgba(42,33,24,0.82)", fontFamily: ''' + SANS + ''', flex: 1 }}>''' + s + '''</Text>
    </Box>''' for i, s in enumerate(steps)])
    return content(title, '''  <Box style={{ flexDirection: "column", height: "100%", justifyContent: "center", width: 920 }}>
''' + items + '''
  </Box>''', page)

def quote(text, page):
    return content("回望", '''  <Box style={{ flexDirection: "column", height: "100%", justifyContent: "center", alignItems: "center" }}>
    <Text style={{ fontSize: 40, fontWeight: "bold", lineHeight: 1.45, color: "''' + INK + '''", fontFamily: ''' + SERIF + ''', textAlign: "center", width: 920 }}>''' + text + '''</Text>
  </Box>''', page)

def cell(text, header=False, w=200, color=None):
    bg = WOOD if header else "rgba(140,90,43,0.05)"
    fg = PAPER if header else (color or INK)
    wt = "bold" if header else "regular"
    return ('''<Box style={{ width: ''' + str(w) + ''', height: "100%", background: "''' + bg + '''", border: "1px solid rgba(140,90,43,0.25)", padding: "10px 14px", justifyContent: "center" }}>
  <Text style={{ fontSize: 15, fontWeight: "''' + wt + '''", color: "''' + fg + '''", fontFamily: ''' + SANS + ''', lineHeight: 1.45 }}>''' + text + '''</Text>
</Box>''')

def table(headers, rows, widths, rowh=64):
    n = len(headers)
    out = ['<Box style={{ width: "100%", flexDirection: "column", gap: 0 }}>']
    out.append('<Box style={{ width: "100%", height: 44, flexDirection: "row" }}>')
    for i, h in enumerate(headers):
        out.append(cell(h, header=True, w=widths[i]))
    out.append('</Box>')
    for r in rows:
        out.append('<Box style={{ width: "100%", height: ' + str(rowh) + ', flexDirection: "row" }}>')
        for i, c in enumerate(r):
            out.append(cell(c, header=False, w=widths[i]))
        out.append('</Box>')
    out.append('</Box>')
    return "\n".join(out)

# ---------- 64 页正文 ----------
pages = {}

pages[1] = cover()

# P02 目录（8 章，每章一句人话导语）
cat = '''  <Box style={{ width: 340, height: "100%", background: "''' + INK + '''", borderRadius: 10, padding: "40px 32px", flexDirection: "column", justifyContent: "center", gap: 8 }}>
    <Text style={{ fontSize: 40, fontWeight: "bold", color: "''' + PAPER + '''", fontFamily: ''' + SERIF + ''' }}>目录</Text>
    <Text style={{ fontSize: 15, color: "rgba(245,227,190,0.6)", fontFamily: ''' + SANS + ''', letterSpacing: 4 }}>CONTENTS</Text>
    <Box style={{ width: 52, height: 3, background: "''' + CIN + '''", marginTop: 6 }} />
  </Box>
  <Box style={{ flex: 1, height: "100%", flexDirection: "column", justifyContent: "center", gap: 11, paddingLeft: 40 }}>
'''
cats = [("01","项目概述","先讲清楚这到底是个什么东西"),
        ("02","核心功能","一场对局要同时成立哪些事"),
        ("03","技术架构","渲染·音频·AI 三条主线的原理"),
        ("04","开发流程","五轮迭代，每轮都是完整闭环"),
        ("05","难点与解法","把「看起来不对」变成可定位的根因"),
        ("06","功能演示","七步走通一局真实对弈"),
        ("07","成果展示","13 项改动，13 项验证"),
        ("08","未来规划","从可交付，走向可发布")]
for k,(n,t,d) in enumerate(cats,1):
    cat += ('''    <Box style={{ flexDirection: "row", alignItems: "baseline", gap: 16 }}>
      <Text style={{ fontSize: 22, fontWeight: "bold", color: "''' + CIN + '''", fontFamily: ''' + SERIF + ''', width: 34 }}>''' + n + '''</Text>
      <Text style={{ fontSize: 20, fontWeight: "bold", color: "''' + INK + '''", fontFamily: ''' + SERIF + ''', width: 150 }}>''' + t + '''</Text>
      <Text style={{ fontSize: 14, color: "rgba(42,33,24,0.6)", fontFamily: ''' + SANS + ''' }}>''' + d + '''</Text>
    </Box>''')
cat += '''  </Box>'''
pages[2] = ('''<Slide style={{ width: 1280, height: 720, padding: "20px 72px", background: "''' + PAPER + '''", flexDirection: "column" }}>
  <Box style={{ width: "100%", height: 96, flexDirection: "column", justifyContent: "center" }}>
    <Text style={{ fontSize: 34, fontWeight: "bold", color: "''' + INK + '''", fontFamily: ''' + SERIF + ''' }}>目录 / CONTENTS</Text>
    <Box style={{ width: 56, height: 2, background: "''' + CIN + '''", marginTop: 10 }} />
  </Box>
  <Box style={{ width: "100%", height: 516, flexDirection: "row", gap: 24 }}>''' + cat + '''  </Box>
''' + C("02") + '''
</Slide>''')

# P03 项目全景（焦点叙述）
pages[3] = narrative("这一份汇报在讲什么", [
    "六子棋、五子棋、中国象棋，三者的棋盘尺寸、连子规则、每轮落子数、AI 后端都不一样。六子棋 19×19 每轮落 1~2 子、连六取胜；五子棋 15×15 每轮落 1 子、连五取胜；中国象棋 9×10、以将死为目标。规则层面它们几乎毫无共性。",
    "但在规则之下，它们共用同一份渲染代码、同一套音频系统、同一套主题与存档体系。棋盘怎么画、棋子怎么抗锯齿、落子声怎么不延迟、对局怎么存进数据库——这些代码只写了一遍，三个棋种都在跑。",
    "所以真正要新增一个棋种，需要动的只有两件事：写一套规则，接一个 AI 后端。界面、基础设施、美术资源全部复用，不必推倒重来。",
    "这正是「棋苑」这个名字的由来——它不是一个游戏，而是一组能一起长起来的棋。下面八章，先交代它是什么，再把它怎么画、怎么响、怎么搜逐层拆开讲透，最后用一局真实对弈完整演示一遍。"
], "03", sub="八章结构：是什么 → 有什么 → 怎么做的 → 怎么推进 → 难在哪 → 演示 → 做到了什么 → 往哪走",
   tail="判断：这是从「能跑」走到「可交付」的完整纪实，重点不是功能清单，而是每个技术决定背后的依据。")

# P04 §01
pages[4] = section("01","项目概述","从一款棋，到一座棋苑")

# P05 起点叙事
pages[5] = narrative("起点：先让六子棋能玩、好看、不卡", [
    "这个项目开始得很朴素：把六子棋做成一个能下、好看、不卡顿的小游戏。最初它只有一个棋盘和一个落子逻辑，连主题切换都没有，界面是 Tkinter 的默认灰。",
    "真正的转折发生在接入第二个棋种的时候。当时以为要给五子棋重写一套界面，动手才发现——渲染层、音效层、难度选择、存档逻辑，几乎没有一行需要改。差异全被收敛在棋盘尺寸、连子规则和 AI 后端这三个点上。",
    "于是一个判断成立了：把这三处做成可替换的「插槽」，剩下的全部沉到公共底座。这在后来接象棋时得到验证——象棋规则和落子方式（翻山炮、飞将、将死）与前两者差异极大，但界面层只补了一个窗口类。",
    "最有价值的产出因此不是某个算法，而是一套可复用的「界面语言」：左边棋盘、右边控制台（音乐、双方身份、轮到谁、胜率、难度、主题）。用户学会一个棋种，就等于学会了三个。"
], "05", sub="从单棋种到三棋种，复用发生在哪一层、差异被压缩在哪几处",
   points=[
       "复用层：渲染 / 音频 / 主题 / 存档 / 难度 / 侧栏布局——三棋种跑同一份代码。",
       "差异层：棋盘尺寸、连子规则、每轮落子数、AI 后端——只有这四处需要各写一份。"
   ],
   tail="结论：接第二个棋种的成本，比接第一个低了将近一个数量级——这是「棋苑」架构成立的直接证据。")

# P06 体量（数据页）
pages[6] = datapage("体量：三个数字", [
    ("3","#B3271E","个棋种，共享一套引擎","六子棋 / 五子棋 / 中国象棋。差异被严格约束在棋盘尺寸、连子数、每轮子数、AI 后端四个维度，其余全部复用同一份代码。"),
    ("20+","#8C5A2B","个模块，全链路自研","覆盖渲染、音频、AI 引擎、数据存档与打包分发，从界面到算法没有借任何外部游戏框架。"),
    ("5","#8C5A2B","轮迭代，每轮走完整闭环","每一轮都走完「现象 → 根因 → 修复 → 验证」，没有一轮是表面修补。")
], "06", sub="规模不是目标，是可维护性的自然结果：模块数多，是因为每条技术线都被单独抽出来治理过",
   tail="这三个数字的真正含义：3 代表复用成立，20+ 代表职责分离，5 代表方法可重复。")

# P07 三棋种对照（单表 + 一句注解）
pages[7] = content("三种棋，一套引擎", '''  <Box style={{ flexDirection: "row", height: "100%", gap: 28, alignItems: "center" }}>
    <Box style={{ width: 700, flexDirection: "column", justifyContent: "center" }}>
''' + table(["棋种","棋盘 / 胜利","每轮落子","AI 后端"],
   [["六子棋 Connect6","19×19 · 连六","1~2 子","自研 AlphaBeta + TSS"],
    ["五子棋 Gomoku","15×15 · 连五","1 子","自研 AlphaBeta + VCF/VCT"],
    ["中国象棋 Xiangqi","9×10 · 将死","1 子","本地 Pikafish NNUE"]],
   [130, 200, 140, 220]) + '''
    </Box>
    <Box style={{ flex: 1, flexDirection: "column", justifyContent: "center", gap: 12 }}>
''' + bullet("差异被严格约束在四个维度——棋盘尺寸 / 连子数 / 每轮子数 / AI 后端。", 17, INK, 6) + '''
''' + bullet("渲染、音效、主题、存档这四块，三棋种跑的是同一份代码。", 16, "rgba(42,33,24,0.78)", 6) + '''
''' + bullet("新增棋种 ≈ 接入规则 + 选后端，界面零重复建设。", 16, "rgba(42,33,24,0.78)", 6) + '''
''' + bullet("AI 后端可替换：五子棋用自研引擎，象棋直接挂本地皮卡鱼。", 16, "rgba(42,33,24,0.78)", 0) + '''
    </Box>
  </Box>''', "07", sub="三个棋种在四个维度上不同，在其余所有维度上相同",
   tail="这正是三棋种能以低成本并存的关键：差异被主动收窄，复用才成为默认。")

# P08 技术底座（流程）
pages[8] = flow("技术底座：五条线，各管一摊", [
    {"t":"渲染层","d":"PIL 4× 超采样绘制，BOX 降采样，预渲染精灵运行期零重绘"},
    {"t":"音频层","d":"MCI 独立线程，双轨队列，常驻 alias，锁泄漏自愈"},
    {"t":"AI 层","d":"AlphaBeta + VCF/VCT 算杀，象棋接皮卡鱼 NNUE"},
    {"t":"数据层","d":"PostgreSQL 自动存档，状态栏 + Toast 双反馈"},
    {"t":"分发层","d":"PyInstaller 打包 myapp.exe，venv 隔离依赖"}
], "08", sub="五条线各自独立、互不阻塞，任何一条出问题都不会拖垮界面主线程",
   notes=[
       "渲染与音频都做了异步或预渲染，主线程只负责画和响应点击。",
       "AI 走子进程 / 工作线程，界面在下棋思考期间仍然流畅可交互。",
       "数据层失败不阻断对局，只降级为提示，不让玩家卡在存档上。"
   ],
   tail="底座设计的唯一目标：把「不可控的外部调用」从 UI 线程和全局锁上剥离出去。")

# P09 §02
pages[9] = section("02","核心功能","对局闭环、交互反馈与氛围系统")

# P10 对局需要哪些事
pages[10] = split_img("一场能玩的对局，至少要同时成立这几件事", "assets/shot_connect6.png", 420, 200, "实机 · 六子棋对局（侧栏含胜率曲线与主题）", [
    "点哪落哪的两步式交互、随时可退的悔棋、听得见的落子音、切得动的棋盘主题——缺任何一环，「能玩」都会打折扣。",
    "右边这张对局界面元素并不密，但每一步操作都有明确反馈、每一步都可回退。这才是真正的「完整」——完整不等于按钮多，而是没有死路、没有不确定。"
], "10", side="left", sub="对局闭环 = 落子可预期 + 操作可回退 + 状态可读 + 氛围可调",
   points=[
       "落子：两步式（选格 → 确认），误触不落子。",
       "回退：悔棋一次撤一整轮，撤到我方落子之前。",
       "氛围：音乐、音效、主题三个系统各归各、可独立切换。"
   ])

# P11 两步式落子（状态机图 + 解释）
pages[11] = split_img("原理 · 两步式落子为什么可靠", "assets/shot_connect6.png", 400, 205, "两步式：先选格高亮，再点确认落子", [
    "落子被拆成「选格 → 确认」两步。先点目标格，棋盘高亮候选点、状态条提示本回合还剩几子；只有再点「确认」才真正落子。误触一格的代价从「下错棋」降到「重新选」。",
    "这个设计背后是一个只有三个态的状态机：idle（轮到你）→ selected（已选、待确认）→ placed（已落）。状态迁移的每一条边都对应一次明确的用户操作，没有隐式跳转。",
    "它带来的收益是可测的：任意 placed 态都能经悔棋回到「上一次落子之前」，状态机和撤销链一一对应。六子棋每轮可落 1~2 子，两步式还能顺带处理「这一轮还剩几个子」的计数问题。"
], "11", side="right", sub="状态机只有三个态，每个态都有明确的进入与退出条件")

# P12 悔棋整轮 bug 故事
pages[12] = narrative("悔棋整轮：一个真实 bug 的来龙去脉", [
    "悔棋原本按 round_no 撤「最近一轮」。人机模式下，最近一轮恰好是 AI 的回合——撤完又轮到 AI，等于没撤。用户点悔棋，棋盘纹丝不动。",
    "根因是「一轮」的语义在两种模式下不一致：人人对战撤一轮就等于撤一回合，人机对战撤一轮只撤了 AI 那一手，玩家的棋还在。",
    "修法是给 undo_round 加 to_human 参数：循环撤销，直到当前行棋方是 human，也就是撤到「我上一次落子之前」。末尾再补一句 _schedule_ai_turn，万一 AI 先手被撤光就重新调度，人类回合则自动跳过。",
    "值得注意的是缺陷的出身：从初始 commit 就埋着。git show 逐字比对可见，注释写的是「撤到人类可控局面」，实现却是无参的「撤最近一轮」——注释和代码从第一版就对不上，光读注释永远发现不了。"
], "12", sub="表面看是「悔棋没反应」，实际是「一轮」的语义在人机/人人两种模式下发生了冲突",
   points=[
       "修复点：undo_round(to_human=True) 循环撤到当前行棋方为人类；",
       "配套：末尾补 _schedule_ai_turn()，处理 AI 先手被撤光的边界；",
       "调用方共 3 处，全部带模式判定，避免只修一处留下暗坑。"
   ],
   tail="教训：逻辑类缺陷不能靠改，必须先做版本取证——确认「它是怎么进来的」，才敢动它。")

# P13 氛围系统
pages[13] = split_img("氛围系统：音乐、音效、主题各归各", "assets/shot_launcher.png", 410, 200, "启动器：音乐入口与主题切换都在这里", [
    "音乐有两个入口：启动页和对局侧栏都能点歌，点完高亮当前曲。两处背后是同一个 MusicPlayer 实例，绝不自建第二个 MCI 引擎——否则两条播放链一起抢设备，必然出问题。",
    "落子音走双轨：mp3 走异步快轨、wav 走同步慢轨，按扩展名自动分流。原因是 wav 的播放命令在 MCI 命令串层是同步阻塞的，和落子音同队列串行会把落子拖后 300ms 以上。",
    "主题系统做了关键的一次解耦：棋盘配色与棋子材质各是各的下拉框，5 套配色和 5 种材质可以自由组合。切换时只重建精灵，不碰底板，代价从「整屏重绘」降到「局部替换」。"
], "13", side="left", sub="三个子系统各管一摊：音乐管播放、音效管延迟、主题管外观")

# P14 §03
pages[14] = section("03","技术架构","渲染 · 音频 · AI 三条主线的原理")

# P15 分层架构（图）
p15svg = '''    <svg width="920" height="300" viewBox="0 0 920 300" style={{ background: "rgba(140,90,43,0.05)", borderRadius: 10, maxWidth: "100%", height: "auto" }}>
      <rect x="40" y="22" width="840" height="46" rx="8" fill="#8C5A2B"/><text x="60" y="51" font-size="17" fill="#F5E3BE" font-family="sans-serif">表现层  gui / xiangqi_gui —— 只负责画与响应，不写规则</text>
      <rect x="40" y="86" width="840" height="46" rx="8" fill="#B3271E"/><text x="60" y="115" font-size="17" fill="#F5E3BE" font-family="sans-serif">逻辑层  game / board / xiangqi —— 规则、胜负、合法着法</text>
      <rect x="40" y="150" width="840" height="46" rx="8" fill="#2A2118"/><text x="60" y="179" font-size="17" fill="#F5E3BE" font-family="sans-serif">智能层  ai / kill_search / pikafish_engine —— 只吃棋盘出着法</text>
      <rect x="40" y="214" width="840" height="46" rx="8" fill="#8C5A2B" opacity="0.72"/><text x="60" y="243" font-size="17" fill="#F5E3BE" font-family="sans-serif">基础层  paths / fonts / music / sounds / winmm / database</text>
      <line x1="460" y1="68" x2="460" y2="86" stroke="#2A2118" stroke-width="2"/>
      <line x1="460" y1="132" x2="460" y2="150" stroke="#2A2118" stroke-width="2"/>
      <line x1="460" y1="196" x2="460" y2="214" stroke="#2A2118" stroke-width="2"/>
    </svg>'''
pages[15] = diagram("原理 · 总体分层与依赖方向", p15svg, "依赖只向下：上层消费下层服务，下层永不反向调用上层", "15",
    sub="四层职责单一，依赖方向单向，任何一层都可以被单独替换或测试",
    notes=[
        "表现层不含规则：换个界面，棋照样能下。",
        "智能层只有一个入口 get_move(board, color, stones)，换引擎不动上层。",
        "基础层无业务语义，谁都能调，但它谁也不调。"
    ],
    tail="分层的收益是可验证性：逻辑层与渲染解耦后，规则可以脱离界面单独跑测试。")

# P16 渲染管线（流程）
pages[16] = flow("原理 · 4× 超采样渲染管线", [
    {"t":"SS=4 绘制","d":"在 4 倍分辨率空间画棋盘/棋子，天然抗锯齿"},
    {"t":"BOX 降采样","d":"面积平均，无负瓣，边界无振铃"},
    {"t":"UnsharpMask","d":"radius 1.1 / 60% / 阈值 2 找回锐度"},
    {"t":"重建 Alpha","d":"圆内不透明 + 最外羽化，与内容取 lighter"}
], "16", sub="四段管线解决同一个问题：让边缘在小尺寸下不糊、放大后不脏",
   notes=[
       "先在 4× 空间画，等于把「锯齿」这一先天问题降级成「采样」这一确定问题。",
       "降采样用面积平均而非插值核，为了从根上避开振铃（详见下页对比）。",
       "降采样会把圆外透明像素混进内部，所以最后必须重建 alpha。"
   ],
   tail="这条管线的每一段都不是设计出来的，而是被具体的画质问题一步步逼出来的。")

# P17 超采样 vs LANCZOS（对比）
pages[17] = compare("原理 · 为什么不用 LANCZOS",
    "之前：LANCZOS 降采样",
    "LANCZOS 的重采样核带负瓣，在「描边 ↔ 透明」这类高对比边界会过冲，产生彩色振铃：边缘泛出一圈青紫色毛边。小尺寸看不清，一旦棋盘铺到全屏大格子就非常明显，棋面看起来发虚发彩。这是它数学性质决定的，不是参数没调好。",
    "现在：BOX + UnsharpMask",
    "BOX（面积平均）核全为正、无负瓣，从根上不产生振铃，边界干净。代价是会略软，于是补一段 UnsharpMask(radius 1.1 / 60% / 阈值 2) 找回锐度。降采样前还要先给圆外透明区填上底色，否则卷积会把黑色卷进边缘，形成断续黑斑。", "17",
    sub="同一个降采样步骤，换一种核，画质问题的性质就完全不同",
    tail="选择依据：负瓣是振铃的必要条件，去掉负瓣就根治了彩边——比事后加滤波补丁更可靠。")

# P18 棋子 8 层（图）
p18svg = '''    <svg width="470" height="300" viewBox="0 0 470 300" style={{ background: "rgba(140,90,43,0.05)", borderRadius: 10, maxWidth: "100%", height: "auto" }}>
      <rect x="30" y="12" width="410" height="26" rx="4" fill="#8C5A2B"/><text x="44" y="30" font-size="13" fill="#F5E3BE" font-family="sans-serif">1 侧壁</text>
      <rect x="30" y="44" width="410" height="26" rx="4" fill="#B3271E"/><text x="44" y="62" font-size="13" fill="#F5E3BE" font-family="sans-serif">2 盘面渐变 · 3 年轮(只画外环) · 4 环境暗角</text>
      <rect x="30" y="76" width="410" height="26" rx="4" fill="#2A2118"/><text x="44" y="94" font-size="13" fill="#F5E3BE" font-family="sans-serif">5 倒角明暗 · 6 底部反光 · 7 丝光(左上象限)</text>
      <rect x="30" y="108" width="410" height="26" rx="4" fill="#8C5A2B"/><text x="44" y="126" font-size="13" fill="#F5E3BE" font-family="sans-serif">8 描边 · 9 阴刻字（0.62 格大小）</text>
      <rect x="160" y="152" width="150" height="130" rx="75" fill="#8C5A2B" opacity="0.26"/>
      <text x="235" y="224" font-size="14" fill="#2A2118" text-anchor="middle" font-family="sans-serif">圆形 · 不透明 · 木纹真实</text>
    </svg>'''
pages[18] = diagram("原理 · 棋子材质渲染的八层管线", p18svg, "侧壁→盘面→年轮→暗角→倒角→反光→丝光→描边→阴刻字", "18",
    sub="顺序不可乱：每一层都建立在前一层的结果之上，光照类图层必须压在纹理之后",
    notes=[
        "年轮只画 0.74r~0.99r 的外环带，中心留给字，避免纹理冲掉刻字。",
        "丝光是唯一的各向异性高光，只在左上象限，宽度约 (10+30g)。",
        "所有高光/纹理都避开中心字区——这是硬约束，不是可调项。"
    ],
    tail="八层叠出来的才是「木头」，少任何一层都会退回「色块」或「玻璃」。")

# P19 材质三坑（叙事）
pages[19] = narrative("原理 · 棋子材质的三个真实翻车点", [
    "① 渐变留缝：`_vbar` 原本用 1 像素间隔的细线逐行画渐变，行与行之间留了缝。小格子上被降采样盖住看不出，全屏大格子立刻爆出横向条纹和摩尔纹。改成连续矩形逐行填充才彻底消掉。",
    "② 降采样振铃：LANCZOS 让描边在高对比边界发彩，换成 BOX 面积平均加 UnsharpMask 补锐度才干净（与 P17 同源）。",
    "③ alpha 掉值：降采样会把圆外的透明像素混进内部，棋面 alpha 从 255 掉到 236~238，观感就是「发虚」。解法是在 4× 超采样空间画圆再降采样，最后与内容 alpha 取 lighter 合成，内部补回 255，最外一圈做 1px 羽化。"
], "19", sub="三个坑分属绘制、采样、合成三个阶段，都是「小尺寸看不出、大尺寸才暴露」",
   tail="共同规律：画质缺陷往往被缩略图掩盖，所以每一层都要在真实分辨率下用放大截图验收。")

# P20 音频异步双轨（图 + 解释）
p20svg = '''    <svg width="900" height="200" viewBox="0 0 900 200" style={{ background: "rgba(140,90,43,0.05)", borderRadius: 10, maxWidth: "100%", height: "auto" }}>
      <rect x="30" y="80" width="150" height="44" rx="8" fill="#8C5A2B"/><text x="105" y="107" font-size="14" fill="#F5E3BE" text-anchor="middle" font-family="sans-serif">UI 入队即返回</text>
      <rect x="220" y="80" width="150" height="44" rx="8" fill="#B3271E"/><text x="295" y="107" font-size="14" fill="#F5E3BE" text-anchor="middle" font-family="sans-serif">按扩展名分流</text>
      <rect x="410" y="18" width="180" height="44" rx="8" fill="#2A2118"/><text x="500" y="45" font-size="14" fill="#F5E3BE" text-anchor="middle" font-family="sans-serif">worker·mp3 快轨</text>
      <rect x="410" y="142" width="180" height="44" rx="8" fill="#2A2118"/><text x="500" y="169" font-size="14" fill="#F5E3BE" text-anchor="middle" font-family="sans-serif">worker·wav 慢轨</text>
      <rect x="640" y="80" width="210" height="44" rx="8" fill="#8C5A2B" opacity="0.72"/><text x="745" y="107" font-size="14" fill="#F5E3BE" text-anchor="middle" font-family="sans-serif">MCI(winmm) 设备</text>
      <line x1="180" y1="102" x2="220" y2="102" stroke="#2A2118" stroke-width="2"/>
      <line x1="370" y1="102" x2="410" y2="40" stroke="#2A2118" stroke-width="2"/>
      <line x1="370" y1="102" x2="410" y2="164" stroke="#2A2118" stroke-width="2"/>
      <line x1="590" y1="40" x2="640" y2="102" stroke="#2A2118" stroke-width="2"/>
      <line x1="590" y1="164" x2="640" y2="102" stroke="#2A2118" stroke-width="2"/>
    </svg>'''
pages[20] = diagram("原理 · 音频系统的异步化与双轨", p20svg, "UI 只入队即返回；mp3/wav 分两条 worker，避免 wav 阻塞拖慢落子音", "20",
    sub="一条主线程、两条工作轨、一份共享设备——用分流换回主线程的即时响应",
    notes=[
        "UI 线程只做「入队」，播放开销全部转移到 worker。",
        "wav 的 play 在命令串层同步阻塞，必须单独一条轨，不能和 mp3 混。",
        "深底色的设备只开一次，两条轨共享，避免重复 open 的开销。"
    ],
    tail="异步化的目的不是「更快」，而是「不阻塞」——主线程一旦被音频占住，整个界面都会顿。")

# P21 音频自愈（叙事）
pages[21] = narrative("原理 · 音频锁死了怎么救回来", [
    "锁用的是 winmm.locked(timeout)，但 timeout 只限制「等锁」的时间。真正麻烦的地方在拿到锁之后：万一 mciSendStringW 因为设备被独占或驱动异常而永久不返回，finally 块永远执行不到，这把锁就被那个死线程永久持有。",
    "后果是连锁的：后续音效 worker 全部卡在等锁上，队列越积越多直到填满，最后音效和背景音乐一起永久静默——而界面上看不出任何报错。",
    "所以补了两层保护。第一层是 force_unlock：探测到锁仍被占用，就整体换一把全新的 Lock，把死锁对象直接抛弃。第二层是 recover：清掉所有常驻 alias，重新开局，保证音效链路从干净状态恢复。",
    "这条自愈链路是踩过实机死锁之后才补上的。在它之前，任何一次设备异常都可能让整个音频系统永久失声，而且必须重启程序才能恢复。"
], "21", sub="根因不在「锁的等待时间」，而在「拿到锁之后永久不返回」这一无解情况",
   points=[
       "force_unlock：判定锁被死线程持有后，整体换新锁对象；",
       "recover：关闭全部常驻 alias 并清空映射表，链路重新初始化；",
       "健康检查：队列积压持续 3 秒不降才触发恢复，避免误判正常播放。"
   ],
   tail="防御性设计的核心：假定外部调用一定会失败，并给出「不重启也能自愈」的路径。")

# P22 AI Negamax+AB（图）
p22svg = '''    <svg width="420" height="290" viewBox="0 0 420 290" style={{ background: "rgba(140,90,43,0.06)", borderRadius: 10, maxWidth: "100%", height: "auto" }}>
      <circle cx="210" cy="40" r="24" fill="#8C5A2B"/><text x="210" y="47" font-size="14" fill="#F5E3BE" text-anchor="middle" font-family="sans-serif">根</text>
      <circle cx="105" cy="135" r="21" fill="#2A2118"/><circle cx="315" cy="135" r="21" fill="#2A2118"/>
      <text x="105" y="141" font-size="12" fill="#F5E3BE" text-anchor="middle" font-family="sans-serif">MAX</text>
      <text x="315" y="141" font-size="12" fill="#F5E3BE" text-anchor="middle" font-family="sans-serif">MAX</text>
      <circle cx="55" cy="235" r="18" fill="#B3271E"/><circle cx="155" cy="235" r="18" fill="#B3271E"/><circle cx="265" cy="235" r="18" fill="#B3271E"/><circle cx="365" cy="235" r="18" fill="#B3271E"/>
      <line x1="210" y1="64" x2="105" y2="114" stroke="#8C5A2B" stroke-width="2"/><line x1="210" y1="64" x2="315" y2="114" stroke="#8C5A2B" stroke-width="2"/>
      <line x1="105" y1="156" x2="55" y2="217" stroke="#B3271E" stroke-width="2"/><line x1="105" y1="156" x2="155" y2="217" stroke="#B3271E" stroke-width="2"/>
      <line x1="315" y1="156" x2="265" y2="217" stroke="#B3271E" stroke-width="2"/><line x1="315" y1="156" x2="365" y2="217" stroke="#B3271E" stroke-width="2"/>
    </svg>'''
pages[22] = diagram("原理 · AI 引擎：搜索、评估与剪枝", p22svg, "Negamax + α/β 剪枝：搜索宽度从 b^d 降到约 b^(d/2)", "22",
    sub="核心不是「搜得全」，而是「把明显不行的分支尽早砍掉」",
    notes=[
        "Negamax：己方取最大、对方取最小，用同一套递归写双方。",
        "α/β 剪枝：一旦证明某分支不可能更好，立即整枝放弃。",
        "迭代加深：先浅后深，保证时限内总能给出「最深的已完成层」。"
    ],
    tail="效果：同样的时限内能多看将近一倍深度——而深度直接决定棋力。")

# P23 评估剪枝细节（叙事）
pages[23] = narrative("原理 · 评估与剪枝怎么做到不爆", [
    "评估函数不整盘扫描。GomokuEval 只重算被这一步落子影响到的 ≤4 条线（横、竖、两条斜），其余部分的分数直接沿用上一手结果。这一步把每节点的评估开销从 O(棋盘面积) 降到 O(4×线长)。",
    "Zobrist 哈希加置换表用来吃「重复局面」：不同搜索路径经常走到同一个局面，置换表缓存子树结果，第二次遇到直接取用，不再重搜。",
    "Killer / History 启发式把历史上容易触发剪枝的强着排到前面，剪枝越早，省下的节点越多。迭代加深则保证在时限内返回「最深的已完成层」，而不是搜到一半被强制砍断、给出一个半成品结果。",
    "最后是兜底：每个节点都查 deadline，一旦超限就放弃当前分支。宁可搜得浅一点，也绝不烧满时间把界面卡死。"
], "23", sub="四条优化分别针对「评估成本 / 重复搜索 / 剪枝时机 / 超时安全」",
   tail="工程取舍：所有优化的前提都是「不能卡界面」——宁可牺牲一点棋力，也不牺牲响应。")

# P24 VCF/VCT AND-OR（图）
p24svg = '''    <svg width="430" height="280" viewBox="0 0 430 280" style={{ background: "rgba(140,90,43,0.06)", borderRadius: 10, maxWidth: "100%", height: "auto" }}>
      <rect x="185" y="18" width="70" height="40" rx="8" fill="#B3271E"/><text x="220" y="43" font-size="14" fill="#F5E3BE" text-anchor="middle" font-family="sans-serif">攻·冲四</text>
      <rect x="85" y="110" width="70" height="40" rx="8" fill="#2A2118"/><rect x="285" y="110" width="70" height="40" rx="8" fill="#2A2118"/>
      <text x="120" y="135" font-size="13" fill="#F5E3BE" text-anchor="middle" font-family="sans-serif">守·堵A</text><text x="320" y="135" font-size="13" fill="#F5E3BE" text-anchor="middle" font-family="sans-serif">守·堵B</text>
      <rect x="35" y="210" width="70" height="40" rx="8" fill="#8C5A2B"/><rect x="195" y="210" width="70" height="40" rx="8" fill="#8C5A2B"/><rect x="335" y="210" width="70" height="40" rx="8" fill="#8C5A2B"/>
      <text x="70" y="235" font-size="12" fill="#F5E3BE" text-anchor="middle" font-family="sans-serif">胜</text><text x="230" y="235" font-size="12" fill="#F5E3BE" text-anchor="middle" font-family="sans-serif">胜</text><text x="370" y="235" font-size="12" fill="#F5E3BE" text-anchor="middle" font-family="sans-serif">胜</text>
      <line x1="210" y1="58" x2="125" y2="110" stroke="#8C5A2B" stroke-width="2"/><line x1="230" y1="58" x2="315" y2="110" stroke="#8C5A2B" stroke-width="2"/>
      <line x1="110" y1="150" x2="70" y2="210" stroke="#B3271E" stroke-width="2"/><line x1="140" y1="150" x2="225" y2="210" stroke="#B3271E" stroke-width="2"/>
      <line x1="300" y1="150" x2="230" y2="210" stroke="#B3271E" stroke-width="2"/><line x1="330" y1="150" x2="370" y2="210" stroke="#B3271E" stroke-width="2"/>
    </svg>'''
pages[24] = diagram("原理 · 五子棋 VCF / VCT 算杀", p24svg, "攻方是「或」节点（任一成五即胜），守方是「与」节点（须堵住全部威胁）", "24",
    sub="把「我能不能必胜」变成一棵 AND-OR 树的枚举问题，而不是靠评估分猜",
    notes=[
        "VCF 只算「连续冲四」的强制序列，深度可控、速度快。",
        "VCT 允许活三，树更大但能抓到更隐蔽的杀。",
        "MIN 层只生成堵点，不给守方生成无用着法，树宽被有效收窄。"
    ],
    tail="这就是「算杀」与「评估」的分工：评估分说谁好，算杀直接证明谁赢。")

# P25 算杀坑（叙事）
pages[25] = narrative("原理 · 算杀层的四个真实 bug", [
    "① 奇偶校验让 foe5 分支连着堵两手，等于跳过了对手整个回合，于是制造出根本不存在的「假必胜」。改成遇到双成五点直接返回 None，单点不跳回合。",
    "② `_find_groups` 把隔着对方棋子的两段误连成一个「跳形」，凭空造出威胁。修法是给联合条件补上 cells[gap]==0，中间有子就不许连。",
    "③ 三三 / 四三的捷径判断没验证对手反手是否有冲四，导致谎报胜势。收窄为只在 not foe_fours 时才成立。",
    "④ 活三识别里己方子被误记 2（应为 1），使威胁被高估，VCT 直接退化。改记 1 之后，双活三才被判为必胜——这一点与 Allis《Go-Moku and Threat-Space Search》的结论一致：双成五点若无解即为必败。"
], "25", sub="四个 bug 都不是「算法错」，而是「规则细节写错」——每一个都会伪造出假的胜利",
   tail="修法一律是「收紧条件」而不是「放宽判断」：宁可算不出杀，也不能报告一个假杀。")

# P26 皮卡鱼 UCI（图）
p26svg = '''    <svg width="900" height="150" viewBox="0 0 900 150" style={{ background: "rgba(140,90,43,0.05)", borderRadius: 10, maxWidth: "100%", height: "auto" }}>
      <rect x="20" y="55" width="130" height="40" rx="8" fill="#8C5A2B"/><text x="85" y="80" font-size="13" fill="#F5E3BE" text-anchor="middle" font-family="sans-serif">主线程</text>
      <rect x="175" y="55" width="150" height="40" rx="8" fill="#B3271E"/><text x="250" y="80" font-size="13" fill="#F5E3BE" text-anchor="middle" font-family="sans-serif">起 UCI 子进程</text>
      <rect x="350" y="55" width="130" height="40" rx="8" fill="#2A2118"/><text x="415" y="80" font-size="13" fill="#F5E3BE" text-anchor="middle" font-family="sans-serif">uci → isready</text>
      <rect x="505" y="55" width="120" height="40" rx="8" fill="#2A2118"/><text x="565" y="80" font-size="13" fill="#F5E3BE" text-anchor="middle" font-family="sans-serif">position</text>
      <rect x="650" y="55" width="90" height="40" rx="8" fill="#2A2118"/><text x="695" y="80" font-size="13" fill="#F5E3BE" text-anchor="middle" font-family="sans-serif">go</text>
      <rect x="765" y="55" width="115" height="40" rx="8" fill="#8C5A2B" opacity="0.72"/><text x="822" y="80" font-size="13" fill="#F5E3BE" text-anchor="middle" font-family="sans-serif">bestmove</text>
      <line x1="150" y1="75" x2="175" y2="75" stroke="#2A2118" stroke-width="2"/><line x1="325" y1="75" x2="350" y2="75" stroke="#2A2118" stroke-width="2"/><line x1="480" y1="75" x2="505" y2="75" stroke="#2A2118" stroke-width="2"/><line x1="625" y1="75" x2="650" y2="75" stroke="#2A2118" stroke-width="2"/><line x1="740" y1="75" x2="765" y2="75" stroke="#2A2118" stroke-width="2"/>
    </svg>'''
pages[26] = diagram("原理 · 象棋接入本地 Pikafish NNUE", p26svg, "UCI 协议封装：起子进程走 uci→isready→position→go，三档难度=搜索深度", "26",
    sub="象棋不用自研引擎，而是把本地皮卡鱼当成一个说 UCI 协议的外部进程来用",
    notes=[
        "通信走标准 UCI 文本协议，引擎可随时替换、可单独升级。",
        "子进程隔离：引擎崩溃不会连带主程序，只是这一手走不出来。",
        "三档难度通过 go depth / movetime 调节，不改编引擎本身。"
    ],
    tail="接入原则：能用成熟引擎的地方不重复造轮子，把精力留给界面与体验。")

# P27 NNUE 胜率换算（叙事）
pages[27] = narrative("原理 · 分数怎么变成胜率", [
    "象棋 AI 返回的是评估分 cp（厘兵分），不是人话。要变成能读懂的胜率，用标准 Elo 换算：P = 1 / (1 + 10^(-cp/400))，锚点取自 Pikafish 官方说明中的 D=400——即评估分每多 400 厘兵，胜率翻一个量级。",
    "但象棋和棋率极高，直接套公式会给出「0% / 100%」这种不可能的结论。所以做了封顶：胜率限制在 [5%, 95%] 区间，绝不显示绝对数字。",
    "显示层的曲线还要平滑：横轴是真实 ply，纵轴在概率域做 EMA(α=0.45) 平滑，再叠加单步限幅 10 个百分点，避免一步棋让曲线上下跳。这里有个容易忽略的坑——平滑绝不能「最后一点不平滑」，否则最新的原始值直接上屏，就是一次肉眼可见的跳变。",
    "横轴按真实 ply 而非回合数展开，窗口取最近 120 步。机机模式下 AI 可能执红，所以换算前必须先按行棋方归一到黑方视角，否则胜率会整体反相。"
], "27", sub="从「引擎的 cp 分」到「玩家看得懂的百分比」，中间要过公式、封顶、平滑、归一四道关",
   points=[
       "公式：P = 1/(1+10^(-cp/400))，D=400 取自 Pikafish 官方口径；",
       "封顶：[5%, 95%]，承认象棋高和棋率，不显示 0/100；",
       "平滑：概率域 EMA + 单步限幅，且最新点也参与平滑。"
   ],
   tail="这一步的意义：把「这步棋好不好」翻译成「我大概几成胜算」，让评委和玩家都能一眼看懂。")

# P28 §04
pages[28] = section("04","开发流程","五轮迭代，每轮都是完整闭环")

# P29 五轮迭代时间线（流程）
pages[29] = flow("五轮迭代：从画面修到交付物", [
    {"t":"迭代一 · 画面","d":"刮痕 / 方形光环 / 落子音 / 歌单 / 侧栏滚动 / 缩放验证"},
    {"t":"迭代二 · 音效图标","d":"MP3 落子音 / 上下首图标方向 / 歌单乱码 / 侧栏稳定"},
    {"t":"迭代三 · PG 配置","d":"PostgreSQL 安装引导 + 启动检测一键化"},
    {"t":"迭代四 · 体积清理","d":"定位 935MB 中 627MB 重复副本"},
    {"t":"迭代五 · 文档","d":"产品说明 / 算法实现 / 讲义 / 报告 四份 Word"}
], "29", sub="五轮的工作对象逐轮外移：从画面 → 音效 → 运行环境 → 磁盘体积 → 交付文档",
   notes=[
       "第一、二轮打磨「打开就能玩」的体验。",
       "第三、四轮解决「换台机器能不能跑、装不装得下」。",
       "第五轮把成果变成可分发、可阅读的文档。"
   ],
   tail="这条曲线说明项目重心已从「功能实现」转向「产品化」。")

# P30-34 各迭代叙事
pages[30] = narrative("迭代一：先让画面能看", [
    "这一轮全部围绕画面：移除棋盘上多余的「刮痕」绘制、修掉大棋子外圈的方形阴影光环、加上嗒嗒嗒的落子音、接通歌单、稳住侧栏滚动、并验证棋盘在不同窗口尺寸下都能正确居中。",
    "其中「方形光环」的根因很有代表性：投影先做高斯模糊、再被裁在一张正方形图像的边界之内，留白不足导致模糊晕开的边缘被切齐，于是圆形的影子变成了方形。修法是按模糊半径反推所需留白（shadow_extent），并把投影拆成环境层与接触层分别绘制。",
    "目标很朴素——打开不丑、下了不卡。它是后面所有打磨的地基，也是「现象 → 根因 → 修复」这套方法第一次被完整跑通。"
], "30", sub="第一轮的目标不是好看，是「不丑、不卡」——先把地基铺平",
   tail="这一轮确立的工作方式：每一个视觉问题都追到绘制代码里的具体一行，而不是调参数碰运气。")

pages[31] = narrative("迭代二：音效与图标", [
    "把旧音效整体换成 MP3 落子音，声音更清脆、体积更小。同时修正了上下首图标的指向——之前两个箭头的方向是反的，点「下一首」实际跳到上一首。",
    "修掉了歌单里的中文乱码，根因是文本编码在读取时没有按 UTF-8 解码；并让侧栏在各种操作（切歌、悔棋、换主题）下不再抖动——抖动的来源是滚动区域的尺寸计算没有把新增内容算进去。",
    "这一轮之后，音频从「能响」走到了「不刺耳、不乱码、不跳」——听感和观感同时上了台阶。"
], "31", sub="第二轮把音频与图标的「细节正确性」补齐：方向、编码、稳定性",
   tail="规律：交互细节的错误往往很小，但用户一眼就能发现——所以每一处都要实测点一遍。")

pages[32] = narrative("迭代三：PostgreSQL 一键配置", [
    "数据库是很多人上手的门槛：要装服务、建库、配连接串，任何一步出错都会让存档功能失效。而存档本身又不是核心玩法，卡在这里非常不划算。",
    "这一轮写了一个安装引导脚本加启动时的环境检测：脚本负责把该装的装好，检测负责判断连不连得上。把「自己配连接串」降级成「点一下就行」，把可能出错的地方全部前置到启动阶段。",
    "配套加了状态栏与 Toast 双反馈：存档成功、失败、降级三种情况都看得见，不会出现「以为存了其实没存」。"
], "32", sub="第三轮把「环境配置」从用户负担变成了程序自己的责任",
   tail="产品化的重要一课：把用户可能踩的坑，用一个脚本提前填平。")

pages[33] = narrative("迭代四：体积清理诊断", [
    "935MB 的工程在磁盘上太臃肿，复制、备份、打包都很累赘。这一轮做了一次体积诊断，逐目录扫描并按大小排序。",
    "结论很明确：627MB 是同一份素材在多个位置留下的重复副本，另外还有 PyInstaller 打包产生的中间目录。清理之后工程体积降到约 308MB，目录结构一眼可读。",
    "这次清理不只是「省空间」——它同时让发布体积可控、让 .gitignore 规则更清楚，为后面「可发布」这个目标扫掉了一个硬障碍。"
], "33", sub="第四轮解决的是「工程存不下、发不出」的问题，靠的是诊断而不是凭感觉删",
   tail="先测量、再动手：没有体积扫描，就不知道 627MB 到底是素材、缓存还是重复副本。")

pages[34] = narrative("迭代五：Word 交付文档", [
    "代码之外，按不同受众写了四份 Word 文档：面向用户的产品说明、面向开发者的算法实现、面向本科生的算法讲义、面向课程的课程设计报告。",
    "四份文档共用同一份工程事实，但口径完全不同：产品说明讲怎么用，算法实现讲怎么写的，讲义讲怎么讲明白，报告讲怎么对齐课程要求。",
    "同一份工程，给评审、给同学、给老师各有一份合适的材料——这是「可交付」的最后一环，也是把个人项目变成「别人能看懂、能复现、能验收」的成品的关键一步。"
], "34", sub="第五轮把工程事实翻译成四套面向不同读者的叙述",
   tail="判断：文档不是附属品——它决定了别人能不能独立复现你的成果。")

# P35 闭环方法（叙事带例子）
pages[35] = narrative("方法：现象 → 根因 → 修复 → 验证", [
    "每一个改动都走四步。第一步盯可观察的现象，比如用户说「圈圈太大了」；第二步下探到能测量的层面找根因，比如用 MCI 直测发现播一条 255ms 的 wav，播放命令要 309~460ms 才返回；第三步选最小改动面去修，不顺手重构无关代码；第四步用可复现的方式证明修对了。",
    "验证手段是多样的：几何自检脚本跑 10 种窗口尺寸、端到端脚本用真实 Tk 实例驱动一次完整对局、数学推导校验胜率公式的锚点、git 取证确认缺陷的引入时间。",
    "关键不是「改完了」，而是「改完且证明改对了」。比如「落子音 16ms」这句话，是 MCI 直测计时算出来的数字，不是主观感觉——它可以被任何人在同一台机器上复现。"
], "35", sub="四步闭环的核心是「可测量」与「可复现」，把主观感受转成客观证据",
   tail="方法的价值在于可迁移：换了问题、换了模块，这四步依然成立。")

# P36 质量保障（叙事/短列）
pages[36] = narrative("质量保障：四道验证手段", [
    "① 几何自检：覆盖 640×520 到 1920×1080 共 10 种窗口尺寸，验证棋盘居中、点击映射可逆（点哪是哪）、棋子不重叠。这是最容易被忽略、也最容易出 bug 的一类问题。",
    "② 端到端脚本：用 venv 里的真实 Tk 实例驱动对话与落子，断言状态、控件引用与可见性，而不是只测纯函数。这样能抓到「逻辑对但界面没刷新」这类问题。",
    "③ 数学推导：胜率的 Elo 锚点、评估函数的对称性，用公式验证而不是凭感觉。凡是能用公式说清的地方，就不留主观判断。",
    "④ 版本取证：用 git show / git log -S 比对历史，定位「这个缺陷从哪一次提交开始存在」，避免在错误的前提上乱改。"
], "36", sub="四条手段分别覆盖「空间几何 / 交互流程 / 数值正确 / 历史追溯」",
   tail="这四条不是流程规定，而是被真实 bug 逼出来的——每一条背后都有一次翻车。")

# P37 §05
pages[37] = section("05","难点与解决方案","把「看起来不对」变成可定位的根因")

# P38 难点一划伤（对比）
pages[38] = compare("难点一 · 棋盘像被划了一道道伤",
    "现象与根因",
    "棋盘看起来像被划伤。根因不是材质贴图有问题，而是：网格线画完之后，代码又叠了一层约 110 条固定种子的短线段——长度在 0.6~2.4 格之间、方向含斜向。这些线段高频、杂乱、且每次生成的位置完全一样，于是读起来就像永久的刀痕，而不像自然的木纹。",
    "解法",
    "删掉那段多余的绘制，改成 16 级纯净的竖向渐变。划痕立刻消失，棋盘恢复成一块干净木面。这说明问题不在「加得不够」，而在「加得过头」——多出来的那层高频特征，正是「假」的来源。", "38",
    sub="看上去是「材质不好」，实际是「多画了一层不该画的高频线段」",
    tail="规律：视觉上的「假」，常常来自叠了一层真实材质本不具有的高频特征——解法是做减法。")

# P39 难点一塑料（叙事）
pages[39] = narrative("难点一续 · 棋子一度像塑料", [
    "棋子一度被评价为「塑料感」：原因是叠加了一个白色点状高光加上过亮的倒角，看着像玻璃球或塑料钮扣，而不是木头。",
    "真实的木材表面不会有圆点状的镜面高光，它只有各向异性的丝光——一道贴着纹理方向的、很窄的柔光带。所以处理上做了三件事：删掉整层点状高光；把定向光的 α 峰值压到 28 以下；暗部颜色不再用固定深棕，而是按每种材质各自的基色去混（否则浅色材质上会泛出脏褐色）。",
    "倒角的亮边也收窄了，过亮会像金属包边。这一轮改动全部是「减」，没有任何「加」——但木头感反而立起来了。"
], "39", sub="塑料感的根因是「加了一层木头没有的东西」：点状高光与过亮倒角",
   points=[
       "删除整层白色点状高光（这是塑料/玻璃的典型特征）；",
       "定向光 α 上限压到 28，暗部按材质基色取色；",
       "丝光、倒角的参数全部回落到克制区间。"
   ],
   tail="木头只有各向异性丝光，没有镜面亮点——把这两者分清，材质才真实。")

# P40 难点二 110ms（图 + 数据）
p40svg = '''    <svg width="780" height="210" viewBox="0 0 780 210" style={{ background: "rgba(140,90,43,0.05)", borderRadius: 10, maxWidth: "100%", height: "auto" }}>
      <rect x="20" y="40" width="320" height="56" rx="8" fill="#8C5A2B"/><text x="180" y="74" font-size="16" fill="#F5E3BE" text-anchor="middle" font-family="sans-serif">旧链路 110ms+</text>
      <rect x="440" y="122" width="320" height="56" rx="8" fill="#B3271E"/><text x="600" y="156" font-size="16" fill="#F5E3BE" text-anchor="middle" font-family="sans-serif">新链路 16ms</text>
      <text x="180" y="118" font-size="12" fill="#2A2118" text-anchor="middle" font-family="sans-serif">wav 同步阻塞 + 每次重开设备</text>
      <text x="600" y="200" font-size="12" fill="#2A2118" text-anchor="middle" font-family="sans-serif">双轨队列 + 常驻 alias + 锁外发</text>
      <path d="M340 68 C 430 68, 400 150, 440 150" stroke="#2A2118" stroke-width="2" fill="none" stroke-dasharray="5,4"/>
    </svg>'''
pages[40] = diagram("难点二 · 落子音链路 110ms → 16ms", p40svg, "wav 的 play 同步阻塞 + 每次重开设备 = 延迟主因", "40",
    sub="用户只说「下棋音效有延迟」，测量后定位到两个叠加的根因",
    notes=[
        "根因一：waveaudio 的 play 在命令串层同步阻塞，309~460ms 才返回。",
        "根因二：每次播放都 close→open 设备，初始化再花 15~45ms。",
        "修法：按扩展名双轨分流 + 常驻 alias 只 seek+play + play 锁外发。"
    ],
    tail="两个根因都藏在系统调用层——不测量就永远只能靠猜，猜不出真正的 300ms。")

# P41 难点三 AI不堵（叙事）
pages[41] = narrative("难点三 · AI 不堵乱走（用户视角）", [
    "用户反馈 AI「不堵乱走」，看着像完全没在防守。第一反应是「评估函数权重不对」，但按 P35 的方法往下查，真正的问题在算杀层。",
    "拆开看是四个 bug（机制见原理 P25）：奇偶校验跳回合造出假必胜、跨子误连造出假跳形、三三捷径忽略对手反手冲四、活三误记使威胁被高估。每一个都会让引擎判断出一个根本不存在的好局面，于是「该堵的地方不堵」。",
    "修复没有一个是凭感觉改的：先 git 取证定位每个缺陷的引入点，再按 Allis 关于威胁空间搜索的规则逐条对齐修法。修完之后，AI 该堵的地方才真的会堵。"
], "41", sub="表面是「AI 太笨」，实际是「算杀层报告了假的胜利」，把评估带偏了",
   tail="重要经验：棋力问题要分层定位——先分清是评估错、搜索错，还是算杀错，再动手。")

# P42 难点四推翻（时间线）
pages[42] = flow("难点四 · 棋子外观推翻了十几轮", [
    {"t":"v8 · 九层立体","d":"球面 + 木纹 + 双圈 + 镜面光，被直接否决"},
    {"t":"v9 · 扁平木片","d":"推翻 3D，改素色木片 + 细描边"},
    {"t":"v10 / v11","d":"5 套主题 + 书法字，定下红繁黑简"},
    {"t":"v13 系","d":"解耦材质与配色，修字形乱码与边缘锯齿"},
    {"t":"v15 · 光泽收敛","d":"去点状高光，压暗定向光，定稿"}
], "42", sub="同一处外观被反复推翻十余次，每一次都留下一条可复用的铁律",
   notes=[
       "v9 的信息：用户要的不是「立体」，是「真实且克制」。",
       "v13 的信息：材质与配色必须解耦，否则组合爆炸且无法维护。",
       "v15 的信息：光泽要自然——宁少勿多，宁暗勿亮。"
   ],
   tail="这十几轮证明：外观打磨不是一次成型，而是靠一次次否决把边界试出来。")

# P43 §06
pages[43] = section("06","功能演示","七步走通一局真实对弈")

# P44-50 演示（图文 + 步骤/注解）
pages[44] = split_img("演示一 · 启动器与新建对局", "assets/shot_launcher.png", 410, 212, "① 启动器：三棋种入口 + 音乐栏", [
    "启动页中央是六子棋 / 五子棋 / 中国象棋三个入口，进入后分别是各自的新建对局窗口；角落另有音乐与设置入口。",
    "象棋的新建窗口可选三种模式：pvp（人机对战）、pve（皮卡鱼执黑）、aia（AI 互弈），并有三档难度。窗口全屏自适应，双击棋盘即落子。"
], "44", side="left", sub="统一入口 + 各棋种独立开局窗，是「一个棋苑、三种棋」的第一印象")

pages[45] = split_img("演示二 · 六子棋完整对局", "assets/shot_connect6.png", 400, 200, "② 六子棋：两步式落子 + 侧栏", [
    "先点目标格高亮、再点「确认」落子；状态条实时提示本回合还剩几子。这一局完整展示了从开局到中盘的交互节奏。",
    "自研 AlphaBeta 在时限内返回最佳着法，配合完整的落子动画链（抬棋 → 移动 → 落地）。「悔棋」一键回到我方决策点，「重开」复位棋盘。"
], "45", side="right", sub="演示重点：落子可预期、AI 有回应、状态可回退")

pages[46] = split_img("演示三 · 五子棋算杀取胜", "assets/shot_gomoku.png", 400, 200, "③ 五子棋终局：连五高亮 + 胜率跳 100%", [
    "困难档启用 VCF/VCT 算杀：构造一串连续冲四的强制序列，让对手每一步都只能被动堵，而自己在序列末端一手成五。",
    "达成五连时即时高亮胜利连线，胜率曲线在终局点直接跳到 100%。右下角可以看到这是「算」出来的胜利，而不是「碰巧」连上的。"
], "46", side="left", sub="演示重点：算杀不是靠运气，而是有一步一步的强制逻辑")

pages[47] = split_img("演示四 · 象棋人机对战", "assets/shot_xiangqi.png", 410, 210, "④ 象棋人机：皮卡鱼 NNUE 应手 + 书法字", [
    "人落子之后，worker 线程调皮卡鱼计算 best_move，返回后播放完整的抬棋 / 移动 / 落地动画。整个过程界面保持可交互，不卡顿。",
    "引擎返回的 score 经 Elo 公式换算成红黑双方胜率并实时精化。当一方被将军时，全盘压暗并弹出红环脉冲提示——状态一眼可见。"
], "47", side="right", sub="演示重点：外部神经网络引擎的接入、动画与胜率的联动")

pages[48] = split_img("演示五 · 主题与材质", "assets/xq_materials.png", 400, 170, "⑤ 五材质样张；棋盘另有 5 套配色", [
    "5 套棋盘配色：素雅木纹 / 青花瓷 / 墨玉宣纸 / 红木金线 / 夜弈玄石。深色底一定会配对浅色棋子，否则红黑字会糊成一片。",
    "5 种棋子材质：原木哑光 / 红木亮漆 / 紫檀深韵 / 胡桃木 / 金丝楠，全部为圆形、不透明、木纹真实。两个下拉框可以任意组合，切换只重建精灵、不重建底板，因此是瞬间生效的。"
], "48", side="left", sub="演示重点：配色与材质解耦，组合空间是 5×5 = 25 种")

pages[49] = split_img("演示六 · 胜率曲线的实时演化", "assets/shot_connect6.png", 400, 200, "⑥ 侧栏胜率曲线（蒙特卡洛全局预测）", [
    "这里的「胜率」不是静态棋形分，而是从当前局面双方一路下到终局的最终胜率——权威信号来自蒙特卡洛 rollout，因此更接近真实结果。",
    "每一步按「成五 &gt; 堵五 &gt; 造四 &gt; 堵四 &gt; 活三 &gt; 随机」的优先级模拟，5000 局约 3 秒跑完。整条曲线在概率域做 EMA 平滑、最新点保留原值，所以看起来平稳又跟得上局势。"
], "49", side="right", sub="演示重点：胜率是「模拟出来的最终结果」，而不是「当前局面的静态评分」")

pages[50] = split_img("演示七 · 悔棋与重开", "assets/shot_gomoku.png", 400, 200, "⑦ 随时可退：悔棋撤到我方落子前", [
    "「悔棋（撤销整轮）」会循环撤销，一直退到我方上一次落子之前——人机模式下不再出现「撤了等于没撤」的尴尬。",
    "「重开」一键复位棋盘与胜负状态。演示和练习中都能随时重来，不必关掉窗口再打开。"
], "50", side="left", sub="演示重点：把 P12 修好的悔棋语义，在真实对局里点一遍")

# P51 §07
pages[51] = section("07","成果展示","13 项修改，13 项验证")

# P52 成果数据
pages[52] = datapage("成果：数字背后是验证", [
    ("13","#B3271E","项修改，13 项验证","代码检查 / 数学推导 / 端到端脚本逐项覆盖，每一项都能说清「用什么方法验证、结论是什么」。"),
    ("10/10","#8C5A2B","几何自检通过","10 种窗口尺寸（640×520 ~ 1920×1080）验证棋盘居中、点击映射可逆、棋子不重叠。"),
    ("627MB","#8C5A2B","可清理体积","在 935MB 的工程中定位并清理 627MB 重复副本，最终降到约 308MB。")
], "52", sub="可交付的标准不是「改完了」，而是「每一项改动都能被独立验证」",
   tail="这三个数字的共同点：它们都是可复现的测量结果，而不是自我评价。")

# P53 真机三棋种（三图）
pages[53] = content("三种棋，同一个界面语言", '''  <Box style={{ flexDirection: "column", height: "100%", justifyContent: "center", gap: 14 }}>
    <Box style={{ flexDirection: "row", gap: 18, height: 300 }}>
''' + img("assets/shot_xiangqi.png", 350, 219, "象棋：皮卡鱼人机 + 书法字") + img("assets/shot_gomoku.png", 350, 219, "五子棋：VCF/VCT 算杀") + img("assets/shot_connect6.png", 350, 219, "六子棋：两步式落子") + '''
    </Box>
''' + para("三张实机截图并置可见：跨棋种统一的不是配色，而是「左侧棋盘 + 右侧控制台」的界面语言与信息层级——音乐、双方身份、轮到谁、胜率、难度、主题，位置和读法完全一致。", 16, "rgba(42,33,24,0.78)", 0) + '''
  </Box>''', "53", sub="同一套界面语言，学会一个棋种就等于学会三个",
   tail="界面凝聚力是「棋苑」这个产品定位最直接的体现。")

# P54 量化指标表
pages[54] = content("量化指标汇总", '''  <Box style={{ flexDirection: "column", height: "100%", justifyContent: "center" }}>
''' + table(["指标","改造前","改造后","验证方式"],
   [["落子音链路","110ms+","16ms","MCI 直测计时"],
    ["超采样倍率","无","4×","源码 + 像素采样"],
    ["音效队列","单队列串行","双轨隔离","单元断言"],
    ["窗口几何自检","—","10/10 通过","10 种尺寸脚本"],
    ["工程体积","935MB","约 308MB","磁盘扫描"],
    ["模块数","—","20+","源码统计"]],
   [210, 200, 240, 486]) + '''
  </Box>''', "54", sub="每一项都给出「改造前 → 改造后 → 验证方式」三列，防止只有结论没有证据",
   tail="这张表的用法：任何一项被质疑，都能顺着「验证方式」那一列把证据调出来。")

# P55 验证口径（叙事带例）
pages[55] = narrative("验证口径：每项改动怎么算「改对了」", [
    "「落子音 16ms」不是自称的，是 MCI 直测计时得到的数字；「4× 超采样」是源码加像素采样确认的；「10/10 几何」是 10 种尺寸脚本逐个跑出来的——每一句结论后面都跟着一个可以重跑的方法。",
    "交付物本身也要过校验：zip 结构的 XML 良构检查、全量文件的 MD5 扫描、关键图像的像素采样。目的是让成果可以被独立复现，而不是「只在我这台机器上成立」。",
    "这也是当时给自己定的一条规矩：凡是要写进汇报的数字，必须先有一个能重复执行的测量脚本。没有脚本的数字，一律不写。"
], "55", sub="口径统一才能避免「自说自话」：数字 → 测量方法 → 可重复脚本",
   tail="这条规矩的副产品：项目里积累了一批可复用的验证脚本，后续改动直接拿来回归。")

# P56 §08
pages[56] = section("08","未来规划","从可交付，走向可发布")

# P57 四条路线（叙事）
pages[57] = narrative("四条路线：从可交付走向可发布", [
    "① 性能与体积：把 assets/music 里的 WAV 转成 MP3 瘦身；清理 theme_boards 中已失效的 grain 冗余字段；继续压缩 dist 相关产物（累计可释放约 627MB 中尚未处理的部分）。",
    "② 模块化与测试：当前验证以几何自检脚本和端到端脚本为主，下一步补一个 tests/ 自动化回归套件，让每次改动都有护栏，而不是每次都靠临时脚本。",
    "③ 发布准备：把 PyInstaller 打包流程做全量验证，并在发布前完成敏感配置脱敏——config/llm.ini 里的 API Key 绝不能随产物或仓库外流。",
    "④ 体验深化：沿「真实、克制、精致」继续打磨 3D 立体感与光照，坚持一次只推进一个改进点的节奏，避免大改引入回归。"
], "57", sub="四条线对应四个发布前置条件：轻量、可回归、安全、体验好",
   tail="发布的前置条件不是功能数量，而是「体积可控 + 回归可自动跑 + 敏感信息不外流」这三件硬事。")

# P58 发布清单（叙事/清单）
pages[58] = narrative("发布检查清单", [
    "安全：config/llm.ini 内含真实 API Key，公开仓库前必须脱敏，绝不提交任何密钥——这是当前唯一的硬阻塞项。",
    "测试：补 tests/ 自动化回归目录；PyInstaller 打包（myapp.exe）做一次全量验证，确保换机器也能跑。",
    "体积：清理 dist/ 中间产物；把 assets/music 的 WAV 转 MP3；删除 theme_boards 中的冗余字段。",
    "文档：开发日志、算法讲义、课程报告均已就位，按受众分发即可，无需再补写。"
], "58", sub="四类前置检查：安全 / 测试 / 体积 / 文档，逐项打勾才能发布",
   tail="顺序上，安全永远排第一——体积小一点只是体验问题，密钥泄露是事故。")

# P59 风险与遗留（诚实列表）
pages[59] = narrative("诚实交代：还没做完的部分", [
    "第一，config/llm.ini 的密钥尚未脱敏。这是发布的硬阻塞项，公开之前必须处理，没有任何回旋余地。",
    "第二，没有 tests/ 自动化回归目录，目前的验证主要靠临时脚本和人工跑；PyInstaller 打包也尚未做全量验证，换机器的兼容性还未确认。",
    "第三，assets/music 里的 WAV 体积偏大，瘦身尚未开始；theme_boards.py 的 grain 字段自 v9 移除刮痕绘制后已无任何实际使用，属于可清理冗余。",
    "把这些写进汇报不是自贬，而是交付的一部分——一份诚实的遗留清单，比一份完美的假象更有价值。"
], "59", sub="已知未完成项全列出，并标注严重程度（阻塞 / 一般 / 可延后）",
   points=[
       "阻塞级：密钥未脱敏——公开前必须处理；",
       "一般级：无自动化回归、打包未全量验证；",
       "可延后：music WAV 瘦身、theme_boards 冗余字段清理。"
   ],
   tail="诚实交代的价值：让接手的人知道哪里是坑，而不是踩上去才发现。")

# P60 个人成长（叙事）
pages[60] = narrative("最大的收获不是某行代码", [
    "从「能跑」到「可维护 + 可交付」，真正长出来的能力其实不是某个算法或某个界面技巧，而是一种习惯：每一个决定都留下依据。",
    "修改日志记录「改了什么、为什么改」；设计文档记录「为什么这么排版」；版本取证回答「这个缺陷从哪来」。三者合起来，让任意一步都能被追溯。",
    "这带来的好处很实在：下次再有人问「这里为什么这么写」，不用翻记忆、不用猜，翻文档就能回答。工程的可维护性，一半来自代码，一半来自这些记录。"
], "60", sub="能力清单：现象定位、根因测量、最小改动、可复现验证、留下书面依据",
   tail="这套方法不只属于这个项目——它是可迁移到任何工程的通用能力。")

# P61 深讲案例（细致一页）
pages[61] = narrative("深讲一例 · 棋子「丝光」这一层", [
    "丝光是木面上唯一的各向异性高光，它几乎决定了棋子读起来是「木头」还是「塑料」。所以它的参数被反复调整过很多轮。",
    "位置约束很硬：只出现在左上象限，且必须避开中心的刻字区——否则重影会冲掉字。宽度约 (10+30g)，其中 g 是材质的 gloss 系数，越亮的材质丝光越宽。",
    "亮度也有上限：过宽会像金属包边，过亮会像玻璃。最终的参数区间不是用公式推出来的，而是在真实棋盘尺寸下反复截图比对调出来的——因为 76px 的实机观感与 136px 的样张差异巨大，只有在真实尺寸下看才作数。",
    "这一层对了，木头感才立得住；这一层错了，前面七层全部白做。"
], "61", sub="以「丝光」为例，展示一个参数从约束、取值到验收的完整过程",
   tail="细节的分量：棋子看起来真不真，往往就取决于这样一层宽度不到十分之一的柔光带。")

# P62 收束金句
pages[62] = quote("棋盘上每一步都可回退，<br />工程上每一个决定都要留下依据。", "62")

# P63 结束前页（联系）
pages[63] = narrative("一份独立的工程练习", [
    "弈趣棋苑是个独立完成的棋类合集：三棋种、20+ 模块、约 8000 行代码，没有团队协作，也没有依赖任何外部游戏框架。算法是自研的，文档是自写的，界面是一层一层磨出来的。",
    "它不追求炫技。它追求的是三件事：打开就能玩、看着舒服、并且每一步都讲得出道理。",
    "如果你对其中任何一层感兴趣——无论是渲染管线、音频自愈还是算杀搜索——欢迎交流。谢谢看到这里。"
], "63", sub="项目定位：可交付、可维护、可复现的个人工程实践",
   tail="把每一步都留下依据，是这个项目最想传达的东西。")

pages[64] = ending()

# ---------- 写出 ----------
os.makedirs(OUT, exist_ok=True)
for n in sorted(pages.keys()):
    fn = "%02d.slide" % n
    with open(os.path.join(OUT, fn), "w", encoding="utf-8", newline="") as f:
        f.write(pages[n])
    print("wrote", fn)
print("TOTAL", len(pages))
