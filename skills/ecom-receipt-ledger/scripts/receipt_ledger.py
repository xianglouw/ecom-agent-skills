#!/usr/bin/env python3
"""手写单据台账：简写标准化 → 自动算账 → 采购/销售日结 → 凭证关联。

用法示例：
  python3 receipt_ledger.py 单据明细.csv --alias 简写映射.csv --photos-dir photos \
      --embed-photos --default-year 2026 \
      --out out/ledger.csv --out-xlsx out/ledger.xlsx --out-md out/ledger.md \
      --out-json out/ledger.json --quarantine out/bad_rows.csv

输入是「单据识别结果表」（由多模态模型按 references/field-schema.md 的字段从手写单据照片提取），
不是照片本身。脚本做四件事：
  1. 简写标准化：手写原文按映射表转标准品名，未命中的不猜、单独进「待映射」清单；
  2. 自动算账：数量 × 单价 = 系统金额，与手写金额比对，差异分级标红；
  3. 日结汇总：按日期 × 采购/销售归集，出日销售总额、日采购总额与净收益；
  4. 凭证关联：原始单据照片写成可点击超链接，可按需嵌入缩略图。
只读输入，只写参数指定文件。
"""

import argparse
import datetime
import os
import shutil
import subprocess
import sys

import sheetio
from sheetio import clean_text, col_letter, file_href, norm_key, to_date, to_number, write_csv

PURCHASE_WORDS = ["采购", "进货", "入库", "买入", "收购", "进仓", "应付", "收货", "purchase", "buy",
                  "payable", "inbound", "expense", "payout"]
SALES_WORDS = ["销售", "出货", "出库", "卖出", "售出", "售卖", "发货", "应收", "回款", "sale", "sales",
               "sell", "outbound", "receivable", "income", "revenue"]

DETAIL_HEADERS = ["行号", "日期", "业务方向", "单据号", "手写原文", "标准品名", "类别", "规格", "数量", "单价",
                  "单位", "手写金额", "系统金额", "差异", "校验状态", "问题", "识别置信度", "凭证",
                  "凭证路径", "备注"]
DAILY_HEADERS = ["日期", "采购笔数", "采购数量", "采购金额", "销售笔数", "销售数量", "销售金额",
                 "净收益", "净收益率", "差异笔数", "待复核笔数", "凭证数"]
MONTHLY_HEADERS = ["月份", "采购笔数", "采购金额", "销售笔数", "销售金额", "净收益", "净收益率",
                   "差异笔数", "待复核笔数"]
ISSUE_HEADERS = ["行号", "日期", "业务方向", "手写原文", "手写金额", "系统金额", "差异", "问题", "建议动作"]
ALIAS_HEADERS = ["手写原文", "出现次数", "涉及金额", "示例日期", "建议动作"]
PHOTO_HEADERS = ["日期", "单据号", "业务方向", "手写原文", "金额", "凭证文件", "缩略图", "凭证状态"]

ACTION_BY_STATUS = {
    "一致": "",
    "小额差异": "核对原始单据的四舍五入或抹零，确认后按系统金额入账",
    "金额不符": "逐笔回看原始单据，确认是识别错误还是单据本身算错",
    "金额缺失": "单据未写金额，按 数量×单价 入账，抽查原单补录",
    "无法复核": "缺数量或单价，无法复核金额，需人工补齐后重算",
    "疑似重复": "确认是否是同一笔重复录入，是则删除一行",
    "方向缺失": "单据未写采购/销售，人工判定后再入账",
}


def normalize_direction(value):
    """把各种写法归到 采购 / 销售；判不出来返回 None（不猜）。"""
    key = norm_key(value)
    if not key:
        return None
    for word in PURCHASE_WORDS:
        if word in key:
            return "采购"
    for word in SALES_WORDS:
        if word in key:
            return "销售"
    return None


def load_alias(path):
    """读简写映射表：简写 / 标准品名（必填）+ 类别 / 规格 / 备注（可选）。"""
    if not path:
        return {}
    headers, body = sheetio.read_table(path)
    columns = sheetio.column_map(headers, ["item_raw", "item_std", "category", "spec", "remark"],
                                 extra_aliases={"item_raw": ["简写", "手写", "别名", "简称", "原写法"],
                                                "item_std": ["标准品名", "标准名称", "标准写法", "规范名称"]})
    if "item_raw" not in columns or "item_std" not in columns:
        raise ValueError(f"映射表 {path} 需要「简写/手写原文」与「标准品名」两列，当前表头：{headers}")
    mapping = {}
    for row in body:
        alias = clean_text(row[columns["item_raw"]])
        standard = clean_text(row[columns["item_std"]])
        if not alias or not standard:
            continue
        entry = {"std": standard,
                 "category": clean_text(row[columns["category"]]) if "category" in columns else "",
                 "spec": clean_text(row[columns["spec"]]) if "spec" in columns else ""}
        mapping[norm_key(alias)] = entry
    return mapping


