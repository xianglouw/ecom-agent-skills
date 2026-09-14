#!/usr/bin/env python3
"""阶段 4：多模态广告素材生产——分镜脚本、生成提示词与前三秒留存检查。

用法：
  python3 video_brief.py products.csv --styles market_styles.csv --hooks hook_patterns.csv \
    --banned banned_words.csv --duration 15 --ratio 9:16 --hooks-per-sku 2 \
    --out storyboard.csv --out-md brief.md --out-json brief.json

做的事：把「产品定义 + 投放市场」与市场风格库、钩子模板库做笛卡尔组合，产出
逐镜头的分镜脚本、可直接粘给视频模型（Seedance / Veo / 即梦等）的生成提示词，
并对每个素材跑一遍前三秒留存硬性检查。

产品表字段：sku、product_name、site（投放市场）、category、audience、selling_points、
proof、offer、price、currency；语种缺省从市场风格库取。
市场风格库字段：site、language、platforms、rhythm、visual_style、talent、scene、tone、avoid、source、as_of。
钩子模板库字段：hook_code、hook_name、desc、first_frame、line_template、caption_template、retention_note。
禁用词表字段：word、reason、scope、level。

只读输入，只写 --out/--out-json/--out-md/--quarantine 指定文件。
不编造地区风格——市场风格库里查不到的站点一律标 high flag，不套用别的市场习惯；
文案里需要创意填空的位置写成 {{待填:字段}} 显式暴露，不猜。
"""

import argparse
import os
import re
import sys

import sheetio
from sheetio import clean_text, to_number

PRODUCT_FIELDS = ["sku", "product_name", "site", "category", "audience", "selling_points",
                  "proof", "offer", "price", "currency", "language"]
STYLE_FIELDS = ["site", "language", "platforms", "rhythm", "visual_style", "talent", "scene",
                "tone", "avoid", "source", "as_of"]
HOOK_FIELDS = ["hook_code", "hook_name", "desc", "first_frame", "line_template",
               "caption_template", "retention_note"]
BANNED_FIELDS = ["word", "reason", "scope", "level"]

EXPORT_HEADERS = ["asset_name", "sku", "product_name", "site", "language", "ratio", "duration_s",
                  "hook_code", "hook_name", "shot_index", "timecode", "shot_seconds", "shot_type",
                  "visual_prompt", "caption", "voiceover", "retention_note", "placeholders", "note"]

# 分镜骨架：每种成片时长一套，第一镜固定 3 秒（前三秒法则）
SHOT_TEMPLATES = {
    15: [("钩子", 3), ("痛点场景", 4), ("产品演示", 4), ("证明", 2), ("CTA", 2)],
    21: [("钩子", 3), ("痛点场景", 5), ("产品演示", 6), ("证明", 4), ("CTA", 3)],
    30: [("钩子", 3), ("痛点场景", 7), ("产品演示", 8), ("证明", 7), ("CTA", 5)],
}

# 口播语速上限（每秒可讲完的字/词数）——经验值，随语种与主播语速浮动，可在此调整
SPEECH_UNITS_PER_SEC = {"zh": 4.5, "en": 2.6, "es": 2.8, "pt": 2.8, "fr": 2.6, "de": 2.4}
DEFAULT_SPEECH_RATE = 2.8

# 前 3 秒禁止出现的开场方式（用户划走最快的位置就是这几类）
BANNED_OPENINGS = ["logo", "片头", "黑屏", "空镜", "慢镜头", "慢动作", "标题动画", "静态产品图", "白底图"]

# 检查项 -> (级别, 说明)
CHECKS = {
    "retention_first_frame": ("high", "前 3 秒首帧要求缺失或用了高划走率的开场方式"),
    "retention_caption": ("high", "前 3 秒没有可读字幕，静音刷到的用户看不懂"),
    "retention_speech": ("medium", "前 3 秒口播超出该语种语速上限，讲不完"),
    "retention_localization": ("low", "前 3 秒文案仍是工作语言草稿，按投放市场语种本地化后需复测时长"),
    "retention_action": ("medium", "首帧只有静态描述，前 3 秒缺少动作或画面变化"),
    "retention_hookline": ("high", "前 3 秒的文案全是待填位，没有可直接生成的钩子内容"),
    "selling_points_missing": ("high", "没有卖点，钩子与分镜无从生成"),
    "selling_points_overload": ("medium", "卖点超过 3 个，观众记不住，钩子会被稀释"),
    "market_style_missing": ("high", "该投放市场没有风格库条目，地区人群/媒体习惯无法适配"),
    "audience_missing": ("medium", "缺目标人群，无法判断语言习惯与场景代入是否贴合"),
    "proof_missing": ("medium", "缺证明材料，转化环节没有信任支撑"),
    "offer_missing": ("medium", "缺 CTA 利益点，结尾只能干喊下单"),
    "banned_word_hit": ("high", "文案命中禁用词，上架或投流可能被拒审"),
    "brief_incomplete": ("low", "分镜里仍有未填的创意位（正常工序，补完再进生成队列）"),
}

