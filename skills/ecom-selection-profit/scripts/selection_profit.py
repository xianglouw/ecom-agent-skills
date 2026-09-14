#!/usr/bin/env python3
"""选品利润测算：按「售价 − 佣金 − 运费 − 关税 − 成本」逐站点、逐渠道算利润与保本价。

用法：
  python3 selection_profit.py items.csv --freight freight.csv --rates rates.csv \
    --site-currency MX:MXN,BR:BRL --fx MXN:18.5,BRL:5.4 \
    --de-minimis 50 --duty-rate 0.16 --target-margin 0.3 \
    --free-shipping-threshold MX:299,BR:79 \
    --out selection.csv --out-json selection.json

商品表字段：sku、cost（落地成本）、weight（单件重量）、box_qty（箱规）、price（零售价）、
wholesale_price（批发价）——价格与成本都缺失时仍会输出保本价与目标售价。
运费表字段：site、weight_min/weight_max（或单个重量区间列）、freight（运费）、currency。
佣金率来自 --rates 的费率表（复用阶段 1 的对照表）或 --commission 直接指定。

只读输入，只写 --out/--out-json/--out-md/--quarantine 指定文件；
外币与关税由命令行参数显式给出，不内置任何费率。
"""

import argparse
import os
import re
import sys

import sheetio
from sheetio import clean_text, to_number

ITEM_FIELDS = ["sku", "product_name", "cost", "weight", "box_qty", "price", "wholesale_price"]
FREIGHT_FIELDS = ["site", "weight_min", "weight_max", "weight_band", "freight", "currency"]

EXPORT_HEADERS = ["sku", "product_name", "site", "channel", "currency", "fx_rate", "qty_per_order",
                  "billed_weight", "weight_unit", "freight_usd", "freight_per_unit_usd", "price_usd",
                  "price_local", "commission_rate", "commission_usd", "cost_usd", "duty_usd",
                  "profit_usd", "margin", "breakeven_price_usd", "target_price_usd", "note"]

LB_PER_KG = 2.2046226218


def parse_pairs(items, value_type=str, what="参数"):
    """解析 KEY:VALUE 形式，支持逗号分隔或多次传参（如 MX:MXN,BR:BRL）。"""
    result = {}
    for item in items or []:
        for piece in str(item).replace("，", ",").split(","):
            text = clean_text(piece)
            if not text:
                continue
            if ":" not in text:
                raise ValueError(f"{what} 需要写成 KEY:VALUE（逗号分隔可写多组），收到：{piece}")
            key, value = text.split(":", 1)
            key = clean_text(key)
            if not key:
                raise ValueError(f"{what} 的 KEY 不能为空：{piece}")
            result[key.upper()] = value_type(clean_text(value))
    return result


def parse_band(text):
    """解析重量区间，返回 (min, max)；只有一个数字时视为下限，max 为 None。"""
    numbers = re.findall(r"\d+(?:\.\d+)?", sheetio.to_halfwidth(clean_text(text)))
    if not numbers:
        return None, None
    if len(numbers) == 1:
        return float(numbers[0]), None
    values = [float(n) for n in numbers]
    return min(values), max(values)


