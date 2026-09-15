#!/usr/bin/env bash
# 【注意】真正的位置在仓库根目录：ecom-agent-skills/demo-all.sh
# 这份是同一内容放在 skills/ 里的副本，为的是在 skills/ 里直接敲 bash demo-all.sh 也能跑。
# 改脚本时请以仓库根目录那份为准，改完把这份同步过去。
#
# 一次跑完带演示的七个技能，看每个技能产出什么样的表格。
#
# 放在哪儿都能跑，两种布局都认：
#   ① 仓库根目录——技能在 skills/ 下面（GitHub 上克隆下来的就是这样）
#   ② 技能所在的那一层——ecom-rules-fee、ecom-data-prep 这些直接同级
#      把这份脚本拷到 ~/.codex/skills/ 里就属于这种
#
# 用法：bash demo-all.sh        跑七个，逐个显示输出（默认）
#       bash demo-all.sh -q     只显示一行结果，输出太多时用
# 产物写到各技能的 examples/out/ 下，都是能直接打开的 CSV 与 Excel。
set -uo pipefail
cd "$(dirname "$0")"

QUIET=0
case "${1:-}" in
  -q|--quiet) QUIET=1 ;;
esac

# 先认布局：认不出就明确说清脚本该放哪儿，而不是甩一堆 cd 报错
if [ -d "skills/ecom-rules-fee" ]; then
  BASE="skills"
elif [ -d "ecom-rules-fee" ]; then
  BASE="."
else
  {
    echo "在 $(pwd) 里没找到技能文件夹，跑不了。"
    echo
    echo "这个脚本可以放在两个位置之一："
    echo "  ① ecom-agent-skills 仓库根目录（里面有 skills/ 文件夹）"
    echo "  ② 技能所在的那一层（ecom-rules-fee、ecom-data-prep 这些直接同级）"
    echo
    echo "现在这个脚本在：$(pwd)"
  } >&2
  exit 1
fi

PY=${PYTHON:-python3}
export PYTHON="$PY"

# 再自检解释器：否则报错只有一句「command not found」，看不出问题在哪
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
TOTAL=7

echo "用 $("$PY" --version 2>&1) 跑七个技能的演示（技能目录：$BASE/）"
echo "产物写到各技能的 examples/out/ 下，都是能直接打开的表格。"
echo

passed=0
failed=""
index=0
for skill in $SKILLS; do
  index=$((index + 1))

  if [ "$QUIET" = "1" ]; then
    printf "  %-24s " "$skill"
    if (cd "$BASE/$skill/examples" && bash demo.sh > /dev/null 2>&1); then
      echo "✓"
      passed=$((passed + 1))
    else
      echo "✗ 失败"
      failed="$failed $skill"
    fi
    continue
  fi

  echo "──────── $index/$TOTAL · $skill ────────"
  if (cd "$BASE/$skill/examples" && bash demo.sh); then
    passed=$((passed + 1))
  else
    failed="$failed $skill"
    echo "↑ 这个技能跑失败了"
  fi
  echo
done

echo "════════════════════════════════════════"
if [ -n "$failed" ]; then
  echo "结果：$TOTAL 个技能，$passed 个通过，$((TOTAL - passed)) 个失败"
  echo "失败的是：$failed"
  echo
  echo "单独跑一次看完整报错：bash $BASE/<技能名>/examples/demo.sh"
  exit 1
fi
echo "结果：$TOTAL 个技能全部通过"
echo "产物位置：$BASE/<技能名>/examples/out/"
