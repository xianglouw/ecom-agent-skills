---
name: ecom-roi-review
description: 跨境电商 ROI 数据复盘技能。核算 ROAS、ACOS、TACOS、CTR、CVR、CPC、CPM、毛利与净利、退款与折扣影响，按活动、广告组、SKU、日期、平台、站点、币种分组对比，与上一周期做环比并定位异常波动，产出「本周动作 → 结果 → 归因 → 下周动作」结构的复盘周报。涉及「这周投放效果怎么样」「ROAS 掉了为什么」「帮我写复盘周报」「哪些活动该关掉」「数据复盘」这类请求时使用。
metadata:
  short-description: 阶段 7 ROI 复盘 — 指标核算、分组环比、异常归因与周报
---

# 阶段 7 · ROI 数据复盘

把投放与销售明细变成能直接开周会的复盘：先给数，再给归因，最后给下周动作。

完整指标口径见 [references/roi-review.md](references/roi-review.md)。

## 输入

- **本期明细**：日期、活动、SKU、曝光、点击、花费、订单、销量、广告销售额、总销售额、单位成本、退款、币种。支持 `.csv` / `.xlsx`。
- **上期同结构明细**（可选，`--compare`）：用于环比对照。
- **口径参数**：毛利率（缺成本列时用 `--gross-margin`）、保本 ROAS（`--breakeven-roas`）、环比告警阈值（`--threshold`，默认 ±20%）、报告币种、分组维度。

## 怎么跑

```bash
python3 scripts/roi_review.py roi_current.csv --group-by campaign --compare roi_prev.csv \
  --gross-margin 0.35 --threshold 0.2 \
  --out review.csv --out-md review.md --out-xlsx review.xlsx --out-json review.json
```

`--out-xlsx` 一次给三张工作表：分组复盘 / 核心指标 / 环比变化。分组维度支持 `campaign`、`ad_group`、`sku`、`date`、`platform`、`site`、`currency`。

## 复盘结构

固定四段：**本周动作 → 结果 → 归因 → 下周动作**。

- 结果先给核心指标总量与环比，再给分组排名（含亏损组与低效组）。
- 归因链固定写法：指标变化 → 拆解到曝光/点击/转化/客单/成本哪一环 → 对应动作与素材 → 是否受外部因素影响。
- 下周动作必须可执行、可判定（谁、做什么、什么时候、达到什么阈值算成功）。
- 结论附「支撑数据 + 判定规则 + 边界/反例」三段，不要只给一个数。

## 风险与人工边界

| 等级 | 本阶段场景 | AI 权限 | 人工权限 |
|---|---|---|---|
| 高 | 连续低于保本线需关停的组、涉及预算调整的结论、退款异常、数据缺口导致结论不可靠 | 只出判定 + 依据 + 待办 | 决定并执行关停/调预算 |
| 中 | 环比波动超阈值、样本量不足、归因口径与平台后台不一致、毛利率取默认值 | 出结论 + 风险标注 | 抽样复核 |
| 低 | 指标核算、分组汇总、表格排版、报告撰写 | 直接执行 | 事后抽查 |

**不编造数据、不美化结论。** 数据缺口写成 `flags` 而不是靠推算补齐；环比异常要指出可能的数据口径原因，不要一律归因到「素材变差」。

## 常见坑

- 归因窗口不同（点击 7 天 vs 1 天）导致与后台对不上，复盘前先对齐口径。
- 退款与折扣没扣掉，ROAS 好看但净利为负。
- 用自然日和周对齐日混着比，环比失真。
- 只看总量不看分组，掩盖了「几个活动严重亏损」的事实。
- 大促期基线完全不同，跨大促做环比没有意义。

## 输出契约

与其他跨境电商技能共用同一个 JSON 信封，便于跨阶段串联、工单回写与事后追责：

```json
{
  "task": "roi_review",
  "status": "ok | partial | blocked",
  "confidence": 0.0,
  "data": {},
  "flags": [{ "level": "high | medium | low", "type": "", "detail": "", "action": "" }],
  "need_human_review": false,
  "sources": [{ "ref": "", "as_of": "" }],
  "assumptions": [],
  "audit": { "snapshot_at": "" }
}
```

- `status`：`ok` 输入齐全 / `partial` 有缺失但结论可用 / `blocked` 关键输入缺失、必须人工先介入。
- 只要出现 `high` 级 flag，`need_human_review` 必须为 `true`。
- `confidence` 口径：有 `high` 不超过 0.7，有 `medium` 不超过 0.85，还有待填位不超过 0.9，上限 0.95。

## 交付表格

**要表格就给文件，不要只给结论。** 逐行测算、对照、明细类交付必须落到能直接打开的文件：

| 参数 | 产物 | 说明 |
|---|---|---|
| `--out` | CSV 主表 | UTF-8 BOM，Excel 双击打开中文不乱码 |
| `--out-xlsx` | Excel 工作簿 | 多工作表、表头加粗并冻结首行、列宽自适应；数字写成数值，打开即可求和与做透视 |
| `--out-md` | Markdown 报告 | 给人读的结论版 |
| `--quarantine` | 问题清单 CSV | 被拦下的素材/行，不静默丢弃 |
| `--out-json` | JSON 信封 | 给下游脚本、工单系统读 |

`.xlsx` 由 `scripts/sheetio.py` 用标准库写出，不需要 openpyxl，Excel 与 WPS 都能直接打开；同一个工具也用来读 `.xlsx`（`--sheet` 支持工作表名）。

## 作业习惯

- 先要数据再下结论；能算就不要估，能引用就不要复述。
- 结论固定附「支撑数据 + 判定规则 + 边界/反例」三段，而不是只给一个数。
- `flags` 比结论更重要：写清「我不确定什么、为什么不确认、需要谁确认」。
- 术语保留英文缩写（ROAS、ACOS、TACOS、PO、MOQ、FBA），其余用中文。

## 上下游

- 上游：[`ecom-ads-plan`](../ecom-ads-plan/) 的结构命名与阈值、[`ecom-rules-fee`](../ecom-rules-fee/) 的费用口径、[`ecom-data-prep`](../ecom-data-prep/) 的干净明细。
- 下游：复盘结论回流到下一轮 [`ecom-ads-plan`](../ecom-ads-plan/) 与 [`ecom-video-creative`](../ecom-video-creative/)；稳定下来的判定规则沉淀成团队 SOP。
- 总控与共享约定见 [`crossborder-ecom-ops`](../crossborder-ecom-ops/)。
