---
name: crossborder-ecom-ops
description: 跨境电商多平台运营端到端工作流总控技能，负责阶段路由与人机协作编排：把「规则检索 → 表格整理 → 选品测算 → 视频素材 → 广告投流 → PO 单 → ROI 复盘」七个阶段串成一条流水线，另含线下门店手写单据台账支线，统一输出信封、风险分级、人机边界与 Prompt 六段式框架，并按阶段调用 ecom-rules-fee、ecom-data-prep、ecom-selection-profit、ecom-video-creative、ecom-ads-plan、ecom-po-build、ecom-roi-review、ecom-receipt-ledger 等专项技能。涉及 Amazon、Shopee、TikTok Shop、Temu、Lazada、Wayfair、美客多、独立站等多平台运营时，若用户在问「运营全链路怎么搭」「从选品到复盘跑一遍」「这套 Agent 工作流怎么落地」「团队 SOP 与 Prompt 模板怎么沉淀」，或一次提出跨阶段任务，用本技能做编排。
metadata:
  short-description: 总控层 — 七阶段路由、人机协作编排、统一输出契约与 Prompt 工程方法
---

# 跨境电商运营 Agent 工作流 · 总控

本技能是**编排层**，不重复实现各阶段细节：它负责判断任务属于哪个阶段、按什么顺序串联、每阶段输出什么、哪些节点必须停下来等人。具体执行交给对应阶段的专项技能。

## 阶段路由

| 阶段 | 做什么 | 专项技能 | 脚本 |
|---|---|---|---|
| 1 规则信息搜集 | 多平台合规规则、费率、税务、政策、物流规范的结构化与检索 | [`ecom-rules-fee`](../ecom-rules-fee/) | `fee_check.py` |
| 2 表格数据整理 | 表头归一、清洗去重、口径统一、结构化落表 | [`ecom-data-prep`](../ecom-data-prep/) | `clean_table.py` |
| 2B 手写单据台账 | 手写采购/销售单据识别结构化、简写标准化、自动算账、日结与凭证回链 | [`ecom-receipt-ledger`](../ecom-receipt-ledger/) | `receipt_ledger.py` |
| 3 选品利润测算 | 逐站点算售价、佣金、运费、关税与净利，反算保本价与目标售价 | [`ecom-selection-profit`](../ecom-selection-profit/) | `selection_profit.py` |
| 4 视频素材生产 | 分镜、生成提示词、前三秒留存检查、任意语种本地化与语速预算；提示词可直连视频生成接口出片 | [`ecom-video-creative`](../ecom-video-creative/) | `video_brief.py`（出分镜）/ `video_render.py`（直连出片，可选） |
| 5 广告投放 | 投放结构、出价预算、放量节奏、止损判优 | [`ecom-ads-plan`](../ecom-ads-plan/) | 无脚本，出表格与清单 |
| 6 PO 单制作 | 需求表 + 报价 → 采购订单 + 下单前校验 | [`ecom-po-build`](../ecom-po-build/) | `po_build.py` |
| 7 ROI 数据复盘 | 指标核算、分组环比、归因、周报与下周动作 | [`ecom-roi-review`](../ecom-roi-review/) | `roi_review.py` |

阶段边界与交接字段、串联顺序与并行关系见 [references/workflow-orchestration.md](references/workflow-orchestration.md)。

**各阶段技能需要各自安装**（每个都是自包含文件夹）。②B 单据台账与 ① ② 并行，不参与主链路串联。只装了本总控技能时，按上表的路径指引人工执行，或先安装对应阶段技能。

## 任务分类与执行策略

| 任务类型 | 典型场景 | AI 执行范围 | 人工介入 |
|---|---|---|---|
| 检索类 | 规则、费率、公告、物流规范查询 | 全自动检索 + 强制引用来源 | 抽样复核 |
| 生成类 | 素材分镜与生成提示词、投流脚本、SOP、周报 | 全自动生成 + 结构化输出 | 发布前确认 |
| 流程类 | PO 单、工单、数据回写、表格交付 | 生成 + 校验 + 待办清单 | 提交与付款终审 |
| 录入类 | 手写单据拍照识别、简写标准化、日结对账 | 识别 + 算账 + 差异标红 + 隔离 | 差异行回看原单、补映射表 |
| 分析类 | 选品测算、ROI/ROAS/毛利核算、异常归因 | 核算 + 异常标记 + 归因链 | 高风险结论复核 |

