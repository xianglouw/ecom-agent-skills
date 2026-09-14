---
name: ecom-selection-profit
description: 跨境电商选品利润与定价测算技能。按站点、渠道、币种逐行测算售价、平台佣金、支付费、履约与头程运费、关税与税费、广告成本后的净利与毛利率，反算保本价与目标售价，核对运费分段与低值免税额度（de minimis），标记负毛利与低毛利组合。涉及「这个品能不能做」「定价多少才有利润」「各站点净利对比」「保本价怎么算」「运费和关税吃掉多少利润」这类请求时使用。
metadata:
  short-description: 阶段 3 选品测算 — 多站点多币种逐行利润、保本价与目标售价反算
---

# 阶段 3 · 选品利润与定价测算

选品不靠感觉，靠逐行算出来的净利。本阶段把候选商品 × 站点 × 渠道做笛卡尔展开，每行给出完整费用链与净利，并反算「保本价」和「达到目标毛利该卖多少钱」。

完整方法论见 [references/selection-profit.md](references/selection-profit.md)。

## 输入

- **候选商品表**：`sku` / 成本 / 单件重量 / 箱规 / 售价（可含批发价），单位与币种要写清。
- **运费表**：站点 × 重量区间的运费分段（表头可不在第一行，用 `--freight-header-row`）。
- **费率表**（可选）：同 [`ecom-rules-fee`](../ecom-rules-fee/) 的合规费率表，用来取站点佣金率；也可以直接用 `--commission MX:0.17` 指定。
- **经济参数**：汇率、站点币种、关税税率、低值免税额度、包邮门槛、目标毛利率、渠道（零售/批发）。

## 怎么跑

```bash
python3 scripts/selection_profit.py items.csv --freight freight.csv --freight-header-row 2 \
  --rates ml_rates.csv --site-currency MX:MXN,BR:BRL,CL:CLP \
  --fx MXN:18.5,BRL:5.4,CLP:950 --de-minimis 50 --duty-rate 0.16 \
  --target-margin 0.3 --free-shipping-threshold MX:299,BR:79 \
  --channel both --out selection.csv --out-md selection.md --out-xlsx selection.xlsx \
  --out-json selection.json --quarantine selection_unpriced.csv
```

`--out-xlsx` 一次给四张工作表：测算明细 / 站点汇总 / 亏损与低毛利 / 未测算（缺重量、缺汇率、超出运费分段的行）。`--out-md` 按站点分节，亏损行排最前。

## 判定口径

- 净利 = 售价 − 成本 − 佣金 − 支付费 − 履约/运费 − 关税 − 广告成本 − 退款与折扣摊销，逐项列出来，不做黑箱。
- 保本价 = 净利为 0 的售价；目标售价 = 达到 `--target-margin` 的售价。两个数一起给，便于定价时取舍。
- 运费分段没覆盖到的重量、缺汇率、缺税率的组合**不算**，直接落成 `flags` 并按站点聚合，不静默跳过。
- 跨过低值免税额度会产生关税跳变，定价在门槛附近时必须给两侧对比。

## 风险与人工边界

| 等级 | 本阶段场景 | AI 权限 | 人工权限 |
|---|---|---|---|
| 高 | 净利为负、定价跨关税门槛、缺少税率或汇率、重量超出运费分段覆盖、新市场首单 | 只出测算 + 依据 + 待办 | 决定是否上架与最终定价 |
| 中 | 低于目标毛利、佣金取默认值、运费未含燃油附加、含税口径不明 | 出结论 + 风险标注 | 抽样复核 |
| 低 | 汇率换算、单位换算、汇总、排序 | 直接执行 | 事后抽查 |

**不编造费率、成本与运费。** 佣金率、税率、运费一律来自费率表/运费表或命令行显式给定，不给经验值；参数缺了就标出来，不要用「大概 15%」蒙过去。

## 常见坑

- 重量单位混用（kg 与 lb 差 2.2 倍），脚本按 `--item-weight-unit` / `--freight-weight-unit` 明确声明。
- 运费表常有「低于某金额卖家不包邮」这类说明行，表头不在第一行，必须指定 `--freight-header-row`。
- 计费重按实重还是体积重，直接影响运费，要按物流商口径。
- 拉美站点存在本币贬值与汇率波动，跨境成本用 USD 结算时毛利会被汇率吃掉，锁汇信息要进假设。

## 输出契约

与其他跨境电商技能共用同一个 JSON 信封，便于跨阶段串联、工单回写与事后追责：

```json
{
  "task": "selection_profit",
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

- 上游：[`ecom-rules-fee`](../ecom-rules-fee/)（费率口径）、[`ecom-data-prep`](../ecom-data-prep/)（干净的商品与运费表）。
- 下游：测算通过的 SKU 进 [`ecom-po-build`](../ecom-po-build/) 下单，进 [`ecom-video-creative`](../ecom-video-creative/) 出素材，进 [`ecom-ads-plan`](../ecom-ads-plan/) 定投放结构。
- 总控与共享约定见 [`crossborder-ecom-ops`](../crossborder-ecom-ops/)。
