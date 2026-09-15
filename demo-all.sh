#!/usr/bin/env bash
# 一次跑完带演示的七个技能，看每个技能产出什么样的表格。
# 用法：在仓库根目录执行  bash demo-all.sh
# 产物写到各技能的 examples/out/ 下，都是能直接打开的 CSV 与 Excel。
set -uo pipefail
cd "$(dirname "$0")"

PY=${PYTHON:-python3}
export PYTHON="$PY"

# 先自检解释器：否则报错只有一句「command not found」，看不出问题在哪
if ! command -v "$PY" >/dev/null 2>&1; then
  echo "找不到 python3，演示跑不起来。" >&2
  echo "装一个 Python 3.8 或更高版本；装了但不在 PATH 里就指定：PYTHON=/你的/python3 bash demo-all.sh" >&2
  exit 1
fi
if ! "$PY" -c 'import sys; raise SystemExit(sys.version_info < (3, 8))' 2>/dev/null; then
  echo "$("$PY" --version 2>&1) 版本太低，本技能集需要 Python 3.8 或更高。" >&2
  exit 1
fi

SKILLS="ecom-rules-fee ecom-data-prep ecom-receipt-ledger ecom-selection-profit ecom-video-creative ecom-po-build ecom-roi-review"

echo "用 $("$PY" --version 2>&1) 跑七个技能的演示"
echo
failed=""
for skill in $SKILLS; do
  printf "  %-24s " "$skill"
  if (cd "skills/$skill/examples" && bash demo.sh > /dev/null 2>&1); then
    echo "✓"
  else
    echo "✗ 失败"
    failed="$failed $skill"
  fi
done
echo

if [ -n "$failed" ]; then
  echo "有失败的技能：$failed"
  echo "单独跑一次看完整报错：bash skills/<技能名>/examples/demo.sh"
  exit 1
fi

echo "七个演示都跑通了。产物在各技能的 examples/out/ 下，都是能直接打开的 CSV 与 Excel。"
