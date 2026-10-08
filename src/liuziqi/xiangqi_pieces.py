"""
xiangqi_pieces.py —— 象棋棋子材质（5 种实心木质工艺）

设计要点
--------
1. **实心**：整枚棋子 alpha 恒为 255，木纹/高光/倒角层全部在不透明底色上
   叠加（`ImageDraw` 带 alpha 的 fill 在 RGBA 图上是**覆盖而非混合**，故所有
   半透明细节必须走独立图层 + `Image.alpha_composite`）。
2. **木质光泽**：木材的高光是**各向异性丝光**——沿纤维方向的柔和条带，
   不是塑料球那样的圆形 hotspot。实现为「左上→右下」方向拉长的多层椭圆叠加，
   外加倒角亮边（光线在斜面聚集）与底部环境反光。
3. **年轮纹理**：同心椭圆加半径扰动，模拟天然不规则木纹；密度/对比度按材质区分。
4. **统一圆形**：五种材质都是圆形棋子（方形/异形一律不做），靠材质与光泽区分观感。

每种材质参数
------------
face_a/face_b : 盘面竖向渐变（上亮 → 下暗），实心底色
wall          : 侧壁（倒角外圈）色，比盘面深一档形成厚度
edge          : 外缘描边 + 字口凿痕色
grain_dk/lt   : 年轮深/浅色
gloss         : 丝光强度 0~1（决定高光层数与不透明度）
rings         : 年轮圈数密度系数
"""
from __future__ import annotations

# PIL 渲染依赖：用受保护导入，避免打包时若 PIL 未被包含，模块在 import 期即崩，
# 导致整个象棋模块（xiangqi_gui 顶层 from .xiangqi_pieces import ...）连带失败。
try:
    from PIL import Image, ImageDraw, ImageChops, ImageFilter
    _PIL_OK = True
except Exception:  # noqa: BLE001 - 缺失时降级而非中断整个象棋模块
    Image = ImageDraw = ImageChops = ImageFilter = None
    _PIL_OK = False

# ---- 5 种材质 ----
PIECE_STYLES = {
    "原木哑光": dict(
        face_a="#F5E3BE", face_b="#DCC094", wall="#C9A46B", edge="#A8763C",
        grain_dk="#9A7343", grain_lt="#F2E6C8", gloss=0.34, rings=7,
        glyph_red="#B3271E", glyph_black="#2A2118",
    ),
    "红木亮漆": dict(
        face_a="#E09A6A", face_b="#B26A3E", wall="#8E4A26", edge="#5E2A12",
        grain_dk="#7C3E1E", grain_lt="#F0B487", gloss=0.78, rings=8,
        glyph_red="#4A1206", glyph_black="#F6E7D6",
    ),
    "紫檀深韵": dict(
        face_a="#9A7460", face_b="#66432F", wall="#4E3222", edge="#2E1B10",
        grain_dk="#3D2415", grain_lt="#C09981", gloss=0.55, rings=9,
        glyph_red="#F2D9A8", glyph_black="#F2D9A8",
    ),
    "胡桃木": dict(
        face_a="#E7CEA6", face_b="#C29A6B", wall="#A87F4E", edge="#7A5230",
        grain_dk="#7E5530", grain_lt="#EBD6B0", gloss=0.50, rings=8,
        glyph_red="#8C2A18", glyph_black="#2C1E12",
    ),
    "金丝楠": dict(
        face_a="#FDF3D4", face_b="#EBD79C", wall="#D8BE7C", edge="#B8933C",
        grain_dk="#C7A75A", grain_lt="#FFF8DC", gloss=0.88, rings=10,
        glyph_red="#9A3410", glyph_black="#241A08",
    ),
}

STYLE_NAMES = list(PIECE_STYLES.keys())
DEFAULT_STYLE = STYLE_NAMES[0]


def _mix(a, b, t):
    t = max(0.0, min(1.0, t))
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(len(a)))


def _hex(c: str):
    return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))


def _vbar(d, cx, cy, r, c_top, c_bot, steps=64):
    """竖向渐变实心圆：自上而下 c_top → c_bot。

    **必须用连续矩形填行**（行高 = 2r/n）——若画 1px 细线，行间会留缝，
    缝隙透出下层深色 → 棋面出现横向条纹（小尺寸被降采样掩盖，
    全屏大尺寸下变成严重摩尔纹，实测踩坑）。
    """
    n = max(2, steps)
    row_h = 2.0 * r / n
    for i in range(n):
        t = i / (n - 1)
        y_mid = cy - r + row_h * (i + 0.5)
        half = (r * r - (y_mid - cy) ** 2) ** 0.5
        if half.__class__ is complex or half <= 0:
            continue          # 边界浮点误差可能产生复数
        d.rectangle([cx - half, cy - r + row_h * i, cx + half,
                     cy - r + row_h * (i + 1) + 1],
                    fill=_mix(c_top, c_bot, t))