PLACEHOLDER_PATTERN = re.compile(r"\{\{待填:[^}]*\}\}")
ACTION_WORDS = ["拿", "放", "倒", "撕", "拆", "打开", "跑", "走", "转", "按", "点", "切", "喷", "擦",
                "戴", "穿", "举", "抬", "推", "拉", "贴", "刷", "量", "称", "对", "试", "变", "弹出",
                "放大", "拉近", "滑动", "撒", "浇", "吹", "拍", "压", "挂", "翻", "快切", "转场",
                "出现", "划掉", "摇头", "点头", "摆手", "挥手", "比划", "走向", "展示", "举起",
                "举起", "合上", "装", "拆开", "塞", "取", "摆", "拧", "卷", "折", "撕开", "倒出",
                "擦拭", "递", "接", "指向", "触摸", "摇", "甩", "提", "戴好", "放下", "换上",
                "手持", "手势", "操作", "对准", "拎", "握", "递出", "翻找", "拍下", "摆出",
                "open", "pour", "cut", "drop", "grab", "walk", "run", "turn", "hold", "lift", "show",
                "test", "try", "spin", "snap", "peel", "click", "tap", "swap", "install", "unbox"]
TEMPLATE_PATTERN = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


def split_points(text):
    """把「；」「、」「|」等分隔的卖点拆开。"""
    return [piece for piece in re.split(r"[|｜;；、/]", clean_text(text)) if piece]


def speech_cap(language, seconds):
    """3 秒能讲完的字数/词数上限。"""
    rate = SPEECH_UNITS_PER_SEC.get((language or "zh").lower(), DEFAULT_SPEECH_RATE)
    return max(1, int(rate * seconds))


def speech_units(text, language):
    """按语种计量口播长度：中文数字，其他语种数词（空格分词）。"""
    if (language or "zh").lower() == "zh" or has_cjk(text):
        return len(re.sub(r"\s", "", text or ""))
    return len([word for word in re.split(r"\s+", (text or "").strip()) if word])


def timecode(start, length):
    return f"{start // 60}:{start % 60:02d}–{(start + length) // 60}:{(start + length) % 60:02d}"


def render(template, mapping):
    """填充模板；取不到值的位置显式留成 {{待填:字段}}，不猜内容。"""
    def substitute(match):
        key = match.group(1)
        value = mapping.get(key)
        return str(value) if value not in (None, "") else "{{待填:" + key + "}}"

    return TEMPLATE_PATTERN.sub(substitute, clean_text(template))


def has_cjk(text):
    """文案里有没有中文字符——用来区分「工作语言草稿」与「已本地化文案」。"""
    return bool(re.search(r"[\u4e00-\u9fff]", text or ""))


def count_placeholders(text):
    return len(PLACEHOLDER_PATTERN.findall(text or ""))


def has_real_content(text):
    """去掉待填位后还有没有实际内容（用来判断字幕/口播是不是等于没写）。"""
    stripped = PLACEHOLDER_PATTERN.sub("", text or "")
    return bool(re.sub(r"[\s，。；、,.;:！!？?—\-/]+", "", stripped))


def contains_action(text, extra_words=None):
    """首帧描述里有没有动作或画面变化（前 3 秒最忌讳静态开场）。

    关键词判定，必然有漏网与误报——词表可用 --actions 外置扩充，
    判定结果只作为提示，最终以人工/模型复核为准。
    """
    lowered = (text or "").lower()
    return any(word.lower() in lowered for word in (extra_words or ACTION_WORDS))


def pick_hooks(hooks, count, offset):
    """按序轮换钩子，让不同 SKU 用到不同钩子类型，避免整套素材同一个开头。"""
    if not hooks or count <= 0:
        return []
    count = min(count, len(hooks))
    return [hooks[(offset + index) % len(hooks)] for index in range(count)]


