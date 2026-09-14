#!/usr/bin/env bash
# 端到端演示：把六个脚本各跑一次，结果写到 examples/out/
#
# 产物约定：<阶段>.csv / <阶段>.md 是主产物，<阶段>.json 是输出信封；
# 信封默认打到 stdout，这里用 --out-json 落盘、stdout 丢弃，进度信息走 stderr。
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p out
S=../scripts
PY=${PYTHON:-python3}

echo "[1/6] 费率核算与扣费风险标记 -> out/fee.csv"
"$PY" "$S/fee_check.py" orders.csv --rates rates.csv \
  --fx USD:7.2 --fx SGD:5.4 --target-currency USD \
  --out out/fee.csv --out-json out/fee.json > /dev/null

echo "[2/6] 表格清洗与结构化 -> out/clean.csv"
"$PY" "$S/clean_table.py" ad_raw.csv \
  --out out/clean.csv --out-json out/clean.json --quarantine out/bad_rows.csv \
  --require sku,date,spend --dedupe-on sku,date > /dev/null

echo "[3/6] 选品利润测算（五国站点） -> out/selection.md"
"$PY" "$S/selection_profit.py" items.csv --freight freight.csv --freight-header-row 2 \
  --rates ml_rates.csv --site-currency MX:MXN,BR:BRL,CL:CLP,CO:COP,AR:ARS \
  --fx MXN:18.5,BRL:5.4,CLP:950,COP:4100,ARS:1450 --de-minimis 50 --duty-rate 0.16 \
  --target-margin 0.3 --free-shipping-threshold MX:299,BR:79,CL:28000,CO:60000 \
  --channel both --out out/selection.csv --out-md out/selection.md \
  --out-json out/selection.json --quarantine out/selection_unpriced.csv > /dev/null

echo "[4/6] 多模态素材生产（分镜 + 生成提示词 + 前三秒留存检查 + 多语种本地化） -> out/brief.md"
"$PY" "$S/video_brief.py" products.csv --styles market_styles.csv \
  --hooks hook_patterns.csv --banned banned_words.csv \
  --duration 15 --ratio 9:16 --hooks-per-sku 2 \
  --out out/storyboard.csv --out-md out/brief.md --out-json out/brief.json \
  --quarantine out/brief_issues.csv > /dev/null

echo "[5/6] PO 单生成与校验 -> out/PO.csv"
"$PY" "$S/po_build.py" sourcing.csv --supplier "Demo Supplier" --currency USD \
  --order-date 2026-09-14 --lead-time 30 --max-amount 20000 --trade-term FOB \
  --out out/PO.csv --out-json out/PO.json > /dev/null

echo "[6/6] ROI 复盘 -> out/review.md"
"$PY" "$S/roi_review.py" roi_current.csv --group-by campaign --compare roi_prev.csv \
  --out-md out/review.md --out-json out/review.json > /dev/null

echo
echo "各阶段输出信封（--out-json 的产物）："
"$PY" - <<'PY'
import json
import pathlib

for stage in ["fee", "clean", "selection", "brief", "PO", "review"]:
    envelope = json.loads(pathlib.Path("out", f"{stage}.json").read_text(encoding="utf-8"))
    flags = envelope["flags"]
    high = sum(1 for item in flags if item["level"] == "high")
    print(f"  {envelope['task']:<18}{envelope['status']:<9}置信度 {envelope['confidence']:<5}"
          f"风险 {high} 高 / {len(flags) - high} 中低    需人工复核：{envelope['need_human_review']}")
PY

echo
echo "完成。输出目录：examples/out/"
ls out | sed 's/^/  /'
echo
echo "看选品测算表：cat out/selection.md"
echo "看素材分镜：  cat out/brief.md"
echo "看复盘结论：  cat out/review.md"
echo "看风险明细：  $PY -c \"import json;print(json.load(open('out/fee.json'))['flags'])\""
