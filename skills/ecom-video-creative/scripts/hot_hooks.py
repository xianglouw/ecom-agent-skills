#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""周期热词与黄金三秒台词套路挖掘：把采样到的爆款前 3 秒台词，变成下一条素材能用的钩子。

运营从平台热榜 / 带货榜 / 竞品素材里采样一批「前 3 秒到底说了什么」，通常是几十条
台词散在一张表里。这个脚本做四件事，每一步都可复核：

1. **套路归类**：按可解释的线索（问句、否定词、价格、对比、自称、痛点、场景）把每条台词
   归到钩子套路。命中几条线索就记几条，主套路按固定优先级选，**认不出来的一律进「未归类」
   交人工，不硬判**。
2. **热词统计**：分两类分开标——「词典命中」是命中内置多语种词表的词（类别明确、可直接用）；
   「候选片段」是机器抽取的高频片段（标出来提醒人工确认，不当成结论）。
3. **套路排行**：每个套路被多少条爆款用到、占比多少、带表现数据的算平均，产出本周期
   「先抄哪个套路」的排序。
4. **钩子候选**：把排在前面的套路 × 产品表，渲染成可直接追加进钩子库的候选行
   （沿用钩子库的口播 / 字幕模板，产品变量填不出的地方保留 {{待填:}}，不替用户编造）。

用法：
    python3 hot_hooks.py viral_samples.csv --hooks hook_patterns.csv --products products.csv \\
      --top 3 --out hot_words.csv --out-xlsx hot_hooks.xlsx --out-md hot_hooks.md \\
      --out-json hot_hooks.json --quarantine hot_hooks_issues.csv

