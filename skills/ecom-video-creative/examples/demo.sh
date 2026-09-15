#!/usr/bin/env bash
# 演示：多模态素材生产：周期热词与套路挖掘 → 分镜与生成提示词 → 前三秒留存检查 → 直连出片，结果写到 examples/out/
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

echo "—— 第一步：采样本周期爆款的前 3 秒台词，看该先抄哪个套路 ——"
"$PY" "$S/hot_hooks.py" viral_samples.csv --hooks hook_patterns.csv --products products.csv \
  --top 3 --out out/hot_words.csv --out-xlsx out/hot_hooks.xlsx --out-md out/hot_hooks.md \
  --out-json out/hot_hooks.json --quarantine out/hot_hooks_issues.csv > /dev/null

"$PY" -c "
import json
e=json.load(open('out/hot_hooks.json'))
d=e['data']
print('  采样',d['samples'],'条｜判出套路',d['classified'],'条｜未归类',d['unclassified'],'条')
print('  本周期套路排行：')
for p in d['top_patterns']:
    print('    %s %s：%d 条用到，占 %.0f%%%s' % (
        p['hook_code'], p['hook_name'], p['count'], p['share']*100,
        ('，平均播放 %s' % int(p['avg_views'])) if p['avg_views'] else ''))
print('  热词：词典命中 %d 个，机器抽取的候选片段 %d 个' % (d['dictionary_words'], d['candidate_fragments']))
print('  钩子候选 %d 条，前两条：' % d['candidates'])
for c in d['hook_candidates'][:2]:
    print('    %s %s → %s' % (c['hook_code'], c['hook_name'], c['target']))
    print('       口播:', c['line_template'], '｜待补:', c['pending'] or '无')
print('  状态:',e['status'],'置信度:',e['confidence'])
for f in e['flags']:
    print('  [%s] %s：%s' % (f['level'], f['type'], f['detail'][:70]))
"

echo
echo "—— 第二步：出分镜、生成提示词，并做前三秒留存检查 ——"
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
echo "—— 第三步：把分镜提示词接到视频生成平台（这里走离线演示，不联网、不花钱）——"
# 每次演示都从头跑：清掉上一次的台账，否则已成功的镜头会被断点续跑跳过
rm -f out/renders.csv out/renders.json out/renders.xlsx
"$PY" "$S/video_render.py" out/storyboard.csv --provider mock --shots 1 --max-clips 2 \
  --outdir out/renders --confirm \
  --out out/renders.csv --out-xlsx out/renders.xlsx --out-json out/renders.json > /dev/null

"$PY" -c "
import json
e=json.load(open('out/renders.json'))
d=e['data']
print('  平台 %s 模型 %s：提交 %d 个镜头，试跑 %s' % (d['provider_label'], d['model'], d['submitted'], d['dry_run']))
print('  状态:',e['status'],'置信度:',e['confidence'])
for f in e['flags']:
    print('  [%s] %s：%s' % (f['level'], f['type'], f['detail'][:70]))
"

echo
echo "完成。输出目录：examples/out/"
ls out | sed 's/^/  /'
echo "看周期热词与套路：  cat out/hot_hooks.md"
echo "看分镜与生成提示词：cat out/brief.md"
echo "看 Excel：          打开 out/brief.xlsx（素材总表 / 分镜 / 语速预算 / 问题清单）"
echo "看生成台账：        打开 out/renders.xlsx（生成台账 / 按状态分表）"
echo "换平台出真片：      先 python3 ../scripts/video_render.py --list-providers 看支持哪些平台"