def load_freight(paths, sheet, header_row):
    """读运费表，返回 (rows, flags)。rows 为 {site: [(min, max, usd, currency, row)]}。"""
    by_site = {}
    flags = []
    for path in paths:
        headers, body = sheetio.read_table(path, sheet=sheet, header_row=header_row)
        columns = sheetio.column_map(headers, FREIGHT_FIELDS)
        if "site" not in columns or "freight" not in columns:
            flags.append(sheetio.flag("high", "freight_table_incomplete",
                                      f"{os.path.basename(path)} 缺少站点列或运费列",
                                      "运费表至少要有 站点 / 重量区间 / 运费 三列"))
            continue
        if "weight_min" not in columns and "weight_band" not in columns:
            flags.append(sheetio.flag("high", "freight_table_incomplete",
                                      f"{os.path.basename(path)} 缺少重量区间列",
                                      "补 重量区间 或 重量下限/重量上限 两列"))
            continue
        for index, raw in enumerate(body, start=header_row + 1):
            def cell(field):
                position = columns.get(field)
                return raw[position] if position is not None and position < len(raw) else ""

            site = clean_text(cell("site"))
            freight = to_number(cell("freight"))
            if not site or freight is None:
                continue
            if "weight_band" in columns:
                low, high = parse_band(cell("weight_band"))
            else:
                low = to_number(cell("weight_min"))
                high = to_number(cell("weight_max"))
            if low is None:
                continue
            currency = (clean_text(cell("currency")) or "USD").upper()
            by_site.setdefault(site, []).append((low, high, freight, currency, index))
    if not by_site:
        flags.append(sheetio.flag("high", "no_freight_rows", "运费表没有可用数据行", "确认文件与表头行号"))
    return by_site, flags


def match_freight(bands, weight):
    """按重量取运费行：命中多段时取下限最大的那段（边界取更贵的一档，偏保守）。"""
    hits = [band for band in bands if band[0] <= weight and (band[1] is None or weight <= band[1])]
    if not hits:
        return None
    return max(hits, key=lambda band: band[0])


def load_rates_map(paths, sheet):
    """从费率表提 {site: commission_rate}，取每个站点最先出现且佣金非 0 的行。"""
    result = {}
    sources = []
    for path in paths:
        headers, body = sheetio.read_table(path, sheet=sheet)
        columns = sheetio.column_map(headers, ["site", "platform", "category", "commission_rate",
                                               "source", "effective_date"])
        if "commission_rate" not in columns or "site" not in columns:
            continue
        ref, as_of = os.path.basename(path), "未标注"
        for raw in body:
            def cell(field):
                position = columns.get(field)
                return raw[position] if position is not None and position < len(raw) else ""

            site = clean_text(cell("site"))
            rate = to_number(cell("commission_rate"))
            if not site or rate is None:
                continue
            key = site.upper()
            result.setdefault(key, rate)
            if "source" in columns:
                ref = clean_text(cell("source")) or ref
            if "effective_date" in columns:
                as_of = sheetio.to_date(cell("effective_date")) or as_of
        if result:
            sources.append({"ref": ref, "as_of": as_of})
    return result, sources


def breakeven_price(cost, freight, commission_rate, duty_rate, de_minimis):
    """保本售价：(成本 + 运费) / (1 − 佣金率 [− 税率])，跨过关税门槛时按含税口径再算一次。"""
    base = cost + freight
    rate = commission_rate or 0.0
    if rate >= 1:
        return None
    price = base / (1 - rate)
    if duty_rate and de_minimis is not None and price > de_minimis and rate + duty_rate < 1:
        price = base / (1 - rate - duty_rate)
    return round(price, 2)


def target_price(cost, freight, commission_rate, duty_rate, target_margin):
    base = cost + freight
    denominator = 1 - (commission_rate or 0.0) - (duty_rate or 0.0) - (target_margin or 0.0)
    if denominator <= 0:
        return None
    return round(base / denominator, 2)


def fmt(value, digits=2, percent=False):
    if value is None or value == "":
        return "—"
    if percent:
        return f"{value:.1%}"
    return f"{value:,.{digits}f}"


def fmt_local(value, fx_rate):
    """当地币金额：汇率大于 100 的币种（JPY/CLP/COP/ARS 等）不显示小数。"""
    if value is None:
        return "—"
    return f"{value:,.0f}" if fx_rate and fx_rate >= 100 else f"{value:,.2f}"


