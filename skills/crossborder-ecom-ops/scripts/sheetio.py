#!/usr/bin/env python3
"""表格读写、字段归一、统一输出信封（仅用 Python 标准库）。

被 clean_table.py / fee_check.py / po_build.py / roi_review.py / selection_profit.py 复用。
支持 .csv/.tsv/.txt 与 .xlsx/.xlsm（xlsx 直接用 zipfile + XML 解析，不依赖 pandas/openpyxl）。
"""

import csv
import datetime
import json
import os
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

XLSX_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
XLSX_RNS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"

# ---------------------------------------------------------------- 文本归一

_HALFWIDTH = {c: c - 0xFEE0 for c in range(0xFF01, 0xFF5F)}
_HALFWIDTH[0x3000] = 0x20


def to_halfwidth(value):
    """全角转半角（含全角数字、字母、标点与全角空格）。"""
    return str(value).translate(_HALFWIDTH)


_KEY_STRIP = re.compile(r"[\s_\-（）()\[\]【】{}:：/\\,，.。\"'`|]+")


def norm_key(value):
    """列名归一：用于别名匹配，去空格/下划线/括号/标点并转小写。"""
    return _KEY_STRIP.sub("", to_halfwidth(value or "").strip().lower())


def clean_text(value):
    """清洗单元格文本：全角转半角、压缩空白。"""
    if value is None:
        return ""
    text = to_halfwidth(value)
    text = text.replace("\u00a0", " ")
    return re.sub(r"\s+", " ", text).strip()


# ---------------------------------------------------------------- 数值解析

_CURRENCY_SYMBOLS = "¥$€£₩₹₽฿₫₴₦₱￥"
_CURRENCY_CODES = re.compile(
    r"\b(USD|CNY|RMB|EUR|GBP|JPY|HKD|TWD|NTD|SGD|MYR|THB|VND|PHP|IDR|KRW|AUD|CAD|MXN|BRL|INR|AED|SAR|PLN|SEK|TRY|NZD|CHF)\b",
    re.I,
)
_MULTIPLIERS = {"万": 1e4, "千": 1e3, "k": 1e3, "K": 1e3, "m": 1e6, "M": 1e6}


