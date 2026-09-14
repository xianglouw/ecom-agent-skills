#!/usr/bin/env bash
# 演示：PO 单生成与下单前校验，结果写到 examples/out/
# 产物约定：主表 CSV + Markdown 报告是给人看的，JSON 是输出信封，xlsx 是 Excel 工作簿。
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p out
S=../scripts
PY=${PYTHON:-python3}

"$PY" "$S/po_build.py" sourcing.csv --supplier "Demo Supplier" --currency USD \
  --order-date 2026-09-14 --lead-time 30 --max-amount 20000 --trade-term FOB \
  --payment-term "T/T 30%+70%" --out out/PO.csv --out-xlsx out/PO.xlsx --out-json out/PO.json > /dev/null

"$PY" -c "
import json
e=json.load(open('out/PO.json'))
d=e['data']
print('  PO 号:',d.get('po_no'),' 明细行:',d.get('line_count'),' 合计:',d.get('total_amount'),d.get('currency'))
print('  状态:',e['status'],'置信度:',e['confidence'],'需人工复核:',e['need_human_review'])
for f in e['flags']:
    print('  [%s] %s：%s' % (f['level'], f['type'], f['detail'][:70]))
"

echo
echo "完成。输出目录：examples/out/"
ls out | sed 's/^/  /'
echo "看 PO 单：  head out/PO.csv"
echo "看 Excel：  打开 out/PO.xlsx（PO 明细 / 订单信息 / 隔离行）"
