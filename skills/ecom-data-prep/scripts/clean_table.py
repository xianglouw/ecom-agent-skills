#!/usr/bin/env python3
"""阶段 2：多来源运营表格清洗与结构化。

用法示例：
  python3 clean_table.py raw.xlsx --out clean.csv --out-json clean.report.json \
      --require sku,price --dedupe-on sku,date --quarantine bad_rows.csv

做的事：表头别名归一、全角半角与空白清洗、金额/比例/日期标准化、空行剔除、
按业务主键去重、必填字段校验并把不合格的行隔离输出。只写 --out/--out-json/--quarantine 指定文件。
"""

import argparse
import os
import sys

import sheetio
from sheetio import clean_text, norm_key, to_date, to_number

NUMERIC_FIELDS = {
    "price", "cost", "spend", "revenue", "total_revenue", "qty", "units", "orders",
    "clicks", "impressions", "amount", "unit_price", "refund", "moq",
    "lead_time_days", "price_min", "price_max",
}
RATE_FIELDS = {"commission_rate", "payment_rate", "tax_rate"}
COUNT_FIELDS = {"qty", "units", "orders", "clicks", "impressions", "moq", "lead_time_days"}
DATE_FIELDS = {"date", "effective_date", "updated_at", "expected_arrival"}
# 费用账单明细金额：平台/3PL 账单常有 4~6 位小数，按原精度输出，不按两位小数四舍五入
PRECISE_FIELDS = {
    "settlement_amount", "settlement_amount_ex_tax", "settlement_tax",
    "quotation_amount", "quotation_amount_ex_tax", "quotation_tax",
    "exchange_rate", "billing_weight", "billing_volume",
}
COERCED_FIELDS = NUMERIC_FIELDS | RATE_FIELDS | DATE_FIELDS | PRECISE_FIELDS
# 数值列合计：写报告用，比率与汇率类不求和
SUM_FIELDS = (NUMERIC_FIELDS | PRECISE_FIELDS) - {"exchange_rate"} - RATE_FIELDS


def _format_value(field, value):
    if field in DATE_FIELDS:
        return to_date(value)
    if field in RATE_FIELDS or field in PRECISE_FIELDS:
        number = to_number(value)
        if number is None:
            return None
        return f"{number:.6f}".rstrip("0").rstrip(".") or "0"
    if field in NUMERIC_FIELDS:
        number = to_number(value)
        if number is None:
            return None
        if field in COUNT_FIELDS and float(number).is_integer():
            return str(int(number))
        return f"{number:.2f}"
    text = clean_text(value)
    return text


def _resolve_names(names, known, known_norm):
    """把 --require / --keep / --dedupe-on 传入的名字解析成实际输出列名。

    兼容三种写法：标准字段原名（clue_no）、去掉下划线与大小写的写法（clueno）、
    原始中英双语列名（线索号 Clue Number / 结算币种含税金额）。
    """
    resolved = []
    for name in names:
        if name in known:
            resolved.append(name)
            continue
        by_canon = sheetio.canonical_field(name)
        if by_canon in known:
            resolved.append(by_canon)
            continue
        resolved.append(known_norm.get(norm_key(name), name))
    return resolved


def build_headers(headers, mapping, dedupe_required):
    renamed = {}
    output = []
    used = set()
    for header in headers:
        key = norm_key(header)
        if key in mapping:
            target = mapping[key]
        else:
            target = sheetio.canonical_field(header)
        if target in used:
            suffix = 2
            while f"{target}_{suffix}" in used:
                suffix += 1
            renamed[header] = f"{target}_{suffix}"
            used.add(f"{target}_{suffix}")
            output.append(f"{target}_{suffix}")
            continue
        used.add(target)
        output.append(target)
        if key != target:
            renamed[header] = target
    return output, renamed


def _num_text(number):
    return f"{number:.6f}".rstrip("0").rstrip(".") or "0"


def _md_table(headers, rows):
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return lines


