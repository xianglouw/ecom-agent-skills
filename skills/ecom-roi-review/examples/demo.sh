#!/usr/bin/env bash
# 演示：ROI 复盘：指标核算、分组环比与归因，结果写到 examples/out/
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

"$PY" "$S/roi_review.py" roi_current.csv --group-by campaign --compare roi_prev.csv \
  --gross-margin 0.35 --threshold 0.2 \
  --out out/review.csv --out-md out/review.md --out-xlsx out/review.xlsx --out-json out/review.json > /dev/null

"$PY" -c "
import json
e=json.load(open('out/review.json'))
d=e['data']
m=d['totals']
print('  花费', m['spend'], ' 广告销售额', m['revenue'], ' ROAS', m['roas'], ' ACOS', m['acos'], ' 净利', m['net_profit'])
print('  保本 ROAS', m['breakeven_roas'], ' 分组数', len(d['groups']))
print('  状态:',e['status'],'置信度:',e['confidence'],'需人工复核:',e['need_human_review'])
for f in e['flags']:
    print('  [%s] %s：%s' % (f['level'], f['type'], f['detail'][:70]))
"

echo
echo "完成。输出目录：examples/out/"
ls out | sed 's/^/  /'
echo "看复盘报告：cat out/review.md"
echo "看 Excel：    打开 out/review.xlsx（分组复盘 / 核心指标 / 环比变化）"