def to_number(value):
    """把各种写法的金额/比例解析成 float；无法解析返回 None。

    - 去货币符号与币种代码：¥1,234.50 / USD 12.3
    - 百分号转小数：15% -> 0.15
    - 中文数量级：1.2万 -> 12000
    - 千分位与欧式小数：1,234.5 -> 1234.5；1.234,56 -> 1234.56；10,84 -> 10.84（逗号后 1-2 位按小数点
      处理，逗号后 3 位按千分位处理）
    - 负号与括号负数：(123) -> -123
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = to_halfwidth(value).strip()
    if not text or text in {"-", "-", "—", "N/A", "n/a", "NA", "null", "None", "不适用"}:
        return None
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]
    text = text.replace("\u00a0", "").replace(" ", "")
    for ch in _CURRENCY_SYMBOLS:
        text = text.replace(ch, "")
    text = _CURRENCY_CODES.sub("", text)
    multiplier = 1.0
    if text.endswith("%"):
        text = text[:-1]
        multiplier = 0.01
    suffix = re.search(r"(万|千|k|K|m|M)$", text)
    if suffix and re.search(r"\d", text):
        multiplier *= _MULTIPLIERS[suffix.group(1)]
        text = text[: suffix.start()]
    text = text.replace("+", "")
    if text.startswith("-"):
        negative = True
        text = text[1:]
    if text.count(",") and text.count("."):
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif text.count(","):
        parts = text.split(",")
        tail = parts[-1]
        if tail and len(tail) <= 2 and all(len(p) == 3 for p in parts[1:-1]):
            text = "".join(parts[:-1]) + "." + tail
        else:
            text = "".join(parts)
    text = re.sub(r"[^0-9eE.\-]", "", text)
    if not text or text in {"-", ".", "e"}:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    return -number * multiplier if negative else number * multiplier


def to_int(value):
    number = to_number(value)
    if number is None:
        return None
    return int(round(number))


def fmt_number(value, digits=2):
    if value is None:
        return ""
    return f"{value:.{digits}f}"


# ---------------------------------------------------------------- 日期解析

_EXCEL_EPOCH = datetime.date(1899, 12, 30)
_FIELD_YEAR = re.compile(r"\d{4}")


def to_date(value, default_year=None):
    """统一成 YYYY-MM-DD；无法判定返回 None。

    支持 2026-09-01 / 2026/9/1 / 2026.9.1 / 2026年9月1日 / 20260901 /
    09-01-2026（判为 M/D/Y） / 13-01-2026（判为 D/M/Y） / Excel 序列号。
    月日无年份时可传 default_year。
    """
    if value is None:
        return None
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.strftime("%Y-%m-%d")
    text = to_halfwidth(value).strip()
    if not text:
        return None
    if re.fullmatch(r"\d{8}", text):
        return _build_date(int(text[:4]), int(text[4:6]), int(text[6:]))
    if re.fullmatch(r"\d{6}", text):
        return _build_date(2000 + int(text[:2]), int(text[2:4]), int(text[4:6]))
    if re.fullmatch(r"\d+(\.\d+)?", text):
        serial = float(text)
        if 20000 <= serial <= 80000:
            day = _EXCEL_EPOCH + datetime.timedelta(days=int(serial))
            return day.strftime("%Y-%m-%d")
        return None
    text = text.replace("年", "-").replace("月", "-").replace("日", "")
    text = re.sub(r"\s+\d{1,2}:\d{2}(:\d{2})?", "", text)
    if re.search(r"\d{13}", text):
        stamp = int(re.search(r"\d{13}", text).group(0)) / 1000.0
        return datetime.datetime.fromtimestamp(stamp).strftime("%Y-%m-%d")
    parts = [p for p in re.split(r"[/\-.]", text) if p.strip()]
    if not all(re.fullmatch(r"\d+", p.strip()) for p in parts):
        return None
    nums = [int(p) for p in parts]
    if len(nums) == 3:
        a, b, c = nums
        if a > 99:
            return _build_date(a, b, c)
        if c > 99:
            if a > 12:
                return _build_date(c, b, a)
            return _build_date(c, a, b)
        return None
    if len(nums) == 2:
        year = default_year or datetime.date.today().year
        return _build_date(year, nums[0], nums[1])
    return None


def _build_date(year, month, day):
    if not (1 <= month <= 12 and 1 <= day <= 31 and 1900 <= year <= 2200):
        return None
    try:
        return datetime.date(year, month, day).strftime("%Y-%m-%d")
    except ValueError:
        return None


def day_shift(start_date, days):
    base = datetime.date.fromisoformat(start_date)
    return (base + datetime.timedelta(days=days)).strftime("%Y-%m-%d")


# ---------------------------------------------------------------- 读表

def _read_delimited(path):
    with open(path, "rb") as handle:
        raw = handle.read()
    text = None
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "cp936", "latin-1"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise ValueError(f"无法解码文件：{path}")
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return []
    head = lines[0]
    delimiter = max([",", "\t", ";", "|"], key=head.count)
    if head.count(delimiter) == 0:
        delimiter = ","
    return [row for row in csv.reader(text.splitlines(), delimiter=delimiter)]


def _col_index(ref):
    letters = "".join(ch for ch in ref if ch.isalpha()).upper()
    index = 0
    for ch in letters:
        index = index * 26 + (ord(ch) - 64)
    return index - 1


def _shared_strings(archive):
    try:
        payload = archive.read("xl/sharedStrings.xml")
    except KeyError:
        return []
    root = ET.fromstring(payload)
    return ["".join(t.text or "" for t in si.iter(f"{XLSX_NS}t")) for si in root.iter(f"{XLSX_NS}si")]


def _sheet_paths(archive):
    fallback = sorted(
        name for name in archive.namelist() if name.startswith("xl/worksheets/sheet") and name.endswith(".xml")
    )
    try:
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    except KeyError:
        return fallback
    rels = {}
    try:
        rel_root = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        for rel in rel_root:
            rels[rel.get("Id")] = rel.get("Target")
    except KeyError:
        pass
    paths = []
    for sheet in workbook.iter(f"{XLSX_NS}sheet"):
        target = rels.get(sheet.get(f"{XLSX_RNS}id"), "")
        if not target:
            continue
        if target.startswith("/"):
            target = target[1:]
        elif not target.startswith("xl/"):
            target = "xl/" + target
        paths.append(target)
    return paths or fallback


def _read_xlsx(path, sheet=1):
    with zipfile.ZipFile(path) as archive:
        names = _sheet_paths(archive)
        if not names:
            raise ValueError(f"xlsx 中没有工作表：{path}")
        index = min(max(sheet, 1), len(names)) - 1
        shared = _shared_strings(archive)
        root = ET.fromstring(archive.read(names[index]))
    rows = []
    for row in root.iter(f"{XLSX_NS}row"):
        cells = {}
        for cell in row.findall(f"{XLSX_NS}c"):
            ref = cell.get("r") or ""
            position = _col_index(ref) if ref else (max(cells) + 1 if cells else 0)
            kind = cell.get("t")
            if kind == "inlineStr":
                node = cell.find(f"{XLSX_NS}is")
                value = "".join(t.text or "" for t in node.iter(f"{XLSX_NS}t")) if node is not None else ""
            else:
                node = cell.find(f"{XLSX_NS}v")
                raw = node.text if node is not None and node.text is not None else ""
                if kind == "s":
                    value = shared[int(raw)] if raw.isdigit() and int(raw) < len(shared) else ""
                elif kind == "b":
                    value = "TRUE" if raw == "1" else "FALSE"
                else:
                    value = raw
            cells[position] = str(value).strip()
        if cells:
            width = max(cells) + 1
            rows.append([cells.get(i, "") for i in range(width)])
    return rows


def _rectangular(rows):
    if not rows:
        return []
    width = max(len(row) for row in rows)
    return [list(row) + [""] * (width - len(row)) for row in rows]


def read_table(path, sheet=1, header_row=1):
    """读表，返回 (headers, rows)。header_row 为 1 基行号。"""
    if not os.path.exists(path):
        raise FileNotFoundError(f"找不到文件：{path}")
    extension = os.path.splitext(path)[1].lower()
    if extension in (".xlsx", ".xlsm"):
        raw = _read_xlsx(path, sheet=sheet)
    elif extension in (".xls",):
        raise ValueError("不支持旧版 .xls，请另存为 .xlsx 或 .csv")
    else:
        raw = _read_delimited(path)
    raw = _rectangular([row for row in raw])
    if not raw:
        return [], []
    index = max(header_row - 1, 0)
    headers = [clean_text(cell) for cell in raw[index]]
    while headers and not headers[-1]:
        headers.pop()
    body = raw[index + 1 :]
    body = [row[: len(headers)] + [""] * max(0, len(headers) - len(row)) for row in body]
    return headers, body


def write_csv(path, headers, rows):
    """写出 UTF-8 BOM 的 CSV，Excel 打开中文不乱码。"""
    with open(path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        for row in rows:
            writer.writerow(["" if cell is None else cell for cell in row])


def write_json(path, payload):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------- 字段别名

ALIASES = {
    "date": ["date", "日期", "报告日期", "统计日期", "数据日期", "时间", "日期时间", "reportdate", "statdate", "day"],
    "sku": ["sku", "商品编码", "商家编码", "店铺sku", "sellersku", "msku", "子sku", "货号", "商品货号", "itemid"],
    "asin": ["asin", "子asin", "listingid", "listing", "产品asin"],
    "product_name": ["商品名称", "品名", "产品名称", "title", "标题", "productname"],
    "spec": ["规格", "颜色尺码", "变体", "variation", "spec", "属性"],
    "platform": ["平台", "渠道", "channel", "platform", "销售平台", "站点平台"],
    "site": ["site", "站点", "国家", "市场", "marketplace", "country", "国家站点", "地区", "销售国家"],
    "category": ["类目", "分类", "品类", "一级类目", "二级类目", "category", "商品类目", "平台类目"],
    "campaign": ["广告活动", "活动", "campaign", "campaigntname", "campaignname", "广告系列", "计划"],
    "ad_group": ["广告组", "adgroup", "adgroupname", "推广组", "单元"],
    "impressions": ["曝光", "曝光量", "展示", "展示量", "impressions", "展现量"],
    "clicks": ["点击", "点击量", "clicks", "click"],
    "spend": ["花费", "广告花费", "广告费", "广告费用", "广告消耗", "消耗", "spend", "adspend"],
    "orders": ["订单", "订单数", "订单量", "转化", "转化数", "成交笔数", "orders", "conversions", "purchases"],
    "units": ["销量", "件数", "下单件数", "units", "销售件数", "销售数量"],
    "revenue": ["销售额", "成交额", "收入", "gmv", "revenue", "sales", "销售金额", "广告销售额", "营业额"],
    "total_revenue": ["总销售额", "总营收", "整体销售额", "totalrevenue", "totalsales", "店铺总销售额"],
    "price": ["售价", "客单价", "price", "unitprice", "销售单价", "平均售价", "零售价"],
    "cost": ["成本", "商品成本", "采购成本", "单位成本", "cost", "unitcost", "货物成本"],
    "refund": ["退款", "退款金额", "退款额", "refund", "refundamount", "退货金额"],
    "qty": ["数量", "采购数量", "下单数量", "qty", "quantity", "件数", "订购数量", "补货数量"],
    "unit_price": ["单价", "采购单价", "供货价", "报价", "unitprice", "price", "含税单价"],
    "amount": ["金额", "小计", "行金额", "总价", "amount", "subtotal", "合计金额"],
    "unit": ["单位", "unit", "计量单位"],
    "moq": ["moq", "起订量", "最小起订量", "minimumorderqty"],
    "lead_time_days": ["交期", "生产周期", "交期天数", "leadtime", "leadtime days", "备货周期"],
    "warehouse": ["仓库", "入库仓", "目的仓", "warehouse", "收货仓"],
    "expected_arrival": ["期望到仓", "到仓日期", "期望到货日期", "expectedarrival", "要求到仓日"],
    "remark": ["备注", "说明", "remark", "note", "notes"],
    "commission_rate": ["佣金", "佣金比例", "佣金率", "commissionrate", "commission", "平台佣金", "佣金费率"],
    "payment_rate": ["支付费率", "支付手续费", "交易手续费", "paymentrate", "payment", "收款手续费"],
    "fulfillment_fee": ["履约费", "派送费", "配送费", "物流费", "fulfillmentfee", "shippingfee", "尾程费"],
    "fba_fee": ["fba费", "fbafee", "fba配送费", "仓储配送费"],
    "storage_fee": ["仓储费", "storagefee", "月度仓储费"],
    "weight": ["重量", "单件重量", "毛重", "净重", "重量kg", "重量lb", "weight", "productweight",
               "itemweight", "shippingweight", "商品重量"],
    "box_qty": ["箱规", "装箱数", "每箱数量", "每箱装数量", "箱装数量", "boxqty", "pcsperbox", "qtyperbox"],
    "freight": ["运费", "运费usd", "物流运费", "国际运费", "头程运费", "尾程运费", "freight",
                "freightusd", "estfreight", "预估运费"],
    "weight_min": ["重量下限", "起始重量", "区间下限", "weightfrom", "weightmin"],
    "weight_max": ["重量上限", "结束重量", "区间上限", "weightto", "weightmax"],
    "weight_band": ["重量区间", "重量段", "weightband", "weightrange", "重量区间lb", "重量区间kg"],
    "wholesale_price": ["批发价", "批发售价", "批发单价", "wholesaleprice", "b2bprice"],
    "free_shipping_threshold": ["免邮门槛", "包邮门槛", "免邮起价", "freeshippingthreshold", "包邮起价"],
    "tax_rate": ["税率", "vat", "vat税率", "taxrate", "税费率", "gst"],
    "audience": ["人群", "受众", "目标人群", "目标受众", "人群画像", "受众画像", "audience",
                 "targetaudience", "targetgroup"],
    "selling_points": ["卖点", "核心卖点", "产品卖点", "主要卖点", "sellingpoints", "usp", "sellingpoint"],
    "proof": ["证明", "证明材料", "资质", "认证", "销量证明", "社会证明", "socialproof", "proof"],
    "offer": ["利益点", "促销利益点", "活动利益点", "优惠信息", "offer", "cta"],
    "language": ["语种", "语言", "language", "lang"],
    "rhythm": ["节奏", "剪辑节奏", "卡点节奏", "rhythm", "pacing"],
    "visual_style": ["画面风格", "视觉风格", "拍摄风格", "visualstyle", "look"],
    "talent": ["出镜", "出镜者", "模特类型", "talent", "oncamercast"],
    "avoid": ["禁忌", "禁用元素", "慎用元素", "avoid"],
    "hook_code": ["钩子编码", "钩子代码", "hookcode"],
    "hook_name": ["钩子类型", "钩子名称", "hookname"],
    "first_frame": ["首帧", "首帧要求", "firstframe"],
    "line_template": ["句式模板", "话术模板", "口播模板", "口播话术", "linetemplate"],
    "retention_note": ["留存说明", "留存要点", "retentionnote"],
    "word": ["禁用词", "敏感词", "违禁词", "word"],
    "scope": ["适用范围", "scope"],
    "reason": ["原因", "违规原因", "依据", "reason"],
    "as_of": ["获取日期", "抓取日期", "asof", "检索日期", "来源日期"],
    "scene": ["场景", "使用场景", "场景偏好", "scene"],
    "tone": ["调性", "话术调性", "语气", "tone", "voice"],
    "platforms": ["主流平台", "媒体平台", "投放平台", "平台组合", "platforms"],
    "desc": ["描述", "钩子说明", "说明文案", "description", "desc"],
    "caption_template": ["字幕模板", "字幕句式", "captiontemplate", "captions"],

    "price_min": ["价格下限", "最低价", "pricemin", "pricefrom", "起始价"],
    "price_max": ["价格上限", "最高价", "pricemax", "priceto", "结束价"],
    "currency": ["币种", "货币", "currency", "结算币种"],
    "source": ["来源", "数据来源", "source", "出处", "规则来源"],
    "effective_date": ["生效日期", "生效时间", "effectivedate", "适用日期"],
    "condition": ["条件", "适用条件", "备注条件", "condition", "限制"],
    "updated_at": ["更新时间", "录入时间", "updatedat", "lastupdated", "更新日期"],
}


ALIAS_TO_CANON = {}
for _canon, _aliases in ALIASES.items():
    ALIAS_TO_CANON.setdefault(norm_key(_canon), _canon)
    for _alias in _aliases:
        ALIAS_TO_CANON.setdefault(norm_key(_alias), _canon)
del _canon, _aliases, _alias
_EXACT_ALIASES = set(ALIAS_TO_CANON)


def canonical_field(header):
    """把表头映射成标准字段名；没有对应标准字段时返回归一化后的原列名。"""
    key = norm_key(header)
    return ALIAS_TO_CANON.get(key, key or "column")


def find_column(headers, canon, extra_aliases=None):
    """按别名在表头里找列下标，找不到返回 None。先精确匹配再包含匹配。"""
    keys = [canon] + list(ALIASES.get(canon, [])) + list((extra_aliases or {}).get(canon, []))
    keys = [norm_key(key) for key in keys if key]
    if not keys:
        return None
    normalized = [norm_key(header) for header in headers]
    for index, name in enumerate(normalized):
        if name and name in keys:
            return index
    for index, name in enumerate(normalized):
        if not name or name in _EXACT_ALIASES:
            continue
        if any(key in name for key in keys):
            return index
    return None


def column_map(headers, fields, extra_aliases=None):
    """返回 {标准字段: 列下标}，只包含找到的字段。"""
    found = {}
    for field in fields:
        index = find_column(headers, field, extra_aliases)
        if index is not None:
            found[field] = index
    return found


def apply_mapping(mapping_args):
    """解析 --map 原列名=标准字段，返回 {norm_key(原列名): 标准字段}。"""
    result = {}
    for item in mapping_args or []:
        if "=" not in item:
            raise ValueError(f"--map 需要写成 原列名=标准字段，收到：{item}")
        source, target = item.split("=", 1)
        result[norm_key(source)] = target.strip()
    return result


# ---------------------------------------------------------------- 输出信封

def make_envelope(task, status, confidence, data, flags=None, sources=None, assumptions=None, audit=None):
    """统一输出信封，字段定义见 SKILL.md。"""
    flags = flags or []
    need_human_review = any(flag.get("level") == "high" for flag in flags)
    return {
        "task": task,
        "status": status,
        "confidence": round(float(confidence), 2),
        "data": data,
        "flags": flags,
        "need_human_review": need_human_review,
        "sources": sources or [],
        "assumptions": assumptions or [],
        "audit": audit or {"snapshot_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds")},
    }


def flag(level, kind, detail, action=""):
    return {"level": level, "type": kind, "detail": detail, "action": action}


def emit(envelope, stream=None, out_json=None):
    """打印输出信封；指定 out_json 时把同一份信封落盘，保证 stdout 与文件内容一致。"""
    target = stream or sys.stdout
    target.write(json.dumps(envelope, ensure_ascii=False, indent=2) + "\n")
    if out_json:
        write_json(out_json, envelope)