## 不可违背的约束

- **不编造规则、费率、政策、销量、成本。** 每条规则或费率必须带 `source` 与 `as_of`；无法确认时写 `unknown` 并标 `need_source`，交人工确认。
- **不自动动钱、不动平台设置。** 改价、改预算出价、下单、付款、提交申诉、调整店铺配置，只输出方案、校验结果与待办清单，由人工在后台执行。
- **取数合规。** 优先官方公告、平台后台导出、供应商报价单、用户提供的文件；遵守平台条款与 robots，不绕过登录、验证码与风控。抓取受限时交付「人工取数清单」。
- **金额带币种，单位带说明。** 比例写法在同一输出内统一并在 `assumptions` 声明。
- **判定可复算。** 记录数据快照时间、规则版本与关键假设，便于事后复盘与 A/B 对照。
- **要表格就给文件。** 逐行明细、对照、测算类交付必须落到能直接打开的文件（CSV / Excel），不要只贴在对话里。

## 统一输出契约

七个阶段技能共用同一个 JSON 信封，便于跨阶段串联、工单回写与事后追责：

```json
{
  "task": "fee_check | clean_table | selection_profit | video_brief | po_build | roi_review | receipt_ledger",
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

## 风险分级与人机边界

| 等级 | 场景示例 | AI 权限 | 人工权限 |
|---|---|---|---|
| 高 | 退款审批、付款下单、超阈值预算、改价、合规申诉、负毛利被判盈利、新供应商首单、素材命中禁用词、市场风格缺失 | 只出判定 + 依据 + 待办 | 终审并执行 |
| 中 | 费率未覆盖、口径不一致、环比异常波动、政策过渡期、含税口径不明、运费分段未覆盖、低于目标毛利、前 3 秒口播超长、语种冲突 | 出结论 + 风险标注 | 抽样复核 |
| 低 | 字段清洗、格式转换、指标核算、脚本草稿、表格汇总 | 直接执行 | 事后抽查 |

## 工具与产物

所有阶段脚本只用 Python 标准库（不需要 pandas / openpyxl），列名支持中英文别名自动识别，识别不到时用 `--map 原列名=标准字段`。产物参数各阶段一致：`--out` 主表 CSV、`--out-xlsx` Excel 工作簿、`--out-md` Markdown 报告、`--quarantine` 问题行、`--out-json` 输出信封。CSV 一律 UTF-8 BOM，Excel 双击打开不乱码。

**Excel 导出**：每个阶段的 `--out-xlsx` 都产出多工作表工作簿（表头加粗、冻结首行、列宽自适应、数字为数值可直接求和与透视），用标准库写出，不依赖 openpyxl。

## 作业习惯

- 先要数据再下结论；能算就不要估，能引用就不要复述。
- 结论固定附「支撑数据 + 判定规则 + 边界/反例」三段。
- `flags` 比结论更重要：写清「我不确定什么、为什么不确认、需要谁确认」。
- 跨阶段串联时，每个阶段先输出该阶段信封再进入下一阶段，不要跨阶段跳步。
- 复盘固定四段：「本周动作 → 结果 → 归因 → 下周动作」。
- 稳定下来的判定规则与模板沉淀成可复用 Skill/SOP，团队口径以沉淀文件为准。
- 术语保留英文缩写（ROAS、ACOS、TACOS、PO、MOQ、FBA），其余用中文。

## 沉淀方法

六段式 Prompt 框架、业务入参字段约束、把一次成功作业封装成可复用模板、Badcase 复盘与 A/B 版本对照：见 [references/prompt-contract.md](references/prompt-contract.md)。
