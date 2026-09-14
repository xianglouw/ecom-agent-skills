#!/usr/bin/env bash
# 演示：多模态素材生产：分镜、生成提示词、前三秒留存检查与多语种本地化，结果写到 examples/out/
# 产物约定：主表 CSV + Markdown 报告是给人看的，JSON 是输出信封，xlsx 是 Excel 工作簿。
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p out
S=../scripts
PY=${PYTHON:-python3}

"$PY" "$S/video_brief.py" products.csv --styles market_styles.csv \
  --hooks hook_patterns.csv --banned banned_words.csv \
  --duration 15 --ratio 9:16 --hooks-per-sku 2 \
  --out out/storyboard.csv --out-md out/brief.md --out-xlsx out/brief.xlsx \
  --out-json out/brief.json --quarantine out/brief_issues.csv > /dev/null

"$PY" -c "
import json
e=json.load(open('out/brief.json'))
d=e['data']
print('  素材',d['asset_count'],'条，分镜',d['shot_rows'],'行；前三秒通过',d['retention_pass'],'条、未通过',d['retention_fail'],'条')
print('  目标语种:',d['languages'])
for r in d['speech_rates']:
    print('    %s %s 前3秒口播预算 %s' % (r['site'], r['language'], r['budget']))
print('  状态:',e['status'],'置信度:',e['confidence'],'需人工复核:',e['need_human_review'])
for f in e['flags']:
    print('  [%s] %s：%s' % (f['level'], f['type'], f['detail'][:70]))
"

echo
echo "完成。输出目录：examples/out/"
ls out | sed 's/^/  /'
echo "看分镜与生成提示词：cat out/brief.md"
echo "看 Excel：          打开 out/brief.xlsx（素材总表 / 分镜 / 语速预算 / 问题清单）"
