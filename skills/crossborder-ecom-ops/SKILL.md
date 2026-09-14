---
name: crossborder-ecom-ops
description: 跨境电商多平台运营端到端工作流，覆盖平台规则与费率检索、运营表格数据整理、选品利润与定价测算、多模态广告素材生产与投流、PO 单制作与校验、ROI 数据复盘六类任务。用于 Amazon、Shopee、TikTok Shop、Temu、Lazada、Wayfair、美客多、独立站等平台的合规规则与费率整理、扣费风险排查、多来源表格合并清洗、售价与关税利润测算、广告分镜脚本与文生视频提示词设计、前三秒留存检查、投流脚本与投放结构设计、采购订单生成、ROAS/ACOS/TACOS 核算与周报复盘等请求。
metadata:
  short-description: 跨境电商运营六阶段自动化工作流（含多模态素材生产与前三秒留存检查）
---

# 跨境电商运营 Agent 工作流

六个阶段可单独调用，也可按 `规则 → 数据 → 选品 → 投流 → PO → 复盘` 串联成端到端作业：

| 阶段 | 做什么 | 读什么 | 跑什么 |
|---|---|---|---|
| 1 规则信息搜集 | 多平台合规规则、费率、政策、物流规范的结构化与检索 | [references/rules-research.md](references/rules-research.md) | `scripts/fee_check.py` |
| 2 表格数据整理 | 多来源表头归一、清洗去重、口径统一、结构化落表 | [references/data-prep.md](references/data-prep.md) | `scripts/clean_table.py` |
| 3 选品利润测算 | 逐站点算售价、佣金、运费、关税与净利，反算保本价与目标售价 | [references/selection-profit.md](references/selection-profit.md) | `scripts/selection_profit.py` |
| 4 广告视频生产与投流 | 多模态素材生产（分镜、生成提示词、前三秒留存检查）+ 投放结构、出价预算与止损 | [references/video-production.md](references/video-production.md) / [references/ads-video.md](references/ads-video.md) | `scripts/video_brief.py` |
| 5 PO 单制作 | 需求表/报价表 → 可执行的采购订单 + 校验 | [references/po-creation.md](references/po-creation.md) | `scripts/po_build.py` |
| 6 ROI 数据复盘 | 指标核算、分组对比、归因、周报与下周动作 | [references/roi-review.md](references/roi-review.md) | `scripts/roi_review.py` |

Prompt 结构、统一输出 Schema、场景封装成可复用 Skill 的方法：见 [references/prompt-contract.md](references/prompt-contract.md)。

## 开工前必须确认

1. **平台与站点**——同一 SKU 在不同站点的费率、认证、税务要求不同，缺站点时按最保守口径处理并在 `assumptions` 声明。
2. **数据来源与口径**——平台后台导出 / 平台公告 / 供应商报价 / 用户口述，口径决定结论可信度。
3. **输出用途**——内部决策、供应商对接、平台申诉、团队 SOP，用途决定输出颗粒度与是否需要留痕。

三者缺失时先输出待补清单（`status: blocked`），不要用行业平均值或记忆中的费率补齐。

## 不可违背的约束

- **不编造规则、费率、政策、销量、成本。** 每条规则/费率必须带 `source` 与 `as_of`（生效或获取日期）。无法确认时写 `"unknown"` 并在 `flags` 标 `need_source`，交人工确认。
- **不自动动钱、不动平台设置。** 改价、改预算出价、下单、付款、提交申诉、调整店铺配置，只输出方案、校验结果与待办清单，由人工在后台执行。
- **取数合规。** 优先官方公告、平台后台导出、供应商报价单、用户提供的文件；遵守平台条款与 robots，不绕过登录、验证码、风控。抓取受限时改为交付「人工取数清单」。
- **金额带币种，单位带说明。** 比例在同一输出内统一写法（`0.15` 或 `15%` 择一）并在 `assumptions` 声明。
- **判定可复算。** 每次输出记录数据快照时间、所用规则版本、关键假设，便于事后复盘与 A/B 对照。

## 任务分类与执行策略

| 任务类型 | 本 skill 中的场景 | AI 执行范围 | 人工介入 |
|---|---|---|---|
| 检索类 | 规则、费率、公告、物流规范查询 | 全自动检索 + 强制引用来源 | 抽样复核 |
| 生成类 | 投流脚本、素材分镜与生成提示词、SOP、周报 | 全自动生成 + 结构化输出 | 发布前确认 |
| 流程类 | PO 单、工单、数据回写 | 生成 + 校验 + 待办清单 | 提交/付款终审 |
| 分析类 | ROI/ROAS/毛利/异常归因、选品定价与保本测算 | 核算 + 异常标记 + 归因链 | 高风险结论复核 |

## 统一输出契约

所有阶段用同一个 JSON 信封，便于脚本串联、工单回写和事后追责：

```json
{
  "task": "fee_check | clean_table | selection_profit | video_brief | po_build | roi_review",
  "status": "ok | partial | blocked",
  "confidence": 0.0,
  "data": {},
  "flags": [
    { "level": "high | medium | low", "type": "negative_margin | rule_missing | threshold_breach", "detail": "", "action": "" }
  ],
  "need_human_review": true,
  "sources": [{ "ref": "", "as_of": "" }],
  "assumptions": [],
  "audit": { "rule_version": "", "prompt_version": "", "snapshot_at": "" }
}
```