def load_styles(paths, sheet, header_row):
    """读市场风格库，返回 ({SITE: {...}}, flags)。"""
    styles, flags = {}, []
    for path in paths or []:
        try:
            headers, body = sheetio.read_table(path, sheet=sheet, header_row=header_row)
        except (OSError, ValueError) as error:
            flags.append(sheetio.flag("high", "style_table_unreadable", f"{os.path.basename(path)} 读取失败：{error}",
                                      "确认文件格式与表头行号"))
            continue
        columns = sheetio.column_map(headers, STYLE_FIELDS)
        if "site" not in columns:
            flags.append(sheetio.flag("high", "style_table_unreadable",
                                      f"{os.path.basename(path)} 没有站点列，无法与产品表关联",
                                      "用 --map 原列名=site 指定站点列"))
            continue
        for raw in body:
            def cell(field, row=raw, cols=columns):
                position = cols.get(field)
                return row[position] if position is not None and position < len(row) else ""

            site = clean_text(cell("site")).upper()
            if not site:
                continue
            styles[site] = {field: clean_text(cell(field)) for field in STYLE_FIELDS if field != "site"}
    return styles, flags


def load_hooks(paths, sheet, header_row):
    hooks, flags = [], []
    for path in paths or []:
        try:
            headers, body = sheetio.read_table(path, sheet=sheet, header_row=header_row)
        except (OSError, ValueError) as error:
            flags.append(sheetio.flag("high", "hook_table_unreadable",
                                      f"{os.path.basename(path)} 读取失败：{error}", "确认文件格式与表头行号"))
            continue
        columns = sheetio.column_map(headers, HOOK_FIELDS)
        for raw in body:
            def cell(field, row=raw, cols=columns):
                position = cols.get(field)
                return row[position] if position is not None and position < len(row) else ""

            code = clean_text(cell("hook_code"))
            if not code:
                continue
            hooks.append({"hook_code": code, "hook_name": clean_text(cell("hook_name")),
                          "desc": clean_text(cell("desc")), "first_frame": clean_text(cell("first_frame")),
                          "line_template": clean_text(cell("line_template")),
                          "caption_template": clean_text(cell("caption_template")),
                          "retention_note": clean_text(cell("retention_note"))})
    return hooks, flags


def load_banned(paths, sheet, header_row):
    words = []
    for path in paths or []:
        try:
            headers, body = sheetio.read_table(path, sheet=sheet, header_row=header_row)
        except (OSError, ValueError):
            continue
        columns = sheetio.column_map(headers, BANNED_FIELDS)
        if "word" not in columns:
            continue
        for raw in body:
            position = columns["word"]
            word = clean_text(raw[position]) if position < len(raw) else ""
            if not word:
                continue

            def cell(field, row=raw, cols=columns):
                index = cols.get(field)
                return clean_text(row[index]) if index is not None and index < len(row) else ""

            words.append({"word": word, "reason": cell("reason"), "scope": cell("scope"),
                          "level": (cell("level") or "high").lower()})
    return words


def load_action_words(paths, sheet, header_row):
    """加载自定义动作词表（word 列），与内置词表合并后用于首帧动态检查。"""
    words = []
    for path in paths or []:
        try:
            headers, body = sheetio.read_table(path, sheet=sheet, header_row=header_row)
        except (OSError, ValueError):
            continue
        columns = sheetio.column_map(headers, ["word"])
        if "word" not in columns:
            continue
        for raw in body:
            position = columns["word"]
            word = clean_text(raw[position]) if position < len(raw) else ""
            if word:
                words.append(word)
    return words


def scan_banned(text, banned, site):
    hits = []
    for item in banned:
        scope = item["scope"].upper()
        if scope and scope not in {"ALL", "通用", "全站点"} and site not in scope:
            continue
        if item["word"] and item["word"] in (text or ""):
            hits.append(item)
    return hits