def match_alias(text, mapping):
    """先整串精确匹配，再逐个词匹配（处理「14pm改17pm 屏幕」这类组合写法）。"""
    key = norm_key(text)
    if not key:
        return None
    if key in mapping:
        return mapping[key], "exact"
    best = None
    for alias_key, entry in mapping.items():
        if alias_key and alias_key in key:
            if best is None or len(alias_key) > len(best[0]):
                best = (alias_key, entry)
    if best:
        return best[1], "partial"
    return None


def parse_photo(raw, photos_dir, photos_base):
    """定位凭证照片，返回 (文件名, 本地绝对路径, 超链接目标)；找不到给 None。"""
    value = clean_text(raw)
    if not value:
        return None
    name = value.replace("\\", "/").split("/")[-1]
    candidates = []
    if os.path.isabs(value):
        candidates.append(value)
    else:
        candidates.append(value)
        if photos_dir:
            candidates.append(os.path.join(photos_dir, value))
            candidates.append(os.path.join(photos_dir, name))
    local = next((path for path in candidates if os.path.isfile(path)), None)
    if photos_base and name:
        target = photos_base.rstrip("/") + "/" + name
    elif local:
        target = file_href(local)
    elif value.lower().startswith(("http://", "https://")):
        target = value
    else:
        target = None
    return {"name": name or value, "local": local, "href": target}


def make_thumbnail(path, cache_dir, max_side):
    """用系统图像工具生成缩略图（macOS sips，可顺带把 HEIC 转成 JPEG）；系统没有工具返回 None。"""
    tool = shutil.which("sips")
    if not tool:
        return None
    os.makedirs(cache_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(path))[0]
    target = os.path.join(cache_dir, f"{stem}_thumb{max_side}.jpg")
    try:
        if os.path.exists(target) and os.path.getmtime(target) >= os.path.getmtime(path):
            return target
        subprocess.run([tool, "-s", "format", "jpeg", "-Z", str(max_side), path, "--out", target],
                       check=True, capture_output=True)
    except (subprocess.CalledProcessError, OSError):
        return None
    return target if os.path.exists(target) else None


