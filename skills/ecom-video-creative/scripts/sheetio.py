#!/usr/bin/env python3
"""表格读写、字段归一、统一输出信封（仅用 Python 标准库）。

被 clean_table.py / fee_check.py / po_build.py / roi_review.py / selection_profit.py / receipt_ledger.py 复用。
支持 .csv/.tsv/.txt 与 .xlsx/.xlsm（xlsx 直接用 zipfile + XML 解析，不依赖 pandas/openpyxl）。
"""

import csv
import datetime
import json
import os
import re
import sys
import urllib.parse
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
    09-01-2026（判为 M/D/Y） / 13-01-2026（判为 D/M/Y） / Excel 序列号 /
    ISO 8601 带时区（2026-08-20T00:00:00+0800）。
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
    iso = re.match(r"^(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})[T ]\d{1,2}:\d{2}", text)
    if iso:
        return _build_date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
    if re.fullmatch(r"\d+(\.\d+)?", text):
        serial = float(text)
        if 20000 <= serial <= 80000:
            day = _EXCEL_EPOCH + datetime.timedelta(days=int(serial))
            return day.strftime("%Y-%m-%d")
        if re.fullmatch(r"\d{4,}", text):
            return None       # 4 位以上的整数不像「月.日」，按 Excel 序列号处理失败就返回空
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
        paths.append((sheet.get("name") or "", target))
    return paths or fallback


def _read_xlsx(path, sheet=1):
    with zipfile.ZipFile(path) as archive:
        sheets = _sheet_paths(archive)
        if not sheets:
            raise ValueError(f"xlsx 中没有工作表：{path}")
        wanted = clean_text(sheet)
        if wanted and not wanted.isdigit():          # 按工作表名找，找不到就退回第一个
            matched = [item for item in sheets if item[0] == wanted] or \
                      [item for item in sheets if item[0].lower() == wanted.lower()]
            if not matched:
                raise ValueError(f"找不到工作表「{wanted}」，现有：{'、'.join(name for name, _ in sheets)}")
            target = matched[0][1]
        else:
            target = sheets[min(max(int(wanted or 1), 1), len(sheets)) - 1][1]
        shared = _shared_strings(archive)
        root = ET.fromstring(archive.read(target))
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
    """读表，返回 (headers, rows)。header_row 为 1 基行号；xlsx 的 sheet 可给序号或工作表名。"""
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


# ---------------------------------------------------------------- 本地路径与图片

def file_href(path):
    """本地文件路径转成 Excel 可点击的 file:/// 超链接（中文与空格自动做百分号编码）。"""
    absolute = os.path.abspath(str(path)).replace(os.sep, "/")
    if not absolute.startswith("/"):
        absolute = "/" + absolute
    return "file://" + urllib.parse.quote(absolute)


def image_size(path):
    """读图片像素尺寸，返回 (宽, 高)；格式不认识时返回 None。

    只看文件头，不解码整张图：png / jpeg / gif / bmp / webp(VP8X, VP8L)。
    尺寸用来给 Excel 里的缩略图算锚点范围，拍多张照片时不必再装图像库。
    """
    try:
        with open(path, "rb") as handle:
            head = handle.read(32)
            if head[:8] == b"\x89PNG\r\n\x1a\n":
                return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")
            if head[:6] in (b"GIF87a", b"GIF89a"):
                return int.from_bytes(head[6:8], "little"), int.from_bytes(head[8:10], "little")
            if head[:2] == b"BM":
                return int.from_bytes(head[18:22], "little"), abs(int.from_bytes(head[22:26], "little"))
            if head[:4] == b"RIFF" and head[8:12] == b"WEBP" and head[12:16] == b"VP8X":
                width = int.from_bytes(head[24:27], "little") + 1
                height = int.from_bytes(head[27:30], "little") + 1
                return width, height
            if head[:2] == b"\xff\xd8":
                return _jpeg_size(handle)
    except OSError:
        return None
    return None


