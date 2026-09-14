#!/usr/bin/env bash
# 端到端演示：把四个脚本各跑一次，结果写到 examples/out/
#
# 产物约定：<阶段>.csv / <阶段>.md 是主产物，<阶段>.json 是输出信封；
# 信封默认打到 stdout，这里用 --out-json 落盘、stdout 丢弃，进度信息走 stderr。
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p out
S=../scripts
PY=${PYTHON:-python3}

echo "[1/4] 费率核算与扣费风险标记 -> out/fee.csv"
"$PY" "$S/fee_check.py" orders.csv --rates rates.csv \
  --fx USD:7.2 --fx SGD:5.4 --target-currency USD \
  --out out/fee.csv --out-json out/fee.json > /dev/null

echo "[2/4] 表格清洗与结构化 -> out/clean.csv"
"$PY" "$S/clean_table.py" ad_raw.csv \
  --out out/clean.csv --out-json out/clean.json --quarantine out/bad_rows.csv \
  --require sku,date,spend --dedupe-on sku,date > /dev/null

echo "[3/4] PO 单生成与校验 -> out/PO.csv"
"$PY" "$S/po_build.py" sourcing.csv --supplier "Demo Supplier" --currency USD \
  --order-date 2026-09-14 --lead-time 30 --max-amount 20000 --trade-term FOB \
  --out out/PO.csv --out-json out/PO.json > /dev/null

echo "[4/4] ROI 复盘 -> out/review.md"
"$PY" "$S/roi_review.py" roi_current.csv --group-by campaign --compare roi_prev.csv \
  --out-md out/review.md --out-json out/review.json > /dev/null

echo
echo "各阶段输出信封（--out-json 的产物）："
"$PY" - <<'PY'
import json
import pathlib

for stage in ["fee", "clean", "PO", "review"]:
    envelope = json.loads(pathlib.Path("out", f"{stage}.json").read_text(encoding="utf-8"))
    flags = envelope["flags"]
    high = sum(1 for item in flags if item["level"] == "high")
    print(f"  {envelope['task']:<12}{envelope['status']:<9}置信度 {envelope['confidence']:<5}"
          f"风险 {high} 高 / {len(flags) - high} 中低    需人工复核：{envelope['need_human_review']}")
PY

echo
echo "完成。输出目录：examples/out/"
ls out | sed 's/^/  /'
echo
echo "看复盘结论：  cat out/review.md"
echo "看风险明细：  $PY -c \"import json;print(json.load(open('out/fee.json'))['flags'])\""