- `status`：`ok` 判定齐全 / `partial` 有字段缺失但结论仍可用 / `blocked` 关键输入缺失或必须人工先介入。
- `confidence`：由数据完整度、规则覆盖度、是否命中异常共同决定；不要在数据缺失时给高置信度。
- 只要出现 `high` 级别 flag，`need_human_review` 必须为 `true`。

## 风险分级与人机边界

| 等级 | 场景示例 | AI 权限 | 人工权限 |
|---|---|---|---|
| 高 | 退款审批、付款下单、超阈值预算、改价、合规申诉、正毛利被判亏损、新供应商首单、选品净利为负、跨关税门槛定价、素材命中禁用词、市场风格缺失 | 只出判定 + 依据 + 待办 | 终审并执行 |
| 中 | 费率未覆盖、口径不一致、环比异常波动、政策过渡期、含税口径不明、运费分段未覆盖、低于目标毛利、前 3 秒口播超长 | 出结论 + 风险标注 | 抽样复核 |
| 低 | 字段清洗、格式转换、指标核算、脚本草稿、表格汇总 | 直接执行 | 事后抽查 |

## 脚本

统一只用 Python 标准库（不需要 pandas / openpyxl，`.xlsx` 由内置读取器解析），列名支持中英文别名自动识别，识别不到时用 `--map 原列名=标准字段`。脚本只做确定性计算与校验，不调用平台接口，除 `--out*` 指定路径外不写任何文件。

产物参数六个脚本一致：`--out` 主表 CSV、`--out-json` 输出信封、`--out-md` Markdown 报告、`--quarantine` 被隔离的问题行 CSV。信封默认打到 stdout，加 `--out-json` 时同一份内容落盘（含 `blocked` 在内的所有路径都写），下游直接读文件即可。

```bash
# 阶段 1：费率核算 + 扣费风险标记
python3 scripts/fee_check.py orders.csv --rates 费率表.csv [--rates 更多表.csv] --fx USD:7.20 \
  --out fee.csv --out-json fee.json
python3 scripts/fee_check.py --rates 费率表.csv --summary    # 只检查规则覆盖度

# 阶段 2：表格清洗与结构化
python3 scripts/clean_table.py raw.xlsx --out clean.csv --out-json clean.json \
  --require sku,price --dedupe-on sku,date --quarantine bad_rows.csv

# 阶段 3：选品利润测算（多站点、多币种，零售与批发）
python3 scripts/selection_profit.py items.csv --freight freight.csv --freight-header-row 2 \
  --rates 费率表.csv --site-currency MX:MXN,BR:BRL --fx MXN:18.5,BRL:5.4 \
  --de-minimis 50 --duty-rate 0.16 --target-margin 0.3 --channel both \
  --out selection.csv --out-md selection.md --out-json selection.json

# 阶段 4：多模态素材生产（分镜 + 生成提示词 + 前三秒留存检查）
python3 scripts/video_brief.py products.csv --styles 市场风格库.csv --hooks 钩子模板库.csv \
  --banned 禁用词表.csv --duration 15 --ratio 9:16,16:9 --hooks-per-sku 2 \
  --out storyboard.csv --out-md brief.md --out-json brief.json

# 阶段 5：PO 单生成 + 校验
python3 scripts/po_build.py sourcing.csv --supplier "供应商A" --currency USD --lead-time 30 \
  --out PO.csv --out-json PO.json [--po-no PO-20260914-001] [--max-amount 5000]

# 阶段 6：ROI 复盘
python3 scripts/roi_review.py 投放明细.xlsx --group-by campaign --compare 上期.csv \
  --out-md review.md --out-json review.json [--gross-margin 0.35]
```

选品测算的汇率、佣金率、关税门槛全部来自命令行参数，脚本不内置任何费率；缺税率、缺重量、重量超出运费分段、缺汇率都会落成 `flags` 并按站点聚合，不会静默跳过。素材 brief 的地区风格一律取自市场风格库，风格库缺失的市场直接标 high；文案里需要创意填空的位置写成 `{{待填:字段}}` 显式暴露，不替你编造卖点与场景。

先用 `--help` 看完整参数。

## 作业习惯

- 先要数据再下结论；能算就不要估，能引用就不要复述。
- 结论固定附「支撑数据 + 判定规则 + 边界/反例」三段，而不是只给一个数。
- `flags` 比结论更重要：把「我不确定什么、为什么不确认、需要谁确认」写清楚。
- 表格默认输出 UTF-8 BOM 的 CSV（Excel 打开中文不乱码），日期统一 `YYYY-MM-DD`。
- **要表格就给文件，不要只给结论。** 涉及逐行测算、对照、明细的交付，必须落到能直接打开的文件（CSV 主表 + Markdown 可读表），并说明每列口径；把表格塞进聊天正文的代码块等于没交付。
- 复盘固定四段：「本周动作 → 结果 → 归因 → 下周动作」。
- 跨阶段串联时，每个阶段先输出该阶段 JSON 信封再进入下一阶段，不要跨阶段跳步。
- 稳定下来的判定规则和模板沉淀成可复用 Skill/SOP（写法见 prompt-contract），团队口径以沉淀文件为准，不要在对话里口头解释。
- 术语保留英文缩写（ROAS、ACOS、TACOS、PO、MOQ、FBA），其余用中文。
