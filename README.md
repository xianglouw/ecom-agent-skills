# ecom-agent-skills

跨境电商运营的 Agent 技能集。每个技能自带业务手册、可执行的核算脚本和风险兜底规则，装进支持 Agent Skills 约定的工具里就能直接用。

## 技能列表

| 技能 | 解决什么 | 覆盖阶段 |
|---|---|---|
| [crossborder-ecom-ops](skills/crossborder-ecom-ops/) | 多平台运营全链路：规则碎片化、重复作业、无标准 SOP、复盘低效、扣费风险 | 规则检索 → 表格整理 → 选品测算 → 视频投流 → PO 单 → ROI 复盘 |

技能的行为规范（路由、输出契约、风险分级、人机边界）写在各自的 [SKILL.md](skills/crossborder-ecom-ops/SKILL.md) 里，用法与示例见下方详解。

## 安装

```bash
git clone https://github.com/xianglouw/ecom-agent-skills.git

# 安装全部技能
cp -r ecom-agent-skills/skills/* ~/.codex/skills/

# 只安装某一个
cp -r ecom-agent-skills/skills/crossborder-ecom-ops ~/.codex/skills/
```

开发时用软链更方便，改完立即生效、不用重复复制：

```bash
ln -s "$(pwd)/ecom-agent-skills/skills/crossborder-ecom-ops" ~/.codex/skills/crossborder-ecom-ops
```

其他支持 Agent Skills 约定的工具（`SKILL.md` + YAML frontmatter）把技能文件夹放进对应的 skills 目录即可。

**运行依赖**：Python 3.8+，只用标准库。所有技能脚本都不需要 pandas、openpyxl 这类第三方包。

## 快速体验

```bash
cd ecom-agent-skills/skills/crossborder-ecom-ops/examples && ./demo.sh
```

用一套虚构的跨境电商数据把五个阶段各跑一次，输出写到 `examples/out/`。示例数据里刻意埋了脏数据，所以异常检测路径都会真实触发：

```text
[1/5] 费率核算  → 6 单中 2 单未匹配规则、1 单负毛利，需人工复核 4 项
[2/5] 表格清洗  → 读入 7 行输出 5 行，去重 1 行、隔离 1 行
[3/5] 选品测算  → 3 个 SKU × 5 个拉美站点 × 零售/批发 = 30 行，4 行净利为负
[4/5] PO 单     → 金额不符 1 行、重复行 1 组、超审批上限
[5/5] ROI 复盘  → 3 个分组，ROAS 1.43、净利 -4423，4 项高风险待复核
```

选品测算用的 `freight.csv` 也刻意做成真实样子：表头上方有一行说明（「299 比索以下卖家不包邮」，所以要用 `--freight-header-row 2` 指定表头），巴西站的运费写成欧式小数 `"10,84"`——脚本会正确读成 10.84，而不是 1084。

选品测算这一步的产物就是能直接打开的表格：`examples/out/selection.csv`（Excel 打开不乱码）和 `selection.md`（按站点分节的测算表，亏损行排在最前，直接给出保本价与目标售价）。

## crossborder-ecom-ops 详解

面向多平台运营的端到端技能：**规则检索 → 表格数据整理 → 选品利润测算 → 广告视频投流 → PO 单制作 → ROI 数据复盘**，把零散的人工重复作业变成标准化、可复算、带风险兜底的人机协作工作流。适用 Amazon、Shopee、TikTok Shop、Temu、Lazada、Wayfair、美客多、独立站等平台。

解决什么问题：

| 业务痛点 | 本技能的做法 |
|---|---|
| 平台规则碎片化，跨平台查一次要一两个小时 | 「规则检索」阶段把费率、税务、物流、政策归一成可检索的对照表，查询压到分钟级 |
| 多站点定价靠拍脑袋，运费与关税吃完利润 | 「选品测算」阶段按站点、渠道逐行算净利，反算保本价与目标售价，负毛利组合强制转人工 |
| 重复性作业量大（算费、算利润、算 ROI、做单） | 五个 Python 脚本做确定性核算，不靠模型心算 |
| 没有标准 SOP，各人一套口径 | 六段式 Prompt 框架 + 统一 JSON 输出契约，团队口径写进文件 |
| 数据复盘低效易错 | 指标口径先声明再计算，异常阈值自动标记，直接产出复盘表格 |
| 合规扣费 / 资金风险 | 风险分级 + 多级兜底：高风险只出判定与待办，钱和平台设置永远由人执行 |

### 六个阶段

