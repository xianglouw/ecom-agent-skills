---
name: ecom-data-prep
description: 跨境电商运营表格数据整理与清洗技能。把平台后台导出、ERP、广告后台、人工维护表等多来源多口径的原始表，合并清洗成统一口径的结构化表：表头归一与中英文列名别名识别、编码与日期格式统一、金额与比例口径统一、重复行去重、必填校验、异常行隔离、字段覆盖率报告。涉及「帮我把这几张表合并」「表头不一致怎么统一」「数据清洗 / 去重 / 格式转换」「后台导出的原始表很乱」这类请求时使用。
metadata:
  short-description: 阶段 2 表格整理 — 多来源表头归一、清洗去重、口径统一与结构化落表
---

# 阶段 2 · 表格数据整理与结构化

把「一个表七八种写法」的原始数据洗成能直接进分析、能直接回写系统的干净表。凡是脏数据，一律**隔离而不是静默丢弃**——被丢掉的行往往就是数据源的配置错误。

完整方法论与字段规范见 [references/data-prep.md](references/data-prep.md)。

## 输入

- 待清洗的原始表（`.csv` / `.tsv` / `.xlsx`），表头可以不在第一行（`--header-row`）。
- 必填字段清单（`--require sku,price`）与去重主键（`--dedupe-on sku,date`）。
- 口径说明：金额是否含税、比例是小数还是百分号、日期格式、币种。

## 怎么跑

```bash
python3 scripts/clean_table.py ad_raw.csv \
  --out clean.csv --quarantine bad_rows.csv --out-xlsx clean.xlsx --out-json clean.json \
  --require sku,date,spend --dedupe-on sku,date \
  --map 商品编码=sku --map 广告花费=spend

# 从 Excel 的指定工作表读
python3 scripts/clean_table.py 后台导出.xlsx --sheet 广告明细 --header-row 2 --out clean.csv

# 物流/仓储费用账单（京东国际、海外仓、3PL 结算单）：中英双语表头自动识别
python3 scripts/clean_table.py 账单.xlsx --sheet "出库-Outbound" \
  --require "线索号 Clue Number,费用发生时间 Cost Incurred,结算币种含税金额" \
  --dedupe-on clue_no \
  --out out/出库.csv --out-xlsx out/出库.xlsx --out-md out/出库.md --quarantine out/出库_隔离行.csv
```

`--require` / `--keep` / `--dedupe-on` 三种写法都认：标准字段名（`clue_no`）、去下划线写法（`clueno`）、
原始中英双语列名（`线索号 Clue Number`）。示例数据见 `examples/bill_raw.csv`。

`--out-xlsx` 一次给四张工作表：清洗结果 / 隔离行 / 字段覆盖率 / 清洗台账（改名映射与转换记录）。

## 清洗口径

- 冲突优先级：平台后台导出 > ERP > 人工维护表 > 第三方工具。同一主键出现多个值**不自动覆盖**，输出冲突清单交人工确认。
- 表结构不一致时先补列再合并，不要合并后再补——那样会丢行。
- 数值统一：`"¥1,234.50"` 这类带符号千分位会被解析成数字；欧式小数 `"10,84"` 读作 10.84 而不是 1084，避免差 100 倍。
- 日期统一 `YYYY-MM-DD`；比例统一写法并在 `assumptions` 声明。
- **费用账单场景**：ISO 8601 带时区日期（`2026-08-20T00:00:00+0800`）自动转 `YYYY-MM-DD`；账单单据里
  常用「两套币种 × 含税/不含税/税额」六列，标准字段分别是 `settlement_amount` / `settlement_amount_ex_tax`
  / `settlement_tax`（结算币种）与 `quotation_amount` / `quotation_amount_ex_tax` / `quotation_tax`（报价币种）。
- **明细金额按原精度保留**（最多 6 位小数，不按两位小数四舍五入）：海外仓仓储费最小到 0.000001 元，
  四舍五入会让逐行合计对不上账单汇总页。广告/采购类金额仍按两位小数输出。
- 3PL 账单常见的 0 元明细行（如 0 元起步价计费）是正常计费凭证，**不要当异常行剔除**；
  做费率分析时再单独筛掉。
- 列顺序固定：维度列 → 数值列 → 来源列。

## 风险与人工边界

| 等级 | 本阶段场景 | AI 权限 | 人工权限 |
|---|---|---|---|
| 高 | 必填字段整列为空、主键重复且值冲突、关键数值列全部无法解析 | 出报告 + 隔离行 | 回查数据源并修正导出配置 |
| 中 | 字段覆盖率偏低、改名映射不确定、含税口径不明、单位混用 | 出结论 + 风险标注 | 抽样复核 |
| 低 | 去重、格式转换、列名归一、汇总 | 直接执行 | 事后抽查 |

**不猜数据。** 数值解析不了就隔离并写清原因，不要用 0 或平均值填补；不要为了凑行数而保留明显重复的行。

## 常见坑

- 后台导出带分组统计行/小计行，混进明细会让汇总翻倍。
- 同一 SKU 在多张表里编码写法不同（大小写、前后空格、全角半角），合并前必须归一。
- 空值有三种：真空、`-`、`N/A`，处理方式不同，要统一。
- 日期混用 `2026/9/1`、`2026-09-01`、`01/09/2026`，跨月时按错格式会串月。

## 输出契约

与其他跨境电商技能共用同一个 JSON 信封，便于跨阶段串联、工单回写与事后追责：

```json
{
  "task": "clean_table",
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

- 上游：[`ecom-rules-fee`](../ecom-rules-fee/) 给出字段口径。
- 下游：清洗后的干净表喂给 [`ecom-selection-profit`](../ecom-selection-profit/)、[`ecom-video-creative`](../ecom-video-creative/)、[`ecom-roi-review`](../ecom-roi-review/)。
- 总控与共享约定见 [`crossborder-ecom-ops`](../crossborder-ecom-ops/)。
