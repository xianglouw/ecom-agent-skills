# Prompt 契约与 Skill 封装

本文件是六个阶段共用的底层约定：怎么写 Prompt、怎么定入参、怎么出结果、怎么把一次成功的作业固化成可复用 Skill。

## 六段式 Prompt 框架

每个运营场景的 Prompt 都按这六段写，顺序固定，缺段即视为不合格 Prompt（因为缺哪段就会在哪段出问题）：

| 段 | 名称 | 作用 | 写不好会怎样 |
|---|---|---|---|
| ① | 角色与目标 | 设定平台/站点语境与本次任务的唯一目标 | 模型给出泛化建议、不落到具体平台 |
| ② | 输入数据契约 | 明确字段、类型、单位、币种、时间范围、允许缺失 | 模型猜字段口径、算错分母 |
| ③ | 业务规则与阈值 | 判定规则、费率口径、阈值、优先级、例外 | 模型凭常识判断，合规结论不可用 |
| ④ | 执行步骤 | 分步要求（取数 → 匹配 → 计算 → 判定 → 归纳） | 跳步导致漏算、归因无链条 |
| ⑤ | 输出格式 | JSON Schema + 需要人看的表格/结论 | 结果不可机读、无法回写工单 |
| ⑥ | 异常与兜底 | 缺数据、规则未覆盖、置信度不足时的行为 | 模型编造数据填坑 |

写 Prompt 的三个硬要求：

- ③ 里的每条规则必须能追溯到来源（写进 `sources`），不要让模型「根据经验」补规则。
- ⑤ 必须同时给「机读 JSON」和「人读摘要」，因为下游既要回写系统又要给人看。
- ⑥ 必须显式写出「不确定时输出 unknown 并标记 need_human_review」，否则模型默认会猜。

## 统一入参约束

跨阶段流转的数据都用同一套字段名，避免每个场景各自造字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `platform` | enum | amazon / shopee / tiktok_shop / temu / lazada / wayfair / shopify / other |
| `site` | string | 站点或市场，如 US、UK、SG、MY、DE |
| `sku` / `msku` / `asin` | string | 商品标识，多个平台并存时保留各自 ID 并给出映射 |
| `category` | string | 平台类目名，保留平台原始写法，另存归一化类目 |
| `date` | date | 统一 `YYYY-MM-DD`，聚合任务必须声明时间范围与边界（含首含尾） |
| `currency` | string | ISO 4217 三字母；混合币种必须给汇率来源与日期 |
| `qty` / `units` | number | 数量，注明单位（件/箱/托） |
| `price` / `cost` / `spend` / `revenue` | number | 金额，注明是否含税、是否扣退款 |
| `source` / `as_of` | string / date | 数据来源与生效（或获取）日期，规则类数据必填 |

字段缺失的处理顺序：`回问用户` → `用更保守口径 + assumptions 声明` → `标 unknown 并进 flags`。**不要**用行业平均值、历史均值或模型记忆填空，除非用户在 `assumptions` 里明确同意。

## JSON 输出 Schema

外层用 SKILL.md 里的统一信封，内层 `data` 按阶段不同：

```json
{
  "task": "roi_review",
  "status": "partial",
  "confidence": 0.72,
  "data": {
    "period": { "start": "2026-09-01", "end": "2026-09-07" },
    "totals": { "spend": 0, "revenue": 0, "roas": 0, "acos": 0, "tacos": 0 },
    "breakdown": [{ "key": "campaign_a", "spend": 0, "revenue": 0, "roas": 0 }],
    "conclusions": ["...", "..."]
  },
  "flags": [
    { "level": "high", "type": "below_breakeven", "detail": "campaign_a ROAS 1.4 低于保本线 2.86", "action": "人工确认是否关停或改素材" }
  ],
  "need_human_review": true,
  "sources": [{ "ref": "Amazon Ads 后台导出", "as_of": "2026-09-08" }],
  "assumptions": ["revenue 已扣除退款，未扣优惠券"],
  "audit": { "rule_version": "2026-09-01", "prompt_version": "v3", "snapshot_at": "2026-09-08T10:00:00+08:00" }
}
```

`conclusions` 每条都必须能被 `data` 里的数字或 `flags` 支撑，不要出现无数据支撑的判断句。

## 把一次成功的作业封装成可复用 Skill

一个新场景跑通后，按这个模板固化（这也是团队 SOP 的落地形式）：

```markdown
### Skill: <场景名，如 refund_review>
- 触发：<什么请求该用，如「审核这批退款申请」>
- 任务类型：检索类 / 生成类 / 流程类 / 分析类
- 入参：<字段清单 + 必填项 + 枚举值>
- 规则与阈值：<判定规则、来源、版本号>
- 输出：<data 结构 + 必出的 flags>
- 兜底：<缺什么就 blocked，什么情况必须人工终审>
- 版本：<rule_version / prompt_version / 最近一次 Badcase 复盘日期>
```

封装要求：

- 阈值、渠道名、费率这类会变的东西抽成配置，不要写死在 Prompt 正文里——否则每次政策调整都要重写 Prompt。
- 每个 Skill 必须能回答「什么情况下这单我不判、交人」。
- 同一场景连续两次出现同类 Badcase，才值得改 Prompt；单次个案先记进 Badcase 清单，避免为个案把规则写歪。

## Badcase 复盘模板

| 字段 | 说明 |
|---|---|
| 案例 | 输入数据 + 期望结论 + 实际结论 |
| 归因层级 | 数据缺失 / 规则缺失 / 规则表述歧义 / 阈值不合理 / 模型推理跳步 |
| 影响 | 是否造成资金、合规、时效损失，金额量级 |
| 修法 | 改入参约束 / 改规则表述 / 加反例 / 改阈值 / 拆 Prompt 步骤 |
| 回归验证 | 用哪批历史数据复跑，结论是否一致 |

## A/B 对照与版本迭代

- 对照方式：同一批历史数据分别跑旧版与新版规则（离线对照），或上线前后两个时间窗对比（在线对照，需控制季节、促销、断货等变量）。
- 观察指标：以业务指标为主（退款准确率、PO 一次通过率、ROAS、人力耗时），别只看模型自评。
- 显著性：样本量太小或窗口内有大型促销时，只作参考结论，标注 `confidence` 不超过 0.6 并说明原因。
- 版本记录：`rule_version` 跟规则变更走，`prompt_version` 跟 Prompt 变更走，两者分开记，否则出问题无法定位是规则错了还是表达错了。