def write_md_report(path, title, report, clean_rows, coverage, quarantined, renamed):
    """Markdown 报告：给人读的结论版，含合计、覆盖率、改名映射与隔离原因。"""
    lines = [f"# {title}", ""]
    lines.append(f"- 输入：`{report['input']}`")
    lines.append(f"- 行数：读入 {report['rows_in']} → 输出 {report['rows_out']}；"
                 f"丢弃空行 {report['empty_rows_dropped']}，删除重复 {report['duplicates_removed']}，"
                 f"隔离 {report['quarantined']}")
    lines.append(f"- 去重主键：{'、'.join(report['dedupe_key']) or '全列'}")
    lines.append(f"- 必填字段：{'、'.join(report['required_fields']) or '无'}")
    lines.append("")

    sums = []
    for field in report["output_columns"]:
        if field not in SUM_FIELDS:
            continue
        total = 0.0
        hit = 0
        for _, values in clean_rows:
            number = to_number(values.get(field) or "")
            if number is not None:
                total += number
                hit += 1
        if hit:
            sums.append((field, _num_text(round(total, 6)), hit))
    lines.append("## 数值列合计")
    lines.append("")
    lines.extend(_md_table(["字段", "合计", "有值行数"], sums) if sums
                 else ["（没有可求和的数值列）"])
    lines.append("")

    low = [(field, pct) for field, pct in coverage.items() if pct < 100]
    low.sort(key=lambda item: item[1])
    lines.append("## 字段覆盖率")
    lines.append("")
    lines.append(f"共 {len(report['output_columns'])} 列；覆盖率不足 100% 的 {len(low)} 列（未列出的列为 100%）。")
    lines.append("")
    if low:
        lines.extend(_md_table(["字段", "有值占比%"],
                               [[field, pct] for field, pct in low[:40]]))
        if len(low) > 40:
            lines.append("")
            lines.append(f"（其余 {len(low) - 40} 列省略，完整口径见字段覆盖率工作表）")
    lines.append("")

    lines.append("## 列名归一")
    lines.append("")
    if renamed:
        items = list(renamed.items())
        lines.extend(_md_table(["原列名", "标准字段"], items[:40]))
        if len(items) > 40:
            lines.append("")
            lines.append(f"（其余 {len(items) - 40} 列省略，完整映射见清洗台账工作表）")
    else:
        lines.append("无需归一，表头已符合标准字段。")
    lines.append("")

    lines.append("## 隔离行")
    lines.append("")
    if quarantined:
        reasons = {}
        for _, _, reason in quarantined:
            reasons[reason] = reasons.get(reason, 0) + 1
        lines.extend(_md_table(["隔离原因", "行数"], sorted(reasons.items(), key=lambda kv: -kv[1])))
    else:
        lines.append("无。")
    lines.append("")

    lines.append("## 数值无法解析")
    lines.append("")
    if report.get("coercion_counts"):
        lines.extend(_md_table(["字段", "解析失败次数"],
                               sorted(report["coercion_counts"].items(), key=lambda kv: -kv[1])[:20]))
    else:
        lines.append("无。")
    lines.append("")

    if report.get("missing_required_columns"):
        lines.append("## 缺失的必填列")
        lines.append("")
        lines.append("、".join(report["missing_required_columns"]))
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("口径：数值列已去掉货币符号与千分位；日期统一 YYYY-MM-DD；明细金额按原精度保留（最多 6 位小数）；"
                 "重复行保留首次出现的记录。")
    lines.append("")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="清洗并结构化运营表格：表头归一、数值与日期标准化、去重、必填校验。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("input", help="输入表格：.csv/.tsv/.xlsx")
    parser.add_argument("--out", default=None, help="输出清洗后的 CSV（UTF-8 BOM）")
    parser.add_argument("--out-json", default=None, help="输出清洗报告 JSON")
    parser.add_argument("--quarantine", default=None, help="输出被隔离的问题行 CSV")
    parser.add_argument("--out-xlsx", default=None, help="输出 Excel 工作簿（清洗结果 + 隔离行 + 字段覆盖率）")
    parser.add_argument("--out-md", default=None, help="输出 Markdown 报告（给人读的结论版）")
    parser.add_argument("--map", action="append", default=[], metavar="原列名=标准字段",
                        help="显式指定列名映射，可重复")
    parser.add_argument("--require", default="", help="必填字段，逗号分隔，例如 sku,price")
    parser.add_argument("--dedupe-on", default="", help="去重主键字段，逗号分隔，默认 sku,date（不存在则用全列）")
    parser.add_argument("--keep", default="", help="只保留这些字段，逗号分隔；默认保留全部")
    parser.add_argument("--sheet", default=1, help="xlsx 工作表序号或名称，默认第 1 个")
    parser.add_argument("--header-row", type=int, default=1, help="表头所在行号，默认 1")
    parser.add_argument("--keep-empty-rows", action="store_true", help="保留全空行（默认剔除）")
    args = parser.parse_args(argv)

    try:
        headers, rows = sheetio.read_table(args.input, sheet=args.sheet, header_row=args.header_row)
    except (OSError, ValueError) as error:
        sheetio.emit(sheetio.make_envelope("clean_table", "blocked", 0.0, {"error": str(error)},
                                           [sheetio.flag("high", "input_error", str(error), "确认文件路径与格式")]), out_json=args.out_json)
        return 2
    if not headers:
        sheetio.emit(sheetio.make_envelope("clean_table", "blocked", 0.0, {"error": "空表或未读到表头"},
                                           [sheetio.flag("high", "empty_input", "未读到表头", "确认表头行号")]), out_json=args.out_json)
        return 2

    mapping = sheetio.apply_mapping(args.map)
    new_headers, renamed = build_headers(headers, mapping, args.dedupe_on)
    flags = []

    known = set(new_headers)
    known_norm = {}
    for name in new_headers:
        known_norm.setdefault(norm_key(name), name)
    required = _resolve_names([item.strip() for item in args.require.split(",") if item.strip()],
                              known, known_norm)
    missing_required_columns = [name for name in required if name not in known]
    for name in missing_required_columns:
        flags.append(sheetio.flag("high", "missing_required_column",
                                  f"必填字段 {name} 在表中不存在", "补齐该列或确认是否用 --map 指定了正确列名"))

    records = []
    coercions = {}
    empty_dropped = 0
    for offset, raw in enumerate(rows, start=args.header_row + 1):
        values = {}
        for index, field in enumerate(new_headers):
            cell = raw[index] if index < len(raw) else ""
            if not clean_text(cell) and cell != 0:
                values[field] = None
                continue
            converted = _format_value(field, cell)
            if converted is None:
                coercions[field] = coercions.get(field, 0) + 1
                values[field] = clean_text(cell)
            else:
                if field in COERCED_FIELDS and str(converted) != clean_text(cell):
                    coercions[field] = coercions.get(field, 0) + 1
                values[field] = converted
        if not any(value not in (None, "") for value in values.values()):
            empty_dropped += 1
            if args.keep_empty_rows:
                records.append((offset, values))
            continue
        records.append((offset, values))

    dedupe_fields = _resolve_names([item.strip() for item in args.dedupe_on.split(",") if item.strip()],
                                  known, known_norm)
    if dedupe_fields and any(field not in known for field in dedupe_fields):
        flags.append(sheetio.flag("medium", "dedupe_key_missing",
                                  f"去重主键 {dedupe_fields} 有字段不存在，已改为整行去重",
                                  "确认主键字段名后重跑"))
        dedupe_fields = []
    if not dedupe_fields:
        dedupe_fields = [field for field in ("sku", "date") if field in known]

    seen = set()
    deduped = []
    duplicates = []
    for offset, values in records:
        if dedupe_fields:
            key = tuple(norm_key(values.get(field) or "") for field in dedupe_fields)
        else:
            key = tuple(norm_key(values.get(field) or "") for field in new_headers)
        if key in seen:
            duplicates.append(offset)
            continue
        seen.add(key)
        deduped.append((offset, values))

    clean_rows = []
    quarantined = []
    for offset, values in deduped:
        missing = [name for name in required if not clean_text(values.get(name) or "")]
        if missing:
            quarantined.append((offset, values, "缺少必填字段：" + "、".join(missing)))
            continue
        clean_rows.append((offset, values))

    if quarantined:
        flags.append(sheetio.flag("medium", "rows_quarantined",
                                  f"{len(quarantined)} 行因缺字段被隔离",
                                  "把这些行退回数据源修正，确认是口径问题还是导出问题"))
    if duplicates:
        flags.append(sheetio.flag("low", "duplicates_removed",
                                  f"按主键 {dedupe_fields or '全列'} 删除 {len(duplicates)} 行重复"))

    if not args.out and not args.out_xlsx and not args.out_md:
        sys.stderr.write("请至少指定 --out（CSV）/ --out-xlsx（Excel）/ --out-md（Markdown）之一\n")
        return 2

    keep = set(_resolve_names([item.strip() for item in args.keep.split(",") if item.strip()],
                              known, known_norm))
    export_headers = [field for field in new_headers if not keep or field in keep]
    export_rows = [[values.get(field) or "" for field in export_headers] for _, values in clean_rows]
    quarantine_headers = list(export_headers) + ["_隔离原因", "_原行号"]
    quarantine_rows = [[values.get(field) or "" for field in export_headers] + [reason, offset]
                       for offset, values, reason in quarantined]
    if args.out:
        sheetio.write_csv(args.out, export_headers, export_rows)

    if args.quarantine:
        sheetio.write_csv(args.quarantine, quarantine_headers, quarantine_rows)

    coverage = {
        field: round(100.0 * sum(1 for _, values in clean_rows if clean_text(values.get(field) or "")) / len(clean_rows), 1)
        for field in export_headers
    } if clean_rows else {}

    report = {
        "input": os.path.abspath(args.input),
        "rows_in": len(rows),
        "rows_out": len(clean_rows),
        "empty_rows_dropped": empty_dropped,
        "duplicates_removed": len(duplicates),
        "duplicate_row_numbers": duplicates[:50],
        "quarantined": len(quarantined),
        "quarantined_rows": [{"row": offset, "reason": reason} for offset, _, reason in quarantined[:50]],
        "renamed_columns": renamed,
        "output_columns": export_headers,
        "coercion_counts": coercions,
        "dedupe_key": dedupe_fields,
        "required_fields": required,
        "missing_required_columns": missing_required_columns,
        "field_coverage_pct": coverage,
    }

    low_coverage = [field for field, pct in coverage.items() if pct < 60 and field in required]
    for field in low_coverage:
        flags.append(sheetio.flag("medium", "low_field_coverage",
                                  f"{field} 仅 {coverage[field]}% 的行有值", "确认该字段在该数据源是否本来就缺"))

    status = "blocked" if missing_required_columns else ("partial" if quarantined else "ok")
    confidence = 0.9 if not quarantined and not missing_required_columns else 0.6
    if args.out_xlsx:
        sheetio.write_xlsx(args.out_xlsx, [
            {"name": "清洗结果", "headers": export_headers, "rows": export_rows,
             "coerce_numbers": True},
            {"name": "隔离行", "headers": quarantine_headers, "rows": quarantine_rows,
             "coerce_numbers": True},
            {"name": "字段覆盖率", "headers": ["字段", "有值占比%"],
             "rows": [[field, pct] for field, pct in coverage.items()]},
            {"name": "清洗台账", "headers": ["项目", "数值"],
             "rows": [["读入行数", report["rows_in"]], ["输出行数", report["rows_out"]],
                      ["丢弃空行", report["empty_rows_dropped"]], ["删除重复行", report["duplicates_removed"]],
                      ["隔离行数", report["quarantined"]], ["去重主键", "、".join(dedupe_fields) or "全列"],
                      ["必填字段", "、".join(required) or "无"],
                      ["列名归一", "；".join(f"{k}→{v}" for k, v in renamed.items()) or "无需归一"]]},
        ])

    if args.out_md:
        sheet_name = args.sheet if not str(args.sheet).isdigit() else ""
        write_md_report(args.out_md,
                        f"数据清洗报告：{os.path.basename(args.input)}" + (f"（{sheet_name}）" if sheet_name else ""),
                        report, clean_rows, coverage, quarantined, renamed)

    envelope = sheetio.make_envelope("clean_table", status, confidence, report, flags,
                                     sources=[{"ref": os.path.basename(args.input), "as_of": sheetio.to_date(
                                         __import__("datetime").datetime.now())}],
                                     assumptions=["数值列已去掉货币符号与千分位；日期统一 YYYY-MM-DD",
                                                  "重复行保留首次出现的记录"])
    sheetio.emit(envelope, out_json=args.out_json)
    sys.stderr.write(
        f"[clean_table] 读入 {len(rows)} 行 → 输出 {len(clean_rows)} 行；"
        f"去重 {len(duplicates)} 行，隔离 {len(quarantined)} 行，空行 {empty_dropped} 行\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