def _jpeg_size(handle):
    handle.seek(2)
    while True:
        marker = handle.read(2)
        if len(marker) < 2 or marker[0] != 0xFF:
            return None
        kind = marker[1]
        if kind in (0xD8, 0xD9) or 0xD0 <= kind <= 0xD7:
            continue
        length_bytes = handle.read(2)
        if len(length_bytes) < 2:
            return None
        length = int.from_bytes(length_bytes, "big")
        if 0xC0 <= kind <= 0xCF and kind not in (0xC4, 0xC8, 0xCC):
            body = handle.read(5)
            if len(body) < 5:
                return None
            return int.from_bytes(body[3:5], "big"), int.from_bytes(body[1:3], "big")
        if length < 2:
            return None
        handle.seek(length - 2, 1)


# ---------------------------------------------------------------- Excel 写出

_XLSX_BAD_SHEET_CHARS = re.compile(r"[\[\]:*?/\\]")
_XLSX_STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts>
<fills count="4"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FFFFF2CC"/><bgColor indexed="64"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFFCE4E4"/><bgColor indexed="64"/></patternFill></fill></fills>
<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="5">
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"><alignment vertical="center"/></xf>
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>
<xf numFmtId="0" fontId="0" fillId="2" borderId="0" xfId="0" applyFill="1"/>
<xf numFmtId="0" fontId="0" fillId="3" borderId="0" xfId="0" applyFill="1"/>
</cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>"""

# 单元格高亮样式编号：3 = 黄色（需复核），4 = 红色（异常/未读准）
HIGHLIGHT_WARN = 3
HIGHLIGHT_ALERT = 4
HIGHLIGHT_LEVELS = {"warn": HIGHLIGHT_WARN, "yellow": HIGHLIGHT_WARN, "todo": HIGHLIGHT_WARN,
                    "alert": HIGHLIGHT_ALERT, "error": HIGHLIGHT_ALERT, "red": HIGHLIGHT_ALERT,
                    "high": HIGHLIGHT_ALERT}


def _xml_text(value):
    return (str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;").replace("'", "&apos;"))


def _col_letter(index):
    """1 → A，27 → AA。"""
    letters = ""
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def col_letter(index):
    """1 → A，27 → AA；给超链接与图片锚点拼单元格引用用。"""
    return _col_letter(index)


def _display_width(value):
    """估算单元格显示宽度：中日韩等全角字符按 2 个字符宽计。"""
    width = 0
    for char in str(value):
        width += 2 if ord(char) > 0x2E7F else 1
    return width


def _numeric_text(value):
    """判断字符串是不是可以安全写成数字的纯数值。

    只认无千分位、无币种符号、无前导零的短数值：`1234.50`、`-3.2`、`0.15`、`120000` 可以；
    `007`（货号/工号）、`20260914000001`（超长条码与订单号，转 float 会丢精度）、`1,234` 一律不转。
    """
    text = str(value).strip()
    if not text or len(re.sub(r"\D", "", text)) > 12:
        return None
    if not re.fullmatch(r"-?(?:0|[1-9]\d*)(?:\.\d+)?", text):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _xlsx_cell(reference, value, coerce_numbers=False, style=None):
    """写单元格：数字按数字写（Excel 可直接求和），文本用内联字符串，空值留空。

    coerce_numbers 打开时，形如 `1234.50` 的纯数值文本也会写成数字，
    便于清洗类产物在 Excel 里直接求和与做透视；`007`、超长条码不受影响。
    style 传 HIGHLIGHT_WARN / HIGHLIGHT_ALERT 时给单元格加底色（低置信、金额不符等
    需要人眼复核的格子）；空值加底色时同样写出空单元格，否则底色不显示。
    """
    attributes = f' s="{style}"' if style else ""
    if value is None or value == "":
        return f'<c r="{reference}"{attributes}/>' if style else ""
    if isinstance(value, bool):
        return f'<c r="{reference}"{attributes} t="b"><v>{1 if value else 0}</v></c>'
    if isinstance(value, (int, float)):
        return f'<c r="{reference}"{attributes}><v>{value!r}</v></c>'
    if coerce_numbers:
        number = _numeric_text(value)
        if number is not None:
            return f'<c r="{reference}"{attributes}><v>{number!r}</v></c>'
    if isinstance(value, (datetime.date, datetime.datetime)):
        value = value.isoformat()
    text = _xml_text(value)
    style_attribute = attributes or (' s="2"' if len(str(value)) > 28 else "")
    return f'<c r="{reference}"{style_attribute} t="inlineStr"><is><t xml:space="preserve">{text}</t></is></c>'


def _xlsx_sheet_xml(headers, rows, widths, coerce_numbers=False, hyperlinks=None, drawing_rid=None,
                    row_heights=None, highlights=None):
    hyperlinks = hyperlinks or []
    row_heights = row_heights or {}
    marked = {}
    for ref, style_id in (highlights or {}).items():
        digits = "".join(char for char in ref if char.isdigit())
        if digits:
            marked[(int(digits), _col_index(ref) + 1)] = style_id
    parts = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>']
    root = '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    if hyperlinks or drawing_rid:
        root += ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
    parts.append(root + ">")
    parts.append('<sheetViews><sheetView workbookViewId="0">'
                 '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
                 '</sheetView></sheetViews>')
    parts.append('<sheetFormatPr defaultRowHeight="15"/>')
    if widths:
        cols = "".join(f'<col min="{index}" max="{index}" width="{width:g}" customWidth="1"/>'
                       for index, width in enumerate(widths, start=1))
        parts.append(f"<cols>{cols}</cols>")
    parts.append("<sheetData>")
    if headers:
        cells = "".join(f'<c r="{_col_letter(col)}1" s="1" t="inlineStr">'
                        f'<is><t xml:space="preserve">{_xml_text(header)}</t></is></c>'
                        for col, header in enumerate(headers, start=1))
        parts.append(f'<row r="1" s="1" customFormat="1">{cells}</row>')
    for offset, row in enumerate(rows, start=2):
        cells = "".join(_xlsx_cell(f"{_col_letter(col)}{offset}", value, coerce_numbers,
                                   marked.get((offset, col)))
                        for col, value in enumerate(row, start=1))
        height = row_heights.get(offset)
        attributes = f' ht="{float(height):g}" customHeight="1"' if height else ""
        parts.append(f'<row r="{offset}"{attributes}>{cells}</row>' if cells
                     else f'<row r="{offset}"{attributes}/>')
    parts.append("</sheetData>")
    if hyperlinks:
        items = "".join(
            f'<hyperlink ref="{_xml_text(item["ref"])}" r:id="rId{index}"'
            + (f' tooltip="{_xml_text(item["tooltip"])}"' if item.get("tooltip") else "")
            + "/>"
            for index, item in enumerate(hyperlinks, start=1))
        parts.append(f"<hyperlinks>{items}</hyperlinks>")
    if drawing_rid:
        parts.append(f'<drawing r:id="{drawing_rid}"/>')
    parts.append("</worksheet>")
    return "".join(parts)


def _xlsx_widths(headers, rows, sample=200, overrides=None):
    if not headers:
        return []
    overrides = overrides or {}
    widths = []
    for index, header in enumerate(headers):
        longest = _display_width(header)
        for row in rows[:sample]:
            if index < len(row) and row[index] not in (None, ""):
                longest = max(longest, _display_width(row[index]))
        widths.append(min(max(longest + 2, 6), 52))
    for index, width in overrides.items():
        if 1 <= index <= len(widths):
            widths[index - 1] = width
    return widths


def _drawing_xml(images, rel_ids):
    """生成 drawing 部件：每张图片按 oneCellAnchor 锚在指定单元格左上角。"""
    anchors = []
    for index, image in enumerate(images):
        xdr_col = max(int(image["col"]) - 1, 0)
        xdr_row = max(int(image["row"]) - 1, 0)
        width = int(image.get("width") or 160)
        height = int(image.get("height") or 120)
        cx, cy = width * 9525, height * 9525
        anchors.append(
            '<xdr:oneCellAnchor>'
            f'<xdr:from><xdr:col>{xdr_col}</xdr:col><xdr:colOff>0</xdr:colOff>'
            f'<xdr:row>{xdr_row}</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:from>'
            f'<xdr:ext cx="{cx}" cy="{cy}"/>'
            "<xdr:pic><xdr:nvPicPr>"
            f'<xdr:cNvPr id="{index + 1}" name="Picture {index + 1}"/>'
            '<xdr:cNvPicPr><a:picLocks noChangeAspect="1"/></xdr:cNvPicPr></xdr:nvPicPr>'
            f'<xdr:blipFill><a:blip r:embed="{rel_ids[index]}"/><a:stretch><a:fillRect/></a:stretch></xdr:blipFill>'
            '<xdr:spPr><a:xfrm><a:off x="0" y="0"/>'
            f'<a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
            '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></xdr:spPr>'
            "</xdr:pic><xdr:clientData/></xdr:oneCellAnchor>")
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing" '
            'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            + "".join(anchors) + "</xdr:wsDr>")


_IMAGE_CONTENT_TYPES = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                        "gif": "image/gif", "bmp": "image/bmp", "webp": "image/webp"}


def _scale_to_box(width, height, max_width, max_height):
    """等比缩放到框内，返回整数尺寸；框为 0 或 None 时保持原尺寸。"""
    scale = 1.0
    if max_width and width > max_width:
        scale = min(scale, max_width / width)
    if max_height and height > max_height:
        scale = min(scale, max_height / height)
    return max(int(round(width * scale)), 1), max(int(round(height * scale)), 1)


def write_xlsx(path, sheets):
    """写出 .xlsx 工作簿；xlsx 本质是一个装着 XML 的 zip，只用标准库即可生成。

    sheets: [{"name": 表名, "headers": [...], "rows": [[...], ...],
              "coerce_numbers": False,
              "hyperlinks": [{"ref": "L2", "target": "file:///...", "tooltip": ""}, ...],
              "images": [{"path": ..., "row": 2, "col": 6, "max_width": 160, "max_height": 120}, ...],
              "row_heights": {2: 90}, "column_widths": {6: 23},
              "highlights": [{"ref": "I5", "level": "warn"}, {"ref": "J7", "level": "alert"}, ...],
              "image_max_width": 160, "image_max_height": 120}, ...]
    数字按数字写（Excel 里能直接求和、做透视），文本走内联字符串，表头加粗并冻结首行，
    列宽按内容自适应，长文本单元格自动换行。表级 coerce_numbers 打开时，纯数值文本
    也按数字写。hyperlinks 写成可点击的单元格超链接（本地文件用 file_href() 转 URL），
    images 把图片按锚点嵌进工作表（凭证缩略图用，行号列号都是 1 基）。
    highlights 给指定单元格加底色（level 传 warn 为黄底、alert 为红底），用来把
    「识别置信度低」「金额不符」这类需要人眼复核的格子直接标在表里。
    不需要 pandas / openpyxl。
    """
    prepared = []
    for sheet in sheets:
        if not sheet:
            continue
        headers = ["" if header is None else header for header in sheet.get("headers") or []]
        rows = [list(row) for row in sheet.get("rows") or []]
        if not headers and not rows:
            continue
        highlights = {}
        for item in sheet.get("highlights") or []:
            if not isinstance(item, dict):
                continue
            ref = str(item.get("ref") or "").strip()
            if not ref:
                continue
            level = str(item.get("level") or item.get("style") or "warn").strip().lower()
            highlights[ref] = HIGHLIGHT_LEVELS.get(level, HIGHLIGHT_WARN)
        hyperlinks = []
        for item in sheet.get("hyperlinks") or []:
            if isinstance(item, dict):
                ref, target = item.get("ref"), item.get("target")
                tooltip = item.get("tooltip")
            else:
                ref, target = (list(item) + [None, None])[:2]
                tooltip = None
            if ref and target:
                hyperlinks.append({"ref": str(ref), "target": str(target), "tooltip": tooltip})
        prepared.append({"name": sheet.get("name") or f"Sheet{len(prepared) + 1}",
                         "headers": headers, "rows": rows,
                         "coerce": bool(sheet.get("coerce_numbers")),
                         "hyperlinks": hyperlinks,
                         "images": [dict(image) for image in sheet.get("images") or [] if image],
                         "max_image_width": sheet.get("image_max_width") or 160,
                         "max_image_height": sheet.get("image_max_height") or 120,
                         "row_heights": {int(key): value for key, value in (sheet.get("row_heights") or {}).items()},
                         "highlights": highlights,
                         "column_widths": {int(key): float(value)
                                           for key, value in (sheet.get("column_widths") or {}).items()}})
    if not prepared:
        raise ValueError("write_xlsx 至少需要一张有内容的工作表")

    names = []
    for sheet in prepared:
        name = _XLSX_BAD_SHEET_CHARS.sub("", str(sheet["name"]).strip())[:31] or "Sheet"
        candidate, suffix = name, 2
        while candidate in names:
            candidate = f"{name[:28]}_{suffix}"
            suffix += 1
        names.append(candidate)

    # 图片：同一路径只存一份，尺寸按框等比缩放；锚点用 1 基行列号。
    media_parts, media_index, extension_types = [], {}, set()
    drawings = []
    for sheet in prepared:
        anchors, image_rels, drawing_rids = [], [], []
        for image in sheet["images"]:
            path_value = image.get("path") or image.get("file")
            if not path_value or not os.path.exists(path_value):
                continue
            key = os.path.abspath(path_value)
            if key not in media_index:
                extension = os.path.splitext(key)[1].lstrip(".").lower() or "png"
                if extension not in _IMAGE_CONTENT_TYPES:
                    continue
                try:
                    with open(key, "rb") as handle:
                        data = handle.read()
                except OSError:
                    continue
                media_index[key] = (f"image{len(media_parts) + 1}.{extension}", extension, data)
                media_parts.append(key)
                extension_types.add(extension)
            media_name, extension, _ = media_index[key]
            size = image_size(key)
            box_width = image.get("max_width") or sheet["max_image_width"]
            box_height = image.get("max_height") or sheet["max_image_height"]
            if size:
                width, height = _scale_to_box(size[0], size[1], box_width, box_height)
            else:
                width, height = int(box_width), int(box_height)
            anchors.append({"path": key, "row": image.get("row") or 1, "col": image.get("col") or 1,
                            "width": width, "height": height, "media": media_name})
            image_rels.append(media_name)
        if anchors:
            drawing_number = len(drawings) + 1
            drawings.append({"anchors": anchors, "rels": image_rels,
                             "rid": f"rId{len(sheet['hyperlinks']) + 1}"})
        else:
            drawings.append(None)

    overrides = "".join(
        f'<Override PartName="/xl/worksheets/sheet{index}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for index in range(1, len(prepared) + 1))
    image_defaults = "".join(
        f'<Default Extension="{extension}" ContentType="{_IMAGE_CONTENT_TYPES[extension]}"/>'
        for extension in sorted(extension_types))
    drawing_overrides = "".join(
        f'<Override PartName="/xl/drawings/drawing{index}.xml" ContentType="application/vnd.openxmlformats-officedocument.drawing+xml"/>'
        for index, drawing in enumerate(drawings, start=1) if drawing)
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        f"{image_defaults}"
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        f"{overrides}{drawing_overrides}</Types>")
    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        "</Relationships>")
    sheet_tags = "".join(
        f'<sheet name="{_xml_text(name)}" sheetId="{index}" r:id="rId{index}"/>'
        for index, name in enumerate(names, start=1))
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<sheets>{sheet_tags}</sheets></workbook>")
    sheet_rels = "".join(
        f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{index}.xml"/>'
        for index in range(1, len(prepared) + 1))
    style_rel_id = len(prepared) + 1
    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f"{sheet_rels}"
        f'<Relationship Id="rId{style_rel_id}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        "</Relationships>")

    def sheet_rels_xml(sheet, drawing, drawing_number):
        entries = "".join(
            f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" '
            f'Target="{_xml_text(item["target"])}" TargetMode="External"/>'
            for index, item in enumerate(sheet["hyperlinks"], start=1))
        if drawing:
            entries += (f'<Relationship Id="{drawing["rid"]}" '
                        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/drawing" '
                        f'Target="../drawings/drawing{drawing_number}.xml"/>')
        return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                f"{entries}</Relationships>")

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", root_rels)
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        archive.writestr("xl/styles.xml", _XLSX_STYLES)
        drawing_number = 0
        for index, sheet in enumerate(prepared, start=1):
            drawing = drawings[index - 1]
            if drawing:
                drawing_number = sheet_drawing_number = drawing_number + 1
            else:
                sheet_drawing_number = None
            archive.writestr(f"xl/worksheets/sheet{index}.xml",
                             _xlsx_sheet_xml(sheet["headers"], sheet["rows"],
                                             _xlsx_widths(sheet["headers"], sheet["rows"],
                                                          overrides=sheet["column_widths"]),
                                             sheet["coerce"], sheet["hyperlinks"],
                                             drawing["rid"] if drawing else None,
                                             sheet["row_heights"], sheet["highlights"]))
            if sheet["hyperlinks"] or drawing:
                archive.writestr(f"xl/worksheets/_rels/sheet{index}.xml.rels",
                                 sheet_rels_xml(sheet, drawing, sheet_drawing_number))
            if drawing:
                archive.writestr(f"xl/drawings/drawing{sheet_drawing_number}.xml",
                                 _drawing_xml(drawing["anchors"],
                                              [f"rId{position}" for position in
                                               range(1, len(drawing["rels"]) + 1)]))
                rels = "".join(
                    f'<Relationship Id="rId{position}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
                    f'Target="../media/{name}"/>'
                    for position, name in enumerate(drawing["rels"], start=1))
                archive.writestr(f"xl/drawings/_rels/drawing{sheet_drawing_number}.xml.rels",
                                 '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                                 '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                                 f"{rels}</Relationships>")
        for key in media_parts:
            media_name, _, data = media_index[key]
            archive.writestr(f"xl/media/{media_name}", data)


# ---------------------------------------------------------------- 字段别名

ALIASES = {
    "date": ["date", "日期", "报告日期", "统计日期", "数据日期", "时间", "日期时间", "reportdate", "statdate", "day",
             "费用发生时间", "费用发生时间costincurred", "计费时间", "costincurred", "账单日期",
             "交易日", "单据日期", "交易日期", "开单日期"],
    "sku": ["sku", "商品编码", "商家编码", "店铺sku", "sellersku", "msku", "子sku", "货号", "商品货号", "itemid",
            "客户商品编码", "客户商品编码sellersku", "商品编号fopsku", "商品编号"],
    "asin": ["asin", "子asin", "listingid", "listing", "产品asin"],
    "product_name": ["商品名称", "品名", "产品名称", "title", "标题", "productname", "商品名称skuname"],
    "spec": ["规格", "颜色尺码", "变体", "variation", "spec", "属性"],
    "platform": ["平台", "渠道", "channel", "platform", "销售平台", "站点平台"],
    "site": ["site", "站点", "国家", "市场", "marketplace", "country", "国家站点", "地区", "销售国家"],
    "category": ["类目", "分类", "品类", "类别", "一级类目", "二级类目", "category", "商品类目",
                 "平台类目", "产品类别"],
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
    "unit_price": ["单价", "采购单价", "供货价", "报价", "unitprice", "price", "含税单价",
                   "进价", "进货价", "拿货价", "成本单价"],
    "amount": ["金额", "小计", "行金额", "总价", "amount", "subtotal", "合计金额"],
    "unit": ["单位", "unit", "计量单位"],
    "moq": ["moq", "起订量", "最小起订量", "minimumorderqty"],
    "lead_time_days": ["交期", "生产周期", "交期天数", "leadtime", "leadtime days", "备货周期"],
    "warehouse": ["仓库", "入库仓", "目的仓", "warehouse", "收货仓",
                  "仓库名称", "仓库编号", "仓库名称warehousename", "仓库编号warehouseno"],
    "expected_arrival": ["期望到仓", "到仓日期", "期望到货日期", "expectedarrival", "要求到仓日"],
    "remark": ["备注", "说明", "remark", "note", "notes", "备注notes"],
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
    "tax_rate": ["税率", "vat", "vat税率", "taxrate", "税费率", "gst", "税率taxrate"],
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
    "speech_rate": ["语速", "语速上限", "口播语速", "语速基线", "每秒字数", "每秒词数",
                    "speechrate", "speech_rate"],
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

    # ---- 物流 / 仓储费用账单（海外仓、3PL、头程尾程结算单）----
    "fee_type": ["费用类型", "费用类型typeoffee", "计费类型"],
    "billing_event": ["事件名称", "事件名称event"],
    "billing_product": ["计费产品", "计费产品billingproduct"],
    "billing_item": ["计费项", "计费项名称", "计费项billingitems", "计费项名称billingitems"],
    "clue_no": ["线索号", "线索号cluenumber", "cluenumber"],
    "settlement_amount": ["结算币种含税金额", "结算币种含税金额amountofsettlementcurrencytaxincluded",
                          "amountofsettlementcurrencytaxincluded", "应付含税金额", "含税应结金额"],
    "settlement_amount_ex_tax": ["结算币种不含税金额", "结算币种不含税金额settlementcurrencyamountexcludingtax",
                                 "settlementcurrencyamountexcludingtax"],
    "settlement_tax": ["结算币种税额", "结算币种税额currencyofsettlementtaxamount",
                       "currencyofsettlementtaxamount"],
    "quotation_amount": ["报价币种含税金额", "报价币种含税金额amountofquotationcurrencytaxincluded",
                         "amountofquotationcurrencytaxincluded", "报价含税金额"],
    "quotation_amount_ex_tax": ["报价币种不含税金额", "报价币种不含税金额quotedcurrencyamountexcludingtax",
                                "quotedcurrencyamountexcludingtax", "报价不含税金额"],
    "quotation_tax": ["报价币种税额", "报价币种税额currencyofquotationtaxamount",
                      "currencyofquotationtaxamount"],
    "quotation_currency": ["报价币种", "报价币种quotationcurrency"],
    "settlement_currency": ["结算币种settlementcurrency", "结算货币"],   # 短名「结算币种」留给 currency，避免与既有口径冲突
    "exchange_rate": ["汇率", "汇率exchangerate", "exchangerate"],
    "billing_weight": ["计费重量", "计费重量billingweight"],
    "billing_volume": ["计费体积", "计费体积billingvolume"],
    "actual_pallets": ["实际托数", "实际托数actualnumberofpallets"],
    "package_qty": ["包裹数", "包裹数packagequantity", "卡派总箱数", "卡派总箱数totalcartonquantitypertruck"],
    "customer_code": ["客户编码", "客户编码paymentsaccountno", "paymentsaccountno", "货主编号ownerno"],
    "customer_name": ["客户名称", "客户名称customername", "货主名称nameoofowner"],
    "destination_country": ["目的国家", "目的国家destinationcounty", "destinationcountry"],
    "origin_country": ["始发国家", "始发国家originatingcountry"],
    "service_product_code": ["服务产品编码", "服务产品编码serviceproductcode"],
    "service_product_name": ["服务产品名称", "服务产品名称serviceproductname"],
    "outbound_order_no": ["出库单号", "出库单号fopoutboundorderno", "fopoutboundorderno"],
    "waybill_no": ["运单号", "fs运单号", "fs运单号fsorderno", "fsorderno", "承运商主运单号waybillcode"],
    # 手写单据 / 收付台账场景（ecom-receipt-ledger）
    "direction": ["业务方向", "方向", "单据方向", "业务类型", "单据类型", "收支方向", "采销方向", "业务",
                  "收支", "收付方向", "direction", "businesstype", "tradetype", "type"],
    "doc_no": ["单据号", "单据编号", "票号", "单号", "凭证号", "流水号", "receiptno", "docno",
               "documentno", "billno", "voucherno", "serialno"],
    "item_raw": ["手写原文", "品名原文", "原文", "识别原文", "手写品名", "潦草原文", "未标准化品名",
                 "itemraw", "rawitem", "rawname", "ocrtext"],
    "item_std": ["标准品名", "标准名称", "标准型号", "标准化品名", "标准商品名", "标准库名称",
                 "itemstd", "stditem", "standardname", "normalizedname"],
    "amount_written": ["手写金额", "单据金额", "票面金额", "手写小计", "手写总额", "手写字迹金额",
                       "amountwritten", "writtenamount", "handwrittenamount"],
    "amount_calc": ["系统金额", "核算金额", "计算金额", "系统小计", "amountcalc", "computedamount",
                    "calculatedamount"],
    "diff": ["差异", "差额", "金额差异", "差异金额", "diff", "variance", "difference"],
    "photo_path": ["凭证", "凭证照片", "凭证图片", "原始照片", "原始单据", "照片", "图片", "附件",
                   "凭证路径", "单据图片", "photopath", "photo", "image", "attachment", "receiptimage"],
    "confidence": ["置信度", "识别置信度", "ocr置信度", "识别度", "可信度", "confidence",
                   "ocrconfidence", "score"],
    "check_status": ["校验状态", "核对状态", "复核状态", "checkstatus", "checkresult", "reviewstatus"],
    "supplier_name": ["供应商", "供应商名称", "供货商", "供货方", "supplier", "vendor", "suppliername"],
    "counterparty": ["往来单位", "交易对象", "对方单位", "客户", "买家", "卖家", "counterparty", "party"],
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