def build_rows(headers, body, columns, args, mapping):
    """逐行归一、标准化、算账；返回 (明细行, 隔离行, 待映射, 问题行)。"""
    rows, quarantined, unmatched, issues = [], [], {}, []
    seen = {}
    today_year = args.default_year or datetime.date.today().year

    def cell(raw, field):
        position = columns.get(field)
        return raw[position] if position is not None and position < len(raw) else ""

    for index, raw in enumerate(body, start=2):
        problems = []
        date = to_date(cell(raw, "date"), default_year=today_year)
        if not date:
            raw_date = clean_text(cell(raw, "date"))
            if raw_date and not sheetio._FIELD_YEAR.search(sheetio.to_halfwidth(raw_date)):
                problems.append("日期缺年份")
        direction = normalize_direction(cell(raw, "direction"))
        qty = to_number(cell(raw, "qty"))
        if qty is None:
            qty = to_number(cell(raw, "units"))      # 「件数」这类表头会落到销量字段上

        unit_price = to_number(cell(raw, "unit_price"))
        written = to_number(cell(raw, "amount_written"))
        if written is None:
            written = to_number(cell(raw, "amount"))
        item_raw = clean_text(cell(raw, "item_raw")) or clean_text(cell(raw, "product_name"))
        item_std = clean_text(cell(raw, "item_std"))
        spec = clean_text(cell(raw, "spec"))
        confidence = to_number(cell(raw, "confidence"))
        if confidence is not None and confidence > 1:
            confidence = confidence / 100.0
        photo = parse_photo(cell(raw, "photo_path"), args.photos_dir, args.photos_base)

        if not date and not item_raw and written is None:
            continue
        reasons = []
        if not date:
            reasons.append("日期无法识别，未进入日结")
        if not direction:
            reasons.append("采购/销售方向无法判定")
        if item_raw == "" and written is None:
            reasons.append("品名与金额都为空")
        if reasons:
            quarantined.append({"row": index, "date": date or "", "direction": direction or "",
                                "item_raw": item_raw, "written": written, "reason": "；".join(reasons)})
            continue

        entry, hit = (None, None)
        if not item_std:
            matched = match_alias(item_raw, mapping)
            if matched:
                entry, hit = matched
                item_std = entry["std"]
        else:
            entry = {"std": item_std, "category": clean_text(cell(raw, "category")), "spec": ""}
            hit = "given"
        category = (entry or {}).get("category", "") or clean_text(cell(raw, "category"))
        if entry and entry.get("spec") and not spec:
            spec = entry["spec"]
        if not item_std:
            key = norm_key(item_raw) or item_raw
            bucket = unmatched.setdefault(key, {"raw": item_raw, "count": 0, "amount": 0.0, "date": date})
            bucket["count"] += 1
            bucket["amount"] += written or 0.0
            problems.append("简写未映射")

        status = "一致"
        if qty is not None and unit_price is not None:
            calc = round(qty * unit_price, 2)
        else:
            calc = None
        diff = None
        if written is None:
            status = "金额缺失"
            if calc is None:
                status = "无法复核"
                problems.append("缺数量或单价且单据未写金额")
            else:
                written = calc
                problems.append("单据未写金额，按 数量×单价 补齐")
        elif calc is None:
            status = "无法复核"
            problems.append("缺数量或单价，无法复核金额")
        else:
            diff = round(written - calc, 2)
            tolerance = args.tolerance
            if abs(diff) <= tolerance:
                status = "一致"
            elif abs(diff) <= max(1.0, 0.01 * abs(calc)):
                status = "小额差异"
                problems.append(f"相差 {diff:+.2f}（抹零/四舍五入级）")
            else:
                status = "金额不符"
                problems.append(f"手写金额与 数量×单价 相差 {diff:+.2f}")

        if confidence is not None and confidence < args.low_confidence:
            problems.append(f"识别置信度偏低（{confidence:.2f}）")
        if not photo or not photo["href"]:
            problems.append("缺凭证照片")

        duplicate_key = (date, direction, norm_key(item_raw), qty, unit_price)
        if duplicate_key in seen:
            status = "疑似重复"
            problems.append(f"与第 {seen[duplicate_key]} 行内容相同")
        else:
            seen[duplicate_key] = index

        row = {"row": index, "date": date, "direction": direction, "doc_no": clean_text(cell(raw, "doc_no")),
               "item_raw": item_raw, "item_std": item_std, "category": category, "spec": spec,
               "qty": qty, "unit_price": unit_price, "unit": clean_text(cell(raw, "unit")) or args.unit,
               "written": written, "calc": calc, "diff": diff, "status": status,
               "problems": problems, "confidence": confidence, "photo": photo,
               "remark": clean_text(cell(raw, "remark"))}
        rows.append(row)
        if problems or status not in ("一致",):
            issues.append(row)
    return rows, quarantined, unmatched, issues


def summarize(rows):
    """日结与月结：采购、销售、净收益、差异与凭证计数。"""
    daily = {}

    def bucket(container, key):
        return container.setdefault(key, {"rows": 0, "purchase_qty": 0.0, "sales_qty": 0.0,
                                          "purchase": 0.0, "sales": 0.0, "purchase_rows": 0,
                                          "sales_rows": 0, "diffs": 0, "issues": 0, "photos": 0,
                                          "purchase_std": {}, "sales_std": {}})

    for row in rows:
        amount = row["written"] if row["written"] is not None else 0.0
        for container, key in ((daily, row["date"]), (daily, row["date"][:7])):
            item = bucket(container, key)
            item["rows"] += 1
            if row["direction"] == "采购":
                item["purchase"] += amount
                item["purchase_rows"] += 1
                item["purchase_qty"] += row["qty"] or 0.0
                if row["item_std"]:
                    item["purchase_std"][row["item_std"]] = item["purchase_std"].get(row["item_std"], 0) + amount
            elif row["direction"] == "销售":
                item["sales"] += amount
                item["sales_rows"] += 1
                item["sales_qty"] += row["qty"] or 0.0
                if row["item_std"]:
                    item["sales_std"][row["item_std"]] = item["sales_std"].get(row["item_std"], 0) + amount
            if row["status"] in ("小额差异", "金额不符"):
                item["diffs"] += 1
            if row["problems"]:
                item["issues"] += 1
            if row["photo"] and row["photo"]["href"]:
                item["photos"] += 1
    day_rows = sorted((key, value) for key, value in daily.items() if len(key) == 10)
    month_rows = sorted((key, value) for key, value in daily.items() if len(key) == 7)
    return day_rows, month_rows


