---
name: ecom-rules-fee
description: 跨境电商平台规则与费率检索核算技能。用于 Amazon、Shopee、TikTok Shop、Temu、Lazada、Wayfair、美客多、独立站等平台的佣金、支付手续费、履约仓储费、VAT/GST/销售税、进口关税、认证与禁限售政策的采集、结构化与对照，生成可检索的合规费率对照表，并按订单逐单核算费用、净利与保本 ROAS，标记负毛利、费率缺口与违规扣费风险。涉及「平台扣费/费率/佣金是多少」「这条规则去哪里查」「这单实际到手多少钱」「有没有违规扣费风险」这类请求时使用。
metadata:
  short-description: 阶段 1 规则与费率 — 多平台合规费率检索、结构化对照表与逐单费用核算
---

# 阶段 1 · 规则信息搜集与合规费率核算

把多平台零散的合规规则、费率标准、公告政策、物流规范，变成**可检索、可对照、可引用、可版本化**的结构化知识库。跨平台查一次费率从「翻几个后台找一两小时」压到分钟级，并且每条结论都能追到来源。

完整方法论见 [references/rules-research.md](references/rules-research.md)。

## 输入

- **费率表**：平台 / 站点 / 类目 / 价格区间 → 佣金、支付费、履约仓储费、税率，带 `source` 与 `effective_date`。可重复传多个文件。
- **订单或商品明细**：要核算的订单/商品表（`.csv` / `.xlsx`），字段含 SKU、站点、售价、成本、数量、币种。
- **汇率与目标币种**：多币种结算时必须给汇率来源与日期，`--fx USD:7.20`。

## 怎么跑

```bash
# 只检查费率表覆盖度（有哪些平台/站点/类目还没有费率）
python3 scripts/fee_check.py --rates 费率表.csv --summary

# 逐单核算费用、净利与保本 ROAS，并标记扣费风险
python3 scripts/fee_check.py orders.csv --rates 费率表.csv \
  --fx USD:7.2 --target-currency USD \
  --out fee.csv --out-xlsx fee.xlsx --out-json fee.json

# 多平台费率表一起读，中英文列名自动识别，认不出就用 --map
python3 scripts/fee_check.py orders.csv --rates amazon_us.csv --rates ml_mx.csv \
  --map 商品编码=sku --map 成交价=price
```

`--out-xlsx` 一次给四张工作表：费用明细 / 核算总计 / 未匹配订单 / 费率覆盖情况。

## 检索与引用规则

来源优先级：平台官方费率页与公告 > 官方文档或招商经理书面答复 > 物流商与支付商报价单 > 用户内部资料（合同、历史账单）> 第三方资讯（**只能当线索，必须回溯核实**）。

引用格式固定为 `来源名称 + 链接或文件路径 + 适用平台与站点 + 生效日期 + 获取日期`，缺任一字段的数据只能进「待核实」区，不能用于结论。费率变更时**新增版本行而不是覆盖旧行**，历史订单要能用当时的费率复算。

## 风险与人工边界

| 等级 | 本阶段场景 | AI 权限 | 人工权限 |
|---|---|---|---|
| 高 | 负毛利订单、费率缺失导致无法判定、类目错放/认证缺失/低申报/侵权/超时发货等违规风险、税率或汇率来源不明 | 只出判定 + 依据 + 待办 | 终审并在后台处理 |
| 中 | 费率未覆盖类目、费率可能过旧（超过 `--max-stale-days`）、币种口径不明、政策过渡期、口径冲突 | 出结论 + 风险标注 | 抽样复核 |
| 低 | 字段清洗、格式转换、指标核算、汇总 | 直接执行 | 事后抽查 |

**不编造费率与规则。** 每条费率必须带 `source` 与 `as_of`；查不到就写 `unknown` 并标 `need_source`，不要用行业平均值或记忆中的费率补齐——费率记错会直接导致定价和利润判断错误。AI 只输出判定与清单，改价、下单、付款、申诉一律由人在后台执行。

## 常见坑

- 佣金阶梯是**分段累进**还是**按总价选档**，结果不同，必须看官方口径。
- 促销期临时费率、新卖家优惠期、活动报名费容易漏算。
- 平台类目名与内部类目名不一致，映射表要单独维护。
- 低价商品可能有小额订单费或最低收费，按比例算会算少。
- 政策有过渡期，按订单实际发生时间选规则，不要一律用最新规则。

## 输出契约

与其他跨境电商技能共用同一个 JSON 信封，便于跨阶段串联、工单回写与事后追责：

```json
{
  "task": "fee_check",
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
| `--quarantine` | 隔离行 CSV | 被拦下的问题行，不静默丢弃 |
| `--out-json` | JSON 信封 | 给下游脚本、工单系统读 |

`.xlsx` 由 `scripts/sheetio.py` 用标准库写出，不需要 openpyxl，Excel 与 WPS 都能直接打开；同一个工具也用来读 `.xlsx`（`--sheet` 支持工作表名）。

## 作业习惯

- 先要数据再下结论；能算就不要估，能引用就不要复述。
- 结论固定附「支撑数据 + 判定规则 + 边界/反例」三段，而不是只给一个数。
- `flags` 比结论更重要：写清「我不确定什么、为什么不确认、需要谁确认」。
- 术语保留英文缩写（ROAS、ACOS、TACOS、PO、MOQ、FBA），其余用中文。

## 上下游

- 上游：无（本技能是数据底座）。
- 下游：[`ecom-selection-profit`](../ecom-selection-profit/) 取用这里的费率表算选品利润；[`ecom-roi-review`](../ecom-roi-review/) 用这里的费率口径算真实毛利。
- 总控与共享约定见 [`crossborder-ecom-ops`](../crossborder-ecom-ops/)。