def build_markdown(data, args, unpriced_rows):
    """把测算结果排成可读的 Markdown 表：先站点汇总，再按站点列 SKU 明细（亏损在前）。"""
    lines = ["# 选品利润测算", ""]
    lines.append(f"- 范围：{data['item_count']} 个 SKU × {len(data['sites'])} 个站点 × "
                 f"{len(data['channels'])} 个渠道（{'/'.join(data['channels'])}），"
                 f"共 {data['row_count']} 行、{data['priced_rows']} 行可算净利")
    lines.append(f"- 口径：利润 = 售价 − 平台佣金 − 单件运费 − 关税 − 落地成本；"
                 f"免税门槛 {fmt(args.de_minimis)} USD、关税率 {fmt(args.duty_rate, percent=True)}、"
                 f"目标毛利 {fmt(args.target_margin, percent=True)}")
    lines.append(f"- 单位：商品重量按 {args.item_weight_unit}、运费表按 {args.freight_weight_unit}，"
                 "1 kg = 2.2046226218 lb；金额除当地售价外均为 USD")
    lines.append("")

    lines.append("## 站点汇总")
    lines.append("")
    lines.append("| 站点 | 币种 | 行数 | 可测算 | 负毛利 | 平均毛利 | 最低毛利 | 最低净利 |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for site in data["sites"]:
        items = [item for item in data["results"] if item["site"] == site]
        priced = [item for item in items if item["profit_usd"] is not None]
        margins = [item["margin"] for item in priced if item["margin"] is not None]
        profits = [item["profit_usd"] for item in priced]
        currency = items[0]["currency"] if items else ""
        lines.append(f"| {site} | {currency or '—'} | {len(items)} | {len(priced)} | "
                     f"{sum(1 for item in priced if item['profit_usd'] < 0)} | "
                     f"{fmt(sum(margins) / len(margins), percent=True) if margins else '—'} | "
                     f"{fmt(min(margins), percent=True) if margins else '—'} | "
                     f"{fmt(min(profits)) if profits else '—'} |")
    lines.append("")

    for site in data["sites"]:
        items = [item for item in data["results"] if item["site"] == site]
        if not items:
            continue
        currency = items[0]["currency"] or "—"
        lines.append(f"## {site}（{currency}）")
        lines.append("")
        lines.append("| SKU | 渠道 | 售价(USD) | 当地售价 | 运费/件 | 佣金率 | 关税 | 净利(USD) | 毛利 | "
                     "保本价(USD) | 目标售价(USD) | 备注 |")
        lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
        ordered = sorted(items, key=lambda item: (item["profit_usd"] is None,
                                                  item["profit_usd"] if item["profit_usd"] is not None else 0))
        fx_rate = data["fx_used"].get((currency or "").upper())
        for item in ordered:
            notes = []
            if item["price_usd"] is None:
                notes.append("未给售价")
            elif item["profit_usd"] is not None and item["profit_usd"] < 0:
                notes.append("亏损")
            elif (item["margin"] is not None and args.target_margin
                  and item["margin"] < args.target_margin):
                notes.append("低于目标毛利")
            threshold = data["free_shipping_thresholds"].get(site.upper())
            if (threshold and item["price_local"] is not None
                    and item["price_local"] < threshold):
                notes.append(f"低于免邮门槛 {threshold:g}")
            duty = item["duty_usd"]
            if duty is not None:
                duty_text = fmt(duty)
            elif item["price_usd"] is None:
                duty_text = "—"
            elif args.de_minimis is not None and item["price_usd"] > args.de_minimis:
                duty_text = "未计（缺税率）"
            else:
                duty_text = "0.00"
            lines.append(
                f"| {item['sku']} | {item['channel']} | {fmt(item['price_usd'])} | "
                f"{fmt_local(item['price_local'], fx_rate)} | {fmt(item['freight_per_unit_usd'])} | "
                f"{fmt(item['commission_rate'], percent=True)} | {duty_text} | "
                f"{fmt(item['profit_usd'])} | {fmt(item['margin'], percent=True)} | "
                f"{fmt(item['breakeven_price_usd'])} | {fmt(item['target_price_usd'])} | "
                f"{'；'.join(notes)} |")
        lines.append("")

    if unpriced_rows:
        lines.append(f"## 未纳入测算（{len(unpriced_rows)} 行）")
        lines.append("")
        lines.append("| SKU | 站点 | 渠道 | 原因 |")
        lines.append("|---|---|---|---|")
        for sku, _name, site, channel, reason in unpriced_rows[:50]:
            lines.append(f"| {sku} | {site} | {channel} | {reason} |")
        if len(unpriced_rows) > 50:
            lines.append(f"| … | | | 其余 {len(unpriced_rows) - 50} 行见 --quarantine 产物 |")
        lines.append("")

    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description="选品利润测算（多站点、多币种、零售与批发）")
    parser.add_argument("items", help="候选商品表：.csv/.xlsx，字段 sku/cost/weight/box_qty/price")
    parser.add_argument("--freight", action="append", required=True, metavar="运费表",
                        help="站点运费分段表，可重复传多个文件")
    parser.add_argument("--rates", action="append", default=[], metavar="费率表",
                        help="平台合规费率表，用于取站点佣金率（同阶段 1 的对照表）")
    parser.add_argument("--commission", action="append", default=[], metavar="站点:佣金率",
                        help="直接指定佣金率，如 MX:0.17；优先于 --rates")
    parser.add_argument("--site-currency", action="append", default=[], metavar="站点:币种",
                        help="站点当地币种，如 MX:MXN,BR:BRL")
    parser.add_argument("--fx", action="append", default=[], metavar="币种:汇率",
                        help="1 USD 兑该币种的汇率，由使用者手工维护，如 MXN:18.5")
    parser.add_argument("--free-shipping-threshold", action="append", default=[], metavar="站点:金额",
                        help="免邮门槛（当地币种），低于该价卖家不包邮，如 MX:299")
    parser.add_argument("--de-minimis", type=float, default=None,
                        help="关税/免税起征门槛（USD），超过则标记税费风险")
    parser.add_argument("--duty-rate", type=float, default=None,
                        help="超过门槛后适用的综合税率；不填只标记不计税")
    parser.add_argument("--target-margin", type=float, default=None, help="目标毛利率，低于则标记，如 0.3")
    parser.add_argument("--channel", default="retail", help="测算渠道：retail / wholesale / both，默认 retail")
    parser.add_argument("--cost-currency", default="USD", help="商品成本币种 USD 或 RMB，默认 USD")
    parser.add_argument("--cost-fx", type=float, default=None, help="1 USD 兑成本币种的汇率，成本为 RMB 时必填")
    parser.add_argument("--item-weight-unit", default="kg", choices=["kg", "lb"], help="商品重量单位，默认 kg")
    parser.add_argument("--freight-weight-unit", default="lb", choices=["kg", "lb"], help="运费表重量单位，默认 lb")
    parser.add_argument("--out", default=None, help="输出测算明细 CSV")
    parser.add_argument("--out-json", default=None, help="输出结果信封 JSON")
    parser.add_argument("--out-md", default=None, help="输出 Markdown 测算表（按站点分节，可直接阅读）")
    parser.add_argument("--quarantine", default=None, help="输出未能测算的行 CSV（含原因）")
    parser.add_argument("--out-xlsx", default=None,
                        help="输出 Excel 工作簿（测算明细 + 站点汇总 + 亏损与低毛利 + 未测算）")
    parser.add_argument("--map", action="append", default=[], metavar="原列名=标准字段")
    parser.add_argument("--sheet", default=1, help="商品表 xlsx 工作表序号或名称，默认第 1 个")
    parser.add_argument("--header-row", type=int, default=1, help="商品表表头行号")
    parser.add_argument("--freight-sheet", type=int, default=1, help="运费表 xlsx 工作表序号")
    parser.add_argument("--freight-header-row", type=int, default=1, help="运费表表头行号")
    args = parser.parse_args(argv)

    flags = []
    try:
        site_currency = parse_pairs(args.site_currency, str, "--site-currency")
        fx = parse_pairs(args.fx, float, "--fx")
        commission_override = parse_pairs(args.commission, float, "--commission")
        thresholds = parse_pairs(args.free_shipping_threshold, float, "--free-shipping-threshold")
    except ValueError as error:
        sheetio.emit(sheetio.make_envelope("selection_profit", "blocked", 0.0, {"error": str(error)},
                                           [sheetio.flag("high", "input_error", str(error), "确认参数写法")]),
                     out_json=args.out_json)
        return 2

    channels = ["retail", "wholesale"] if args.channel == "both" else [args.channel]
    if args.channel not in ("retail", "wholesale", "both"):
        flags.append(sheetio.flag("medium", "unknown_channel",
                                  f"--channel 收到 {args.channel}，按 retail 处理", "改用 retail/wholesale/both"))

    try:
        freight_map, freight_flags = load_freight(args.freight, args.freight_sheet, args.freight_header_row)
    except (OSError, ValueError) as error:
        sheetio.emit(sheetio.make_envelope("selection_profit", "blocked", 0.0, {"error": str(error)},
                                           [sheetio.flag("high", "input_error", str(error), "确认文件路径与格式")]),
                     out_json=args.out_json)
        return 2
    flags += freight_flags

    commission_map, rate_sources = {}, []
    if args.rates:
        commission_map, rate_sources = load_rates_map(args.rates, args.sheet)
    commission_map.update(commission_override)

    mapping = sheetio.apply_mapping(args.map)
    try:
        headers, body = sheetio.read_table(args.items, sheet=args.sheet, header_row=args.header_row)
    except (OSError, ValueError) as error:
        sheetio.emit(sheetio.make_envelope("selection_profit", "blocked", 0.0, {"error": str(error)},
                                           [sheetio.flag("high", "input_error", str(error), "确认文件路径与格式")]),
                     out_json=args.out_json)
        return 2
    if mapping:
        headers = [mapping.get(sheetio.norm_key(header), header) for header in headers]
    columns = sheetio.column_map(headers, ITEM_FIELDS)
    if "sku" not in columns:
        flags.append(sheetio.flag("high", "missing_sku", "商品表没有 SKU 列，无法逐品核算",
                                  "用 --map 指定，例如 --map 商品编码=sku"))
        sheetio.emit(sheetio.make_envelope("selection_profit", "blocked", 0.0, {"detected_columns": sorted(columns)},
                                           flags), out_json=args.out_json)
        return 2

    cost_currency = args.cost_currency.strip().upper()
    if cost_currency in ("RMB", "CNY") and not args.cost_fx:
        flags.append(sheetio.flag("high", "missing_cost_fx",
                                  "成本为 RMB 但未给 --cost-fx，无法折算成 USD",
                                  "补 --cost-fx 7.20（1 USD 兑 RMB），或改用 USD 成本表"))
    weight_to_kg = 1.0 if args.item_weight_unit == "kg" else 1.0 / LB_PER_KG
    freight_unit_is_lb = args.freight_weight_unit == "lb"

    rows = []
    results = []
    covered_sites = set()
    sites_without_commission = set()
    unpriced_freight_currency = set()
    sites_without_fx = set()
    no_freight_rows_dropped = []
    negative_rows = []
    thin_margin_rows = []
    duty_unknown_rows = []
    skus_without_weight = []
    unpriced_rows = []
    for index, raw in enumerate(body, start=args.header_row + 1):
        def cell(field):
            position = columns.get(field)
            return raw[position] if position is not None and position < len(raw) else ""

        sku = clean_text(cell("sku"))
        if not sku:
            continue
        name = clean_text(cell("product_name"))
        cost = to_number(cell("cost"))
        if cost is not None and cost_currency in ("RMB", "CNY") and args.cost_fx:
            cost = cost / args.cost_fx
        weight = to_number(cell("weight"))
        if weight is None or weight <= 0:
            skus_without_weight.append(sku)
        box_qty = to_number(cell("box_qty")) or 1.0
        prices = {"retail": to_number(cell("price")), "wholesale": to_number(cell("wholesale_price"))}

        for site, bands in sorted(freight_map.items()):
            for channel in channels:
                qty = 1.0 if channel == "retail" else box_qty
                currency = site_currency.get(site.upper(), "")
                fx_rate = fx.get(currency.upper()) if currency else None
                price = prices[channel]
                note = []

                billed_weight = (weight or 0) * qty
                match = match_freight(bands, billed_weight) if weight else None
                if match is None:
                    if weight:
                        no_freight_rows_dropped.append(f"{sku}@{site} {billed_weight:g}lb")
                    freight_total = None
                else:
                    covered_sites.add(site)
                    freight_total = match[2]
                    if match[3] != "USD":
                        rate = fx.get(match[3])
                        if rate:
                            freight_total = freight_total / rate
                        else:
                            unpriced_freight_currency.add(match[3])
                    freight_total = round(freight_total, 2)
                freight_per_unit = round(freight_total / qty, 2) if freight_total is not None else None

                rate = commission_map.get(site.upper()) or commission_map.get("*")
                if rate is None:
                    sites_without_commission.add(site)

                duty = None
                if price is not None and args.de_minimis is not None and price > args.de_minimis:
                    if args.duty_rate:
                        duty = round(price * args.duty_rate, 2)
                    else:
                        duty_unknown_rows.append(f"{sku}@{site} {price:.2f}USD")

                profit = margin = None
                if price is not None and freight_per_unit is not None and rate is not None:
                    commission = round(price * rate, 2)
                    profit = round(price - (cost or 0) - freight_per_unit - commission - (duty or 0), 2)
                    margin = round(profit / price, 4) if price else None
                    if profit < 0:
                        negative_rows.append((profit, f"{sku}@{site}({channel}) {profit:.2f}USD"))
                    elif args.target_margin and margin is not None and margin < args.target_margin:
                        thin_margin_rows.append((margin, f"{sku}@{site}({channel}) {margin:.1%}"))
                else:
                    commission = None
                    if price is None:
                        note.append("未提供售价，仅输出保本价与目标售价")
                        unpriced_rows.append([sku, name, site, channel, "未提供该渠道售价"])
                    elif not weight:
                        unpriced_rows.append([sku, name, site, channel, "缺少单件重量"])
                    elif freight_per_unit is None:
                        unpriced_rows.append([sku, name, site, channel,
                                              f"重量 {billed_weight:g}{args.freight_weight_unit} 超出运费表分段"])
                    elif rate is None:
                        unpriced_rows.append([sku, name, site, channel, "缺少站点佣金率"])

                price_local = None
                if price is not None and fx_rate:
                    price_local = round(price * fx_rate, 2)
                if currency and not fx_rate:
                    sites_without_fx.add(f"{site}({currency})")
                threshold = thresholds.get(site.upper())
                if threshold and price_local is not None and price_local < threshold:
                    note.append(f"低于免邮门槛 {threshold:g} {currency}")

                breakeven = None
                target = None
                if cost is not None and freight_per_unit is not None and rate is not None:
                    duty_rate = args.duty_rate if (price is None or price > (args.de_minimis or 0)) else 0.0
                    breakeven = breakeven_price(cost, freight_per_unit, rate, duty_rate, args.de_minimis)
                    target = target_price(cost, freight_per_unit, rate, duty_rate, args.target_margin)

                results.append({
                    "sku": sku, "site": site, "channel": channel,
                    "price_usd": price, "price_local": price_local, "currency": currency,
                    "freight_per_unit_usd": freight_per_unit, "commission_rate": rate,
                    "duty_usd": duty,
                    "profit_usd": profit, "margin": margin,
                    "breakeven_price_usd": breakeven, "target_price_usd": target,
                })
                rows.append([sku, name, site, channel, currency, fx_rate, qty, round(billed_weight, 4),
                             args.freight_weight_unit, freight_total, freight_per_unit, price, price_local,
                             rate, commission, round(cost, 2) if cost is not None else None, duty,
                             profit, margin, breakeven, target, "；".join(note)])

    if sites_without_commission:
        names = "、".join(sorted(sites_without_commission))
        flags.append(sheetio.flag("high", "commission_missing",
                                  f"{names} 没有佣金率，这些站点的利润无法核算",
                                  "在费率表补对应站点佣金率，或用 --commission 站点:佣金率 指定"))
    if unpriced_freight_currency:
        flags.append(sheetio.flag("high", "freight_currency_unpriced",
                                  f"运费表币种 {'、'.join(sorted(unpriced_freight_currency))} 没有汇率，未折算成 USD",
                                  "补 --fx 汇率或改用 USD 报价的运费表"))

    if skus_without_weight:
        preview = "、".join(skus_without_weight[:5]) + ("…" if len(skus_without_weight) > 5 else "")
        flags.append(sheetio.flag(
            "high", "missing_weight",
            f"{len(skus_without_weight)} 个 SKU 缺少有效重量（{preview}），这些 SKU 无法匹配运费、未纳入利润核算",
            "补齐单件重量（kg 或 lb）后重跑，本次结果不含这些 SKU"))
    if no_freight_rows_dropped:
        preview = "、".join(no_freight_rows_dropped[:5]) + ("…" if len(no_freight_rows_dropped) > 5 else "")
        flags.append(sheetio.flag(
            "medium", "freight_not_covered",
            f"{len(no_freight_rows_dropped)} 个 SKU×站点组合的重量超出运费表最大分段（{preview}），"
            "这些组合没有可用运费，未计入净利",
            "核对分段表上限或补充超重段报价，否则超重订单的真实运费会被低估"))
    if duty_unknown_rows:
        worst = max(duty_unknown_rows, key=lambda text: float(text.split()[-1].removesuffix("USD")))
        flags.append(sheetio.flag(
            "high", "duty_threshold_exceeded",
            f"{len(duty_unknown_rows)} 个 SKU×站点组合售价超过免税门槛 {args.de_minimis:g} USD 但未给 --duty-rate，"
            f"关税按 0 计，利润被高估（最高一档 {worst}）",
            "补 --duty-rate（如 0.16 表示 16% IVA）后重算，或由人工按目的国清关口径确认"))
    if negative_rows:
        negative_rows.sort()
        worst = "；".join(text for _, text in negative_rows[:3])
        flags.append(sheetio.flag(
            "high", "negative_margin",
            f"{len(negative_rows)} 个 SKU×站点组合净利为负，亏损最大 3 项：{worst}",
            "逐项人工复核定价、运费档位与佣金率，确认后调整售价或下架该站点"))
    if thin_margin_rows:
        thin_margin_rows.sort()
        worst = "；".join(text for _, text in thin_margin_rows[:3])
        flags.append(sheetio.flag(
            "medium", "below_target_margin",
            f"{len(thin_margin_rows)} 个 SKU×站点组合毛利低于目标 {args.target_margin:.0%}，最低 3 项：{worst}",
            "参考输出中的 target_price_usd 提价至目标毛利，或更换更优运费档"))
    if sites_without_fx:
        names = "、".join(sorted(sites_without_fx))
        flags.append(sheetio.flag(
            "medium", "missing_fx",
            f"{names} 缺少汇率，只输出 USD 口径，未给出当地币售价",
            "补 --fx 币种:汇率 后重算，汇率由使用者按当期实际情况维护"))

    unpriced_headers = ["sku", "product_name", "site", "channel", "_未测算原因"]
    if args.out:
        sheetio.write_csv(args.out, EXPORT_HEADERS, rows)
    if args.quarantine:
        sheetio.write_csv(args.quarantine, unpriced_headers, unpriced_rows)

    priced = [item for item in results if item["profit_usd"] is not None]
    negative = [item for item in priced if item["profit_usd"] < 0]
    high_level = [flag for flag in flags if flag["level"] == "high"]
    coverage = len(covered_sites) / len(freight_map) if freight_map else 0.0
    sites = sorted(freight_map)
    data = {
        "sites": sites,
        "channels": channels,
        "item_count": len({item["sku"] for item in results}),
        "row_count": len(results),
        "priced_rows": len(priced),
        "totals": {
            "negative_margin_rows": len(negative),
            "avg_margin": round(sum(item["margin"] for item in priced if item["margin"] is not None)
                                / len(priced), 4) if priced else None,
        },
        "de_minimis_usd": args.de_minimis,
        "duty_rate": args.duty_rate,
        "fx_used": {key: value for key, value in fx.items()},
        "site_currency": site_currency,
        "free_shipping_thresholds": thresholds,
        "results": results,
    }

    if args.out_md:
        with open(args.out_md, "w", encoding="utf-8") as handle:
            handle.write(build_markdown(data, args, unpriced_rows))

    if args.out_xlsx:
        site_rows = []
        for site in sorted({item["site"] for item in results}):
            group = [item for item in results if item["site"] == site and item["profit_usd"] is not None]
            if not group:
                site_rows.append([site, 0, "", "", "", "", "未测算"])
                continue
            site_rows.append([
                site, len(group),
                round(sum(item["profit_usd"] for item in group) / len(group), 2),
                round(min(item["profit_usd"] for item in group), 2),
                round(sum(item["profit_usd"] for item in group), 2),
                round(sum(item["margin"] for item in group if item["margin"] is not None)
                      / len(group), 4),
                "有亏损" if any(item["profit_usd"] < 0 for item in group) else "正常",
            ])
        risk_rows = [row for row in rows
                     if isinstance(row[17], (int, float))
                     and (row[17] < 0 or (isinstance(row[18], (int, float))
                                          and row[18] < args.target_margin))]
        risk_rows.sort(key=lambda row: row[17])
        sheetio.write_xlsx(args.out_xlsx, [
            {"name": "测算明细", "headers": EXPORT_HEADERS, "rows": rows},
            {"name": "站点汇总", "headers": ["站点", "可算行数", "平均净利", "最低净利",
                                             "净利合计", "平均毛利率", "判定"], "rows": site_rows},
            {"name": "亏损与低毛利", "headers": EXPORT_HEADERS, "rows": risk_rows},
            {"name": "未测算", "headers": unpriced_headers, "rows": unpriced_rows},
        ])

    status = "ok"
    if high_level:
        status = "partial"
    row_coverage = len(priced) / len(results) if results else 0.0
    confidence = round(0.3 + 0.5 * coverage + 0.2 * row_coverage, 2) if freight_map else 0.4
    if not priced:
        confidence = min(confidence, 0.5)
    if high_level:
        confidence = min(confidence, 0.7)
    elif any(flag["level"] == "medium" for flag in flags):
        confidence = min(confidence, 0.85)
    confidence = min(confidence, 0.95)

    envelope = sheetio.make_envelope(
        "selection_profit", status, confidence, data, flags,
        sources=rate_sources + [{"ref": os.path.basename(path), "as_of": ""} for path in args.freight],
        assumptions=[
            "利润 = 售价 − 平台佣金 − 单件运费 − 关税 − 落地成本；落地成本需自行包含采购、头程与入仓费",
            "运费按「站点 + 计费重量」匹配分段表；命中多段时取下限更大的一档（边界偏保守）",
            f"商品重量按 {args.item_weight_unit} 读取、运费表重量按 {args.freight_weight_unit} 计，"
            "1 kg = 2.2046226218 lb",
            "汇率与其他费率全部来自命令行参数，由使用者按当期实际情况手工维护",
            "关税按「售价超过门槛即全额计税」估算；实际以目的国清关口径与申报价为准",
        ],
    )
    sheetio.emit(envelope, out_json=args.out_json)
    sys.stderr.write(f"[selection_profit] {len(results)} 行测算（{len(priced)} 行可算净利），"
                     f"负毛利 {len(negative)} 行，站点 {len(sites)} 个\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
