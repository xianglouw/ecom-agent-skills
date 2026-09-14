#!/usr/bin/env python3
"""阶段 6：ROI / ROAS 数据复盘核算。

用法示例：
  python3 roi_review.py 投放明细.xlsx --group-by campaign --compare 上期.csv \
      --out-md review.md --out-json review.json --gross-margin 0.35

按维度聚合投放与销售数据，算出 CTR/CVR/CPC/CPA/ROAS/ACOS/TACOS/净利与保本 ROAS，
与上期对照标记超阈值波动，并生成复盘用的 Markdown 表格。
只读输入，只写 --out-md/--out-json 指定文件；归因文字与下周动作由调用方撰写。
"""

import argparse
import datetime
import os
import sys

import sheetio
from sheetio import clean_text, to_date, to_number

METRIC_FIELDS = ["date", "campaign", "ad_group", "sku", "platform", "site", "impressions", "clicks",
                 "spend", "orders", "units", "revenue", "total_revenue", "cost", "price", "refund", "currency"]
GROUP_FIELDS = ["campaign", "ad_group", "sku", "date", "platform", "site", "currency"]


def load_rows(path, sheet, header_row, mapping):
    headers, body = sheetio.read_table(path, sheet=sheet, header_row=header_row)
    if mapping:
        headers = [mapping.get(sheetio.norm_key(header), header) for header in headers]
    columns = sheetio.column_map(headers, METRIC_FIELDS)
    records = []
    for index, raw in enumerate(body, start=header_row + 1):
        def cell(field):
            position = columns.get(field)
            return raw[position] if position is not None and position < len(raw) else ""
        record = {"_row": index}
        for field in METRIC_FIELDS:
            value = cell(field)
            if field in ("date",):
                record[field] = to_date(value)
            elif field in ("campaign", "ad_group", "sku", "platform", "site", "currency"):
                record[field] = clean_text(value)
            else:
                record[field] = to_number(value)
        if all(record[field] is None for field in ("spend", "revenue", "orders", "clicks", "impressions")):
            continue
        records.append(record)
    return records, columns


def safe_div(numerator, denominator):
    if numerator is None or not denominator:
        return None
    return numerator / denominator


def aggregate(records, key_field, cost_mode, fallback_margin):
    groups = {}
    for record in records:
        key = record.get(key_field) or "（未标注）" if key_field else "全部"
        bucket = groups.setdefault(key, {"key": key, "rows": 0, "impressions": 0.0, "clicks": 0.0,
                                         "spend": 0.0, "orders": 0.0, "units": 0.0, "revenue": 0.0,
                                         "cost_value": 0.0, "cost_total": 0.0, "refund": 0.0,
                                         "total_revenue": 0.0, "has_total_revenue": False})
        bucket["rows"] += 1
        for field in ("impressions", "clicks", "spend", "orders", "units", "revenue", "refund"):
            bucket[field] += record.get(field) or 0.0
        if record.get("total_revenue") is not None:
            bucket["total_revenue"] += record["total_revenue"]
            bucket["has_total_revenue"] = True
        if cost_mode == "unit":
            bucket["cost_total"] += (record.get("cost") or 0.0) * (record.get("units") or 0.0)
            bucket["cost_value"] += record.get("cost") or 0.0
        elif cost_mode == "total":
            bucket["cost_total"] += record.get("cost") or 0.0
            bucket["cost_value"] += record.get("cost") or 0.0

    for bucket in groups.values():
        revenue = bucket["revenue"]
        spend = bucket["spend"]
        clicks = bucket["clicks"]
        orders = bucket["orders"]
        impressions = bucket["impressions"]
        bucket["ctr"] = safe_div(clicks, impressions)
        bucket["cvr"] = safe_div(orders, clicks)
        bucket["cpc"] = safe_div(spend, clicks)
        bucket["cpa"] = safe_div(spend, orders)
        bucket["roas"] = safe_div(revenue, spend)
        bucket["acos"] = safe_div(spend, revenue)
        bucket["tacos"] = safe_div(spend, bucket["total_revenue"]) if bucket["has_total_revenue"] else None
        if cost_mode == "none":
            # 没有成本数据时用经验毛利率替代商品成本，并在 assumptions 中声明
            gross_profit = revenue * fallback_margin - bucket["refund"]
        else:
            gross_profit = revenue - bucket["cost_total"] - bucket["refund"]
        bucket["gross_profit"] = gross_profit
        bucket["net_profit"] = gross_profit - spend
        margin = safe_div(bucket["gross_profit"], revenue) if revenue else None
        bucket["gross_margin"] = margin
        bucket["breakeven_roas"] = (1 / margin) if margin and margin > 0 else None
    return groups


