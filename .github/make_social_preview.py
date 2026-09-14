#!/usr/bin/env python3
"""生成仓库社交预览图 docs/social-preview.png（1280×640）。

分享到群、公众号或社交媒体时，GitHub 会显示这张图而不是默认头像。
改文案只要改下面的 COPY 再跑一次，版式不动、自动适配宽度。

用法：python3 .github/make_social_preview.py
需要 Pillow（只在生成这张图时用到，技能本身零依赖）。
"""

import os
import sys

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # 让报错信息说人话
    sys.exit("需要 Pillow 才能生成预览图：pip install Pillow")

WIDTH, HEIGHT = 1280, 640
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "social-preview.png")
FONT_PATH = "/System/Library/Fonts/Hiragino Sans GB.ttc"

# 配色（与仓库既有的深色卡片一致）
BG_TOP, BG_BOTTOM = (18, 41, 64), (20, 32, 56)
BAR_START, BAR_END = (56, 188, 247), (129, 140, 248)
TITLE_COLOR = (255, 255, 255)
SUBTITLE_COLOR = (57, 194, 254)
BOX_FILL, BOX_BORDER = (30, 40, 61), (31, 87, 121)
BOX_INDEX_COLOR = (141, 147, 158)
BOX_LABEL_COLOR = (255, 255, 255)
RULE_COLOR = (38, 58, 86)
LINE1_COLOR = (233, 239, 246)
LINE2_COLOR = (151, 166, 187)
FOOTER_COLOR = (103, 119, 142)

COPY = {
    "title": "把重复的运营活交给 AI",
    "subtitle": "跨境电商多平台运营 · 9 个技能 · 一条流水线跑完",
    "stages": ["规则费率", "表格清洗", "单据台账", "选品测算",
               "素材生产", "投流结构", "PO 采购单", "数据复盘"],
    "line1": "广告素材直连 12 家视频大模型：Seedance / Veo / Sora / 可灵 / 通义万相，写完提示词就出片",
    "line2": "每步都输出能直接打开的 Excel 表格；花钱、退款、合规只给判定与依据，落地由人执行",
    "footer_left": "github.com/xianglouw/ecom-agent-skills",
    "footer_right": "MIT License · Python 标准库，零依赖",
}


def font(size, weight="W6"):
    """Hiragino Sans GB 的粗细在同一个 ttc 里按顺序取：W3 细、W6 粗。"""
    index = 1 if weight == "W6" else 0
    return ImageFont.truetype(FONT_PATH, size, index=index)


def fit(text, max_width, start, weight="W6", floor=16):
    """字号从 start 往下试，直到这行文字塞得进 max_width。"""
    size = start
    while size > floor:
        f = font(size, weight)
        if f.getbbox(text)[2] - f.getbbox(text)[0] <= max_width:
            return f
        size -= 1
    return font(floor, weight)


def gradient_background():
    """纵向渐变底色，顶部略亮、底部压暗。"""
    image = Image.new("RGB", (WIDTH, HEIGHT), BG_TOP)
    draw = ImageDraw.Draw(image)
    for y in range(HEIGHT):
        ratio = y / (HEIGHT - 1)
        draw.line([(0, y), (WIDTH, y)],
                  fill=tuple(round(a + (b - a) * ratio) for a, b in zip(BG_TOP, BG_BOTTOM)))
    return image


def rounded_box(draw, box, radius=10):
    draw.rounded_rectangle(box, radius=radius, fill=BOX_FILL, outline=BOX_BORDER, width=2)


def main():
    image = gradient_background()
    draw = ImageDraw.Draw(image)

    # 顶部渐变条
    for x in range(WIDTH):
        ratio = x / (WIDTH - 1)
        color = tuple(round(a + (b - a) * ratio) for a, b in zip(BAR_START, BAR_END))
        draw.line([(x, 0), (x, 4)], fill=color)

    left = 80
    draw.text((left, 58), COPY["title"], font=font(54), fill=TITLE_COLOR)
    draw.text((left, 166), COPY["subtitle"], font=font(24, "W3"), fill=SUBTITLE_COLOR)

    # 8 个阶段方块：4 列 × 2 行
    box_w, box_h, gap = 260, 70, 22
    for index, label in enumerate(COPY["stages"]):
        row, col = divmod(index, 4)
        x = 90 + col * (box_w + gap)
        y = 228 + row * (box_h + gap)
        rounded_box(draw, [x, y, x + box_w, y + box_h])
        draw.text((x + 26, y + 22), str(index + 1), font=font(26, "W3"), fill=BOX_INDEX_COLOR)
        draw.text((x + 62, y + 20), label, font=font(27), fill=BOX_LABEL_COLOR)

    draw.line([(left, 424), (WIDTH - left, 424)], fill=RULE_COLOR, width=1)

    max_width = WIDTH - left * 2
    draw.text((left, 450), COPY["line1"], font=fit(COPY["line1"], max_width, 27, "W3"), fill=LINE1_COLOR)
    draw.text((left, 500), COPY["line2"], font=fit(COPY["line2"], max_width, 27, "W3"), fill=LINE2_COLOR)

    draw.text((left, 574), COPY["footer_left"], font=font(19, "W3"), fill=FOOTER_COLOR)
    right_font = font(19, "W3")
    right_width = right_font.getbbox(COPY["footer_right"])[2] - right_font.getbbox(COPY["footer_right"])[0]
    draw.text((WIDTH - left - right_width, 574), COPY["footer_right"], font=right_font, fill=FOOTER_COLOR)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    image.save(OUT, "PNG", optimize=True)
    print(f"已写出 {os.path.normpath(OUT)}（{image.size[0]}×{image.size[1]}，"
          f"{os.path.getsize(OUT) / 1024:.0f} KB，GitHub 上限 1 MB）")


if __name__ == "__main__":
    main()