def write_markdown(path, args, rows, day_rows, month_rows, quarantined, unmatched, issues, totals):
    lines = ["# 手写单据日结对账报告", "",
             f"- 数据来源：`{args.input}`" + (f"（工作表 {args.sheet}）" if args.sheet else ""),
             f"- 生成时间：{datetime.datetime.now().astimezone().isoformat(timespec='seconds')}",
             f"- 统计区间：{totals['first_date']} ~ {totals['last_date']}（{len(day_rows)} 天，共 {len(rows)} 笔）",
             ""]
    lines += ["## 一、总账", "",
              "| 项目 | 笔数 | 金额 |", "|---|---|---|",
              f"| 采购 | {totals['purchase_rows']} | {totals['purchase']:,.2f} |",
              f"| 销售 | {totals['sales_rows']} | {totals['sales']:,.2f} |",
              f"| 净收益 | — | {totals['net']:,.2f}（{totals['net_margin'] * 100:.1f}%）|", ""]
    lines += ["## 二、日结明细", "",
              "| 日期 | 采购金额 | 销售金额 | 净收益 | 净收益率 | 笔数 | 差异/待复核 |",
              "|---|---|---|---|---|---|---|"]
    for key, value in day_rows:
        net = value["sales"] - value["purchase"]
        margin = f"{net / value['sales'] * 100:.1f}%" if value["sales"] else "—"
        lines.append(f"| {key} | {value['purchase']:,.2f} | {value['sales']:,.2f} | {net:,.2f} | "
                     f"{margin} | {value['rows']} | {value['diffs']} |")
    lines += ["", "## 三、计算校验", "",
              f"- 一致：{totals['status']['一致']} 笔",
              f"- 小额差异：{totals['status']['小额差异']} 笔（抹零/四舍五入级，可接受）",
              f"- 金额不符：{totals['status']['金额不符']} 笔，差异合计 {totals['mismatch_amount']:,.2f}（**需人工复核**）",
              f"- 金额缺失（按 数量×单价 补齐）：{totals['status']['金额缺失']} 笔",
              f"- 无法复核（缺数量或单价）：{totals['status']['无法复核']} 笔",
              f"- 疑似重复：{totals['status']['疑似重复']} 笔", ""]
    if issues:
        lines += ["## 四、需人工确认清单（按金额差异排序）", "",
                  "| 行号 | 日期 | 方向 | 手写原文 | 手写金额 | 系统金额 | 差异 | 问题 |",
                  "|---|---|---|---|---|---|---|---|"]
        for row in sorted(issues, key=lambda item: -abs(item["diff"] or 0))[:40]:
            lines.append(f"| {row['row']} | {row['date']} | {row['direction']} | {row['item_raw']} | "
                         f"{show(row['written'])} | {show(row['calc'])} | {show(row['diff'])} | "
                         f"{'；'.join(row['problems'])} |")
        if len(issues) > 40:
            lines.append(f"| … | | | | | | | 另有 {len(issues) - 40} 笔见台账「异常行」工作表 |")
        lines.append("")
    if unmatched:
        lines += ["## 五、待映射的手写简写", "",
                  "| 手写原文 | 出现次数 | 涉及金额 | 建议 |", "|---|---|---|---|"]
        for item in sorted(unmatched.values(), key=lambda value: -value["count"])[:30]:
            lines.append(f"| {item['raw']} | {item['count']} | {item['amount']:,.2f} | "
                         "补进简写映射表后重跑 |")
        lines.append("")
    if quarantined:
        lines += ["## 六、被隔离的行（未进入日结）", "",
                  "| 行号 | 手写原文 | 原因 |", "|---|---|---|"]
        for item in quarantined[:30]:
            lines.append(f"| {item['row']} | {item['item_raw']} | {item['reason']} |")
        lines.append("")
    lines += ["## 七、口径与假设", ""]
    for note in totals["assumptions"]:
        lines.append(f"- {note}")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def show(value):
    return "" if value is None else f"{value:,.2f}"