def build_shot_rows(product, style, hook, duration):
    """按分镜骨架生成逐镜头行；创意位留 {{待填:...}}，不编造。"""
    points = split_points(product["selling_points"])
    mapping = {
        "selling_point": points[0] if points else "",
        "selling_point2": points[1] if len(points) > 1 else "",
        "selling_point3": points[2] if len(points) > 2 else "",
        "audience": product["audience"],
        "proof": product["proof"],
        "offer": product["offer"],
        "market": product["site"],
        "category": product["category"],
        "price": f"{product['price']} {product['currency']}".strip() if product["price"] else "",
    }
    rows = []
    start = 0
    for index, (shot_type, seconds) in enumerate(SHOT_TEMPLATES[duration], start=1):
        if shot_type == "钩子":
            caption = render(hook["caption_template"] or hook["line_template"], mapping)
            voiceover = render(hook["line_template"], mapping)
            visual = "；".join(piece for piece in [
                hook["first_frame"] or "{{待填:首帧画面}}",
                style.get("talent") or "{{待填:出镜者}}",
                style.get("visual_style") or "{{待填:画面风格}}",
            ] if piece)
        elif shot_type == "痛点场景":
            caption = "{{待填:痛点关键词}}"
            voiceover = "{{待填:用户最痛的场景，1 句}}"
            visual = "；".join(piece for piece in [
                style.get("scene") or "{{待填:使用场景}}",
                style.get("talent") or "{{待填:出镜者}}",
                "痛点场景还原，真实环境实拍，不用绿幕",
            ] if piece)
        elif shot_type == "产品演示":
            caption = "{{待填:卖点关键词}}"
            voiceover = "、".join(points[:3]) or "{{待填:核心卖点}}"
            visual = "；".join(piece for piece in [
                "产品实拍演示",
                points[0] if points else "{{待填:核心卖点}}",
                style.get("visual_style") or "{{待填:画面风格}}",
            ] if piece)
        elif shot_type == "证明":
            caption = product["proof"] or "{{待填:证明材料}}"
            voiceover = product["proof"] or "{{待填:证明材料}}"
            visual = "；".join(piece for piece in [
                "证明镜头", product["proof"] or "{{待填:实测/对比/资质画面}}",
                style.get("visual_style") or "{{待填:画面风格}}",
            ] if piece)
        else:  # CTA
            caption = product["offer"] or "{{待填:CTA 利益点}}"
            voiceover = product["offer"] or "{{待填:CTA 利益点}}"
            visual = "；".join(piece for piece in [
                "CTA 收尾", "口播指向行动", style.get("talent") or "{{待填:出镜者}}",
            ] if piece)
        note = []
        if shot_type == "钩子":
            note.append("前三秒法则：首帧即主体或冲突，禁止 " + "、".join(BANNED_OPENINGS[:4]) + " 开场")
        if index == len(SHOT_TEMPLATES[duration]):
            note.append("全片只留一个 CTA 动作")
        rows.append({
            "shot_index": index, "timecode": timecode(start, seconds), "shot_seconds": seconds,
            "shot_type": shot_type, "visual_prompt": visual, "caption": caption, "voiceover": voiceover,
            "retention_note": hook["retention_note"] if shot_type == "钩子" else "",
            "note": "；".join(note),
        })
        start += seconds
    return rows


def check_asset(product, style, hook, rows, banned, action_words=None):
    """跑前三秒法则与素材完整性检查，返回问题列表 [(check, detail)]。"""
    issues = []
    hook_shot = rows[0]
    first_frame = hook["first_frame"]
    lowered = (first_frame or "").lower()
    if not first_frame or any(word.lower() in lowered for word in BANNED_OPENINGS):
        issues.append(("retention_first_frame", f"首帧要求：{first_frame or '（空）'}"))
    elif not contains_action(first_frame, action_words):
        issues.append(("retention_action", f"首帧只有静态描述：{first_frame}"))

    language = (product["language"] or style.get("language") or "").lower()
    caption_ok = has_real_content(hook_shot["caption"])
    voice_ok = has_real_content(hook_shot["voiceover"])
    if not caption_ok and not voice_ok:
        issues.append(("retention_hookline", "前 3 秒字幕与口播都由待填位组成"))
    else:
        if not caption_ok:
            issues.append(("retention_caption", "前 3 秒没有可读字幕，静音刷到的用户看不懂"))
        if voice_ok:
            copy_text = hook_shot["voiceover"] + hook_shot["caption"]
            copy_language = "zh" if has_cjk(copy_text) else (language or "zh")
            cap = speech_cap(copy_language, 3)
            spoken = speech_units(hook_shot["voiceover"], copy_language)
            if spoken > cap:
                suffix = "（当前为中文草稿，本地化后需按目标语种重新配词）" if copy_language == "zh" else ""
                unit = "字" if copy_language == "zh" else "词"
                issues.append(("retention_speech",
                               f"前 3 秒口播 {spoken} {unit}，超过 {copy_language} 语速上限 "
                               f"{cap} {unit}/3s{suffix}"))
            if copy_language == "zh" and language and language != "zh":
                issues.append(("retention_localization",
                               f"文案为中文草稿，需按 {language} 重写并复测前 3 秒时长"))

    points = split_points(product["selling_points"])
    if not points:
        issues.append(("selling_points_missing", ""))
    elif len(points) > 3:
        issues.append(("selling_points_overload", f"{len(points)} 个卖点：{'、'.join(points)}"))
    if not style:
        issues.append(("market_style_missing", f"站点 {product['site']}"))
    if not product["audience"]:
        issues.append(("audience_missing", ""))
    if not product["proof"]:
        issues.append(("proof_missing", ""))
    if not product["offer"]:
        issues.append(("offer_missing", ""))

    text = "；".join([product["selling_points"], product["proof"], product["offer"],
                      "；".join(row["caption"] for row in rows),
                      "；".join(row["voiceover"] for row in rows)])
    for item in scan_banned(text, banned, product["site"]):
        issues.append(("banned_word_hit", f"{item['word']}（{item['reason'] or '未注明原因'}）"))

    placeholders = sum(count_placeholders(row["visual_prompt"]) + count_placeholders(row["caption"])
                       + count_placeholders(row["voiceover"]) for row in rows)
    if placeholders:
        issues.append(("brief_incomplete", f"{placeholders} 处创意位待填"))
    return issues, placeholders