| 阶段 | 做什么 | 读什么 | 跑什么 |
|---|---|---|---|
| 1 规则信息搜集 | 合规规则、费率、政策、物流规范的结构化与检索 | [references/rules-research.md](skills/crossborder-ecom-ops/references/rules-research.md) | `scripts/fee_check.py` |
| 2 表格数据整理 | 多来源表头归一、清洗去重、口径统一、结构化落表 | [references/data-prep.md](skills/crossborder-ecom-ops/references/data-prep.md) | `scripts/clean_table.py` |
| 3 选品利润测算 | 逐站点算佣金、运费、关税与净利，反算保本价、目标售价，标记亏损组合 | [references/selection-profit.md](skills/crossborder-ecom-ops/references/selection-profit.md) | `scripts/selection_profit.py` |
| 4 广告视频投流 | 投放结构、素材分镜脚本、出价预算、测品与止损规则 | [references/ads-video.md](skills/crossborder-ecom-ops/references/ads-video.md) | — |
| 5 PO 单制作 | 需求表/报价表 → 可执行的采购订单 + 下单前校验 | [references/po-creation.md](skills/crossborder-ecom-ops/references/po-creation.md) | `scripts/po_build.py` |
| 6 ROI 数据复盘 | 指标核算、分组对比、归因、周报与下周动作 | [references/roi-review.md](skills/crossborder-ecom-ops/references/roi-review.md) | `scripts/roi_review.py` |

跨阶段共用的东西在 [references/prompt-contract.md](skills/crossborder-ecom-ops/references/prompt-contract.md)：六段式 Prompt 框架、统一入参字段、输出 Schema、把一次成功作业封装成可复用 Skill 的模板、Badcase 复盘与 A/B 对照方法。

### 五个脚本

| 脚本 | 做什么 | 典型用法 |
|---|---|---|
| `fee_check.py` | 按平台/站点/类目/价格阶梯匹配费率，算佣金、支付费、履约仓储、税费、净利与保本 ROAS | `fee_check.py orders.csv --rates 费率表.csv --summary` |
| `clean_table.py` | 表头中英文别名归一、金额与日期标准化、去重、必填校验、问题行隔离 | `clean_table.py raw.xlsx --out clean.csv --require sku,price --dedupe-on sku,date` |
| `selection_profit.py` | 逐站点、逐渠道算售价/佣金/运费/关税/净利，反算保本价与目标售价，按站点聚合风险 | `selection_profit.py items.csv --freight freight.csv --de-minimis 50 --duty-rate 0.16 --channel both --out-md selection.md` |
| `po_build.py` | 需求表生成 PO 单，校验 MOQ、单位、金额、审批阈值与交期 | `po_build.py sourcing.csv --supplier "A" --currency USD --max-amount 5000` |
| `roi_review.py` | CTR/CVR/CPC/CPA/ROAS/ACOS/TACOS/净利/保本 ROAS + 环比对照 + 复盘表格 | `roi_review.py 投放.xlsx --group-by campaign --compare 上期.csv --out-md review.md` |

先用 `--help` 看完整参数。共同特性：

- 列名自动识别中英文别名（`花费` / `ad_spend` / `广告花费` 都能认出来），认不出时用 `--map 原列名=标准字段` 显式指定。
- 数值清洗能吃 `¥1,234.50`、`USD 800`、`15%`、`1.2万`、`(123)`、欧式小数 `10,84` 这类写法；日期能吃 `2026/9/1`、`2026年9月1日`、`09/02/2026`、Excel 序列号。分隔符 `,` `\t` `;` `|` 自动识别。
- 输出 CSV 一律 UTF-8 BOM，Excel 打开中文不乱码。
- 每个脚本只写 `--out*` 指定的文件，不调用任何平台接口，不碰你的原始数据。

### 输出契约

每个阶段都输出同一个 JSON 信封，便于脚本串联、工单回写和事后追责：

```json
{
  "task": "roi_review",
  "status": "ok | partial | blocked",
  "confidence": 0.9,
  "data": {},
  "flags": [{ "level": "high", "type": "below_breakeven", "detail": "", "action": "" }],
  "need_human_review": true,
  "sources": [{ "ref": "", "as_of": "" }],
  "assumptions": [],
  "audit": { "rule_version": "", "prompt_version": "", "snapshot_at": "" }
}
```

只要出现 `high` 级别标记，`need_human_review` 必为 `true`。

五个脚本的产物参数一致：`--out` 主表 CSV、`--out-json` 输出信封、`--out-md` Markdown 报告、`--quarantine` 被隔离的问题行 CSV。信封默认打到 stdout，加 `--out-json` 时同一份内容落盘（含 `blocked` 在内的所有路径都写），下游直接读文件即可。

### 风险分级与人机边界

| 等级 | 场景示例 | AI 权限 | 人工权限 |
|---|---|---|---|
| 高 | 退款审批、付款下单、超阈值预算、改价、合规申诉、正毛利被判亏损、新供应商首单 | 只出判定 + 依据 + 待办 | 终审并执行 |
| 中 | 费率未覆盖、口径不一致、环比异常波动、政策过渡期、含税口径不明 | 出结论 + 风险标注 | 抽样复核 |
| 低 | 字段清洗、格式转换、指标核算、脚本草稿、表格汇总 | 直接执行 | 事后抽查 |

