#!/usr/bin/env python3
"""阶段 4：采购订单（PO）生成与校验。

用法示例：
  python3 po_build.py sourcing.csv --supplier "供应商A" --currency USD --lead-time 30 \
      --out PO.csv --report PO.report.json --max-amount 5000

把选品/补货需求表转成供应商可直接执行的 PO 单，并在生成前拦下必填缺失、数量单价异常、
重复行、MOQ 不足、单位不一致、金额对不上、超审批阈值、交期来不及这类问题。
只读输入，只写 --out/--report 指定文件。
"""

import argparse
import datetime
import os
import sys

import sheetio
from sheetio import clean_text, norm_key, to_date, to_number

LINE_FIELDS = ["sku", "product_name", "spec", "qty", "unit_price", "unit", "amount",
               "moq", "lead_time_days", "remark", "expected_arrival"]


def build_lines(headers, body, columns, args):
    good, isolated, flags = [], [], []
    duplicates = {}
    for index, raw in enumerate(body, start=2):
        def cell(field):
            position = columns.get(field)
            return raw[position] if position is not None and position < len(raw) else ""

        line = {
            "row": index,
            "sku": clean_text(cell("sku")),
            "product_name": clean_text(cell("product_name")),
            "spec": clean_text(cell("spec")),
            "qty": to_number(cell("qty")),
            "unit_price": to_number(cell("unit_price")),
            "unit": clean_text(cell("unit")) or args.default_unit,
            "amount": to_number(cell("amount")),
            "moq": to_number(cell("moq")),
            "lead_time_days": to_int_or_none(cell("lead_time_days"), args.lead_time),
            "remark": clean_text(cell("remark")),
            "expected_arrival": to_date(cell("expected_arrival")),
        }
        reasons = []
        if not line["sku"]:
            reasons.append("缺少 SKU")
        if line["qty"] is None:
            reasons.append("缺少数量")
        elif line["qty"] <= 0:
            reasons.append(f"数量非法（{line['qty']:g}）")
        if line["unit_price"] is None:
            reasons.append("缺少单价")
        elif line["unit_price"] <= 0:
            reasons.append(f"单价非法（{line['unit_price']:g}）")
        if reasons:
            isolated.append((line, "；".join(reasons)))
            continue
        key = (norm_key(line["sku"]), norm_key(line["spec"]))
        duplicates.setdefault(key, []).append(index)
        good.append(line)

    for key, rows in duplicates.items():
        if len(rows) > 1:
            flags.append(sheetio.flag("medium", "duplicate_line",
                                      f"SKU {key[0]} 规格 {key[1] or '-'} 出现 {len(rows)} 行（第 {rows} 行）",
                                      "确认是重复录入还是确实要拆单，合并后再下单"))
    if isolated:
        flags.append(sheetio.flag("high", "line_isolated",
                                  f"{len(isolated)} 行因缺少 SKU/数量/单价被隔离，未进入 PO",
                                  "退回需求表补齐后再生成"))
    return good, isolated, flags


def to_int_or_none(value, fallback):
    number = to_number(value)
    if number is None:
        return fallback
    return int(round(number))