def build_model_prompt(product, style, hook, rows, ratio, duration):
    """拼出可直接粘给视频模型的生成提示词（由结构化字段拼装，不含编造内容）。"""
    shots = "；".join(f"{row['timecode']}（{row['shot_type']}）{row['visual_prompt']}" for row in rows)
    captions = " / ".join(f"{row['timecode']} {row['caption']}" for row in rows)
    return "\n".join([
        f"【主题】{product['product_name'] or product['sku']}——{product['category'] or '{{待填:品类}}'}"
        f"，面向{product['audience'] or '{{待填:目标人群}}'}（{product['site']} 市场）",
        f"【风格】{style.get('visual_style') or '{{待填:画面风格}}'}；{style.get('tone') or '{{待填:话术调性}}'}；"
        f"{style.get('rhythm') or '{{待填:剪辑节奏}}'}；出镜：{style.get('talent') or '{{待填:出镜者}}'}",
        f"【规格】{duration}s，{ratio}，竖版优先；字幕全程常驻，静音可读",
        f"【分镜】{shots}",
        f"【字幕】{captions}",
        f"【钩子】{hook['hook_name'] or hook['hook_code']}：{hook['desc']}"
        + (f"（{hook['retention_note']}）" if hook["retention_note"] else ""),
        f"【配乐】{{{{待填:BGM/音效}}}}，{style.get('rhythm') or '节奏跟随剪辑'}",
        f"【合规】避免：{style.get('avoid') or '{{待填:该市场禁忌元素}}'}；"
        "不使用绝对化用语、功效承诺、未经证实的对比",
    ])