def render_piece(px: int, style: str, glyph: str, glyph_color: str,
                 font=None, ss: int = 4) -> Image.Image:
    """渲染一枚实心木质棋子（RGBA，尺寸 px×px，棋子区域实心 alpha=255）。

    层次：侧壁 → 盘面渐变 → 年轮纹理 → 环境暗角 → 倒角亮/暗边 →
    丝光高光（方向性条带）→ 外缘描边 → 雕刻字（暗口 + 主字）。
    """
    st = PIECE_STYLES.get(style, PIECE_STYLES[DEFAULT_STYLE])
    face_a, face_b = _hex(st["face_a"]), _hex(st["face_b"])
    wall, edge = _hex(st["wall"]), _hex(st["edge"])
    grain_dk, grain_lt = _hex(st["grain_dk"]), _hex(st["grain_lt"])
    gloss = float(st["gloss"])
    glyph_rgb = _hex(glyph_color) if isinstance(glyph_color, str) else glyph_color

    r = int(px * 0.5 * ss)          # 棋子半径（含超采样）
    S = int(2 * r + 2 * int(r * 0.10))
    cx = cy = S // 2
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    box = [cx - r, cy - r, cx + r, cy + r]
    ir = r * 0.84                                   # 盘面（倒角内侧）
    lw = max(1, int(r * 0.045))

    # ① 侧壁：外圈一环深色木，形成厚度
    _vbar(d, cx, cy, r, _mix(face_b, wall, 0.55), wall, steps=48)
    # ② 盘面：实心竖向渐变（整枚不透明，alpha 恒 255）
    _vbar(d, cx, cy, ir, face_a, face_b)

    # 盘面圆形 mask（② 之后立即创建，供后续所有盘面图层裁剪复用）
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).ellipse([cx - ir, cy - ir, cx + ir, cy + ir], fill=255)

    # ②b 定向光：以左上光心为圆心的径向明暗——受光面亮、右下远光面暗，
    # 这是"光泽立体"的主线索（纯竖向渐变立体感弱）。
    # **自然度铁律**：α 峰 ≤30（64 实测"发暗发闷"），且暗色必须按材质
    # 从 face_b 调出——固定深棕 (24,14,4) 在浅色材质（金丝楠）上会泛脏褐色。
    light_cx, light_cy = cx - ir * 0.30, cy - ir * 0.35
    dshade = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    kd = ImageDraw.Draw(dshade)
    steps = 26
    max_rr = ir * 2.05
    ring_w = max(2, int(max_rr / steps) + 2)
    shade_c = _mix(face_b, (0, 0, 0), 0.60)
    for i in range(steps):
        u = i / (steps - 1)
        rr = max_rr * (0.22 + 0.78 * u)
        a = int(28 * u ** 1.6)
        kd.ellipse([light_cx - rr, light_cy - rr, light_cx + rr, light_cy + rr],
                   outline=shade_c + (a,), width=ring_w)
    img = Image.composite(Image.alpha_composite(img, dshade), img, mask)
    d = ImageDraw.Draw(img)

    # ②c 高光点——**已删除**：白色椭圆环叠出的小光斑是塑料/玻璃的镜面反射，
    # 真木头只有各向异性丝光，没有点状 hotspot（实测"光泽不自然"的主因）。

    # ③ 年轮纹理：同心椭圆 + 半径扰动（天然不规则），低对比度
    grain = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grain)
    # 年轮只出现在**外环带**（0.60r~0.99r）：中心区留干净木面，
    # 否则密集纹路会把棋子文字淹没（字才是棋子的核心信息）。
    rings = int(st["rings"])
    for i in range(rings):
        u = i / max(1, rings - 1)
        rr = ir * (0.74 + 0.25 * u)
        wob = 1.0 + 0.030 * ((i % 3) - 1)          # 轻微扰动，避免机械同心感
        ox, oy = ir * 0.010 * ((i % 2) * 2 - 1), ir * 0.008 * ((i % 4) - 1.5)
        a = int(14 + 12 * (1 - abs(u - 0.5) * 2))
        gd.ellipse([cx - rr * wob + ox, cy - rr / wob + oy,
                    cx + rr * wob + ox, cy + rr / wob + oy],
                   outline=grain_dk + (max(6, a),), width=max(1, int(r * 0.014)))
    img = Image.composite(Image.alpha_composite(img, grain), img, mask)
    d = ImageDraw.Draw(img)

    # ④ 环境暗角：靠近外缘微暗，塑造碗状体积
    ao = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ad = ImageDraw.Draw(ao)
    for i in range(9):
        u = i / 8.0
        rr = ir * (1.0 - 0.055 * i)
        ad.ellipse([cx - rr, cy - rr, cx + rr, cy + rr],
                   outline=_mix(face_b, (0, 0, 0), 0.24) + (int(4 + 14 * u),),
                   width=max(1, int(r * 0.030)))
    img = Image.composite(Image.alpha_composite(img, ao), img, mask)
    d = ImageDraw.Draw(img)

    # ⑤ 倒角：左上受光亮边 + 右下背光暗边（斜面上的光线聚集）。
    # 混白比例走温和区间：过亮（0.24+0.42g / α180 实测）会像金属包边。
    d.arc([box[0] + lw * 0.6, box[1] + lw * 0.6, box[2] - lw * 0.6, box[3] - lw * 0.6],
          start=188, end=268,
          fill=_mix(face_a, (255, 255, 255), 0.14 + 0.24 * gloss) + (150,),
          width=max(1, int(r * 0.055)))
    d.arc([box[0] + lw * 0.6, box[1] + lw * 0.6, box[2] - lw * 0.6, box[3] - lw * 0.6],
          start=8, end=88,
          fill=_mix(wall, (0, 0, 0), 0.30) + (195,),
          width=max(1, int(r * 0.055)))
    # 底部环境反光：把棋子从棋盘上"托"起来
    d.arc([cx - ir * 0.86, cy - ir * 0.86, cx + ir * 0.86, cy + ir * 0.86],
          start=32, end=148,
          fill=_mix(face_a, (255, 250, 235), 0.40) + (int(60 + 70 * gloss),),
          width=max(1, int(r * 0.045)))

    # ⑥ 木质丝光：细窄条带，**贴在左上象限**，绝不覆盖中心字区
    # （实机 76px 小尺寸下，过宽的光带会惨白一片并冲掉棋子文字）
    shine = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    sh = ImageDraw.Draw(shine)
    bands = 3
    for i in range(bands):
        u = i / (bands - 1)
        half_w = ir * (0.34 - 0.07 * u)
        half_h = ir * (0.075 - 0.018 * u)
        ox, oy = -ir * 0.26, -ir * 0.40 + ir * 0.09 * u
        a = int((10 + 30 * gloss) * (1.0 - 0.66 * u))
        sh.ellipse([cx + ox - half_w, cy + oy - half_h,
                    cx + ox + half_w, cy + oy + half_h],
                   fill=(255, 253, 245, a))
    # 一条极细的纤维亮线（沿左上→右下），点出丝光方向即可
    sh.line([cx - ir * 0.52, cy - ir * 0.30, cx + ir * 0.02, cy - ir * 0.19],
            fill=(255, 255, 250, int(14 + 26 * gloss)), width=max(1, int(r * 0.010)))
    img = Image.composite(Image.alpha_composite(img, shine), img, mask)
    d = ImageDraw.Draw(img)

    # ⑦ 外缘描边
    d.ellipse(box, outline=edge + (255,), width=lw)

    # ⑧ 雕刻字：暗口（下沉阴影）+ 主字；红黑字色由材质决定
    if font is not None and glyph:
        tb = d.textbbox((0, 0), glyph, font=font)
        gx = cx - (tb[2] - tb[0]) / 2 - tb[0]
        gy = cy - (tb[3] - tb[1]) / 2 - tb[1]
        off = max(1, int(r * 0.032))
        # 阴刻：字为凹槽 —— 右上受光侧浅色槽壁 + 左下暗口 + 主字。
        # 槽壁要淡（alpha 120 会显糊），偏移要小，只留细腻受光暗示。
        d.text((gx + off, gy - off), glyph,
               fill=_mix(face_a, (255, 255, 255), 0.50) + (75,), font=font)
        d.text((gx - off, gy + off), glyph,
               fill=_mix(face_b, (0, 0, 0), 0.62) + (150,), font=font)
        d.text((gx, gy), glyph, fill=glyph_rgb + (255,), font=font)

    # 降采样后做**实心化**：LANCZOS 会把圆外透明像素混入内部（实测棋面
    # alpha 只剩 236~238），观感就是"半透明"。这里重建 alpha：
    # 圆内恒 255，边缘走 SS 空间圆的 BOX 降采样 AA 过渡，圆外全透明。
    # **铁坑：mask 圆绝不能在 px 分辨率直接画**——ImageDraw.ellipse 无抗锯齿，
    # 会把 4x 超采样渲染出的平滑边缘整个覆盖成锯齿楼梯边（实测踩坑）。
    # 正解：在 SS 空间画圆 → BOX 降采样成平滑 mask，再与内容 alpha 取 lighter
    # （内容内部 alpha 被 LANCZOS/BOX 混入透明像素只剩 ~237，取 max 补回 255）。
    img = img.resize((px, px), Image.Resampling.BOX)
    a_content = img.split()[3]
    # **铁坑：锐化前必须给圆外透明区填 edge 色**。convert("RGB") 会把透明
    # 像素变纯黑，UnsharpMask 的卷积核跨过圆边界会把黑色卷进边缘 → 外缘
    # 出现不连续黑斑（BOX 降采样的圆边界覆盖度逐像素随机，220px 大图实测
    # 暴露）。填成描边色后过冲 halo 与描边同色，不可见。
    rgb = img.convert("RGB")
    rgb = Image.composite(rgb, Image.new("RGB", rgb.size, edge), a_content)
    rgb = rgb.filter(
        ImageFilter.UnsharpMask(radius=1.1, percent=60, threshold=2))
    img = rgb.convert("RGBA")
    img.putalpha(a_content)
    big = Image.new("L", (S, S), 0)
    ImageDraw.Draw(big).ellipse(box, fill=255)
    mask = big.resize((px, px), Image.Resampling.BOX)   # 平滑 AA 圆 mask
    alpha_final = ImageChops.lighter(img.split()[3], mask)
    img.putalpha(alpha_final)
    return img