def ensure_dirs(*paths):
    """产物目录不存在时自动建，省得因为忘记 mkdir 而白跑一次。"""
    for path in paths:
        if path:
            parent = os.path.dirname(os.path.abspath(path))
            if parent:
                os.makedirs(parent, exist_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description="手写单据台账：标准化、算账校验、采销日结与凭证关联")
    parser.add_argument("input", help="单据识别结果表（.csv/.xlsx，字段见 references/field-schema.md）")
    parser.add_argument("--sheet", default=None, help="xlsx 工作表名或序号")
    parser.add_argument("--header-row", type=int, default=1, help="表头行号，默认 1")
    parser.add_argument("--alias", default=None, help="简写映射表（.csv：简写,标准品名,类别,规格）")
    parser.add_argument("--photos-dir", default=None, help="凭证照片目录；表里只写文件名时按此目录找")
    parser.add_argument("--photos-base", default=None, help="凭证在线地址前缀（有则超链接指向云端）")
    parser.add_argument("--embed-photos", action="store_true", help="在凭证索引表内嵌缩略图")
    parser.add_argument("--thumb-max", type=int, default=480, help="缩略图长边像素，默认 480")
    parser.add_argument("--max-embed", type=int, default=200, help="最多嵌入多少张缩略图，默认 200")
    parser.add_argument("--tolerance", type=float, default=0.01, help="金额比对容差，默认 0.01")
    parser.add_argument("--low-confidence", type=float, default=0.75, help="识别置信度告警线，默认 0.75")
    parser.add_argument("--default-year", type=int, default=None,
                        help="手写日期只有月日时补的年份，默认取当年")
    parser.add_argument("--unit", default="台", help="默认计量单位，默认「台」")
    parser.add_argument("--map", action="append", default=[], help="原列名=标准字段，可重复")
    parser.add_argument("--out", default=None, help="明细 CSV")
    parser.add_argument("--out-xlsx", default=None, help="Excel 工作簿（明细/日结/月结/异常行/待映射/凭证索引）")
    parser.add_argument("--out-md", default=None, help="Markdown 对账报告")
    parser.add_argument("--out-json", default=None, help="JSON 输出信封")
    parser.add_argument("--quarantine", default=None, help="隔离行 CSV")
    args = parser.parse_args(argv)
    if not any([args.out, args.out_xlsx, args.out_md, args.out_json, args.quarantine]):
        parser.error("至少要指定一个产物：--out / --out-xlsx / --out-md / --out-json / --quarantine")

    try:
        headers, body = sheetio.read_table(args.input, sheet=args.sheet or 1, header_row=args.header_row)
    except (OSError, ValueError) as error:
        sheetio.emit(sheetio.make_envelope("receipt_ledger", "blocked", 0.0, {"error": str(error)},
                                           [sheetio.flag("high", "input_error", str(error),
                                                         "确认文件路径与格式")]), out_json=args.out_json)
        return 2
    if not headers:
        sheetio.emit(sheetio.make_envelope("receipt_ledger", "blocked", 0.0,
                                           {"error": "空表或未读到表头"},
                                           [sheetio.flag("high", "empty_input", "没有读到表头",
                                                         "确认文件格式或 --header-row")]),
                    out_json=args.out_json)
        return 2
    extra = sheetio.apply_mapping(args.map) if args.map else {}
    fields = ["date", "direction", "doc_no", "item_raw", "item_std", "category", "spec", "product_name",
              "qty", "units", "unit", "unit_price", "amount_written", "amount", "photo_path", "confidence",
              "remark"]
    columns = sheetio.column_map(headers, fields)
    for name, canon in extra.items():
        for index, header in enumerate(headers):
            if norm_key(header) == name:
                columns[canon] = index
    if not columns:
        sheetio.emit(sheetio.make_envelope("receipt_ledger", "blocked", 0.0,
                                           {"error": "没认出任何标准字段", "headers": headers},
                                           [sheetio.flag("high", "no_field_recognized",
                                                         f"表头 {headers} 里没认出任何标准字段",
                                                         "用 --map 原列名=标准字段 手工指定")]),
                    out_json=args.out_json)
        return 2

    ensure_dirs(args.out, args.out_xlsx, args.out_md, args.out_json, args.quarantine)
    try:
        mapping = load_alias(args.alias)
    except (OSError, ValueError) as error:
        sheetio.emit(sheetio.make_envelope("receipt_ledger", "blocked", 0.0, {"error": str(error)},
                                           [sheetio.flag("high", "alias_error", str(error),
                                                         "确认映射表有「简写」与「标准品名」两列")]),
                    out_json=args.out_json)
        return 2
    rows, quarantined, unmatched, issues = build_rows(headers, body, columns, args, mapping)
    if not rows:
        if quarantined and args.quarantine:
            write_csv(args.quarantine, ["行号", "日期", "业务方向", "手写原文", "手写金额", "隔离原因"],
                      [[item["row"], item["date"], item["direction"], item["item_raw"],
                        show(item["written"]), item["reason"]] for item in quarantined])
        sheetio.emit(sheetio.make_envelope(
            "receipt_ledger", "blocked", 0.0,
            {"input": args.input, "rows_in": len(body), "rows_out": 0, "quarantined": len(quarantined),
             "detected_columns": sorted(columns), "quarantined_sample": quarantined[:10]},
            [sheetio.flag("high", "all_rows_quarantined",
                          f"{len(body)} 行全部被隔离，没有一笔能入账",
                          "看隔离原因：多半是日期或采购/销售方向没识别到；用 --map 指定这两列")]),
            out_json=args.out_json)
        return 2
    day_rows, month_rows = summarize(rows)

    totals = {
        "first_date": min((row["date"] for row in rows), default=""),
        "last_date": max((row["date"] for row in rows), default=""),
        "purchase": sum(row["written"] or 0 for row in rows if row["direction"] == "采购"),
        "sales": sum(row["written"] or 0 for row in rows if row["direction"] == "销售"),
        "purchase_rows": sum(1 for row in rows if row["direction"] == "采购"),
        "sales_rows": sum(1 for row in rows if row["direction"] == "销售"),
        "status": {name: sum(1 for row in rows if row["status"] == name)
                   for name in ("一致", "小额差异", "金额不符", "金额缺失", "无法复核", "疑似重复")},
        "mismatch_amount": sum(abs(row["diff"] or 0) for row in rows if row["status"] == "金额不符"),
        "photos_linked": sum(1 for row in rows if row["photo"] and row["photo"]["href"]),
        "photos_missing": sum(1 for row in rows if not row["photo"] or not row["photo"]["href"]),
        "低置信度": sum(1 for row in rows if row["confidence"] is not None
                        and row["confidence"] < args.low_confidence),
        "assumptions": [f"金额口径：{args.unit}为单位、单价含税与否沿用单据写法，未做税额拆分",
                        f"日期：手写只写月日时按 {args.default_year or datetime.date.today().year} 年补全",
                        "采购/销售按单据上的方向字段归类，方向判定不了的行走隔离清单不参与日结",
                        f"金额比对容差 {args.tolerance}；差异 ≤ max(1 元, 系统金额的 1%) 记为小额差异"],
    }
    totals["net"] = totals["sales"] - totals["purchase"]
    totals["net_margin"] = (totals["net"] / totals["sales"]) if totals["sales"] else 0.0

    flags = []
    if quarantined:
        flags.append(sheetio.flag("high", "row_quarantined",
                                  f"{len(quarantined)} 行走无法进入日结（日期或采购/销售方向识别不出）",
                                  "按隔离清单回看原始单据补录后再跑一次"))
    if totals["status"]["金额不符"]:
        flags.append(sheetio.flag("high", "amount_mismatch",
                                  f"{totals['status']['金额不符']} 笔手写金额与 数量×单价 不符，"
                                  f"差异合计 {totals['mismatch_amount']:,.2f}",
                                  "逐笔回看原始单据，确认是识别错误还是单据本身算错"))
    if totals["status"]["无法复核"]:
        flags.append(sheetio.flag("high", "unverifiable",
                                  f"{totals['status']['无法复核']} 笔缺数量或单价，金额无法复核",
                                  "补齐数量/单价后重算，不要直接入账"))
    if not columns.get("direction"):
        flags.append(sheetio.flag("high", "no_direction_column",
                                  "输入表没有业务方向列，采购/销售无法自动区分",
                                  "加一列「业务方向」（采购/销售）或用 --map 指定"))
    if unmatched:
        top = sorted(unmatched.values(), key=lambda value: -value["count"])[:5]
        detail = "、".join(f"{item['raw']}×{item['count']}" for item in top)
        flags.append(sheetio.flag("medium", "alias_unmatched",
                                  f"{sum(item['count'] for item in unmatched.values())} 条简写未命中映射表：{detail}",
                                  "把高频简写补进映射表（references/alias-dictionary.md）后重跑"))
    if totals["status"]["金额缺失"]:
        flags.append(sheetio.flag("medium", "amount_missing",
                                  f"{totals['status']['金额缺失']} 笔单据未写金额，已按 数量×单价 补齐",
                                  "抽查原始单据确认单价无误"))
    if totals["低置信度"]:
        flags.append(sheetio.flag("medium", "low_confidence",
                                  f"{totals['低置信度']} 笔识别置信度低于 {args.low_confidence}",
                                  "对照原始单据复核这些行的品名与数字"))
    if totals["photos_missing"]:
        flags.append(sheetio.flag("medium", "photo_missing",
                                  f"{totals['photos_missing']} 笔没有关联到凭证照片",
                                  "把照片放进 --photos-dir 或补齐照片文件名"))
    if totals["status"]["疑似重复"]:
        flags.append(sheetio.flag("medium", "duplicate_row",
                                  f"{totals['status']['疑似重复']} 笔与前面某行内容完全相同",
                                  "确认是否重复录入，是则删掉一行"))
    if not mapping:
        flags.append(sheetio.flag("medium", "no_alias_table",
                                  "没提供简写映射表，手写原文未做标准化",
                                  "用 --alias 提供映射表，后期按标准品名统计库存与毛利"))
    if len(quarantined) > len(rows) * 0.2 and rows:
        flags.append(sheetio.flag("high", "low_parse_rate",
                                  f"隔离比例偏高（{len(quarantined)}/{len(quarantined) + len(rows)}）",
                                  "先修拍照质量与识别提示词，再重跑"))

    levels = {item["level"] for item in flags}
    confidence = 0.95
    if "high" in levels:
        confidence = min(confidence, 0.68)
    elif "medium" in levels:
        confidence = min(confidence, 0.82)
    if quarantined:
        confidence = min(confidence, 0.9)

    envelope = sheetio.make_envelope(
        "receipt_ledger", "partial" if flags else "ok", confidence,
        {"input": args.input, "rows_in": len(body), "rows_out": len(rows),
         "quarantined": len(quarantined), "date_range": [totals["first_date"], totals["last_date"]],
         "days": len(day_rows),
         "purchase": {"rows": totals["purchase_rows"], "amount": round(totals["purchase"], 2)},
         "sales": {"rows": totals["sales_rows"], "amount": round(totals["sales"], 2)},
         "net": round(totals["net"], 2), "net_margin": round(totals["net_margin"], 4),
         "calc_check": dict(totals["status"], mismatch_amount=round(totals["mismatch_amount"], 2)),
         "alias": {"provided": bool(mapping), "entries": len(mapping),
                   "matched": sum(1 for row in rows if row["item_std"]),
                   "unmatched": sum(1 for row in rows if not row["item_std"]),
                   "top_unmatched": [{"item_raw": item["raw"], "count": item["count"],
                                      "amount": round(item["amount"], 2)}
                                     for item in sorted(unmatched.values(), key=lambda v: -v["count"])[:10]]},
         "photos": {"linked": totals["photos_linked"], "missing": totals["photos_missing"]},
         "daily": [{"date": key, "purchase": round(value["purchase"], 2), "sales": round(value["sales"], 2),
                    "net": round(value["sales"] - value["purchase"], 2), "rows": value["rows"],
                    "issues": value["issues"]} for key, value in day_rows]},
        flags=flags,
        sources=[{"ref": f"{args.input}（单据识别结果）", "as_of": totals["last_date"] or ""}]
        + ([{"ref": args.alias, "as_of": ""}] if args.alias else []),
        assumptions=totals["assumptions"])

    if args.quarantine and quarantined:
        write_csv(args.quarantine, ["行号", "日期", "业务方向", "手写原文", "手写金额", "隔离原因"],
                  [[item["row"], item["date"], item["direction"], item["item_raw"],
                    show(item["written"]), item["reason"]] for item in quarantined])

    detail_rows, hyperlinks = [], []
    for position, row in enumerate(rows, start=2):
        photo = row["photo"] or {"name": "", "local": None, "href": None}
        detail_rows.append([row["row"], row["date"], row["direction"], row["doc_no"], row["item_raw"],
                            row["item_std"], row["category"], row["spec"], row["qty"], row["unit_price"],
                            row["unit"], row["written"], row["calc"], row["diff"], row["status"],
                            "；".join(row["problems"]), row["confidence"], photo["name"],
                            photo["local"] or "", row["remark"]])
        if photo["href"]:
            hyperlinks.append({"ref": f"{col_letter(18)}{position}", "target": photo["href"],
                               "tooltip": f"查看 {photo['name']} 原始单据"})

    daily_table = [[key, value["purchase_rows"], round(value["purchase_qty"], 2),
                    round(value["purchase"], 2), value["sales_rows"], round(value["sales_qty"], 2),
                    round(value["sales"], 2), round(value["sales"] - value["purchase"], 2),
                    round((value["sales"] - value["purchase"]) / value["sales"], 4) if value["sales"] else "",
                    value["diffs"], value["issues"], value["photos"]] for key, value in day_rows]
    monthly_table = [[key, value["purchase_rows"], round(value["purchase"], 2), value["sales_rows"],
                      round(value["sales"], 2), round(value["sales"] - value["purchase"], 2),
                      round((value["sales"] - value["purchase"]) / value["sales"], 4) if value["sales"] else "",
                      value["diffs"], value["issues"]] for key, value in month_rows]

    if args.out:
        write_csv(args.out, DETAIL_HEADERS, detail_rows)
    if args.out_md:
        write_markdown(args.out_md, args, rows, day_rows, month_rows, quarantined, unmatched, issues, totals)

    if args.out_xlsx:
        photo_rows, photo_hyperlinks, photo_images, row_heights = [], [], [], {}
        thumbnail_dir = os.path.join(os.path.dirname(os.path.abspath(args.out_xlsx)), "_thumbs")
        embedded = skipped = 0
        for position, row in enumerate(rows, start=2):
            photo = row["photo"]
            status = "已关联" if photo and photo["href"] else "缺照片"
            photo_rows.append([row["date"], row["doc_no"], row["direction"], row["item_raw"],
                               row["written"], photo["name"] if photo else "", "", status])
            if photo and photo["href"]:
                photo_hyperlinks.append({"ref": f"F{position}", "target": photo["href"],
                                         "tooltip": "打开原始单据照片"})
            if not (args.embed_photos and photo and photo["local"]):
                continue
            if embedded >= args.max_embed:
                skipped += 1
                continue
            thumbnail = make_thumbnail(photo["local"], thumbnail_dir, args.thumb_max)
            if thumbnail is None and os.path.getsize(photo["local"]) > 300 * 1024:
                skipped += 1
                continue
            photo_images.append({"path": thumbnail or photo["local"], "row": position, "col": 7,
                                 "max_width": 150, "max_height": 110})
            row_heights[position] = 86
            embedded += 1
        if skipped:
            flags.append(sheetio.flag("medium", "thumbnail_skipped",
                                      f"{skipped} 张照片没能生成缩略图（超过 {args.max_embed} 张上限或原图过大）",
                                      "用 --thumb-max 调整缩略图尺寸，或先批量压缩照片"))
        sheets = [
            {"name": "单据明细", "headers": DETAIL_HEADERS, "rows": detail_rows, "hyperlinks": hyperlinks},
            {"name": "日结", "headers": DAILY_HEADERS, "rows": daily_table},
            {"name": "月结", "headers": MONTHLY_HEADERS, "rows": monthly_table},
            {"name": "异常行", "headers": ISSUE_HEADERS,
             "rows": [[row["row"], row["date"], row["direction"], row["item_raw"], row["written"],
                       row["calc"], row["diff"], "；".join(row["problems"]),
                       ACTION_BY_STATUS.get(row["status"], "人工确认")]
                      for row in sorted(issues, key=lambda item: -abs(item["diff"] or 0))]},
            {"name": "待映射简写", "headers": ALIAS_HEADERS,
             "rows": [[item["raw"], item["count"], round(item["amount"], 2), item["date"],
                       "在 alias-dictionary 里补一行标准品名"] for item in
                      sorted(unmatched.values(), key=lambda value: -value["count"])]},
            {"name": "凭证索引", "headers": PHOTO_HEADERS, "rows": photo_rows,
             "hyperlinks": photo_hyperlinks, "images": photo_images, "row_heights": row_heights,
             "column_widths": {4: 30, 6: 22, 7: 23, 8: 10}},
        ]
        sheetio.write_xlsx(args.out_xlsx, [sheet for sheet in sheets if sheet["rows"]])

    sheetio.emit(envelope, out_json=args.out_json)

    summary = (f"读入 {len(body)} 行 → 入账 {len(rows)} 笔，隔离 {len(quarantined)} 行；"
               f"采购 {totals['purchase']:,.2f} / 销售 {totals['sales']:,.2f} / 净收益 {totals['net']:,.2f}")
    print(summary, file=sys.stderr)
    print(f"差异行 {len(issues)} 笔，日结 {len(day_rows)} 天，凭证关联 {totals['photos_linked']}/"
          f"{totals['photos_linked'] + totals['photos_missing']}", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main() or 0)