def build_markdown(data, args, detail_count):
    lines = ["# 多模态素材 Brief（阶段 4）", ""]
    lines.append(f"- 范围：{data['product_count']} 个产品 × {len(data['sites'])} 个市场 × "
                 f"{len(data['hooks'])} 个钩子 × {len(data['ratios'])} 个比例，共 {data['asset_count']} 条素材")
    lines.append(f"- 规格：成片 {args.duration}s，分镜骨架 "
                 + " → ".join(f"{shot}（{sec}s）" for shot, sec in SHOT_TEMPLATES[args.duration]))
    lines.append("- 口径：文案中 {{待填:字段}} 是刻意留出的创意位，由模型或人工补齐后再进生成队列；"
                 "本表不编造地区人群习惯，风格一律取自市场风格库")
    lines.append("")

    lines.append("## 素材总表")
    lines.append("")
    lines.append("| 素材名 | 市场 | 语种 | 钩子 | 前 3 秒检查 | 提示 | 待填 |")
    lines.append("|---|---|---|---|---|---|---|")
    for asset in data["assets"]:
        status = "通过" if not asset["retention_blocking"] else "；".join(
            f"{CHECKS[key][1]}（{detail}）" if detail else CHECKS[key][1]
            for key, detail in asset["retention_blocking"])
        hint = "；".join(f"{CHECKS[key][1]}" for key, _ in asset["retention_notes"]) or "—"
        lines.append(f"| {asset['asset_name']} | {asset['site']} | {asset['language'] or '—'} | "
                     f"{asset['hook_code']} {asset['hook_name']} | {status} | {hint} | "
                     f"{asset['placeholders']} |")
    lines.append("")

    lines.append(f"## 分镜详情（前 {detail_count} 条素材）")
    lines.append("")
    for asset in data["assets"][:detail_count]:
        lines.append(f"### {asset['asset_name']}")
        lines.append("")
        lines.append(f"- 市场/语种：{asset['site']} / {asset['language'] or '未指定'}；"
                     f"钩子：{asset['hook_code']} {asset['hook_name']}")
        lines.append(f"- 前 3 秒检查："
                     + ("通过" if not asset["retention_blocking"] else "；".join(
                         f"{key}（{detail}）" if detail else key for key, detail in asset["retention_blocking"]))
                     + ("；提示：" + "；".join(key for key, _ in asset["retention_notes"])
                        if asset["retention_notes"] else ""))
        lines.append("")
        lines.append("| 时间码 | 镜头 | 画面 | 字幕 | 口播 |")
        lines.append("|---|---|---|---|---|")
        for row in asset["rows"]:
            lines.append(f"| {row['timecode']} | {row['shot_type']} | {row['visual_prompt']} | "
                         f"{row['caption']} | {row['voiceover']} |")
        lines.append("")
        lines.append("生成提示词（可直接粘给文生视频模型）：")
        lines.append("")
        lines.append("```text")
        lines.append(asset["model_prompt"])
        lines.append("```")
        lines.append("")

    if data["uncovered_sites"]:
        lines.append("## 风格库缺口")
        lines.append("")
        lines.append("以下市场在市场风格库里没有条目，未做地区适配，请补风格库后重跑："
                     + "、".join(data["uncovered_sites"]))
        lines.append("")
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description="多模态广告素材生产：分镜脚本 + 生成提示词 + 前三秒留存检查")
    parser.add_argument("input", help="产品表：.csv/.xlsx，字段 sku/site/selling_points 等")
    parser.add_argument("--styles", action="append", default=[], metavar="市场风格库",
                        help="市场风格库，可重复传多个文件")
    parser.add_argument("--hooks", action="append", default=[], metavar="钩子模板库",
                        help="钩子模板库，可重复传多个文件")
    parser.add_argument("--banned", action="append", default=[], metavar="禁用词表",
                        help="禁用词表，可重复传多个文件")
    parser.add_argument("--actions", action="append", default=[], metavar="动作词表",
                        help="自定义动作词表（word 列），用于首帧动态检查，可重复传多个文件")
    parser.add_argument("--duration", type=int, default=15, choices=sorted(SHOT_TEMPLATES),
                        help="成片时长秒数，默认 15")
    parser.add_argument("--ratio", default="9:16", help="画幅比例，逗号分隔可传多个，如 9:16,16:9")
    parser.add_argument("--hooks-per-sku", type=int, default=2, help="每个 SKU×市场 生成几条钩子，默认 2")
    parser.add_argument("--markets", default="", help="只测算这些市场，逗号分隔，如 MX,BR")
    parser.add_argument("--top", type=int, default=5, help="Markdown 里展开详情的素材数，默认 5")
    parser.add_argument("--out", default=None, help="输出分镜表 CSV")
    parser.add_argument("--out-json", default=None, help="输出结果信封 JSON")
    parser.add_argument("--out-md", default=None, help="输出 Markdown brief")
    parser.add_argument("--quarantine", default=None, help="输出未适配/未通过检查的素材清单 CSV")
    parser.add_argument("--map", action="append", default=[], metavar="原列名=标准字段")
    parser.add_argument("--sheet", type=int, default=1, help="xlsx 工作表序号")
    parser.add_argument("--header-row", type=int, default=1, help="产品表表头行号")
    parser.add_argument("--styles-header-row", type=int, default=1, help="风格库表头行号")
    parser.add_argument("--hooks-header-row", type=int, default=1, help="钩子库表头行号")
    parser.add_argument("--banned-header-row", type=int, default=1, help="禁用词表表头行号")
    args = parser.parse_args(argv)

    flags = []
    ratios = [piece.strip() for piece in args.ratio.replace("，", ",").split(",") if piece.strip()]
    only_markets = {piece.strip().upper() for piece in args.markets.replace("，", ",").split(",") if piece.strip()}
    if not ratios:
        sheetio.emit(sheetio.make_envelope("video_brief", "blocked", 0.0, {"error": "--ratio 为空"},
                                           [sheetio.flag("high", "input_error", "--ratio 为空", "写成 9:16 或 9:16,16:9")]),
                     out_json=args.out_json)
        return 2

    styles, style_flags = load_styles(args.styles, args.sheet, args.styles_header_row)
    flags += style_flags
    hooks, hook_flags = load_hooks(args.hooks, args.sheet, args.hooks_header_row)
    flags += hook_flags
    banned = load_banned(args.banned, args.sheet, args.banned_header_row)
    action_words = ACTION_WORDS + load_action_words(args.actions, args.sheet, args.banned_header_row)

    if not hooks:
        flags.append(sheetio.flag("high", "hook_library_missing", "没有可用的钩子模板，无法生成分镜",
                                  "用 --hooks 指定钩子模板库（字段：hook_code/hook_name/first_frame/line_template）"))

    mapping = sheetio.apply_mapping(args.map)
    try:
        headers, body = sheetio.read_table(args.input, sheet=args.sheet, header_row=args.header_row)
    except (OSError, ValueError) as error:
        sheetio.emit(sheetio.make_envelope("video_brief", "blocked", 0.0, {"error": str(error)},
                                           [sheetio.flag("high", "input_error", str(error), "确认文件路径与格式")]),
                     out_json=args.out_json)
        return 2
    if mapping:
        headers = [mapping.get(sheetio.norm_key(header), header) for header in headers]
    columns = sheetio.column_map(headers, PRODUCT_FIELDS)
    if "sku" not in columns or "site" not in columns:
        missing = [field for field in ("sku", "site") if field not in columns]
        flags.append(sheetio.flag("high", "missing_required_columns",
                                  f"产品表缺少 { '、'.join(missing) } 列，无法生成素材 brief",
                                  "用 --map 指定，例如 --map 商品编码=sku、--map 投放市场=site"))
        sheetio.emit(sheetio.make_envelope("video_brief", "blocked", 0.0,
                                           {"detected_columns": sorted(columns)}, flags), out_json=args.out_json)
        return 2

    rows_out, assets, uncovered_sites = [], [], set()
    issue_index = {}
    product_count = 0
    for row_ordinal, raw in enumerate(body):
        def cell(field, row=raw, cols=columns):
            position = cols.get(field)
            return row[position] if position is not None and position < len(row) else ""

        sku = clean_text(cell("sku"))
        if not sku:
            continue
        site = clean_text(cell("site")).upper()
        if only_markets and site not in only_markets:
            continue
        price = to_number(cell("price"))
        product = {
            "sku": sku, "product_name": clean_text(cell("product_name")), "site": site,
            "category": clean_text(cell("category")), "audience": clean_text(cell("audience")),
            "selling_points": clean_text(cell("selling_points")), "proof": clean_text(cell("proof")),
            "offer": clean_text(cell("offer")),
            "price": f"{price:g}" if price is not None else "",
            "currency": clean_text(cell("currency")), "language": clean_text(cell("language")),
        }
        product_count += 1
        style = styles.get(site, {})
        if not style:
            uncovered_sites.add(site)

        for hook in pick_hooks(hooks, args.hooks_per_sku, row_ordinal * max(0, args.hooks_per_sku)):
            for ratio in ratios:
                shot_rows = build_shot_rows(product, style, hook, args.duration)
                issues, placeholders = check_asset(product, style, hook, shot_rows, banned, action_words)
                language = product["language"] or style.get("language", "")
                asset_name = f"{sku}_{site}_{hook['hook_code']}_{ratio.replace(':', 'x')}_{args.duration}s_v1"
                retention = [(key, detail) for key, detail in issues if key.startswith("retention_")]
                asset = {
                    "asset_name": asset_name, "sku": sku, "site": site, "language": language,
                    "hook_code": hook["hook_code"], "hook_name": hook["hook_name"],
                    "ratio": ratio, "rows": shot_rows, "placeholders": placeholders,
                    "retention_issues": retention,
                    "retention_blocking": [(key, detail) for key, detail in retention
                                           if CHECKS.get(key, ("medium", ""))[0] != "low"],
                    "retention_notes": [(key, detail) for key, detail in retention
                                        if CHECKS.get(key, ("low", ""))[0] == "low"],
                    "issues": issues,
                    "model_prompt": build_model_prompt(product, style, hook, shot_rows, ratio, args.duration),
                }
                assets.append(asset)
                for key, detail in issues:
                    issue_index.setdefault(key, []).append((asset_name, detail))
                for row in shot_rows:
                    rows_out.append([asset_name, sku, product["product_name"], site, language, ratio,
                                     args.duration, hook["hook_code"], hook["hook_name"], row["shot_index"],
                                     row["timecode"], row["shot_seconds"], row["shot_type"],
                                     row["visual_prompt"], row["caption"], row["voiceover"],
                                     row["retention_note"], placeholders, row["note"]])

    for key, hits in sorted(issue_index.items()):
        level, description = CHECKS.get(key, ("medium", key))
        preview = "；".join(f"{asset}{('（' + detail + '）') if detail else ''}" for asset, detail in hits[:3])
        flags.append(sheetio.flag(level, key, f"{len(hits)} 条素材：{description}——{preview}",
                                  "按 references/video-production.md 的检查项修正后重跑"))

    if args.out:
        sheetio.write_csv(args.out, EXPORT_HEADERS, rows_out)
    if args.quarantine:
        quarantine_rows = [[asset["asset_name"], asset["site"], asset["language"],
                            "；".join(f"{key}:{detail}" if detail else key for key, detail in asset["issues"]),
                            asset["placeholders"]]
                           for asset in assets if asset["issues"]]
        sheetio.write_csv(args.quarantine,
                          ["asset_name", "site", "language", "_问题", "placeholders"], quarantine_rows)

    high_level = [flag for flag in flags if flag["level"] == "high"]
    retention_fail = sum(1 for asset in assets if asset["retention_blocking"])
    pending_assets = sum(1 for asset in assets if asset["placeholders"])
    data = {
        "product_count": product_count,
        "asset_count": len(assets),
        "shot_rows": len(rows_out),
        "duration_s": args.duration,
        "ratios": ratios,
        "sites": sorted({asset["site"] for asset in assets}),
        "hooks": [{"hook_code": hook["hook_code"], "hook_name": hook["hook_name"]} for hook in hooks],
        "assets": assets,
        "uncovered_sites": sorted(uncovered_sites),
        "retention_pass": len(assets) - retention_fail,
        "retention_fail": retention_fail,
        "assets_with_placeholders": pending_assets,
        "issue_counts": {key: len(hits) for key, hits in issue_index.items()},
    }

    if args.out_md:
        with open(args.out_md, "w", encoding="utf-8") as handle:
            handle.write(build_markdown(data, args, args.top))

    status = "ok"
    if high_level:
        status = "partial"
    if not assets:
        status = "blocked"
    style_coverage = (len(data["sites"]) - len(uncovered_sites)) / len(data["sites"]) if data["sites"] else 0.0
    retention_ratio = (len(assets) - retention_fail) / len(assets) if assets else 0.0
    confidence = round(0.35 + 0.3 * style_coverage + 0.3 * retention_ratio, 2) if assets else 0.2
    if pending_assets:
        confidence = min(confidence, 0.9)
    if high_level:
        confidence = min(confidence, 0.7)
    elif any(flag["level"] == "medium" for flag in flags):
        confidence = min(confidence, 0.85)
    confidence = min(confidence, 0.95)

    envelope = sheetio.make_envelope(
        "video_brief", status, confidence, data, flags,
        sources=[{"ref": os.path.basename(path), "as_of": ""} for path in args.styles]
        + [{"ref": os.path.basename(path), "as_of": ""} for path in args.hooks],
        assumptions=[
            "分镜骨架固定五段：3 秒钩子 → 痛点场景 → 产品演示 → 证明 → CTA，第一镜永远是钩子",
            "口播语速上限按语种经验值折算（zh 4.5 字/秒、en 2.6、es/pt 2.8 词/秒），随主播语速浮动，可按自查结果调整",
            "文案中的 {{待填:字段}} 是刻意留出的创意位，必须由模型或人工补齐后再进生成队列",
            "地区人群与媒体风格一律取自 --styles 指定的风格库，本脚本不编造地区习惯与平台偏好",
        ],
    )
    sheetio.emit(envelope, out_json=args.out_json)
    sys.stderr.write(f"[video_brief] {len(assets)} 条素材、{len(rows_out)} 行分镜；"
                     f"前三秒检查通过 {data['retention_pass']} 条，待填素材 {pending_assets} 条，"
                     f"市场覆盖 {len(data['sites']) - len(uncovered_sites)}/{len(data['sites'])}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
