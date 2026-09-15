#!/usr/bin/env bash
# 演示：清洗多来源运营表格：表头归一、去重、必填校验与隔离，结果写到 examples/out/
# 产物约定：主表 CSV + Markdown 报告是给人看的，JSON 是输出信封，xlsx 是 Excel 工作簿。
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p out
S=../scripts
PY=${PYTHON:-python3}

# 先自检解释器：否则报错只有一句「command not found」，看不出问题在哪
if ! command -v "$PY" >/dev/null 2>&1; then
  echo "找不到 python3，演示跑不起来。" >&2
  echo "装一个 Python 3.8 或更高版本；装了但不在 PATH 里就指定：PYTHON=/你的/python3 ./demo.sh" >&2
  exit 1
fi
if ! "$PY" -c 'import sys; raise SystemExit(sys.version_info < (3, 8))' 2>/dev/null; then
  echo "$("$PY" --version 2>&1) 版本太低，本技能需要 Python 3.8 或更高。" >&2
  exit 1
fi

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
echo "== 场景二：物流/仓储费用账单（中英双语表头 + ISO 8601 带时区日期 + 6 位小数金额）"
"$PY" "$S/clean_table.py" bill_raw.csv \
  --require "线索号 Clue Number,费用发生时间 Cost Incurred,结算币种含税金额" --dedupe-on clue_no \
  --out out/bill_clean.csv --out-md out/bill_clean.md --out-xlsx out/bill_clean.xlsx > /dev/null

"$PY" -c "
import csv
rows = list(csv.DictReader(open('out/bill_clean.csv', encoding='utf-8-sig')))
total = sum(float(r['settlement_amount'] or 0) for r in rows)
print('  清洗', len(rows), '行；结算币种含税金额合计 =', round(total, 6))
print('  日期', rows[0]['date'], '｜金额', rows[4]['settlement_amount'], '（6 位小数原样保留）')
print('  必填列校验通过：线索号 / 费用发生时间 / 结算币种含税金额 三列均用原始双语列名指定')
"

echo
echo "完成。输出目录：examples/out/"
ls out | sed 's/^/  /'
echo "看干净表：  head out/clean.csv"
echo "看隔离行：  cat out/bad_rows.csv"
echo "看 Excel：   打开 out/clean.xlsx（清洗结果 / 隔离行 / 字段覆盖率 / 清洗台账）"
