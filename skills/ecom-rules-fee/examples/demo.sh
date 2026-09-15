#!/usr/bin/env bash
# 演示：按平台费率表核算订单费用、净利与扣费风险，结果写到 examples/out/
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

"$PY" "$S/fee_check.py" orders.csv --rates rates.csv --rates ml_rates.csv \
  --fx USD:7.2 --fx MXN:0.39 --target-currency USD --low-margin 0.1 \
  --out out/fee.csv --out-xlsx out/fee.xlsx --out-json out/fee.json > /dev/null

echo "费率覆盖情况（不给订单，只看规则覆盖）："
"$PY" "$S/fee_check.py" --rates rates.csv --rates ml_rates.csv --summary --out-json out/coverage.json > /dev/null
"$PY" -c "
import json
s=json.load(open('out/coverage.json'))['data']['summary']
print('  费率行数:', s['rule_rows'], ' 覆盖平台/站点组合:', len(s['platform_site_groups']), '个')
for key, info in list(s['platform_site_groups'].items())[:8]:
    print('    %-22s %s 行，类目 %s' % (key, info['rows'], ','.join(info['categories'])))
"

echo "风险明细："
"$PY" -c "
import json
e=json.load(open('out/fee.json'))
print('  任务:',e['task'],'状态:',e['status'],'置信度:',e['confidence'],'需人工复核:',e['need_human_review'])
for f in e['flags']:
    print('  [%s] %s：%s' % (f['level'], f['type'], f['detail'][:70]))
" || true

echo
echo "完成。输出目录：examples/out/"
ls out | sed 's/^/  /'
echo "看明细表：  head out/fee.csv"
echo "看 Excel：   打开 out/fee.xlsx（费用明细 / 核算总计 / 未匹配订单 / 费率覆盖）"
