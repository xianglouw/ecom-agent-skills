#!/usr/bin/env python3
"""阶段 1：平台费率核算与扣费风险标记。

用法示例：
  python3 fee_check.py orders.csv --rates amazon_us_fee_v2026-09.csv --out fee.csv --out-json fee.json
  python3 fee_check.py --rates 费率表.csv --summary          # 只看规则覆盖度

按订单（平台/站点/类目/价格）在费率表里做优先级匹配，算出佣金、支付手续费、
履约/仓储费、税费，得出净利与保本 ROAS，并标记规则未覆盖、负毛利、汇率缺失、
费率过旧等风险。只读输入，只写 --out/--out-json 指定文件。
"""

import argparse
import datetime
import os
import sys

import sheetio
from sheetio import clean_text, norm_key, to_date, to_number

RATE_FIELDS = ["commission_rate", "payment_rate", "fulfillment_fee", "fba_fee", "storage_fee", "tax_rate"]
RATE_HEADER_FIELDS = ["platform", "site", "category", "price_min", "price_max", "currency",
                      "condition", "source", "effective_date", "updated_at"] + RATE_FIELDS
ORDER_FIELDS = ["platform", "site", "category", "price", "qty", "cost", "currency", "sku", "date"]
WILDCARD = {"", "*", "all", "全部", "所有", "-"}


def load_rates(paths, sheet=1):
    rows = []
    flags = []
    missing_columns = []
    for path in paths:
        headers, body = sheetio.read_table(path, sheet=sheet)
        columns = sheetio.column_map(headers, RATE_HEADER_FIELDS)
        if "platform" not in columns:
            missing_columns.append(f"{os.path.basename(path)}:platform")
            continue
        provided = [name for name in RATE_FIELDS if name in columns]
        if not provided:
            missing_columns.append(f"{os.path.basename(path)}:费率列")
        for index, raw in enumerate(body, start=2):
            def cell(field):
                position = columns.get(field)
                return raw[position] if position is not None and position < len(raw) else ""
            platform = clean_text(cell("platform"))
            if not platform:
                continue
            record = {
                "platform": platform,
                "site": clean_text(cell("site")),
                "category": clean_text(cell("category")),
                "price_min": to_number(cell("price_min")),
                "price_max": to_number(cell("price_max")),
                "currency": (clean_text(cell("currency")) or "CNY").upper(),
                "condition": clean_text(cell("condition")),
                "source": clean_text(cell("source")) or os.path.basename(path),
                "effective_date": to_date(cell("effective_date")),
                "updated_at": to_date(cell("updated_at")),
                "file": os.path.basename(path),
                "row": index,
            }
            for field in RATE_FIELDS:
                record[field] = to_number(cell(field)) or 0.0
            rows.append(record)
    if missing_columns:
        flags.append(sheetio.flag("medium", "rate_table_incomplete",
                                  "费率表缺少必要列：" + "、".join(missing_columns),
                                  "补齐 platform 与至少一个费率列后重跑"))
    return rows, flags


def describe_rates(rates):
    platforms = {}
    stale = []
    today = datetime.date.today()
    for item in rates:
        key = f"{item['platform']}/{item['site'] or '*'}"
        entry = platforms.setdefault(key, {"rows": 0, "categories": set(), "with_source": 0})
        entry["rows"] += 1
        entry["categories"].add(item["category"] or "*")
        if item["source"]:
            entry["with_source"] += 1
        if not item["effective_date"]:
            stale.append({"rule": f"{item['platform']}/{item['site']}/{item['category']}",
                          "file": item["file"], "row": item["row"], "reason": "缺少生效日期"})
        else:
            age = (today - datetime.date.fromisoformat(item["effective_date"])).days
            if age > 365:
                stale.append({"rule": f"{item['platform']}/{item['site']}/{item['category']}",
                              "file": item["file"], "row": item["row"], "reason": f"生效日期距今 {age} 天"})
    summary = {
        "rule_rows": len(rates),
        "platform_site_groups": {
            key: {"rows": value["rows"], "category_count": len(value["categories"]),
                  "categories": sorted(value["categories"])[:20]}
            for key, value in sorted(platforms.items())
        },
        "without_effective_date": sum(1 for item in rates if not item["effective_date"]),
        "suspicious_rows": stale[:50],
        "rate_columns_all_zero": [
            field for field in RATE_FIELDS
            if rates and all(item[field] == 0 for item in rates)
        ],
    }
    return summary