def compare_with_previous(groups, previous_groups, threshold):
    changes = []
    for key, bucket in groups.items():
        before = previous_groups.get(key)
        if not before:
            continue
        delta = {}
        for field in ("spend", "revenue", "roas", "orders", "net_profit"):
            current_value = bucket.get(field)
            before_value = before.get(field)
            if current_value is None or before_value in (None, 0):
                continue
            rate = (current_value - before_value) / abs(before_value)
            delta[field] = round(rate, 4)
            if abs(rate) > threshold:
                changes.append(sheetio.flag(
                    "medium", "threshold_breach",
                    f"{key} 的 {field} 环比 {rate:+.1%}（{before_value:.2f} → {current_value:.2f}）",
                    "确认是投放动作、季节还是数据口径变化导致"))
        bucket["change"] = delta
    return changes


def fmt(value, digits=2, percent=False):
    if value is None:
        return "-"
    if percent:
        return f"{value * 100:.1f}%"
    return f"{value:.{digits}f}"


def build_markdown(group_field, groups, totals, changes, flags, period, assumptions, top, breakeven_hint):
    lines = [f"# ROI 复盘（按 {group_field or '整体'}）", ""]
    lines.append(f"- 数据区间：{period}")
    lines.append(f"- 口径：{assumptions[0] if assumptions else '见 JSON 输出的 assumptions'}")
    lines.append("")

    lines.append("## 核心指标")
    lines.append("")
    lines.append("| 指标 | 本期 |")
    lines.append("|---|---|")
    lines.append(f"| 广告花费 | {fmt(totals['spend'])} |")
    lines.append(f"| 广告收入 | {fmt(totals['revenue'])} |")
    lines.append(f"| ROAS | {fmt(totals['roas'])} |")
    lines.append(f"| 保本 ROAS | {fmt(totals.get('breakeven_roas'))} |")
    lines.append(f"| ACOS | {fmt(totals['acos'], percent=True)} |")
    if totals.get("tacos") is not None:
        lines.append(f"| TACOS | {fmt(totals['tacos'], percent=True)} |")
    lines.append(f"| 点击 / 转化 | {fmt(totals['clicks'], 0)} / {fmt(totals['orders'], 0)} |")
    lines.append(f"| CTR / CVR | {fmt(totals['ctr'], percent=True)} / {fmt(totals['cvr'], percent=True)} |")
    lines.append(f"| CPC / CPA | {fmt(totals['cpc'])} / {fmt(totals['cpa'])} |")
    lines.append(f"| 净利 | {fmt(totals['net_profit'])} |")
    lines.append("")

    lines.append(f"## 分组明细（按花费降序，前 {top} 组）")
    lines.append("")
    lines.append("| 分组 | 花费 | 收入 | ROAS | 保本ROAS | ACOS | 转化 | CPA | 净利 | 花费占比 |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    ordered = sorted(groups.values(), key=lambda item: item["spend"], reverse=True)
    for bucket in ordered[:top]:
        share = safe_div(bucket["spend"], totals["spend"])
        lines.append("| {key} | {spend} | {revenue} | {roas} | {breakeven} | {acos} | {orders} | {cpa} | {profit} | {share} |".format(
            key=bucket["key"], spend=fmt(bucket["spend"]), revenue=fmt(bucket["revenue"]),
            roas=fmt(bucket["roas"]), breakeven=fmt(bucket["breakeven_roas"]),
            acos=fmt(bucket["acos"], percent=True), orders=fmt(bucket["orders"], 0),
            cpa=fmt(bucket["cpa"]), profit=fmt(bucket["net_profit"]), share=fmt(share, percent=True)))
    if len(ordered) > top:
        lines.append("")
        lines.append(f"（另有 {len(ordered) - top} 个分组未列出，完整数据见 JSON）")
    lines.append("")

    lines.append("## 结论")
    lines.append("")
    for item in build_conclusions(groups, totals, breakeven_hint):
        lines.append(f"- {item}")
    lines.append("")

    lines.append("## 风险与待确认")
    lines.append("")
    if flags or changes:
        for flag in flags + changes:
            lines.append(f"- [{flag['level']}] {flag['detail']} → {flag['action']}")
    else:
        lines.append("- 未触发阈值告警，仍需人工确认数据口径与归因窗口")
    lines.append("")
    lines.append("## 下周动作")
    lines.append("")
    lines.append("- 待填：按上方结论逐条给出动作、责任人与判断依据（加预算 / 关停 / 换素材 / 调价）")
    lines.append("")
    return "\n".join(lines)


def build_conclusions(groups, totals, breakeven_hint):
    ordered = sorted(groups.values(), key=lambda item: item["spend"], reverse=True)
    conclusions = []
    if totals.get("roas") is not None:
        breakeven = totals.get("breakeven_roas") or breakeven_hint
        if breakeven:
            relation = "高于" if totals["roas"] >= breakeven else "低于"
            conclusions.append(
                f"整体 ROAS {fmt(totals['roas'])}，{relation}保本线 {fmt(breakeven)}，"
                f"整体净利 {fmt(totals['net_profit'])}")
        else:
            conclusions.append(f"整体 ROAS {fmt(totals['roas'])}，缺少成本数据无法判断是否保本")
    profitable = [bucket for bucket in ordered if bucket.get("net_profit") is not None]
    if profitable:
        best = max(profitable, key=lambda item: item["net_profit"])
        worst = min(profitable, key=lambda item: item["net_profit"])
        conclusions.append(f"净利最高：{best['key']}（{fmt(best['net_profit'])}，花费占比 "
                           f"{fmt(safe_div(best['spend'], totals['spend']), percent=True)}）")
        if worst["net_profit"] < 0:
            conclusions.append(f"亏损最大：{worst['key']}（{fmt(worst['net_profit'])}，"
                               f"ROAS {fmt(worst['roas'])}，建议优先排查素材与出价）")
    zero_conversion = [bucket for bucket in ordered if bucket["orders"] == 0 and bucket["spend"] > 0]
    if zero_conversion:
        wasted = sum(bucket["spend"] for bucket in zero_conversion)
        conclusions.append(f"{len(zero_conversion)} 个分组有花费但零转化，合计浪费 {fmt(wasted)}，"
                           "优先关停或换素材")
    if len(ordered) > 1:
        share = safe_div(ordered[0]["spend"], totals["spend"])
        if share and share > 0.4:
            conclusions.append(f"花费集中度偏高：{ordered[0]['key']} 占 {fmt(share, percent=True)}，"
                               "单点波动会直接影响整体，建议分散测试")
    if not conclusions:
        conclusions.append("数据不足以形成结论，请确认花费与收入字段是否正确映射")
    return conclusions


def main(argv=None):
    parser = argparse.ArgumentParser(description="按维度核算 ROAS/ACOS/净利并与上期对照，输出复盘表。")
    parser.add_argument("input", help="投放/销售明细：.csv/.xlsx")
    parser.add_argument("--group-by", default="campaign", choices=GROUP_FIELDS, help="聚合维度，默认 campaign")
    parser.add_argument("--compare", default=None, help="上期同结构明细，用于环比对照")
    parser.add_argument("--out-md", default=None, help="输出 Markdown 复盘表")
    parser.add_argument("--out-json", default=None, help="输出结果 JSON")
    parser.add_argument("--gross-margin", type=float, default=None,
                        help="缺少成本列时使用的毛利率（不含广告费），例如 0.35")
    parser.add_argument("--breakeven-roas", type=float, default=None, help="直接指定保本 ROAS，优先于毛利率推算")
    parser.add_argument("--threshold", type=float, default=0.2, help="环比告警阈值，默认 0.2（即 ±20%%）")
    parser.add_argument("--top", type=int, default=15, help="Markdown 表中列出的分组数，默认 15")
    parser.add_argument("--currency", default=None, help="报告币种标注")
    parser.add_argument("--map", action="append", default=[], metavar="原列名=标准字段")
    parser.add_argument("--sheet", type=int, default=1, help="xlsx 工作表序号")
    parser.add_argument("--header-row", type=int, default=1, help="表头行号")
    args = parser.parse_args(argv)

    mapping = sheetio.apply_mapping(args.map)
    try:
        records, columns = load_rows(args.input, args.sheet, args.header_row, mapping)
    except (OSError, ValueError) as error:
        sheetio.emit(sheetio.make_envelope("roi_review", "blocked", 0.0, {"error": str(error)},
                                           [sheetio.flag("high", "input_error", str(error), "确认文件路径与格式")]), out_json=args.out_json)
        return 2

    flags = []
    if not records:
        sheetio.emit(sheetio.make_envelope("roi_review", "blocked", 0.0, {"error": "没有可核算的数据行"},
                                           [sheetio.flag("high", "empty_input", "没有读到有效的投放数据",
                                                         "确认表头行与字段名")]), out_json=args.out_json)
        return 2
    if "spend" not in columns:
        flags.append(sheetio.flag("high", "missing_spend", "没有识别到花费列，无法计算 ROAS",
                                  "用 --map 指定，例如 --map 消耗=spend"))
    if "revenue" not in columns and "total_revenue" not in columns:
        flags.append(sheetio.flag("high", "missing_revenue", "没有识别到收入列，无法计算 ROAS",
                                  "用 --map 指定，例如 --map 成交额=revenue"))
    if any(flag["type"] in ("missing_spend", "missing_revenue") for flag in flags):
        sheetio.emit(sheetio.make_envelope("roi_review", "blocked", 0.0,
                                           {"detected_columns": sorted(columns)}, flags), out_json=args.out_json)
        return 2

    cost_mode = "none"
    if "cost" in columns:
        if columns.get("cost") == columns.get("spend"):
            flags.append(sheetio.flag("medium", "ambiguous_cost_column",
                                      "成本列与花费列指向同一列，已按「不含商品成本」处理",
                                      "若该列其实是商品成本，请用 --map 明确区分"))
        elif "units" in columns:
            cost_mode = "unit"
        else:
            cost_mode = "total"
    if cost_mode == "none":
        if not args.gross_margin:
            flags.append(sheetio.flag("medium", "missing_cost",
                                      "缺少商品成本数据，已按毛利率 0 处理，保本 ROAS 不可用",
                                      "用 --gross-margin 提供经验毛利率，或补上成本列"))
        else:
            flags.append(sheetio.flag("low", "estimated_margin",
                                      f"使用经验毛利率 {args.gross_margin:.0%} 推算保本 ROAS",
                                      "结论如需用于预算决策，请用真实成本替换"))
    fallback_margin = args.gross_margin if args.gross_margin is not None else 0.0

    group_field = args.group_by if args.group_by in columns else None
    if group_field is None:
        flags.append(sheetio.flag("medium", "group_field_missing",
                                  f"没有识别到 {args.group_by} 列，已按整体汇总",
                                  f"用 --map 指定后重跑，例如 --map 广告活动={args.group_by}"))

    groups = aggregate(records, group_field, cost_mode, fallback_margin)
    currency_values = sorted({record.get("currency") for record in records if record.get("currency")})
    if len(currency_values) > 1:
        flags.append(sheetio.flag("high", "mixed_currency",
                                  f"同一份数据出现多种币种：{'、'.join(currency_values)}，金额未换汇即聚合",
                                  "按币种拆分或先换汇再复盘"))
    if "refund" not in columns:
        flags.append(sheetio.flag("low", "refund_not_provided",
                                  "数据中没有退款字段，净利未扣退款",
                                  "大促后复盘建议补上退款数据"))

    totals_group = aggregate(records, None, cost_mode, fallback_margin)["全部"]
    breakeven = args.breakeven_roas
    if breakeven is None and totals_group.get("breakeven_roas"):
        breakeven = totals_group["breakeven_roas"]
    totals_group["breakeven_roas"] = breakeven

    for bucket in groups.values():
        if breakeven and bucket.get("roas") is not None and bucket["roas"] < breakeven:
            bucket["below_breakeven"] = True
            flags.append(sheetio.flag("high", "below_breakeven",
                                      f"{bucket['key']} ROAS {fmt(bucket['roas'])} 低于保本线 {fmt(breakeven)}，"
                                      f"净利 {fmt(bucket['net_profit'])}",
                                      "人工确认关停、降价还是换素材"))
        if bucket["spend"] > 0 and bucket["orders"] == 0:
            share = safe_div(bucket["spend"], totals_group["spend"]) or 0
            flags.append(sheetio.flag("high" if share > 0.2 else "medium", "zero_conversion_spend",
                                      f"{bucket['key']} 花费 {fmt(bucket['spend'])} 但零转化"
                                      f"（占总花费 {fmt(share, percent=True)}）",
                                      "检查素材、落地页与受众，必要时先关停"))
        if bucket.get("net_profit") is not None and bucket["net_profit"] < 0:
            flags.append(sheetio.flag("high", "negative_profit_group",
                                      f"{bucket['key']} 净利为负（{fmt(bucket['net_profit'])}）",
                                      "核对成本与费率，确认是否继续投放"))

    ordered = sorted(groups.values(), key=lambda item: item["spend"], reverse=True)
    if len(ordered) > 1:
        top_share = safe_div(ordered[0]["spend"], totals_group["spend"])
        if top_share and top_share > 0.6:
            flags.append(sheetio.flag("medium", "spend_concentration",
                                      f"前 1 个分组占总花费 {fmt(top_share, percent=True)}，集中度过高",
                                      "确认是策略性集中还是缺少测试组"))

    changes = []
    if args.compare:
        try:
            previous_records, _ = load_rows(args.compare, args.sheet, args.header_row, mapping)
            previous_groups = aggregate(previous_records, group_field, cost_mode, fallback_margin)
            changes = compare_with_previous(groups, previous_groups, args.threshold)
        except (OSError, ValueError) as error:
            flags.append(sheetio.flag("medium", "compare_failed", f"上期数据读取失败：{error}",
                                      "确认 --compare 文件路径与结构一致"))
    if records:
        period_start = min((record["date"] for record in records if record.get("date")), default=None)
        period_end = max((record["date"] for record in records if record.get("date")), default=None)
    else:
        period_start = period_end = None
    period = f"{period_start or '未标注'} ~ {period_end or '未标注'}"

    assumptions = [
        "收入为广告报表口径的广告收入；未提供总销售额时不计算 TACOS",
        f"商品成本口径：{'单位成本 × 销量' if cost_mode == 'unit' else ('按列合计' if cost_mode == 'total' else '缺失，未计入')}",
    ]
    if args.gross_margin:
        assumptions.append(f"缺少成本时按毛利率 {args.gross_margin:.2%} 估算")
    markdown = build_markdown(group_field, groups, totals_group, changes, flags, period,
                              assumptions, args.top, breakeven)

    export = {
        "period": {"start": period_start, "end": period_end},
        "group_by": group_field,
        "currency": args.currency or (currency_values[0] if len(currency_values) == 1 else None),
        "breakeven_roas": breakeven,
        "cost_mode": cost_mode,
        "totals": dict(
            [(key, round(value, 4) if isinstance(value, float) else value)
             for key, value in totals_group.items() if key != "rows"] + [("rows", totals_group["rows"])]),
        "groups": [
            {key: (round(value, 4) if isinstance(value, float) else value)
             for key, value in bucket.items() if key not in ("cost_value", "has_total_revenue")}
            for bucket in ordered
        ],
        "detected_columns": sorted(columns),
    }
    if args.out_md:
        with open(args.out_md, "w", encoding="utf-8") as handle:
            handle.write(markdown)

    status = "ok"
    if any(flag["level"] == "high" for flag in flags):
        status = "partial"
    if cost_mode == "none":
        status = "partial"
    confidence = 0.9 if cost_mode != "none" and not any(
        flag["type"] in ("missing_cost", "mixed_currency", "ambiguous_cost_column") for flag in flags) else 0.6
    envelope = sheetio.make_envelope(
        "roi_review", status, confidence, export, flags + changes,
        sources=[{"ref": os.path.basename(args.input), "as_of": period_end or ""}],
        assumptions=assumptions,
    )
    sheetio.emit(envelope, out_json=args.out_json)
    sys.stderr.write(f"[roi_review] {len(groups)} 个分组，{totals_group['rows']} 行数据，"
                     f"ROAS {fmt(totals_group['roas'])}，净利 {fmt(totals_group['net_profit'])}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
