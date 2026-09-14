#!/usr/bin/env python3
"""阶段 4：多模态广告素材生产——分镜脚本、生成提示词与前三秒留存检查。

用法：
  python3 video_brief.py products.csv --styles market_styles.csv --hooks hook_patterns.csv \
    --banned banned_words.csv --duration 15 --ratio 9:16 --hooks-per-sku 2 \
    --out storyboard.csv --out-md brief.md --out-json brief.json

做的事：把「产品定义 + 投放市场」与市场风格库、钩子模板库做笛卡尔组合，产出
逐镜头的分镜脚本、可直接粘给视频模型（Seedance / Veo / 即梦等）的生成提示词，
并对每个素材跑一遍前三秒留存硬性检查。语种无关：西语、葡语、英语、越南语、
日语、泰语、韩语、印尼语、德语、阿拉伯语等走同一套流程，语速按目标语种的
计量单位折算，不写死某个市场。

产品表字段：sku、product_name、site（投放市场）、category、audience、selling_points、
proof、offer、price、currency、language（语种，可留空从风格库取）。
市场风格库字段：site、language、platforms、rhythm、visual_style、talent、scene、tone、
avoid、speech_rate（该市场语速上限，覆盖内置表）、source、as_of。
钩子模板库字段：hook_code、hook_name、desc、first_frame、line_template、caption_template、retention_note。
禁用词表字段：word、reason、scope、level。

只读输入，只写 --out/--out-json/--out-md/--quarantine 指定文件。
不编造地区风格——市场风格库里查不到的站点一律标 high flag，不套用别的市场习惯；
文案里需要创意填空的位置写成 {{待填:字段}} 显式暴露，不猜。
语速上限是广告口播的经验值（比自然语速慢约 10–20%），可用 --speech-rate 或风格库
的「语速上限」列覆盖，最终以目标语种实际配音试听为准。
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
                "tone", "avoid", "speech_rate", "source", "as_of"]
HOOK_FIELDS = ["hook_code", "hook_name", "desc", "first_frame", "line_template",
               "caption_template", "retention_note"]
BANNED_FIELDS = ["word", "reason", "scope", "level"]

EXPORT_HEADERS = ["asset_name", "sku", "product_name", "site", "language", "ratio", "duration_s",
                  "hook_code", "hook_name", "shot_index", "timecode", "shot_seconds", "shot_type",
                  "visual_prompt", "caption", "voiceover", "retention_note", "localize_to",
                  "speech_budget", "placeholders", "note"]

# 分镜骨架：每种成片时长一套，第一镜固定 3 秒（前三秒法则）
SHOT_TEMPLATES = {
    15: [("钩子", 3), ("痛点场景", 4), ("产品演示", 4), ("证明", 2), ("CTA", 2)],
    21: [("钩子", 3), ("痛点场景", 5), ("产品演示", 6), ("证明", 4), ("CTA", 3)],
    30: [("钩子", 3), ("痛点场景", 7), ("产品演示", 8), ("证明", 7), ("CTA", 5)],
}

# 语种代码归一：兼容 BCP-47 变体（vi-VN、ja-JP）、中文名与常见写法
LANGUAGE_ALIASES = {
    "zh": ["zh", "cn", "chs", "zhcn", "zhhans", "zhhant", "zt", "中文", "简体", "简体中文", "繁体",
           "繁体中文", "chinese", "mandarin", "普通话", "华语"],
    "en": ["en", "eng", "english", "英语", "英文", "enus", "engb", "enau", "engg"],
    "es": ["es", "spa", "esp", "spanish", "西班牙语", "西语", "esmx", "esar", "esco", "escl", "espe"],
    "pt": ["pt", "por", "portuguese", "葡萄牙语", "葡语", "ptbr", "ptpt"],
    "vi": ["vi", "vn", "vie", "vietnamese", "越南语", "越语", "vivn"],
    "ja": ["ja", "jp", "jpn", "japanese", "日语", "日文", "jajp"],
    "ko": ["ko", "kr", "kor", "korean", "韩语", "韩文", "朝鲜语", "kokr"],
    "th": ["th", "tha", "thai", "泰语", "泰文", "thth"],
    "id": ["id", "ind", "indonesian", "印尼语", "印度尼西亚语", "idid", "bahasa"],
    "ms": ["ms", "msa", "malay", "马来语", "马来西亚语"],
    "tl": ["tl", "fil", "filipino", "tagalog", "菲律宾语", "他加禄语"],
    "km": ["km", "khm", "khmer", "柬埔寨语", "高棉语"],
    "lo": ["lo", "lao", "老挝语", "寮语"],
    "my": ["my", "mya", "burmese", "缅甸语"],
    "hi": ["hi", "hin", "hindi", "印地语", "北印度语"],
    "bn": ["bn", "ben", "bengali", "孟加拉语"],
    "ta": ["ta", "tam", "tamil", "泰米尔语"],
    "ur": ["ur", "urd", "urdu", "乌尔都语"],
    "ar": ["ar", "ara", "arabic", "阿拉伯语", "阿语", "arsa", "arae"],
    "he": ["he", "iw", "heb", "hebrew", "希伯来语"],
    "fa": ["fa", "per", "persian", "farsi", "波斯语"],
    "tr": ["tr", "tur", "turkish", "土耳其语"],
    "ru": ["ru", "rus", "russian", "俄语", "ruRU"],
    "uk": ["uk", "ukr", "ukrainian", "乌克兰语"],
    "de": ["de", "deu", "ger", "german", "德语", "dede", "deat"],
    "fr": ["fr", "fra", "fre", "french", "法语", "frfr", "frca"],
    "it": ["it", "ita", "italian", "意大利语"],
    "nl": ["nl", "nld", "dut", "dutch", "荷兰语"],
    "pl": ["pl", "pol", "polish", "波兰语"],
    "cs": ["cs", "ces", "czech", "捷克语"],
    "sk": ["sk", "slk", "slovak", "斯洛伐克语"],
    "hu": ["hu", "hun", "hungarian", "匈牙利语"],
    "ro": ["ro", "ron", "romanian", "罗马尼亚语"],
    "bg": ["bg", "bul", "bulgarian", "保加利亚语"],
    "el": ["el", "ell", "greek", "希腊语"],
    "sv": ["sv", "swe", "swedish", "瑞典语"],
    "da": ["da", "dan", "danish", "丹麦语"],
    "nb": ["nb", "no", "nor", "norwegian", "挪威语"],
    "fi": ["fi", "fin", "finnish", "芬兰语"],
    "hr": ["hr", "hrv", "croatian", "克罗地亚语"],
    "sr": ["sr", "srp", "serbian", "塞尔维亚语"],
    "lt": ["lt", "lit", "lithuanian", "立陶宛语"],
    "lv": ["lv", "lav", "latvian", "拉脱维亚语"],
    "et": ["et", "est", "estonian", "爱沙尼亚语"],
    "sl": ["sl", "slv", "slovenian", "斯洛文尼亚语"],
    "sw": ["sw", "swa", "swahili", "斯瓦希里语"],
    "az": ["az", "aze", "azerbaijani", "阿塞拜疆语"],
    "kk": ["kk", "kaz", "kazakh", "哈萨克语"],
    "uz": ["uz", "uzb", "uzbek", "乌兹别克语"],
    "ka": ["ka", "kat", "georgian", "格鲁吉亚语"],
    "hy": ["hy", "hye", "armenian", "亚美尼亚语"],
    "ne": ["ne", "nep", "nepali", "尼泊尔语"],
    "si": ["si", "sin", "sinhala", "僧伽罗语"],
}
# 补充写法，两类：
#   1. 原生语言写法——平台后台的语种下拉框、当地团队的反馈里最常见（「Tiếng Việt」「日本語」「ภาษาไทย」
#      「العربية」），按原样收录；多词写法同时收录连写形式，防止少了空格就认不出
#   2. 中文简称——团队口头与文档里常用的「X文」写法（越南文、阿拉伯文、俄文…）
LANGUAGE_EXTRA_ALIASES = {
    "zh": ["汉语", "國語", "国语"],
    "es": ["español", "espanol", "castellano", "西班牙文"],
    "pt": ["português", "portugues", "葡萄牙文"],
    "vi": ["tiếng việt", "tiếngviệt", "tieng viet", "tiengviet", "越南文"],
    "ja": ["日本語", "にほんご", "nihongo"],
    "ko": ["한국어", "한국말", "조선어"],
    "th": ["ภาษาไทย", "ไทย", "phasa thai"],
    "id": ["bahasa indonesia", "bahasaindonesia", "indonesia", "印尼文"],
    "ms": ["bahasa melayu", "bahasamelayu", "melayu", "马来文"],
    "tl": ["wikang filipino", "pilipino"],
    "km": ["ភាសាខ្មែរ", "ខ្មែរ", "高棉文", "柬埔寨文"],
    "lo": ["ພາສາລາວ", "ລາວ", "老挝文", "寮文"],
    "my": ["မြန်မာဘာသာ", "မြန်မာ", "缅甸文"],
    "hi": ["हिन्दी", "हिंदी", "印地文"],
    "bn": ["বাংলা", "孟加拉文"],
    "ta": ["தமிழ்", "泰米尔文"],
    "ur": ["اردو", "乌尔都文"],
    "ar": ["العربية", "عربي", "阿拉伯文"],
    "he": ["עברית", "希伯来文"],
    "fa": ["فارسی", "波斯文"],
    "tr": ["türkçe", "turkce", "土耳其文"],
    "ru": ["русский", "俄文"],
    "uk": ["українська", "乌克兰文"],
    "de": ["deutsch", "德文"],
    "fr": ["français", "francais", "法文"],
    "it": ["italiano", "意大利文"],
    "nl": ["nederlands", "荷兰文"],
    "pl": ["polski", "波兰文"],
    "cs": ["čeština", "cestina", "捷克文"],
    "sk": ["slovenčina", "slovencina", "斯洛伐克文"],
    "hu": ["magyar", "匈牙利文"],
    "ro": ["română", "romana", "罗马尼亚文"],
    "bg": ["български", "保加利亚文"],
    "el": ["ελληνικά", "ellinika", "希腊文"],
    "sv": ["svenska", "瑞典文"],
    "da": ["dansk", "丹麦文"],
    "nb": ["norsk", "挪威文"],
    "fi": ["suomi", "芬兰文"],
    "hr": ["hrvatski", "克罗地亚文"],
    "sr": ["српски", "塞尔维亚文"],
    "lt": ["lietuvių", "lietuviu", "立陶宛文"],
    "lv": ["latviešu", "latviesu", "拉脱维亚文"],
    "et": ["eesti", "爱沙尼亚文"],
    "sl": ["slovenščina", "slovenscina", "斯洛文尼亚文"],
    "sw": ["kiswahili", "斯瓦希里文"],
    "az": ["azərbaycan", "azerbaijan", "阿塞拜疆文"],
    "kk": ["қазақша", "哈萨克文"],
    "uz": ["oʻzbek", "ozbek", "乌兹别克文"],
    "ka": ["ქართული", "格鲁吉亚文"],
    "hy": ["հայերեն", "亚美尼亚文"],
    "ne": ["नेपाली", "尼泊尔文"],
    "si": ["සිංහල", "僧伽罗文"],
}
LANGUAGE_INDEX = {alias.lower(): code
                  for code, names in LANGUAGE_ALIASES.items()
                  for alias in names + LANGUAGE_EXTRA_ALIASES.get(code, [])}

# 语种中文名（用于报告文案，查不到就直接用代码）
LANGUAGE_NAMES = {
    "zh": "中文", "en": "英语", "es": "西语", "pt": "葡语", "vi": "越南语", "ja": "日语",
    "ko": "韩语", "th": "泰语", "id": "印尼语", "ms": "马来语", "tl": "菲律宾语", "km": "高棉语",
    "lo": "老挝语", "my": "缅甸语", "hi": "印地语", "bn": "孟加拉语", "ta": "泰米尔语",
    "ur": "乌尔都语", "ar": "阿拉伯语", "he": "希伯来语", "fa": "波斯语", "tr": "土耳其语",
    "ru": "俄语", "uk": "乌克兰语", "de": "德语", "fr": "法语", "it": "意大利语", "nl": "荷兰语",
    "pl": "波兰语", "cs": "捷克语", "sk": "斯洛伐克语", "hu": "匈牙利语", "ro": "罗马尼亚语",
    "bg": "保加利亚语", "el": "希腊语", "sv": "瑞典语", "da": "丹麦语", "nb": "挪威语",
    "fi": "芬兰语", "hr": "克罗地亚语", "sr": "塞尔维亚语", "lt": "立陶宛语", "lv": "拉脱维亚语",
    "et": "爱沙尼亚语", "sl": "斯洛文尼亚语", "sw": "斯瓦希里语", "az": "阿塞拜疆语",
    "kk": "哈萨克语", "uz": "乌兹别克语", "ka": "格鲁吉亚语", "hy": "亚美尼亚语",
    "ne": "尼泊尔语", "si": "僧伽罗语",
}

# 语种 → (计量单位, 广告口播每秒上限)
# 单位 char＝按字符计（中文/日文/韩文/泰文/高棉文/老挝文/缅甸文等不用空格分词的语言）；
#      word＝按空格分词计（英语/西语/葡语/越南语/印尼语/阿拉伯语等）。
# 数值是**广告口播的经验上限**（比日常自然语速慢约 10–20%），随语种、主播、品类、平台浮动，
# 属可调配置：命令行 --speech-rate 优先级最高，其次市场风格库的「语速上限」列，最后才是这张表。
# 最终以目标语种实际配音试听为准，不要把它当成语言学结论。
LANGUAGE_SPEECH = {
    "zh": ("char", 4.5), "ja": ("char", 5.5), "ko": ("char", 5.0), "th": ("char", 4.5),
    "km": ("char", 4.0), "lo": ("char", 4.0), "my": ("char", 3.5),
    "en": ("word", 2.6), "es": ("word", 3.0), "pt": ("word", 2.8), "vi": ("word", 3.5),
    "id": ("word", 2.8), "ms": ("word", 2.8), "tl": ("word", 2.8),
    "fr": ("word", 2.8), "it": ("word", 2.9), "de": ("word", 2.4), "nl": ("word", 2.6),
    "pl": ("word", 2.4), "cs": ("word", 2.4), "sk": ("word", 2.4), "hu": ("word", 2.4),
    "ro": ("word", 2.5), "bg": ("word", 2.5), "hr": ("word", 2.4), "sr": ("word", 2.4),
    "sl": ("word", 2.4), "lt": ("word", 2.3), "lv": ("word", 2.3), "et": ("word", 2.2),
    "sv": ("word", 2.6), "da": ("word", 2.6), "nb": ("word", 2.6), "fi": ("word", 2.2),
    "ru": ("word", 2.2), "uk": ("word", 2.2), "tr": ("word", 2.2), "el": ("word", 2.3),
    "ar": ("word", 2.4), "he": ("word", 2.4), "fa": ("word", 2.4), "ur": ("word", 2.4),
    "hi": ("word", 2.6), "bn": ("word", 2.4), "ta": ("word", 2.4), "ne": ("word", 2.4),
    "si": ("word", 2.2), "sw": ("word", 2.4), "az": ("word", 2.3), "kk": ("word", 2.2),
    "uz": ("word", 2.4), "ka": ("word", 2.4), "hy": ("word", 2.4),
}
FALLBACK_SPEECH = ("word", 2.6)
UNIT_LABELS = {"char": "字符", "word": "词"}

# 目标语种 → 该语种正文必然出现的书写系统，用来判断文案是否已经本地化
NON_LATIN_TARGETS = {
    "zh": "han", "ja": "kana", "ko": "hangul", "th": "thai", "km": "khmer", "lo": "lao",
    "my": "myanmar", "ar": "arabic", "he": "hebrew", "fa": "arabic", "ur": "arabic",
    "hi": "devanagari", "bn": "bengali", "ta": "tamil", "ne": "devanagari", "si": "sinhala",
    "ru": "cyrillic", "uk": "cyrillic", "bg": "cyrillic", "el": "greek",
}
SCRIPT_RANGES = {
    "han": [(0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xF900, 0xFAFF)],
    "kana": [(0x3040, 0x30FF), (0x31F0, 0x31FF)],
    "hangul": [(0x1100, 0x11FF), (0x3130, 0x318F), (0xAC00, 0xD7AF)],
    "thai": [(0x0E00, 0x0E7F)], "lao": [(0x0E80, 0x0EFF)],
    "khmer": [(0x1780, 0x17FF)], "myanmar": [(0x1000, 0x109F)],
    "arabic": [(0x0600, 0x06FF), (0x0750, 0x077F), (0xFB50, 0xFDFF), (0xFE70, 0xFEFF)],
    "hebrew": [(0x0590, 0x05FF)], "cyrillic": [(0x0400, 0x04FF)],
    "greek": [(0x0370, 0x03FF)], "devanagari": [(0x0900, 0x097F)],
    "bengali": [(0x0980, 0x09FF)], "tamil": [(0x0B80, 0x0BFF)],
    "sinhala": [(0x0D80, 0x0DFF)],
}

DEFAULT_WORKING_LANGUAGE = "zh"   # 钩子模板库与分镜文案的工作语言
PLACEHOLDER_WEIGHT = 2            # 口播长度测算时，每个 {{待填:}} 记作几个单位
CAPTION_CHAR_LIMIT = 20           # 前 3 秒字幕单行可容纳的全角字符数（经验值，--caption-limit 可调）

# 标点不参与口播长度计算
PUNCT_PATTERN = re.compile(r"[\s，。、；：！？…—～·「」『』（）【】《》〈〉“”‘’\"'.,;:!?()\[\]{}]")

# 前 3 秒禁止出现的开场方式（用户划走最快的位置就是这几类）
BANNED_OPENINGS = ["logo", "片头", "黑屏", "空镜", "慢镜头", "慢动作", "标题动画", "静态产品图", "白底图"]

# 检查项 -> (级别, 说明)
CHECKS = {
    "retention_first_frame": ("high", "前 3 秒首帧要求缺失或用了高划走率的开场方式"),
    "retention_caption": ("high", "前 3 秒没有可读字幕，静音刷到的用户看不懂"),
    "retention_speech": ("medium", "前 3 秒口播超出该语种语速上限，讲不完"),
    "retention_localization": ("low", "前 3 秒文案仍是工作语言草稿，按目标语种本地化后需复测时长"),
    "caption_too_long": ("medium", "前 3 秒字幕超过单行可显示长度，手机上会折行或被裁掉"),
    "language_conflict": ("medium", "产品表语种与市场风格库语种不一致，配音与字幕会做错语种"),
    "language_unrecognized": ("medium", "语种写得不认识，语速按保守默认值折算"),
    "language_missing": ("medium", "没写目标语种，无法判断本地化与语速基线"),
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
                "跟拍", "跟随", "跟着", "环绕", "摇镜", "推近", "拉远",
                "open", "pour", "cut", "drop", "grab", "walk", "run", "turn", "hold", "lift", "show",
                "test", "try", "spin", "snap", "peel", "click", "tap", "swap", "install", "unbox"]
TEMPLATE_PATTERN = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


def split_points(text):
    """把「；」「、」「|」等分隔的卖点拆开。"""
    return [piece for piece in re.split(r"[|｜;；、/]", clean_text(text)) if piece]


def normalize_language(value):
    """把语种写法归一到短代码：'ja-JP'/'日语'/'JP' → 'ja'；识别不了返回空串。"""
    raw = clean_text(value).lower()
    if not raw:
        return ""
    for candidate in (raw, raw.replace("-", "").replace("_", "").replace(" ", ""),
                      raw.split("-")[0].split("_")[0]):
        if candidate and candidate in LANGUAGE_INDEX:
            return LANGUAGE_INDEX[candidate]
    return ""


def language_label(code):
    return LANGUAGE_NAMES.get(code, code or "未指定")


def parse_rate_overrides(text):
    """解析 --speech-rate vi=3.5,ja=6 —— 返回 {语种代码: 每秒上限}。"""
    overrides = {}
    for piece in (text or "").replace("，", ",").split(","):
        piece = piece.strip()
        if "=" not in piece:
            continue
        key, _, value = piece.partition("=")
        number = to_number(value)
        code = normalize_language(key)
        if code and number is not None and number > 0:
            overrides[code] = float(number)
    return overrides


def speech_profile(language, overrides=None, market_rate=None):
    """返回 (语种代码, 计量单位, 每秒上限)。优先级：命令行 > 风格库语速列 > 内置表。"""
    code = normalize_language(language)
    unit, rate = LANGUAGE_SPEECH.get(code, FALLBACK_SPEECH)
    if market_rate:
        rate = float(market_rate)
    if code and code in (overrides or {}):
        rate = float(overrides[code])
    return code, unit, rate


def speech_cap(rate, seconds):
    """seconds 秒内能讲完的单位数上限。"""
    return max(1, int(rate * seconds))


def speech_units(text, unit):
    """按计量单位数口播长度；{{待填:}} 记作 PLACEHOLDER_WEIGHT 个单位（会被真实内容替换，不能当 0）。"""
    text = text or ""
    placeholders = len(PLACEHOLDER_PATTERN.findall(text))
    body = PLACEHOLDER_PATTERN.sub(" ", text)
    if unit == "char":
        counted = len(PUNCT_PATTERN.sub("", body))
    else:
        counted = len([word for word in re.split(r"\s+", PUNCT_PATTERN.sub(" ", body).strip()) if word])
    return counted + placeholders * PLACEHOLDER_WEIGHT


def script_of(text):
    """返回文案里出现的书写系统集合——只用来判断「换没换语种」，不判断语义。"""
    found = set()
    for char in text or "":
        point = ord(char)
        for script, ranges in SCRIPT_RANGES.items():
            if script in found:
                continue
            if any(low <= point <= high for low, high in ranges):
                found.add(script)
                break
    if re.search(r"[A-Za-z]", text or ""):
        found.add("latin")
    return found


def looks_localized(text, target_language):
    """文案看起来已经换成目标语种了吗？只看书写系统，判不了语义与用词是否地道。"""
    scripts = script_of(text)
    required = NON_LATIN_TARGETS.get(target_language or "")
    if required:
        return required in scripts
    return "latin" in scripts and "han" not in scripts


def caption_units(text):
    """字幕占几个全角字符位：全角算 1，半角算 0.5；{{待填:}} 不计（内容未定）。"""
    body = PLACEHOLDER_PATTERN.sub("", text or "")
    return round(sum(1.0 if ord(char) > 0x2E80 else 0.5
                     for char in body if not char.isspace()), 1)


def timecode(start, length):
    return f"{start // 60}:{start % 60:02d}–{(start + length) // 60}:{(start + length) % 60:02d}"


def render(template, mapping):
    """填充模板；取不到值的位置显式留成 {{待填:字段}}，不猜内容。"""
    def substitute(match):
        key = match.group(1)
        value = mapping.get(key)
        return str(value) if value not in (None, "") else "{{待填:" + key + "}}"

    return TEMPLATE_PATTERN.sub(substitute, clean_text(template))


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


def resolve_target_language(product_language, style_language):
    """定目标语种：产品表优先，取不到再落风格库；同时收集语言字段本身的问题。"""
    issues = []
    declared = normalize_language(product_language)
    from_style = normalize_language(style_language)
    if product_language and not declared:
        issues.append(("language_unrecognized", f"产品表语种「{product_language}」不在已知语种表里"))
    if style_language and not from_style:
        issues.append(("language_unrecognized", f"风格库语种「{style_language}」不在已知语种表里"))
    if declared and from_style and declared != from_style:
        issues.append(("language_conflict",
                       f"产品表写 {declared}（{language_label(declared)}），"
                       f"风格库写 {from_style}（{language_label(from_style)}）"))
    target = declared or from_style
    if not target:
        if product_language or style_language:
            issues.append(("language_missing", "语种字段没有可识别的值，本地化与语速基线都无法确定"))
        else:
            issues.append(("language_missing", "产品表与市场风格库都没给语种"))
    return target, issues


def check_asset(product, style, hook, rows, banned, action_words=None, options=None):
    """跑前三秒法则与素材完整性检查，返回 (问题列表, 待填数, 语速预算信息)。"""
    options = options or {}
    working = options.get("working_language") or DEFAULT_WORKING_LANGUAGE
    overrides = options.get("speech_overrides") or {}
    caption_limit = options.get("caption_limit", CAPTION_CHAR_LIMIT)
    market_rate = to_number(style.get("speech_rate"))

    issues = []
    hook_shot = rows[0]
    first_frame = hook["first_frame"]
    lowered = (first_frame or "").lower()
    if not first_frame or any(word.lower() in lowered for word in BANNED_OPENINGS):
        issues.append(("retention_first_frame", f"首帧要求：{first_frame or '（空）'}"))
    elif not contains_action(first_frame, action_words):
        issues.append(("retention_action", f"首帧只有静态描述：{first_frame}"))

    target, language_issues = resolve_target_language(product["language"], style.get("language"))
    issues += language_issues

    # 目标语种的前 3 秒口播预算（本地化后的硬指标）
    _, budget_unit, budget_rate = speech_profile(target or working, overrides, market_rate)
    budget = {
        "target": target,
        "target_label": language_label(target) if target else "待确认",
        "code": target or "",
        # 目标语种没定下来时，这份预算只是按工作语言给出的占位值，不能当成目标语种口径
        "provisional": not target,
        "unit": UNIT_LABELS[budget_unit],
        "cap": speech_cap(budget_rate, 3),
    }
    budget["text"] = f"≤{budget['cap']} {budget['unit']}/3s"

    caption_ok = has_real_content(hook_shot["caption"])
    voice_ok = has_real_content(hook_shot["voiceover"])
    if not caption_ok and not voice_ok:
        issues.append(("retention_hookline", "前 3 秒字幕与口播都由待填位组成"))
    else:
        if not caption_ok:
            issues.append(("retention_caption", "前 3 秒没有可读字幕，静音刷到的用户看不懂"))
        elif caption_units(hook_shot["caption"]) > caption_limit:
            issues.append(("caption_too_long",
                           f"前 3 秒字幕约 {caption_units(hook_shot['caption'])} 个全角字位，"
                           f"超过单行 {caption_limit} 字预算"))
        if voice_ok:
            copy_text = hook_shot["voiceover"] + hook_shot["caption"]
            localized = looks_localized(copy_text, target)
            # 草稿按工作语言的语速与单位预检；已本地化才用目标语种（含风格库语速覆盖）
            copying_target = localized or (target or working) == working
            copy_code, copy_unit, copy_rate = speech_profile(
                (target or working) if copying_target else working, overrides,
                market_rate if copying_target else None)
            cap = speech_cap(copy_rate, 3)
            spoken = speech_units(hook_shot["voiceover"], copy_unit)
            if spoken > cap:
                unit_label = UNIT_LABELS[copy_unit]
                if localized:
                    detail = (f"前 3 秒口播 {spoken} {unit_label}，超过"
                              f"{language_label(copy_code)}语速上限 {cap} {unit_label}/3s")
                else:
                    detail = (f"前 3 秒口播 {spoken} {unit_label}，按{language_label(copy_code)}"
                              f"语速上限 {cap} {unit_label}/3s 预检已讲不完；"
                              f"本地化到{budget['target_label']}后按预算 {budget['text']} 重写再复测")
                issues.append(("retention_speech",
                               detail + (f"（当前是{language_label(working)}草稿）" if not localized else "")))
            if not localized and target and target != working:
                issues.append(("retention_localization",
                               f"文案为{language_label(working)}草稿，需按{language_label(target)}"
                               f"（{target}）重写，前 3 秒口播预算 {budget['text']}"))

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

    return issues, placeholders, budget


def build_model_prompt(product, style, hook, rows, ratio, duration, budget):
    """拼出可直接粘给视频模型的生成提示词（由结构化字段拼装，不含编造内容）。"""
    shots = "；".join(f"{row['timecode']}（{row['shot_type']}）{row['visual_prompt']}" for row in rows)
    captions = " / ".join(f"{row['timecode']} {row['caption']}" for row in rows)
    return "\n".join([
        f"【主题】{product['product_name'] or product['sku']}——{product['category'] or '{{待填:品类}}'}"
        f"，面向{product['audience'] or '{{待填:目标人群}}'}（{product['site']} 市场）",
        f"【风格】{style.get('visual_style') or '{{待填:画面风格}}'}；{style.get('tone') or '{{待填:话术调性}}'}；"
        f"{style.get('rhythm') or '{{待填:剪辑节奏}}'}；出镜：{style.get('talent') or '{{待填:出镜者}}'}",
        f"【规格】{duration}s，{ratio}，竖版优先；字幕全程常驻，静音可读",
        f"【语言】目标语种 {budget['target_label']}"
        + (f"（{budget['code']}）" if budget["code"] else "（语种待确认，先按下面的占位预算写，确认后重算）")
        + f"；字幕、口播、配音全部用目标语种，交付前按本地语速复测前 3 秒（口播预算 {budget['text']}）",
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
    target_list = "、".join(f"{language_label(code)}（{code}）" for code in data["languages"]) or "未指定"
    lines.append(f"- 语种：工作语言 {language_label(data.get('working_language', DEFAULT_WORKING_LANGUAGE))}；"
                 f"目标语种 {target_list}；语速上限取自语种表，可由风格库「语速上限」列或 "
                 f"--speech-rate 覆盖")
    lines.append("")

    lines.append("## 素材总表")
    lines.append("")
    lines.append("| 素材名 | 市场 | 目标语种 | 钩子 | 前 3 秒检查 | 提示 | 前 3 秒口播预算 | 待填 |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for asset in data["assets"]:
        status = "通过" if not asset["retention_blocking"] else "；".join(
            f"{CHECKS[key][1]}（{detail}）" if detail else CHECKS[key][1]
            for key, detail in asset["retention_blocking"])
        hint = "；".join(f"{CHECKS[key][1]}" for key, _ in asset["retention_notes"]) or "—"
        lines.append(f"| {asset['asset_name']} | {asset['site']} | {asset['language_label']} | "
                     f"{asset['hook_code']} {asset['hook_name']} | {status} | {hint} | "
                     f"{asset['speech_budget']} | {asset['placeholders']} |")
    lines.append("")

    lines.append("## 本地化与语速预算")
    lines.append("")
    lines.append(f"文案默认用工作语言（{language_label(data.get('working_language', DEFAULT_WORKING_LANGUAGE))}）"
                 "写成草稿，语速预检也按工作语言跑一遍；本地化到目标语种后，"
                 "口播长度必须按下面这个预算复测——超了就得砍词，不是调语速。")
    lines.append("")
    lines.append("| 市场 | 目标语种 | 素材数 | 前 3 秒口播预算 | 字幕单行上限 |")
    lines.append("|---|---|---|---|---|")
    for entry in data["speech_rates"]:
        count = sum(1 for asset in data["assets"]
                    if asset["site"] == entry["site"] and asset["language"] == entry["language"])
        if entry["language"]:
            language_cell = f"{language_label(entry['language'])}（{entry['language']}）"
        else:
            language_cell = "待确认"
        budget_cell = entry["budget"]
        if entry.get("provisional"):
            budget_cell += f"（暂按{language_label(data.get('working_language', DEFAULT_WORKING_LANGUAGE))}预检）"
        lines.append(f"| {entry['site']} | {language_cell} | "
                     f"{count} | {budget_cell} | ≤ {args.caption_limit:g} 全角字 |")
    lines.append("")
    lines.append("本地化交付清单（逐项过一遍，缺一项就会在投放端露馅）：")
    lines.append("")
    lines.append("1. 前 3 秒钩子口播与字幕：按预算重写，删到讲得完为止，再复测时长。")
    lines.append("2. 全片字幕与口播：用目标语种标点，数字与货币按当地写法（千分位、小数点、币种位置）。")
    lines.append("3. 配音：优先目标市场本地口音，配音语种与字幕语种必须一致，不要出现英语配音配本地字幕。")
    lines.append("4. 字幕排版：中文/日文/韩文/泰文断行规则与拉丁语不同，"
                 "阿拉伯语/希伯来语为从右往左排版，字体要能显示目标语种字形。")
    lines.append("5. 画面里的文字（包装、招牌、界面）：出现中文或英语会削弱本地感，能换就换成本地语言。")
    lines.append("")

    lines.append(f"## 分镜详情（前 {detail_count} 条素材）")
    lines.append("")
    for asset in data["assets"][:detail_count]:
        lines.append(f"### {asset['asset_name']}")
        lines.append("")
        lines.append(f"- 市场/语种：{asset['site']} / {asset['language_label']}"
                     + (f"（{asset['language']}）" if asset["language"] else "")
                     + f"；钩子：{asset['hook_code']} {asset['hook_name']}")
        budget_note = "（本地化后必须复测）"
        if asset.get("language_provisional"):
            budget_note = ("（语种未确认，这是按工作语言给的占位预算；"
                           "补齐目标语种后重跑才知道真实上限）")
        lines.append(f"- 本地化：目标语种 {asset['language_label']}；前 3 秒口播预算 "
                     f"{asset['speech_budget']}{budget_note}")
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
    parser.add_argument("--working-language", default=DEFAULT_WORKING_LANGUAGE,
                        help="钩子模板与分镜文案当前使用的工作语言，默认 zh；文案已按目标语种重写后可改这里")
    parser.add_argument("--speech-rate", default="", metavar="语种=每秒上限",
                        help="覆盖内置语速表，如 vi=3.5,ja=6 —— 优先级最高")
    parser.add_argument("--caption-limit", type=float, default=CAPTION_CHAR_LIMIT,
                        help=f"前 3 秒字幕单行可容纳的全角字符数，默认 {CAPTION_CHAR_LIMIT}")
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
    working_language = normalize_language(args.working_language) or DEFAULT_WORKING_LANGUAGE
    speech_overrides = parse_rate_overrides(args.speech_rate)
    check_options = {"working_language": working_language, "speech_overrides": speech_overrides,
                     "caption_limit": args.caption_limit}
    if args.speech_rate and not speech_overrides:
        flags.append(sheetio.flag("medium", "speech_rate_ignored",
                                  f"--speech-rate「{args.speech_rate}」没解析出任何有效项",
                                  "写成「语种=每秒上限」的形式，例如 vi=3.5,ja=6"))
    if args.working_language and not normalize_language(args.working_language):
        flags.append(sheetio.flag("medium", "working_language_unrecognized",
                                  f"--working-language「{args.working_language}」不在已知语种表里，按中文处理",
                                  "改用 --working-language ja 这类语种代码"))
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
                issues, placeholders, budget = check_asset(
                    product, style, hook, shot_rows, banned, action_words, check_options)
                language = budget["code"] or ""
                asset_name = f"{sku}_{site}_{hook['hook_code']}_{ratio.replace(':', 'x')}_{args.duration}s_v1"
                retention = [(key, detail) for key, detail in issues if key.startswith("retention_")]
                asset = {
                    "asset_name": asset_name, "sku": sku, "site": site, "language": language,
                    "language_label": budget["target_label"], "localize_to": budget["code"],
                    "language_provisional": budget["provisional"],
                    "speech_budget": budget["text"],
                    "hook_code": hook["hook_code"], "hook_name": hook["hook_name"],
                    "ratio": ratio, "rows": shot_rows, "placeholders": placeholders,
                    "retention_issues": retention,
                    "retention_blocking": [(key, detail) for key, detail in retention
                                           if CHECKS.get(key, ("medium", ""))[0] != "low"],
                    "retention_notes": [(key, detail) for key, detail in retention
                                        if CHECKS.get(key, ("low", ""))[0] == "low"],
                    "issues": issues,
                    "model_prompt": build_model_prompt(product, style, hook, shot_rows, ratio,
                                                       args.duration, budget),
                }
                assets.append(asset)
                for key, detail in issues:
                    issue_index.setdefault(key, []).append((asset_name, detail))
                for row in shot_rows:
                    rows_out.append([asset_name, sku, product["product_name"], site, language, ratio,
                                     args.duration, hook["hook_code"], hook["hook_name"], row["shot_index"],
                                     row["timecode"], row["shot_seconds"], row["shot_type"],
                                     row["visual_prompt"], row["caption"], row["voiceover"],
                                     row["retention_note"], budget["code"], budget["text"],
                                     placeholders, row["note"]])

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
        "working_language": working_language,
        "languages": sorted({asset["language"] for asset in assets if asset["language"]}),
        "speech_rates": [{"site": site, "language": language, "budget": budget, "provisional": provisional}
                         for site, language, budget, provisional in sorted(
                             {(asset["site"], asset["language"], asset["speech_budget"],
                               asset["language_provisional"]) for asset in assets})],
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
            "口播语速上限按目标语种折算：中文/日文/韩文/泰文等按字符，其余语种按空格分词；"
            "数值是广告口播的经验上限（比自然语速慢约 10–20%），可用 --speech-rate 或风格库的"
            "「语速上限」列覆盖，最终以目标语种实际配音试听为准",
            "口播长度测算把每个 {{待填:}} 记作 2 个单位（会被真实内容替换，不能按 0 计），"
            "本地化后必须按目标语种重新复测前 3 秒",
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