def main(argv=None):
    parser = argparse.ArgumentParser(description="把采购/补货需求表生成 PO 单并做下单前校验。")
    parser.add_argument("input", help="需求或报价表：.csv/.xlsx")
    parser.add_argument("--supplier", required=True, help="供应商名称")
    parser.add_argument("--currency", default=None, help="采购币种，如 USD；表内有币种列时以表内为准")
    parser.add_argument("--out", required=True, help="输出 PO 单 CSV")
    parser.add_argument("--report", default=None, help="输出校验报告 JSON")
    parser.add_argument("--po-no", default=None, help="PO 号；不填则按日期自动生成")
    parser.add_argument("--order-date", default=None, help="下单日期，默认今天")
    parser.add_argument("--lead-time", type=int, default=30, help="默认交期天数，默认 30")
    parser.add_argument("--moq", type=float, default=None, help="统一最小起订量，表内 moq 列优先")
    parser.add_argument("--max-amount", type=float, default=None, help="审批金额上限，超过则标记需资金终审")
    parser.add_argument("--arrive-by", default=None, help="要求到仓日期，用于反推最晚下单日")
    parser.add_argument("--default-unit", default="件", help="表内没有单位列时的默认单位")
    parser.add_argument("--trade-term", default="", help="贸易条款，如 FOB / DDP")
    parser.add_argument("--payment-term", default="", help="付款条件，如 T/T 30%%+70%%")
    parser.add_argument("--map", action="append", default=[], metavar="原列名=标准字段")
    parser.add_argument("--sheet", type=int, default=1, help="xlsx 工作表序号")
    args = parser.parse_args(argv)

    order_date = to_date(args.order_date) or datetime.date.today().strftime("%Y-%m-%d")
    arrive_by = to_date(args.arrive_by)
    po_no = args.po_no or f"PO-{order_date.replace('-', '')}-001"

    try:
        headers, body = sheetio.read_table(args.input, sheet=args.sheet)
    except (OSError, ValueError) as error:
        sheetio.emit(sheetio.make_envelope("po_build", "blocked", 0.0, {"error": str(error)},
                                           [sheetio.flag("high", "input_error", str(error), "确认文件路径与格式")]))
        return 2
    if not headers:
        sheetio.emit(sheetio.make_envelope("po_build", "blocked", 0.0, {"error": "空表"},
                                           [sheetio.flag("high", "empty_input", "没有读到表头", "确认表头行")]))
        return 2

    mapping = sheetio.apply_mapping(args.map)
    if mapping:
        headers = [mapping.get(norm_key(header), header) for header in headers]
    columns = sheetio.column_map(headers, LINE_FIELDS + ["currency"])

    flags = []
    for required in ("sku", "qty", "unit_price"):
        if required not in columns:
            flags.append(sheetio.flag("high", "missing_column",
                                      f"需求表缺少 {required} 列，无法生成有效 PO",
                                      f"用 --map 指定该列，例如 --map 商品编码={required}"))
    if any(flag["level"] == "high" and flag["type"] == "missing_column" for flag in flags):
        sheetio.emit(sheetio.make_envelope("po_build", "blocked", 0.0, {"po_no": po_no}, flags))
        return 2

    lines, isolated, line_flags = build_lines(headers, body, columns, args)
    flags.extend(line_flags)
    if not lines:
        sheetio.emit(sheetio.make_envelope("po_build", "blocked", 0.0,
                                           {"po_no": po_no, "isolated": [item[0]["row"] for item in isolated]},
                                           flags + [sheetio.flag("high", "no_valid_lines", "没有可用明细行",
                                                                 "修正需求表后重跑")]))
        return 2

    units = sorted({line["unit"] for line in lines})
    if len(units) > 1:
        flags.append(sheetio.flag("medium", "unit_inconsistent",
                                  f"同一张 PO 出现多种单位：{'、'.join(units)}",
                                  "确认件/箱/托换算关系，单位不统一会造成数量级错误"))

    currencies = sorted({clean_text(raw[columns["currency"]]) for raw in body}) if "currency" in columns else []
    currencies = [item.upper() for item in currencies if item]
    currency = (currencies[0].upper() if len(currencies) == 1 else None) or (args.currency or "").upper()
    if not currency:
        flags.append(sheetio.flag("medium", "currency_unknown",
                                  "没有确定采购币种，PO 未标注币种",
                                  "用 --currency 指定，避免付款时汇率与金额争议"))

    total_qty = 0.0
    total_amount = 0.0
    amount_mismatch = []
    for position, line in enumerate(lines, start=1):
        line["line_no"] = position
        computed = line["qty"] * line["unit_price"]
        if line["amount"] is not None and abs(line["amount"] - computed) > 0.01:
            amount_mismatch.append({"row": line["row"], "sku": line["sku"],
                                    "declared": line["amount"], "computed": round(computed, 2)})
        line["computed_amount"] = computed
        line["etd"] = sheetio.day_shift(order_date, int(line["lead_time_days"] or args.lead_time))
        total_qty += line["qty"]
        total_amount += computed

    if amount_mismatch:
        flags.append(sheetio.flag("high", "amount_mismatch",
                                  f"{len(amount_mismatch)} 行金额与数量×单价不一致，最大差异 "
                                  f"{max(abs(item['declared'] - item['computed']) for item in amount_mismatch):.2f}",
                                  "先查清差异再下单，PO 金额不一致会导致付款纠纷"))

    effective_moq = args.moq
    below_moq = []
    for line in lines:
        moq = line["moq"] if line["moq"] is not None else effective_moq
        if moq and line["qty"] < moq:
            below_moq.append({"row": line["row"], "sku": line["sku"], "qty": line["qty"], "moq": moq})
    if below_moq:
        flags.append(sheetio.flag("medium", "below_moq",
                                  f"{len(below_moq)} 行低于最小起订量（如 {below_moq[0]['sku']} "
                                  f"{below_moq[0]['qty']:g} < {below_moq[0]['moq']:g}）",
                                  "补足到 MOQ 或与供应商确认可否接受小批量"))

    if args.max_amount is not None and total_amount > args.max_amount:
        flags.append(sheetio.flag("high", "over_approval_limit",
                                  f"PO 总额 {total_amount:.2f} {currency} 超过审批上限 {args.max_amount:.2f}",
                                  "提交资金终审后再下单"))

    if arrive_by:
        latest_order = None
        for line in lines:
            candidate = sheetio.day_shift(arrive_by, -int(line["lead_time_days"] or args.lead_time))
            latest_order = candidate if latest_order is None else min(latest_order, candidate)
        if latest_order and latest_order < order_date:
            flags.append(sheetio.flag("medium", "lead_time_risk",
                                      f"按当前交期，最晚应在 {latest_order} 前下单才能赶上 {arrive_by} 到仓",
                                      "提前下单或与供应商确认加急"))

    po_rows = []
    for line in lines:
        po_rows.append([po_no, args.supplier, currency, line["line_no"], line["sku"], line["product_name"],
                        line["spec"], f"{line['qty']:g}", line["unit"], f"{line['unit_price']:.2f}",
                        f"{line['computed_amount']:.2f}", f"{line['moq']:g}" if line["moq"] else "",
                        line["lead_time_days"], line["etd"], args.trade_term, args.payment_term, line["remark"]])
    export_headers = ["po_no", "supplier", "currency", "line_no", "sku", "product_name", "spec", "qty",
                      "unit", "unit_price", "amount", "moq", "lead_time_days", "etd",
                      "trade_term", "payment_term", "remark"]
    sheetio.write_csv(args.out, export_headers, po_rows)

    report = {
        "po_no": po_no,
        "supplier": args.supplier,
        "currency": currency,
        "order_date": order_date,
        "trade_term": args.trade_term,
        "payment_term": args.payment_term,
        "arrive_by": arrive_by,
        "line_count": len(lines),
        "total_qty": round(total_qty, 2),
        "total_amount": round(total_amount, 2),
        "isolated_rows": [{"row": line["row"], "reason": reason} for line, reason in isolated],
        "amount_mismatch": amount_mismatch[:50],
        "below_moq": below_moq[:50],
        "units": units,
        "lines": [{key: value for key, value in line.items() if key != "computed_amount"} for line in lines],
        "source_file": os.path.basename(args.input),
    }
    if args.report:
        sheetio.write_json(args.report, report)

    status = "ok" if not isolated and not amount_mismatch else "partial"
    confidence = 0.92 if status == "ok" else 0.65
    envelope = sheetio.make_envelope(
        "po_build", status, confidence, report, flags,
        sources=[{"ref": os.path.basename(args.input), "as_of": datetime.date.today().isoformat()}],
        assumptions=[f"ETD = 下单日 {order_date} + 交期天数；单位默认 {args.default_unit}",
                     "未校验供应商报价有效期、认证与包装要求，需人工确认后再下单"],
        audit={"snapshot_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
               "po_no": po_no},
    )
    sheetio.emit(envelope)
    sys.stderr.write(f"[po_build] {po_no} 共 {len(lines)} 行，总额 {total_amount:.2f} {currency}，"
                     f"隔离 {len(isolated)} 行\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