def rate_summary_sheet(summary):
    """费率表覆盖情况，做成一张可读的工作表。"""
    rows = [["平台/站点", "规则行数", "类目数", "类目示例"]]
    for key, value in sorted(summary.get("platform_site_groups", {}).items()):
        rows.append([key, value.get("rows", 0), value.get("category_count", 0),
                     "、".join(value.get("categories", []))])
    rows.append([])
    rows.append(["缺少生效日期的费率行", summary.get("without_effective_date", 0), "", ""])
    zero = summary.get("rate_columns_all_zero", [])
    rows.append(["整列为 0 的费率字段", "、".join(zero) if zero else "无", "", ""])
    return {"name": "费率覆盖情况", "headers": rows[0], "rows": rows[1:]}


def match_rule(order, rates):
    """返回 (最佳匹配规则, 匹配说明)。优先级：站点精确 > 站点通配；类目精确 > 类目模糊 > 通配。"""
    platform_key = norm_key(order["platform"])
    site_key = norm_key(order["site"])
    category_key = norm_key(order["category"])
    candidates = []
    for item in rates:
        if norm_key(item["platform"]) != platform_key:
            continue
        rule_site = norm_key(item["site"])
        site_score = 4 if rule_site and rule_site == site_key else (0 if rule_site in {norm_key(w) for w in WILDCARD} else None)
        if site_score is None:
            continue
        rule_category = norm_key(item["category"])
        if rule_category in {norm_key(w) for w in WILDCARD}:
            category_score = 0
        elif rule_category == category_key:
            category_score = 2
        elif rule_category and category_key and (rule_category in category_key or category_key in rule_category):
            category_score = 1
        else:
            continue
        price = order["price"]
        if price is not None:
            if item["price_min"] is not None and price < item["price_min"]:
                continue
            if item["price_max"] is not None and price > item["price_max"]:
                continue
        window = float("inf")
        if item["price_min"] is not None and item["price_max"] is not None:
            window = item["price_max"] - item["price_min"]
        candidates.append((site_score + category_score, site_score, category_score, -window,
                           item["effective_date"] or "", item))
    if not candidates:
        return None, "无匹配规则"
    candidates.sort(key=lambda entry: (entry[0], entry[1], entry[2], entry[3], entry[4]), reverse=True)
    best = candidates[0][5]
    notes = []
    if candidates[0][1] == 0:
        notes.append("站点使用通配规则")
    if candidates[0][2] == 0:
        notes.append("类目使用通配规则")
    elif candidates[0][2] == 1:
        notes.append("类目为模糊匹配")
    return best, "；".join(notes) or "精确匹配"


def convert(amount, from_currency, to_currency, fx):
    if not amount or not from_currency:
        return amount, True
    from_currency = from_currency.upper()
    to_currency = (to_currency or from_currency).upper()
    if from_currency == to_currency:
        return amount, True
    if from_currency in fx and to_currency in fx:
        return amount * fx[from_currency] / fx[to_currency], True
    return amount, False