采到的台词是别人的素材，只用来提炼套路与用词，**不要直接搬运别人的画面、口播原句与 BGM**；
换脸、数字人、去水印这类操作另有平台标注与肖像权红线，见 references/creative-stack.md。
"""

import argparse
import os
import re
import sys

import sheetio
from sheetio import clean_text, to_number

# ---------------------------------------------------------------- 字段与别名

SAMPLE_FIELDS = ["platform", "site", "language", "category", "line", "views", "sales", "likes", "ref", "collected_at"]

SAMPLE_ALIASES = {
    "platform": ["平台", "渠道", "platform", "channel", "投放平台"],
    "site": ["站点", "国家", "市场", "site", "country", "marketplace"],
    "language": ["语种", "语言", "language", "lang"],
    "category": ["类目", "品类", "category", "商品类目"],
    "line": ["前3秒台词", "前3秒", "黄金3秒", "台词", "开场", "开头", "开场白", "钩子台词", "口播",
             "line", "hook_line", "hook", "script", "opening", "first_line"],
    "views": ["播放量", "播放", "播放数", "views", "view", "play", "plays", "曝光"],
    "sales": ["销量", "出单", "成交", "sales", "orders", "sold"],
    "likes": ["点赞", "点赞数", "likes", "like", "digg", "收藏"],
    "ref": ["作品", "作品id", "作品或链接", "作品链接", "链接", "ref", "url", "video_id", "作品号"],
    "collected_at": ["采集日期", "采样日期", "日期", "collected_at", "date", "collected"],
}

REQUIRED_FIELDS = ["line"]

DETAIL_HEADERS = ["序号", "平台", "站点", "语种", "类目", "前3秒台词", "主套路", "套路类型",
                  "命中线索", "兼中套路", "播放量", "销量", "点赞", "作品", "采集日期"]
WORD_HEADERS = ["词", "类别", "出现次数", "覆盖作品数", "来源类型", "示例台词"]
RANK_HEADERS = ["排行", "套路编码", "套路类型", "本周期作品数", "占比", "平均播放量", "平均销量",
                "代表台词", "典型线索", "建议用法"]
CANDIDATE_HEADERS = ["钩子编码", "钩子类型", "钩子说明", "首帧要求", "口播模板", "字幕模板", "留存说明",
                     "本周期证据", "代表作", "建议产品", "该市场热词", "待补变量"]
ISSUE_HEADERS = ["行号", "问题", "说明", "原台词", "建议动作"]

# ---------------------------------------------------------------- 套路判定

# priority 越大越优先当主套路：否定/反常识最鲜明，价格次之，再是提问与对比；
# 一条台词命中多个套路时全部记录，主套路只取优先级最高的那个。
HOOK_PATTERNS = [
    {
        "code": "H05", "name": "反常识", "priority": 30,
        "why": "先否定一个大家都在做的做法，制造「那我做错了？」的停顿",
        "structural": (),
        "cues": ["别再", "别买", "不要买", "别再用", "错了", "白买", "交智商税", "被坑",
                  "don't", "dont", "stop buying", "stop using", "no compres", "no uses", "deja de",
                  "estás haciendo mal", "pare de", "para de", "não compre", "deixa de", "chega de",
                  "đừng", "đừng mua", "sai rồi", "やめて", "買わないで", "間違い",
                  "อย่า", "ผิด", "그만", "사지 마"],
    },
    {
        "code": "H03", "name": "价格锚点", "priority": 26,
        "why": "把价格直接甩在前面，用划算感换停留",
        "structural": ("price",),
        "cues": ["只要", "才", "立减", "打折", "半价", "白菜价", "免费", "白送",
                  "only", "just", "for only", "price", "cheap", "free", "dollars", "$", "€", "£",
                  "solo", "por solo", "por sólo", "barato", "gratis", "descuento", "pesos", "dólares",
                  "só", "apenas", "por apenas", "reais",
                  "chỉ", "giá", "rẻ", "miễn phí", "đồng", "円", "安い", "無料",
                  "บาท", "ฟรี", "ถูก", "원", "무료"],
    },
    {
        "code": "H08", "name": "悬念提问", "priority": 24,
        "why": "用问句制造未完成感，逼观众留下来找答案",
        "structural": ("question",),
        "cues": ["为什么", "凭什么", "怎么做到", "知道吗", "你知道吗", "猜猜",
                  "why", "how", "guess what", "por qué", "por que", "cómo", "adivina",
                  "tại sao", "vì sao", "sao lại", "なぜ", "どうして", "ทำไม", "왜", "어떻게"],
    },
    {
        "code": "H06", "name": "对比测试", "priority": 23,
        "why": "当场摆出两个方案对比，用看得见的差别替代口头说服",
        "structural": (),
        "cues": ["对比", "比一比", "左边", "右边", "旧款", "老款", "新款", "vs", "versus", "than",
                  "compare", "comparado", "mejor que", "antes y después", "em vez de",
                  "hơn", "so với", "より", "比べて", "เทียบ", "비교"],
    },
    {
        "code": "H04", "name": "身份代入", "priority": 22,
        "why": "直接点名目标人群，让对的人觉得「说的就是我」",
        "structural": (),
        "cues": ["如果你也是", "如果你", "宝妈", "上班族", "司机", "学生", "独居", "新手", "房东", "摆摊",
                  "if you are", "if you're", "for moms", "for parents", "si eres", "si tienes",
                  "se você", "se vocês", "para mães",
                  "nếu bạn", "あなたも", "mẹ", "phụ huynh", "คุณแม่", "ถ้าคุณ", "엄마", "직장인"],
    },
    {
        "code": "H01", "name": "痛点直击", "priority": 21,
        "why": "把用户正在忍的麻烦直接说出来，让他确认「说的就是我」",
        "structural": (),
        "cues": ["还在忍", "每次都要", "受不了", "麻烦", "头疼", "心累", "烦", "难用", "脏", "乱",
                  "卡", "慢", "annoying", "struggle", "tired of", "hate", "messy",
                  "cansado", "difícil", "sucio", "lento", "complicado", "chán", "phiền",
                  "面倒", "大変", "汚い", "遅い", "น่ารำคาญ", "불편", "힘들"],
    },
    {
        "code": "H02", "name": "结果前置", "priority": 20,
        "why": "先把最终效果甩出来，再回头讲怎么做到",
        "structural": (),
        "cues": ["效果自己看", "直接看结果", "看结果", "结果", "前后对比", "瞬间", "一秒",
                  "look at this", "result", "before and after", "instant",
                  "resultado", "en segundos", "veja o resultado", "em segundos",
                  "kết quả", "結果", "ก่อนหลัง", "결과"],
    },
    {
        "code": "H07", "name": "场景代入", "priority": 19,
        "why": "把产品放进用户每天都会遇到的场景，降低想象成本",
        "structural": (),
        "cues": ["每天", "每次", "在家", "出门", "开车", "通勤", "露营", "厨房", "办公室", "旅行", "带娃",
                  "every day", "everyday", "at home", "in the car", "office", "camping",
                  "cada día", "cada mañana", "todos los días", "en casa", "en el coche", "en el auto",
                  "todo dia", "todos os dias", "em casa", "no carro",
                  "mỗi ngày", "ở nhà", "毎日", "家で", "ทุกวัน", "매일", "집에서"],
    },
]

UNCLASSIFIED = {"code": "", "name": "未归类", "priority": 0, "why": "", "structural": (), "cues": []}

QUESTION_MARKS = ("?", "？", "¿", "؟")
CURRENCY_MARKS = ("$", "€", "£", "¥", "￥", "฿", "₫", "₹", "₩", "r$", "usd", "mxn", "brl", "vnd", "thb", "jpy")

# ---------------------------------------------------------------- 热词词典

# 只做「命中即计数」的确定词，歧义大的不进表；机器抽出来的高频片段另算一类并明确标注。
WORD_CATEGORIES = {
    "人群词": ["宝妈", "妈妈", "爸爸", "上班族", "司机", "学生", "老人", "孩子", "家庭", "新手", "独居",
               "露营", "健身", "房东", "摆摊",
               "mom", "mommy", "dad", "parents", "driver", "student", "family", "renters",
               "mamá", "papá", "conductor", "estudiante", "familia",
               "mẹ", "bố", "nhân viên", "sinh viên", "gia đình", "お母さん", "お父さん", "学生", "家族",
               "คุณแม่", "นักเรียน", "ครอบครัว", "엄마", "직장인", "학생"],
    "痛点词": ["麻烦", "头疼", "心累", "受不了", "脏", "乱", "卡", "慢", "难用", "占地方", "费电", "漏水",
               "缠", "绕", "散", "乱糟糟",
               "annoying", "messy", "mess", "slow", "expensive", "struggle", "clutter", "pain",
               "waste", "tangled", "leak",
               "difícil", "sucio", "lento", "caro", "problema", "enredo", "desastre", "molesto",
               "incómodo", "pierde tiempo", "peleas",
               "difícil", "bagunça", "perde tempo", "demora", "caro",
               "phiền", "bẩn", "chậm", "đắt", "vấn đề", "rối", "mất thời gian", "khó chịu",
               "面倒", "汚い", "遅い", "高い", "絡まる", "困る", "散らかる",
               "น่ารำคาญ", "แพง", "ยุ่ง", "ช้า", "รก",
               "불편", "비싼", "복잡", "느린"],
    "价格词": ["只要", "立减", "打折", "半价", "白菜价", "免费", "白送", "划算", "便宜",
               "cheap", "free", "discount", "deal", "save",
               "barato", "gratis", "descuento", "oferta",
               "rẻ", "miễn phí", "giảm giá", "安い", "無料", "お得",
               "ถูก", "ฟรี", "ลด", "저렴", "무료"],
    "场景词": ["在家", "出门", "开车", "通勤", "露营", "厨房", "办公室", "旅行", "洗澡", "阳台", "后备箱",
               "at home", "in the car", "office", "kitchen", "camping", "travel",
               "en casa", "cocina", "oficina", "viaje",
               "ở nhà", "trên xe", "nhà bếp", "văn phòng", "家で", "キッチン", "車で",
               "ที่บ้าน", "ในรถ", "ครัว", "집에서", "차에서"],
    "结果词": ["一秒", "瞬间", "立刻", "马上", "三分钟", "一分钟", "省一半", "翻倍",
               "instant", "immediately", "in seconds", "double",
               "al instante", "en segundos", "ngay", "tức thì", "すぐ", "一瞬", "ทันที", "즉시"],
    "动作词": ["装", "拆", "洗", "挂", "切", "握", "拧", "放", "倒", "贴", "拉",
               "install", "wash", "clean", "stack", "attach", "fold",
               "instalar", "lavar", "limpiar", "doblar",
               "lắp", "rửa", "gấp", "付ける", "洗う", "ติดตั้ง", "설치"],
    "情绪词": ["惊了", "绝了", "太香", "真香", "后悔", "离谱", "amazing", "wow", "unbelievable",
               "increíble", "tuyệt vời", "すごい", "สุดยอด", "대박"],
}

WORD_CATEGORY_LABELS = list(WORD_CATEGORIES)

CJK_STOPWORDS = ["我们", "你们", "他们", "她们", "这个", "那个", "什么", "怎么", "可以", "就是", "但是",
                 "因为", "所以", "已经", "还是", "没有", "一个", "这样", "那样", "时候", "现在", "知道",
                 "觉得", "真的", "不是", "有没有", "一定", "直接", "其实", "如果", "然后", "而且", "非常"]

LATIN_STOPWORDS = ["the", "and", "you", "your", "for", "this", "that", "with", "have", "from", "they",
                   "will", "just", "like", "what", "when", "only", "also", "very", "more", "than",
                   "there", "their", "about", "would", "could", "should", "these", "those", "them",
                   "because", "before", "after", "with", "into", "over", "yourself",
                   "porque", "para", "pero", "como", "cuando", "todo", "toda", "muy", "más", "mas",
                   "não", "nao", "você", "voce", "uma", "dos", "das", "com",
                   "của", "cho", "với", "người", "được", "trong", "những", "này", "không",
                   "します", "です", "ます", "the", "and"]

ASCII_WORD = re.compile(r"^[a-z][a-z ]*$")
MATCHER_CACHE = {}


def cue_matcher(cue):
    """给线索词 / 词典词做匹配器，返回正则或 None。

    纯 ASCII 的词必须按词边界匹配：不这么做的话 "dad" 会命中 enredado、"mom" 会命中
    momento，热词表会混进一堆假词。带重音符号的拉丁词、中日韩、泰文、越南文一律按子串
    匹配——这些语言靠附加符号区分词形，子串匹配才对（"chỉ" 不会误命中 "chị"）。
    """
    if cue in MATCHER_CACHE:
        return MATCHER_CACHE[cue]
    pattern = None
    if ASCII_WORD.match(cue):
        pattern = re.compile(r"(?<![a-z])" + re.escape(cue) + r"(?:s|es)?(?![a-z])")
    MATCHER_CACHE[cue] = pattern
    return pattern


def cue_in(cue, lower):
    """线索词是否出现在台词里（已是小写）。"""
    pattern = cue_matcher(cue)
    if pattern is None:
        return cue in lower
    return bool(pattern.search(lower))


REPRESENTATIVE_LIMIT = 3
CANDIDATE_WORD_LIMIT = 25


# ---------------------------------------------------------------- 读采样表
def load_samples(paths, sheet=1, header_row=1, mapping=None):
    """读采样表，返回 (rows, headers, columns, flags)。"""
    rows, flags = [], []
    columns, headers = {}, []
    for path in paths or []:
        try:
            headers, body = sheetio.read_table(path, sheet=sheet, header_row=header_row)
        except (OSError, ValueError) as error:
            flags.append(sheetio.flag("high", "sample_table_unreadable",
                                      f"{os.path.basename(path)} 读取失败：{error}", "确认文件格式与表头行号"))
            continue
        columns = sheetio.column_map(headers, SAMPLE_FIELDS, SAMPLE_ALIASES)
        if mapping:
            for index, header in enumerate(headers):
                target = mapping.get(sheetio.norm_key(header))
                if target:
                    columns[target] = index
        if "line" not in columns:
            flags.append(sheetio.flag("high", "sample_table_no_line_column",
                                      f"{os.path.basename(path)} 没有找到「前3秒台词」列",
                                      "用 --map 原列名=line 指定台词列"))
            continue
        for offset, raw in enumerate(body):
            def cell(field, row=raw):
                position = columns.get(field)
                return row[position] if position is not None and position < len(row) else ""

            rows.append({
                "source_file": os.path.basename(path),
                "source_row": header_row + 1 + offset,
                "platform": clean_text(cell("platform")),
                "site": clean_text(cell("site")).upper(),
                "language": clean_text(cell("language")),
                "category": clean_text(cell("category")),
                "line": clean_text(cell("line")),
                "views": to_number(cell("views")),
                "sales": to_number(cell("sales")),
                "likes": to_number(cell("likes")),
                "ref": clean_text(cell("ref")),
                "collected_at": clean_text(cell("collected_at")),
            })
    return rows, headers, columns, flags


def load_hooks(paths, sheet=1, header_row=1):
    """读钩子库，按钩子类型建索引，用来给套路排名补模板与首帧要求。"""
    index, flags = {}, []
    for path in paths or []:
        try:
            headers, body = sheetio.read_table(path, sheet=sheet, header_row=header_row)
        except (OSError, ValueError) as error:
            flags.append(sheetio.flag("high", "hook_table_unreadable",
                                      f"{os.path.basename(path)} 读取失败：{error}", "确认文件格式与表头行号"))
            continue
        found = sheetio.column_map(headers, ["hook_code", "hook_name", "desc", "first_frame",
                                             "line_template", "caption_template", "retention_note"])
        if "hook_name" not in found:
            flags.append(sheetio.flag("high", "hook_table_no_name_column",
                                      f"{os.path.basename(path)} 没有「钩子类型」列，无法与套路对上",
                                      "确认表头或改用 --map"))
            continue
        for raw in body:
            def cell(field, row=raw):
                position = found.get(field)
                return row[position] if position is not None and position < len(row) else ""

            name = clean_text(cell("hook_name"))
            if not name:
                continue
            index[name] = {
                "hook_code": clean_text(cell("hook_code")),
                "hook_name": name,
                "desc": clean_text(cell("desc")),
                "first_frame": clean_text(cell("first_frame")),
                "line_template": clean_text(cell("line_template")),
                "caption_template": clean_text(cell("caption_template")),
                "retention_note": clean_text(cell("retention_note")),
            }
    return index, flags


def load_products(paths, sheet=1, header_row=1):
    """读产品表：SKU、站点、人群、卖点、售价、币种。"""
    products = []
    for path in paths or []:
        try:
            headers, body = sheetio.read_table(path, sheet=sheet, header_row=header_row)
        except (OSError, ValueError):
            continue
        found = sheetio.column_map(headers, ["sku", "product_name", "site", "audience",
                                             "selling_points", "price", "currency"])
        if "sku" not in found:
            continue
        for raw in body:
            def cell(field, row=raw):
                position = found.get(field)
                return row[position] if position is not None and position < len(row) else ""

            sku = clean_text(cell("sku"))
            if not sku:
                continue
            products.append({
                "sku": sku,
                "product_name": clean_text(cell("product_name")),
                "site": clean_text(cell("site")).upper(),
                "audience": clean_text(cell("audience")),
                "selling_points": [clean_text(item) for item in re.split(r"[|/、]", clean_text(cell("selling_points"))) if clean_text(item)],
                "price": clean_text(cell("price")),
                "currency": clean_text(cell("currency")),
            })
    return products


# ---------------------------------------------------------------- 套路判定
def has_price_mark(line, lower):
    """价格锚点的结构线索：出现数字，且带货币符号或价格词。"""
    if not re.search(r"\d", line):
        return None
    for mark in CURRENCY_MARKS:
        if mark in lower:
            return mark
    for cue in pattern_by_code("H03")["cues"]:
        if cue_in(cue, lower):
            return cue
    return None


def pattern_by_code(code):
    """按钩子编码取套路定义；改了套路顺序也不会错位。"""
    for pattern in HOOK_PATTERNS:
        if pattern["code"] == code:
            return pattern
    raise KeyError(f"没有这个钩子编码：{code}")


def classify(line):
    """给一条台词判套路，返回 (主套路, 命中详情列表)。命中线索全部留痕，不猜。"""
    lower = line.lower()
    hits = []

    for pattern in HOOK_PATTERNS:
        matched = []
        if "question" in pattern["structural"]:
            for mark in QUESTION_MARKS:
                if mark in line:
                    matched.append(f"问句「{mark}」")
                    break
        if "price" in pattern["structural"]:
            mark = has_price_mark(line, lower)
            if mark:
                matched.append(f"价格线索「{mark}」")
        for cue in pattern["cues"]:
            if cue and cue_in(cue, lower):
                matched.append(f"词「{cue}」")
        if matched:
            hits.append({"pattern": pattern, "cues": matched[:4]})

    if not hits:
        return UNCLASSIFIED, []
    hits.sort(key=lambda item: (-item["pattern"]["priority"], item["pattern"]["name"]))
    return hits[0]["pattern"], hits


def extract_words(line):
    """返回这条台词命中的词典词（去重）。"""
    lower = line.lower()
    found = []
    for category, words in WORD_CATEGORIES.items():
        for word in words:
            if word and cue_in(word, lower):
                found.append((word, category))
    return found


IDEOGRAPH_PATTERN = re.compile(r"[\u4e00-\u9fff\uac00-\ud7af]")


def cjk_fragments(line):
    """抽 CJK 连续片段里的 2-3 字子串，作为候选热词（机器抽取，需人工确认）。

    纯假名碎片一律丢掉：日语里 って / ません / いま 这类是语法成分不是卖点词，
    留进热词表只会干扰判断。含汉字或韩文音节的才留下。
    """
    fragments = set()
    for chunk in re.findall(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]{2,}", line):
        for size in (2, 3):
            for index in range(len(chunk) - size + 1):
                fragment = chunk[index:index + size]
                if not IDEOGRAPH_PATTERN.search(fragment):
                    continue
                fragments.add(fragment)
    return fragments


def latin_fragments(line):
    """抽拉丁字母词（≥4 字母），过滤功能词，作为候选热词。"""
    words = set()
    for word in re.findall(r"[a-zà-ÿ]{4,}", line.lower()):
        if word not in LATIN_STOPWORDS:
            words.add(word)
    return words


# ---------------------------------------------------------------- 统计
def build_word_table(rows):
    """热词表：词典命中与候选片段分两类标，互不混淆。"""
    dictionary = {}
    fragments = {}

    for row in rows:
        line = row["line"]
        seen_here = set()
        for word, category in extract_words(line):
            key = (word, category)
            entry = dictionary.setdefault(key, {"count": 0, "samples": [], "sample_set": set()})
            entry["count"] += 1
            entry["sample_set"].add(row["source_row"])
            if len(entry["samples"]) < 2:
                entry["samples"].append(line)
            seen_here.add(word.lower())

        for fragment in (cjk_fragments(line) | latin_fragments(line)):
            if fragment.lower() in seen_here:
                continue
            entry = fragments.setdefault(fragment, {"count": 0, "samples": [], "sample_set": set(),
                                                    "category": "候选片段"})
            entry["count"] += 1
            entry["sample_set"].add(row["source_row"])
            if len(entry["samples"]) < 2:
                entry["samples"].append(line)

    items = []
    for (word, category), entry in dictionary.items():
        items.append({
            "word": word, "category": category, "count": entry["count"],
            "lines": len(entry["sample_set"]), "kind": "词典命中",
            "sample": entry["samples"][0] if entry["samples"] else "",
        })

    # 候选片段只留跨作品重复出现的，且去掉被抓到更长片段包含的短片段，压掉噪声
    repeated = {word: entry for word, entry in fragments.items() if len(entry["sample_set"]) >= 2}
    kept = {}
    for word in sorted(repeated, key=lambda item: (-repeated[item]["count"], -len(item))):
        if any(word != other and word in other and repeated[other]["count"] >= repeated[word]["count"]
               for other in kept):
            continue
        kept[word] = repeated[word]
    for word, entry in sorted(kept.items(), key=lambda item: (-item[1]["count"], item[0]))[:CANDIDATE_WORD_LIMIT]:
        items.append({
            "word": word, "category": "候选片段", "count": entry["count"],
            "lines": len(entry["sample_set"]), "kind": "候选片段（机器抽取，需人工确认）",
            "sample": entry["samples"][0] if entry["samples"] else "",
        })

    items.sort(key=lambda item: (item["kind"] != "词典命中", -item["lines"], -item["count"], item["word"]))
    return items


def build_rank_table(rows):
    """套路排行：本周期每个套路被多少条爆款用到，带表现数据的算平均。"""
    buckets = {}
    for row in rows:
        pattern = row["pattern"]
        if not pattern["code"]:
            continue
        bucket = buckets.setdefault(pattern["code"], {
            "pattern": pattern, "rows": [], "cues": {},
        })
        bucket["rows"].append(row)
        for hit in row["hits"]:
            if hit["pattern"]["code"] != pattern["code"]:
                continue
            for cue in hit["cues"][:1]:
                bucket["cues"][cue] = bucket["cues"].get(cue, 0) + 1

    total = sum(len(bucket["rows"]) for bucket in buckets.values()) or 1
    items = []
    for bucket in buckets.values():
        group = bucket["rows"]
        views = [row["views"] for row in group if row["views"] is not None]
        sales = [row["sales"] for row in group if row["sales"] is not None]
        top_cues = sorted(bucket["cues"].items(), key=lambda item: (-item[1], item[0]))[:3]
        items.append({
            "pattern": bucket["pattern"],
            "count": len(group),
            "share": round(len(group) / total, 4),
            "avg_views": round(sum(views) / len(views), 1) if views else None,
            "avg_sales": round(sum(sales) / len(sales), 1) if sales else None,
            "representatives": [row["line"] for row in group[:REPRESENTATIVE_LIMIT]],
            "cues": "；".join(f"{cue}×{count}" for cue, count in top_cues),
            "lines": group,
        })
    items.sort(key=lambda item: (-item["count"], item["pattern"]["code"]))
    return items


def build_candidates(rank_items, hooks_index, products, top, pain_by_site=None, site=None):
    """把排在前面的套路 × 产品，渲染成可直接追加进钩子库的候选行。"""
    candidates = []
    pain_by_site = pain_by_site or {}
    chosen = rank_items[:max(0, top)]
    for item in chosen:
        pattern = item["pattern"]
        library = hooks_index.get(pattern["name"], {})
        for product in products:
            if site and product["site"] and product["site"] != site.upper():
                continue
            point = product["selling_points"][0] if product["selling_points"] else ""
            site_words = pain_by_site.get(product["site"], [])
            pain = site_words[0][0] if site_words else ""
            uses_pain = "{pain}" in (library.get("line_template") or "") + (library.get("caption_template") or "")
            note = (f"；pain 取自 {product['site']} 同期采样热词"
                    if pain and product["site"] and uses_pain else "")
            mapping = {
                "audience": product["audience"],
                "pain": pain,
                "selling_point": point,
                "price": product["price"],
                "market": product["site"],
                "currency": product["currency"],
                "product": product["product_name"] or product["sku"],
            }
            line_text = render_template(library.get("line_template") or "", mapping)
            caption_text = render_template(library.get("caption_template") or "", mapping)
            candidates.append({
                "hook_code": library.get("hook_code") or pattern["code"],
                "hook_name": library.get("hook_name") or pattern["name"],
                "desc": library.get("desc") or pattern["why"],
                "first_frame": library.get("first_frame") or "{{待填:首帧要求}}",
                "line_template": line_text,
                "caption_template": caption_text,
                "retention_note": library.get("retention_note") or "{{待填:留存说明}}",
                "evidence": f"本周期采样里 {item['count']} 条用到" + note,
                "representative": item["representatives"][0] if item["representatives"] else "",
                "target": f"{product['sku']}｜{product['site'] or '—'}",
                "market_words": "、".join(word for word, _ in site_words[:5]),
                "pending": pending_fields(line_text + caption_text),
            })
    return candidates


def site_pain_words(rows):
    """按站点归纳采样里出现过的痛点词，返回 {站点: [(词, 次数), ...]}。

    必须按站点收敛：西语采样里提炼的痛点词填到越南语产品的口播里，是语言混用，
    比留空更糟。归纳不出来的站点就老实留 {{待填:pain}}。
    """
    buckets = {}
    for row in rows:
        site = row["site"]
        if not site:
            continue
        counts = buckets.setdefault(site, {})
        for word, category in extract_words(row["line"]):
            if category == "痛点词":
                counts[word] = counts.get(word, 0) + 1
    return {site: sorted(counts.items(), key=lambda item: (-item[1], item[0])) for site, counts in buckets.items()}


TEMPLATE_PATTERN = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")
PLACEHOLDER_PATTERN = re.compile(r"\{\{待填:[^}]*\}\}")


def render_template(template, mapping):
    """填模板变量；填不出来的保留成 {{待填:变量}}，不替用户编造。"""
    if not template:
        return ""

    def replace(match):
        key = match.group(1)
        value = mapping.get(key)
        return value if value else "{{待填:%s}}" % key

    return TEMPLATE_PATTERN.sub(replace, template)


def pending_fields(text):
    names = []
    for item in PLACEHOLDER_PATTERN.findall(text or ""):
        name = item[len("{{待填:"):-2]
        if name not in names:
            names.append(name)
    return "、".join(names)


# ---------------------------------------------------------------- 主流程
def analyze(rows, hooks_index, products, top, site=None):
    detail, issues = [], []
    for index, row in enumerate(rows, 1):
        line = row["line"]
        if not line:
            issues.append({"row_no": row["source_row"], "kind": "缺少台词",
                           "detail": "这一行没有前 3 秒台词，无法归类",
                           "line": "", "action": "补齐台词后重新采样，或删掉这行"})
            continue
        pattern, hits = classify(line)
        row = dict(row)
        row["pattern"] = pattern
        row["hits"] = hits
        others = [hit["pattern"]["name"] for hit in hits if hit["pattern"]["code"] != pattern["code"]]
        row["others"] = others
        row["cues"] = "；".join(cue for hit in hits[:2] for cue in hit["cues"][:2])
        detail.append(row)
        if not pattern["code"]:
            issues.append({
                "row_no": row["source_row"], "kind": "未归类",
                "detail": "这条台词没命中任何可解释线索，无法判定套路",
                "line": line, "action": "人工看一眼归到哪个套路，或补进 HOOK_PATTERNS 的线索词",
            })

    words = build_word_table(detail)
    rank = build_rank_table(detail)
    candidates = build_candidates(rank, hooks_index, products, top,
                                  pain_by_site=site_pain_words(detail), site=site)
    stats = {
        "samples": len(rows),
        "classified": len(detail) - len([item for item in issues if item["kind"] == "未归类"]),
        "unclassified": len([item for item in issues if item["kind"] == "未归类"]),
        "missing_line": len([item for item in issues if item["kind"] == "缺少台词"]),
        "words": len(words),
        "dictionary_words": len([item for item in words if item["kind"] == "词典命中"]),
        "candidate_fragments": len([item for item in words if item["kind"] != "词典命中"]),
        "patterns": len(rank),
        "candidates": len(candidates),
        "sites": sorted({row["site"] for row in detail if row["site"]}),
        "platforms": sorted({row["platform"] for row in detail if row["platform"]}),
        "categories": sorted({row["category"] for row in detail if row["category"]}),
    }
    return detail, words, rank, candidates, issues, stats


def build_flags(stats, issues, total_samples):
    flags = []
    if stats["unclassified"]:
        level = "high" if stats["unclassified"] / max(total_samples, 1) > 0.3 else "medium"
        flags.append(sheetio.flag(
            level, "unclassified_lines",
            f"{stats['unclassified']} 条台词没归到套路（占 {stats['unclassified'] / max(total_samples, 1):.0%}），没有硬判成某个套路",
            "人工归类，或把这些台词里的特征词补进脚本的线索表"))
    if stats["missing_line"]:
        flags.append(sheetio.flag("medium", "missing_line",
                                  f"{stats['missing_line']} 行没有前 3 秒台词", "补齐后重跑，否则这部分爆款没进入统计"))
    if total_samples and total_samples < 20:
        flags.append(sheetio.flag("medium", "small_sample",
                                  f"本次只采到 {total_samples} 条台词，套路占比还不稳",
                                  "再补一批同平台同周期的爆款，样本到 30 条以上再定主推套路"))
    if stats["patterns"] and stats["patterns"] < 3:
        flags.append(sheetio.flag("medium", "few_patterns",
                                  f"只用到 {stats['patterns']} 个套路，说明采样面偏窄或确实集中",
                                  "确认采样里是否只看了同一类账号；套路集中时优先做差异化版本"))
    if not stats["dictionary_words"]:
        flags.append(sheetio.flag("medium", "no_dictionary_words",
                                  "没有命中内置词典热词，热词表里只有机器抽取的候选片段",
                                  "候选片段需要人工确认后再用，或按市场补充词典"))
    return flags


def thousands(value):
    """报告里给人的数字带千分位，163500.0 写成 163,500。"""
    if value is None:
        return "—"
    text = ("%.2f" % value).rstrip("0").rstrip(".")
    whole, _, decimal = text.partition(".")
    groups = []
    while len(whole) > 3:
        groups.insert(0, whole[-3:])
        whole = whole[:-3]
    groups.insert(0, whole)
    return ",".join(groups) + (("." + decimal) if decimal else "")


def render_markdown(stats, words, rank, candidates, issues, args):
    lines = []
    lines.append("# 周期热词与黄金三秒套路（采样 %d 条）" % stats["samples"])
    lines.append("")
    lines.append("采样范围：平台 %s；站点 %s；类目 %s。" % (
        "、".join(stats["platforms"]) or "—",
        "、".join(stats["sites"]) or "—",
        "、".join(stats["categories"]) or "—"))
    lines.append("归类结果：%d 条判出套路，%d 条未归类，%d 行缺台词。" % (
        stats["classified"], stats["unclassified"], stats["missing_line"]))
    lines.append("")
    lines.append("## 本周期先抄哪个套路")
    lines.append("")
    for index, item in enumerate(rank, 1):
        pattern = item["pattern"]
        performance = []
        if item["avg_views"] is not None:
            performance.append("平均播放 %s" % thousands(item["avg_views"]))
        if item["avg_sales"] is not None:
            performance.append("平均销量 %s" % thousands(item["avg_sales"]))
        lines.append("%d. **%s（%s）**：%d 条用到，占 %.0f%%%s。%s" % (
            index, pattern["name"], pattern["code"], item["count"], item["share"] * 100,
            ("，%s" % "，".join(performance)) if performance else "",
            pattern["why"]))
        for representative in item["representatives"]:
            lines.append("   - 代表台词：%s" % representative)
        if item["cues"]:
            lines.append("   - 典型线索：%s" % item["cues"])
    lines.append("")
    lines.append("## 本周期热词")
    lines.append("")
    lines.append("词典命中（类别明确，可直接进脚本）：")
    for item in [item for item in words if item["kind"] == "词典命中"][:15]:
        lines.append("- %s（%s）：%d 条用到" % (item["word"], item["category"], item["lines"]))
    fragments = [item for item in words if item["kind"] != "词典命中"]
    if fragments:
        lines.append("")
        lines.append("候选片段（机器抽取，需人工确认后再用）：")
        for item in fragments[:15]:
            lines.append("- %s：%d 条用到｜示例：%s" % (item["word"], item["lines"], item["sample"][:40]))
    lines.append("")
    lines.append("## 钩子候选（可直接追加进钩子库）")
    lines.append("")
    if not candidates:
        lines.append("没有产出候选：要么没采到台词，要么没给 --products。")
    for item in candidates:
        lines.append("- **%s %s → %s**（%s）" % (item["hook_code"], item["hook_name"], item["target"], item["evidence"]))
        lines.append("   - 口播：%s" % item["line_template"])
        lines.append("   - 字幕：%s" % item["caption_template"])
        if item["market_words"]:
            lines.append("   - 该市场本周期热词：%s" % item["market_words"])
        if item["pending"]:
            lines.append("   - 待补变量：%s —— 补齐后才进生成队列" % item["pending"])
    lines.append("")
    lines.append("## 需要人工处理")
    lines.append("")
    if not issues:
        lines.append("没有。")
    for issue in issues[:20]:
        lines.append("- 第 %s 行（%s）：%s｜%s" % (issue["row_no"], issue["kind"], issue["detail"][:40], issue["action"]))
    lines.append("")
    lines.append("## 边界")
    lines.append("")
    lines.append("- 采样台词来自别人的素材，**只用来提炼套路与用词**：不照抄原句、不搬画面、不盗 BGM。")
    lines.append("- 套路占比只说明「这个周期大家怎么开场」，不代表必然有效；真正该上哪条，还是要 A/B 测出来。")
    lines.append("- 机器抽取的候选片段只是线索，用之前人工确认一遍。")
    lines.append("- 钩子候选里的 {pain} 用的是**该市场同期采样里的原词**（不是翻译过来的），"
                 "本地化时直接沿用这个词最贴当地说法；没采到的市场留 {{待填}} 不硬填。")
    lines.append("- 口播与字幕模板沿用钩子库的工作语言，进生成队列前要按目标语种重写，不是直译。")
    lines.append("")
    return "\n".join(lines)


def build_data(stats, rank, words, candidates):
    return {
        "samples": stats["samples"],
        "classified": stats["classified"],
        "unclassified": stats["unclassified"],
        "dictionary_words": stats["dictionary_words"],
        "candidate_fragments": stats["candidate_fragments"],
        "patterns": stats["patterns"],
        "candidates": stats["candidates"],
        "sites": stats["sites"],
        "platforms": stats["platforms"],
        "top_patterns": [
            {"hook_code": item["pattern"]["code"], "hook_name": item["pattern"]["name"],
             "count": item["count"], "share": item["share"],
             "avg_views": item["avg_views"], "avg_sales": item["avg_sales"],
             "representatives": item["representatives"]}
            for item in rank[:6]
        ],
        "top_words": [
            {"word": item["word"], "category": item["category"], "lines": item["lines"], "kind": item["kind"]}
            for item in words[:20]
        ],
        "hook_candidates": [
            {"hook_code": item["hook_code"], "hook_name": item["hook_name"], "target": item["target"],
             "line_template": item["line_template"], "caption_template": item["caption_template"],
             "evidence": item["evidence"], "representative": item["representative"],
             "market_words": item["market_words"], "pending": item["pending"]}
            for item in candidates
        ],
    }


def write_outputs(args, detail, words, rank, candidates, issues):
    if args.out:
        rows = [[index, row["platform"], row["site"], row["language"], row["category"], row["line"],
                 row["pattern"]["name"] or "未归类", row["pattern"]["code"] or "—", row["cues"],
                 "、".join(row["others"]), row["views"], row["sales"], row["likes"], row["ref"],
                 row["collected_at"]] for index, row in enumerate(detail, 1)]
        sheetio.write_csv(args.out, DETAIL_HEADERS, rows)
    if args.quarantine:
        sheetio.write_csv(args.quarantine, ISSUE_HEADERS,
                          [[item["row_no"], item["kind"], item["detail"], item["line"], item["action"]]
                           for item in issues])
    if args.out_xlsx:
        word_rows = [[item["word"], item["category"], item["count"], item["lines"], item["kind"], item["sample"]]
                     for item in words]
        rank_rows = [[index, item["pattern"]["code"], item["pattern"]["name"], item["count"],
                      "%.1f%%" % (item["share"] * 100), item["avg_views"], item["avg_sales"],
                      " ｜ ".join(item["representatives"]), item["cues"], item["pattern"]["why"]]
                     for index, item in enumerate(rank, 1)]
        detail_rows = [[index, row["platform"], row["site"], row["language"], row["category"], row["line"],
                        row["pattern"]["name"] or "未归类", row["pattern"]["code"] or "—", row["cues"],
                        "、".join(row["others"]), row["views"], row["sales"], row["likes"], row["ref"],
                        row["collected_at"]] for index, row in enumerate(detail, 1)]
        candidate_rows = [[item["hook_code"], item["hook_name"], item["desc"], item["first_frame"],
                           item["line_template"], item["caption_template"], item["retention_note"],
                           item["evidence"], item["representative"], item["target"],
                           item["market_words"], item["pending"]]
                          for item in candidates]
        sheetio.write_xlsx(args.out_xlsx, [
            {"name": "套路排行", "headers": RANK_HEADERS, "rows": rank_rows, "coerce_numbers": True},
            {"name": "热词表", "headers": WORD_HEADERS, "rows": word_rows},
            {"name": "台词归类", "headers": DETAIL_HEADERS, "rows": detail_rows, "coerce_numbers": True},
            {"name": "钩子候选", "headers": CANDIDATE_HEADERS, "rows": candidate_rows},
        ])


def parse_map(items):
    return sheetio.apply_mapping(items or [])


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="周期热词与黄金三秒套路挖掘：采样爆款前 3 秒台词 → 套路归类 → 热词统计 → 钩子候选")
    parser.add_argument("input", nargs="+", help="采样表：.csv/.xlsx，字段见脚本头部说明")
    parser.add_argument("--hooks", action="append", default=[], metavar="钩子库",
                        help="钩子模板库（可多次传），用来给套路补首帧要求与口播/字幕模板")
    parser.add_argument("--products", action="append", default=[], metavar="产品表",
                        help="产品表（可多次传），用来把套路渲染成具体产品的钩子候选")
    parser.add_argument("--top", type=int, default=3, help="取排前几的套路生成钩子候选，默认 3")
    parser.add_argument("--site", default="", help="只对某个站点生成钩子候选，例如 MX")
    parser.add_argument("--sheet", default=1, help="工作表名或序号，默认第 1 个")
    parser.add_argument("--header-row", type=int, default=1, help="表头行号，默认 1")
    parser.add_argument("--map", action="append", default=[], metavar="原列名=标准字段",
                        help="手动指定列映射，例如 开场白=line")
    parser.add_argument("--out", default="", help="台词归类明细 CSV")
    parser.add_argument("--out-xlsx", default="", help="Excel 工作簿：套路排行 / 热词表 / 台词归类 / 钩子候选")
    parser.add_argument("--out-md", default="", help="Markdown 报告")
    parser.add_argument("--out-json", default="", help="JSON 输出信封")
    parser.add_argument("--quarantine", default="", help="问题清单 CSV（未归类、缺台词的行）")
    args = parser.parse_args(argv)

    sheet = args.sheet if args.sheet in (None, "") or not str(args.sheet).isdigit() else int(args.sheet)
    mapping = parse_map(args.map)

    rows, headers, columns, flags = load_samples(args.input, sheet=sheet, header_row=args.header_row,
                                                 mapping=mapping)
    if not rows:
        flags.append(sheetio.flag("high", "no_samples",
                                  "一条采样台词都没读到，无法统计",
                                  "确认采样表里的台词列名，或用 --map 原列名=line 指定"))
        envelope = sheetio.make_envelope("hot_hooks", "blocked", 0.2,
                                         {"samples": 0}, flags,
                                         assumptions=["采样表需含「前3秒台词」列"])
        sheetio.emit(envelope, out_json=args.out_json)
        return 1

    hooks_index, hook_flags = load_hooks(args.hooks, sheet=sheet, header_row=args.header_row)
    flags.extend(hook_flags)
    products = load_products(args.products, sheet=sheet, header_row=args.header_row)

    detail, words, rank, candidates, issues, stats = analyze(
        rows, hooks_index, products, args.top, site=args.site)

    flags.extend(build_flags(stats, issues, len(rows)))
    if args.top and not products:
        flags.append(sheetio.flag("medium", "no_products",
                                  "没给 --products，只出套路与热词，没生成具体产品的钩子候选",
                                  "补 --products 产品表，候选才落到具体 SKU"))
    if hooks_index and all(item["pattern"]["name"] not in hooks_index for item in rank):
        flags.append(sheetio.flag("medium", "hook_name_mismatch",
                                  "采样判出的套路名与钩子库里的钩子类型对不上，候选用了默认模板",
                                  "把钩子库的钩子类型改成与套路同名，或补一份映射"))

    write_outputs(args, detail, words, rank, candidates, issues)
    if args.out_md:
        with open(args.out_md, "w", encoding="utf-8") as handle:
            handle.write(render_markdown(stats, words, rank, candidates, issues, args) + "\n")

    status = "ok" if not [item for item in flags if item["level"] == "high"] else "partial"
    confidence = 0.95
    if any(item["level"] == "high" for item in flags):
        confidence = 0.65
    elif any(item["level"] == "medium" for item in flags):
        confidence = 0.8
    sources = [{"ref": os.path.basename(path), "as_of": ""} for path in args.input]
    assumptions = [
        "采样数据来自平台榜单或竞品素材的人工采集，覆盖率与口径以采集时的记录为准",
        "套路归类按脚本内的线索词与优先级判定，未命中的一律计入未归类交人工",
    ]
    envelope = sheetio.make_envelope("hot_hooks", status, confidence,
                                     build_data(stats, rank, words, candidates), flags,
                                     sources=sources, assumptions=assumptions)
    sheetio.emit(envelope, out_json=args.out_json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
