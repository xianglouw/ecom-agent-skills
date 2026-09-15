#!/usr/bin/env bash
# 演示：手写采购/销售单据 → 结构化台账 → 简写标准化 → 自动算账 → 日结对账 → 凭证照片回链
# 产物约定：明细 CSV 与 Excel 是给人看的台账，JSON 是输出信封，隔离行 CSV 是不静默丢掉的证据。
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

echo "== 场景一：一天的账，从 8 张手写单据照片到日结台账 =="
"$PY" "$S/receipt_ledger.py" receipts_raw.csv --alias alias_map.csv \
  --price-ref price_ref.csv \
  --photos-dir photos --embed-photos --default-year 2026 \
  --out out/ledger.csv --out-xlsx out/ledger.xlsx --out-md out/ledger.md \
  --out-json out/ledger.json --quarantine out/bad_rows.csv > /dev/null

"$PY" -c "
import json
e = json.load(open('out/ledger.json'))
d = e['data']
print('  读入', d['rows_in'], '行 → 入账', d['rows_out'], '笔，隔离', d['quarantined'], '行')
print('  采销总账：采购 %.2f ｜ 销售 %.2f ｜ 净收益 %.2f（%.1f%%）'
      % (d['purchase']['amount'], d['sales']['amount'], d['net'], d['net_margin'] * 100))
print('  算账校验：', {k: v for k, v in d['calc_check'].items() if k != 'mismatch_amount'})
print('  简写命中 %d 条、未命中 %d 条；凭证关联 %d 张、缺 %d 张'
      % (d['alias']['matched'], d['alias']['unmatched'], d['photos']['linked'], d['photos']['missing']))
print('  价格核对：命中 %d 笔、偏离 %d 笔、价格库未收录 %d 笔'
      % (d['price_check']['hit'], d['price_check']['outlier'], d['price_check']['missing']))
print('  识别加固：低置信 %d 笔、带候选值 %d 笔；补拍清单 %d 行 / %d 张照片'
      % (d['confidence']['low'], d['confidence']['with_candidates'],
         d['reshoot']['rows'], d['reshoot']['photos']))
print('  状态:', e['status'], '｜ 置信度:', e['confidence'], '｜ 需人工复核:', e['need_human_review'])
for f in e['flags']:
    print('  [%s] %s：%s' % (f['level'], f['type'], f['detail'][:64]))
print()
print('  日结（日期 / 采购 / 销售 / 净收益）:')
for day in d['daily']:
    print('    %s  采购 %10.2f   销售 %10.2f   净收益 %10.2f'
          % (day['date'], day['purchase'], day['sales'], day['net']))
"

echo
echo "== 场景二：别家写法（交易日/业务/票号/进价）+ 照片存在云端 =="
"$PY" -c "
import csv
rows = list(csv.reader(open('receipts_raw.csv', encoding='utf-8-sig')))
rows[0] = ['交易日', '业务', '票号', '手写品名', '规格', '件数', '进价', '票面金额', '拍的图', '识别度',
           '备注', '候选']
with open('out/renamed_input.csv', 'w', encoding='utf-8-sig', newline='') as fh:
    csv.writer(fh).writerows(rows)
"
"$PY" "$S/receipt_ledger.py" out/renamed_input.csv --alias alias_map.csv \
  --photos-dir photos --photos-base https://cdn.example.com/receipts/2026-09 --default-year 2026 \
  --map 拍的图=photo_path \
  --out out/ledger_renamed.csv --out-xlsx out/ledger_renamed.xlsx > /dev/null
"$PY" -c "
import csv
rows = list(csv.DictReader(open('out/ledger_renamed.csv', encoding='utf-8-sig')))
hit = sum(1 for r in rows if r['标准品名'])
print('  换了写法的表头也能直接跑：入账 %d 笔，其中标准化命中 %d 笔' % (len(rows), hit))
print('  只有「拍的图」认不出来，用 --map 补一条即可；凭证改指云端地址：')
print('   ', rows[0]['凭证'], '→ https://cdn.example.com/receipts/2026-09/' + rows[0]['凭证'])
"

echo
echo "完成。输出目录：examples/out/"
ls out | sed 's/^/  /'
echo "看台账：    head out/ledger.csv"
echo "看对账报告：cat out/ledger.md"
echo "看隔离行：  cat out/bad_rows.csv"
echo "看补拍清单：head out/ledger.csv 第 21 列是候选值；Excel 的「补拍清单」按照片列出要重拍哪一行"
echo "看 Excel：  打开 out/ledger.xlsx —— 单据明细 / 日结 / 月结 / 异常行 / 待映射简写 / 补拍清单 / 价格核对 / 凭证索引"
echo "            （明细里黄底=要复核、红底=异常或没读准，凭证索引含照片缩略图）"