### 设计原则

- **不编造规则、费率、成本。** 每条费率必须带来源与生效日期，查不到就输出 `unknown` 并标记待人工确认，不用经验值填坑。
- **不自动动钱。** 改价、改预算出价、下单、付款、提交申诉、改店铺配置，只输出方案、校验结果与待办清单。
- **取数合规。** 优先官方公告、后台导出、供应商报价、你自己提供的文件；不绕过登录、验证码与风控，取不到就交付「人工取数清单」。
- **判定可复算。** 记录数据快照时间、规则版本与关键假设，事后能复现当时的结论。

### 改成你自己的业务

1. **换费率表**：按 `references/rules-research.md` 的字段结构维护你自己的合规费率对照表，`fee_check.py` 直接读，支持多个文件。
2. **加字段别名**：常见列名不够用时，在 `scripts/sheetio.py` 的 `ALIASES` 里补，或用 `--map` 临时指定。
3. **调阈值**：环比告警、费率有效期、低毛利提醒、审批金额上限都是命令行参数，不需要改代码。
4. **加阶段**：新建 `references/<阶段>.md`，在 `SKILL.md` 的路由表里加一行，按 `prompt-contract.md` 的模板定义入参、规则、输出与兜底。

## 仓库结构

```text
ecom-agent-skills/
├── README.md
├── LICENSE
└── skills/
    └── crossborder-ecom-ops/
        ├── SKILL.md               技能入口：六阶段路由、输出契约、风险分级、人机边界
        ├── agents/openai.yaml     UI 元数据
        ├── references/            按需加载的阶段手册（7 份）
        ├── scripts/               五个业务脚本 + 一个共用表格工具
        └── examples/              示例数据与 demo.sh
```

一个技能 = 一个自包含文件夹，只包含 `SKILL.md` 与它实际需要的资源。技能内部的相对路径不依赖仓库根目录，可以单独复制走。

## 所有技能共享的约定

- **只用 Python 标准库**，不引入第三方依赖，保证在任何装了 Python 3.8+ 的机器上都能跑。
- **统一 JSON 输出信封**：每个技能都输出 `task / status / confidence / data / flags / need_human_review / sources / assumptions / audit`，便于脚本串联、工单回写和事后追责。
- **风险分级**：高风险动作（涉及资金、退款、合规、平台设置）只输出判定、依据与待办清单，落地永远由人执行。
- **不编造数据**：规则、费率、成本必须带来源与生效日期，查不到就标 `unknown` 交给人工，不用经验值填坑。
- **判定可复算**：记录数据快照时间、规则版本与关键假设。
- **配置与阈值外置**：费率表、字段别名、告警阈值都放在数据文件或命令行参数里，不写死在提示词中。

## 新增一个技能

1. 在 `skills/` 下新建文件夹，命名用小写连字符，例如 `ads-budget-guard`。
2. 写 `SKILL.md`，frontmatter 只需要 `name` 和 `description`——description 要写清「做什么 + 什么时候该用」，因为它决定技能会不会被自动选中。
3. 按需加 `references/`（业务手册、字段字典、口径说明）、`scripts/`（确定性计算）、`examples/`（示例数据 + `demo.sh`）。
4. 如果涉及跨阶段流转，沿用上面的统一输出信封与风险分级。
5. 在根 README 的技能列表里加一行。

写技能的通用方法（六段式 Prompt 框架、入参字段约束、把一次成功作业封装成可复用模板、Badcase 复盘与 A/B 版本对照）可以参考 [crossborder-ecom-ops/references/prompt-contract.md](skills/crossborder-ecom-ops/references/prompt-contract.md)。

## 贡献

欢迎 issue 和 PR。提 PR 时说明：解决什么真实场景的问题、是否用示例数据验证过、是否影响既有输出字段。新增或修改脚本请保持只用标准库。

## License

[MIT](LICENSE)

## English

A collection of agent skills for cross-border e-commerce operations. Each skill bundles its own playbooks, dependency-free Python scripts, and human-in-the-loop risk rules.

Currently included: **crossborder-ecom-ops** — platform rule & fee research, messy spreadsheet cleanup, per-site selection & pricing profit modeling, video ad planning, purchase order generation with validation, and ROI/ROAS review.

```bash
git clone https://github.com/xianglouw/ecom-agent-skills.git
cp -r ecom-agent-skills/skills/* ~/.codex/skills/
cd ecom-agent-skills/skills/crossborder-ecom-ops/examples && ./demo.sh
```

Requires Python 3.8+, no third-party packages. MIT licensed.
