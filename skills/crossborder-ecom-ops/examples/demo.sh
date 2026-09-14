#!/usr/bin/env bash
# 端到端演示：一次跑完五个阶段里的四个脚本，结果写到 examples/out/
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p out
S=../scripts
PY=${PYTHON:-python3}

echo "[1/4] 费率核算与扣费风险标记 -> out/fee.csv"
"$PY" "$S/fee_check.py" orders.csv --rates rates.csv \
  --fx USD:7.2 --fx SGD:5.4 --target-currency USD \
  --out-csv out/fee.csv --out-json out/fee.json > out/fee.envelope.json

echo "[2/4] 表格清洗与结构化 -> out/clean.csv"
"$PY" "$S/clean_table.py" ad_raw.csv \
  --out out/clean.csv --report out/clean.report.json --quarantine out/bad_rows.csv \
  --require sku,date,spend --dedupe-on sku,date > out/clean.envelope.json

echo "[3/4] PO 单生成与校验 -> out/PO.csv"
"$PY" "$S/po_build.py" sourcing.csv --supplier "Demo Supplier" --currency USD \
  --order-date 2026-09-14 --lead-time 30 --max-amount 20000 --trade-term FOB \
  --out out/PO.csv --report out/PO.report.json > out/PO.envelope.json

echo "[4/4] ROI 复盘 -> out/review.md"
"$PY" "$S/roi_review.py" roi_current.csv --group-by campaign --compare roi_prev.csv \
  --out-md out/review.md --out-json out/review.json > out/review.envelope.json

echo
echo "完成。输出目录：examples/out/"
ls out | sed 's/^/  /'
echo
echo "看复盘结论：  cat out/review.md"
echo "看风险标记：  python3 -c \"import json;print([f['type'] for f in json.load(open('out/fee.envelope.json'))['flags']])\""