def evaluate(order, rates, fx, max_stale_days, low_margin):
    rule, note = match_rule(order, rates)
    problems = []
    if rule is None:
        # 未匹配到规则时仍保留订单基础信息与收入，便于人工补算
        result = {field: None for field in
                  ("commission", "payment_fee", "tax", "fulfillment_fee", "fba_fee", "storage_fee",
                   "fees_total", "profit", "margin", "breakeven_roas")}
        result.update({
            "sku": order["sku"], "platform": order["platform"], "site": order["site"],
            "category": order["category"], "price": round(order["price"], 2), "qty": order["qty"],
            "currency": order["currency"],
            "revenue": round(order["price"] * order["qty"], 2),
            "cost_total": round((order["cost"] or 0.0) * order["qty"], 2),
            "matched_rule": None, "match_note": note,
        })
        return result, [sheetio.flag("high", "rule_missing",
                         f"{order['platform']}/{order['site']}/{order['category']} 未在费率表中匹配到规则",
                         "补录该组合的费率，或人工核算后再定价")]

    target = order["currency"] or rule["currency"]
    commission = order["price"] * rule["commission_rate"]
    payment = order["price"] * rule["payment_rate"]
    tax = order["price"] * rule["tax_rate"]
    fulfillment = rule["fulfillment_fee"]
    fba = rule["fba_fee"]
    storage = rule["storage_fee"]
    per_order_fees = commission + payment + tax + fulfillment + fba + storage
    raw_fees = per_order_fees * order["qty"]
    fees_total, converted = convert(raw_fees, rule["currency"], target, fx)
    if not converted:
        problems.append(sheetio.flag("high", "fx_missing",
                                     f"{rule['currency']} 与 {target} 之间缺少汇率，费用本轮按 1:1 计入",
                                     f"补 --fx {rule['currency']}:<汇率> 与 --fx {target}:<汇率>，"
                                     f"或直接指定 --target-currency 后重算"))
    cost_total = (order["cost"] or 0.0) * order["qty"]
    revenue = order["price"] * order["qty"]
    profit = revenue - fees_total - cost_total
    margin = (profit / revenue) if revenue else None
    breakeven = (revenue / (revenue - fees_total - cost_total)) if (revenue - fees_total - cost_total) > 0 else None
    if profit < 0:
        problems.append(sheetio.flag("high", "negative_margin",
                                     f"{order['sku']} 单件净利 {profit:.2f} {target}（收入 {revenue:.2f} − 费用 {fees_total:.2f} − 成本 {cost_total:.2f}）",
                                     "核对费率与成本，确认是否调价或停售"))
    elif margin is not None and margin < low_margin:
        problems.append(sheetio.flag("medium", "thin_margin",
                                     f"{order['sku']} 毛利率 {margin:.1%} 低于 {low_margin:.0%}",
                                     "确认是否受促销、广告或汇率挤压"))
    if not rule["effective_date"]:
        problems.append(sheetio.flag("medium", "rate_missing_date",
                                     f"匹配到的规则缺少生效日期（{rule['file']} 第 {rule['row']} 行）",
                                     "回官方来源补生效日期"))
    else:
        age = (datetime.date.today() - datetime.date.fromisoformat(rule["effective_date"])).days
        if age > max_stale_days:
            problems.append(sheetio.flag("medium", "stale_rate",
                                         f"费率生效日期距今 {age} 天，可能已调整",
                                         "回官方来源核对最新费率"))
    if "通配" in note or "模糊" in note:
        problems.append(sheetio.flag("low", "wildcard_match", f"{order['sku']} {note}",
                                     "如需精确核算，补录该站点/类目的专属费率"))

    result = {
        "sku": order["sku"], "platform": order["platform"], "site": order["site"],
        "category": order["category"], "price": round(order["price"], 2), "qty": order["qty"],
        "currency": target,
        "commission": round(convert(commission * order["qty"], rule["currency"], target, fx)[0], 2),
        "payment_fee": round(convert(payment * order["qty"], rule["currency"], target, fx)[0], 2),
        "tax": round(convert(tax * order["qty"], rule["currency"], target, fx)[0], 2),
        "fulfillment_fee": round(convert(fulfillment * order["qty"], rule["currency"], target, fx)[0], 2),
        "fba_fee": round(convert(fba * order["qty"], rule["currency"], target, fx)[0], 2),
        "storage_fee": round(convert(storage * order["qty"], rule["currency"], target, fx)[0], 2),
        "fees_total": round(fees_total, 2),
        "cost_total": round(cost_total, 2),
        "revenue": round(revenue, 2),
        "profit": round(profit, 2),
        "margin": round(margin, 4) if margin is not None else None,
        "breakeven_roas": round(breakeven, 2) if breakeven else None,
        "matched_rule": {
            "platform": rule["platform"], "site": rule["site"] or "*", "category": rule["category"] or "*",
            "commission_rate": rule["commission_rate"], "source": rule["source"],
            "effective_date": rule["effective_date"], "currency": rule["currency"],
            "file": rule["file"], "row": rule["row"], "condition": rule["condition"],
        },
        "match_note": note,
    }
    return result, problems


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="按平台费率表核算订单费用、净利与保本 ROAS，并标记扣费风险。")
    parser.add_argument("orders", nargs="?", help="订单/商品明细表：.csv/.xlsx")
    parser.add_argument("--rates", action="append", required=True, metavar="费率表",
                        help="费率对照表，可重复传入多个平台/站点文件")
    parser.add_argument("--summary", action="store_true", help="只输出费率表覆盖情况，不核算订单")
    parser.add_argument("--out-json", default=None, help="输出结果 JSON")
    parser.add_argument("--out", default=None, help="输出明细 CSV")
    parser.add_argument("--out-xlsx", default=None, help="输出 Excel 工作簿（明细 + 总计 + 未匹配订单 + 费率覆盖）")
    parser.add_argument("--fx", action="append", default=[], metavar="币种:汇率",
                        help="1 单位该币种等于多少目标币种，例如 USD:7.20，可重复")
    parser.add_argument("--target-currency", default=None,
                        help="统一折算目标币种；不指定时沿用订单自身币种，此时费率币种与订单币种不同就必须给出两个币种的汇率")
    parser.add_argument("--max-stale-days", type=int, default=180, help="费率超过该天数标记为可能过旧，默认 180")
    parser.add_argument("--low-margin", type=float, default=0.05, help="毛利率低于该值标记提醒，默认 0.05")
    parser.add_argument("--default-qty", type=float, default=1.0, help="订单表没有数量列时的默认数量")
    parser.add_argument("--map", action="append", default=[], metavar="原列名=标准字段")
    parser.add_argument("--sheet", default=1, help="xlsx 工作表序号或名称，默认第 1 个")
    args = parser.parse_args(argv)

    fx = {}
    for item in args.fx:
        if ":" not in item:
            sys.stderr.write(f"[fee_check] 忽略无法解析的汇率：{item}（应写成 USD:7.20）\n")
            continue
        currency, value = item.split(":", 1)
        rate = to_number(value)
        if rate:
            fx[currency.strip().upper()] = rate
    if args.target_currency:
        # 汇率以目标币种为基准，目标币种自身汇率为 1
        fx.setdefault(args.target_currency.strip().upper(), 1.0)

    rates, rate_flags = load_rates(args.rates, sheet=args.sheet)
    flags = list(rate_flags)
    summary = describe_rates(rates)
    if not rates:
        sheetio.emit(sheetio.make_envelope("fee_check", "blocked", 0.0, {"summary": summary}, flags +
                                           [sheetio.flag("high", "no_rate_rows", "费率表没有可用规则行", "确认文件与列名")]), out_json=args.out_json)
        return 2

    if args.summary or not args.orders:
        for field in summary["rate_columns_all_zero"]:
            flags.append(sheetio.flag("medium", "rate_column_all_zero",
                                      f"整张费率表 {field} 均为 0", "确认该列是否漏填"))
        if summary["without_effective_date"]:
            flags.append(sheetio.flag("medium", "rate_missing_date",
                                      f"{summary['without_effective_date']} 行费率缺少生效日期",
                                      "补齐生效日期，否则无法判断是否已被平台调整"))
        if args.out_xlsx:
            sheetio.write_xlsx(args.out_xlsx, [rate_summary_sheet(summary)])
        envelope = sheetio.make_envelope("fee_check", "ok", 0.85, {"summary": summary}, flags)
        sheetio.emit(envelope, out_json=args.out_json)
        return 0

    mapping = sheetio.apply_mapping(args.map)
    try:
        headers, body = sheetio.read_table(args.orders, sheet=args.sheet)
    except (OSError, ValueError) as error:
        sheetio.emit(sheetio.make_envelope("fee_check", "blocked", 0.0, {"error": str(error)},
                                           [sheetio.flag("high", "input_error", str(error), "确认文件路径与格式")]), out_json=args.out_json)
        return 2

    if mapping:
        headers = [mapping.get(norm_key(header), header) for header in headers]
    columns = sheetio.column_map(headers, ORDER_FIELDS)
    if "price" not in columns:
        flags.append(sheetio.flag("high", "missing_price",
                                  "订单表没有价格列，无法核算费率",
                                  "用 --map 指定价格列，例如 --map 售价=price"))
        sheetio.emit(sheetio.make_envelope("fee_check", "blocked", 0.0, {"summary": summary}, flags), out_json=args.out_json)
        return 2

    results = []
    unmatched = []
    for index, raw in enumerate(body, start=2):
        def cell(field):
            position = columns.get(field)
            return raw[position] if position is not None and position < len(raw) else ""

        price = to_number(cell("price"))
        if price is None:
            continue
        currency = (clean_text(cell("currency")) or args.target_currency or "").upper()
        order = {
            "sku": clean_text(cell("sku")) or f"row{index}",
            "platform": clean_text(cell("platform")),
            "site": clean_text(cell("site")),
            "category": clean_text(cell("category")),
            "price": price,
            "qty": to_number(cell("qty")) or args.default_qty,
            "cost": to_number(cell("cost")),
            "currency": currency,
            "date": to_date(cell("date")),
        }
        if args.target_currency:
            order["currency"] = args.target_currency.upper()
        if not order["platform"]:
            flags.append(sheetio.flag("medium", "missing_platform",
                                      f"第 {index} 行没有平台字段，无法匹配费率", "补齐平台列"))
            continue
        result, problems = evaluate(order, rates, fx, args.max_stale_days, args.low_margin)
        result["row"] = index
        results.append(result)
        flags.extend(problems)
        if result["matched_rule"] is None:
            unmatched.append(index)

    totals = {
        "orders": len(results),
        "revenue": round(sum(item["revenue"] or 0 for item in results), 2),
        "fees": round(sum(item["fees_total"] or 0 for item in results), 2),
        "cost": round(sum(item["cost_total"] or 0 for item in results), 2),
        "profit": round(sum(item["profit"] or 0 for item in results), 2),
        "unmatched_orders": len(unmatched),
    }
    if totals["revenue"]:
        totals["margin"] = round(totals["profit"] / totals["revenue"], 4)
    coverage = (len(results) - len(unmatched)) / len(results) if results else 0.0
    data = {"summary": summary, "totals": totals, "orders": results,
            "unmatched_rows": unmatched[:50], "fx_used": fx, "target_currency": args.target_currency}

    export_headers = ["row", "sku", "platform", "site", "category", "price", "qty", "currency",
                      "commission", "payment_fee", "tax", "fulfillment_fee", "fba_fee", "storage_fee",
                      "fees_total", "cost_total", "revenue", "profit", "margin", "breakeven_roas",
                      "match_note", "rule_source", "rule_effective_date", "rule_file"]
    rows = []
    if args.out or args.out_xlsx:
        for item in results:
            rule = item["matched_rule"] or {}
            rows.append([item.get("row"), item["sku"], item["platform"], item["site"], item["category"],
                         item["price"], item["qty"], item["currency"], item.get("commission"),
                         item.get("payment_fee"), item.get("tax"), item.get("fulfillment_fee"),
                         item.get("fba_fee"), item.get("storage_fee"), item.get("fees_total"),
                         item.get("cost_total"), item.get("revenue"), item.get("profit"),
                         item.get("margin"), item.get("breakeven_roas"), item["match_note"],
                         rule.get("source", ""), rule.get("effective_date", ""), rule.get("file", "")])
    if args.out:
        sheetio.write_csv(args.out, export_headers, rows)
    if args.out_xlsx:
        sheetio.write_xlsx(args.out_xlsx, [
            {"name": "费用明细", "headers": export_headers, "rows": rows},
            {"name": "核算总计", "headers": ["指标", "数值"],
             "rows": [["订单行数", totals["orders"]], ["收入合计", totals["revenue"]],
                      ["费用合计", totals["fees"]], ["成本合计", totals["cost"]],
                      ["利润合计", totals["profit"]], ["毛利率", totals.get("margin", "")],
                      ["未匹配规则的订单数", totals["unmatched_orders"]]]},
            {"name": "未匹配订单", "headers": ["表内行号", "说明"],
             "rows": [[index, "未匹配到费率规则，费用无法核算"] for index in unmatched]},
            rate_summary_sheet(summary),
        ])

    if unmatched:
        flags.append(sheetio.flag("high", "rule_coverage_gap",
                                  f"{len(unmatched)} 个订单未匹配到费率规则，费用无法核算",
                                  "优先补录这些平台/站点/类目组合的费率"))
    status = "ok" if not unmatched else "partial"
    seen_sources = set()
    rate_sources = []
    for item in rates:
        key = (item["file"], item["effective_date"])
        if key in seen_sources:
            continue
        seen_sources.add(key)
        rate_sources.append({"ref": item["file"], "as_of": item["effective_date"] or "未标注"})
    envelope = sheetio.make_envelope(
        "fee_check", status, round(0.4 + 0.55 * coverage, 2), data, flags,
        sources=rate_sources,
        assumptions=["费率取自 --rates 指定的对照表，未在表中的费用（如广告费、退货处理费）未计入",
                     "保本 ROAS = 收入 / (收入 − 费用 − 成本)，低于该值的广告投放即为亏损"]
                      + ([f"币种按 --fx 汇率折算到 {args.target_currency}；订单表中的价格与成本视为已使用该币种"]
                         if args.target_currency else []),
    )
    sheetio.emit(envelope, out_json=args.out_json)
    sys.stderr.write(f"[fee_check] 核算 {len(results)} 单，未匹配规则 {len(unmatched)} 单，"
                     f"合计费用 {totals['fees']}，合计利润 {totals['profit']}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
