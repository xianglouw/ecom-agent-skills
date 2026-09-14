#!/usr/bin/env bash
# 演示：多站点选品利润测算：净利、保本价与目标售价，结果写到 examples/out/
# 产物约定：主表 CSV + Markdown 报告是给人看的，JSON 是输出信封，xlsx 是 Excel 工作簿。
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p out
S=../scripts
PY=${PYTHON:-python3}

"$PY" "$S/selection_profit.py" items.csv --freight freight.csv --freight-header-row 2 \
  --rates ml_rates.csv --site-currency MX:MXN,BR:BRL,CL:CLP,CO:COP,AR:ARS \
  --fx MXN:18.5,BRL:5.4,CLP:950,COP:4100,ARS:1450 --de-minimis 50 --duty-rate 0.16 \
  --target-margin 0.3 --free-shipping-threshold MX:299,BR:79,CL:28000,CO:60000 \
  --channel both --out out/selection.csv --out-md out/selection.md \
  --out-xlsx out/selection.xlsx --out-json out/selection.json \
  --quarantine out/selection_unpriced.csv > /dev/null

"$PY" -c "
import json
e=json.load(open('out/selection.json'))
d=e['data']
print('  商品', d['item_count'], '个 → 测算', d['row_count'], '行，可算净利', d['priced_rows'], '行；站点', len(d['sites']), '个')
print('  负毛利行:', d['totals']['negative_margin_rows'], ' 平均毛利率:', d['totals']['avg_margin'])
print('  状态:',e['status'],'置信度:',e['confidence'],'需人工复核:',e['need_human_review'])
for f in e['flags']:
    print('  [%s] %s：%s' % (f['level'], f['type'], f['detail'][:70]))
"

echo
echo "完成。输出目录：examples/out/"
ls out | sed 's/^/  /'
echo "看测算表：  cat out/selection.md"
echo "看 Excel：   打开 out/selection.xlsx（测算明细 / 站点汇总 / 亏损与低毛利 / 未测算）"
