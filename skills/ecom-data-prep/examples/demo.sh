#!/usr/bin/env bash
# 演示：清洗多来源运营表格：表头归一、去重、必填校验与隔离，结果写到 examples/out/
# 产物约定：主表 CSV + Markdown 报告是给人看的，JSON 是输出信封，xlsx 是 Excel 工作簿。
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p out
S=../scripts
PY=${PYTHON:-python3}

"$PY" "$S/clean_table.py" ad_raw.csv \
  --require sku,date,spend --dedupe-on sku,date \
  --out out/clean.csv --quarantine out/bad_rows.csv --out-xlsx out/clean.xlsx --out-json out/clean.json > /dev/null

"$PY" -c "
import json
e=json.load(open('out/clean.json'))
d=e['data']
print('  读入',d.get('rows_in'),'行 → 输出',d.get('rows_out'),'行；去重删除',d.get('duplicates_removed'),'行，隔离',d.get('quarantined'),'行')
print('  列名归一:',d.get('renamed_columns'))
print('  状态:',e['status'],'置信度:',e['confidence'],'需人工复核:',e['need_human_review'])
for f in e['flags']:
    print('  [%s] %s：%s' % (f['level'], f['type'], f['detail'][:70]))
"

echo
echo "完成。输出目录：examples/out/"
ls out | sed 's/^/  /'
echo "看干净表：  head out/clean.csv"
echo "看隔离行：  cat out/bad_rows.csv"
echo "看 Excel：   打开 out/clean.xlsx（清洗结果 / 隔离行 / 字段覆盖率 / 清洗台账）"
