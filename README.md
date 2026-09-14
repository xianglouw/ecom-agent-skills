# ecom-agent-skills

> Cross-border e-commerce agent skills — a 7-stage AI workflow (platform rules & fees → data cleaning → product selection → video creative → ads planning → PO build → ROI review) plus a handwritten-receipt ledger track for offline shops. Works with Amazon, Shopee, TikTok Shop, Temu, Lazada, Wayfair and Mercado Libre.

面向跨境电商多平台运营的 Agent 技能集。把运营全链路拆成**可独立安装、可单独调用、可串成流水线**的技能：每个技能自带业务手册、可执行的核算脚本和风险兜底规则，装进支持 Agent Skills 约定的工具里就能直接用。

适用于 Amazon、Shopee、TikTok Shop、Temu、Lazada、Wayfair、美客多、独立站等平台；线下档口与门店的手写采购/销售单据，走 `ecom-receipt-ledger` 这条台账支线。

## 技能清单

| 技能 | 说明 |
|---|---|
| `crossborder-ecom-ops` | 总控编排 — 七阶段路由、人机协作边界、统一输出契约与 Prompt 工程方法 |
| `ecom-rules-fee` | 规则费率 — 多平台合规费率检索、对照表搭建、逐单费用与扣费风险核算 |
| `ecom-data-prep` | 数据制表 — 多来源表头归一、清洗去重、口径统一，产出能直接分析的干净表 |
| `ecom-selection-profit` | 选品测算 — 多站点多币种逐行净利、保本价与目标售价反算，标记亏损组合 |
| `ecom-video-creative` | 视频生成 — 分镜、文生视频提示词、前三秒留存检查、任意语种本地化与语速预算 |
| `ecom-ads-plan` | 广告投放 — 投放结构、出价预算、保本 ROAS、放量节奏与止损判优规则 |
| `ecom-receipt-ledger` | 单据台账 — 手写采购/销售单据识别结构化、简写标准化、自动算账与采销日结，凭证照片回链 |
| `ecom-po-build` | PO 单制作 — 采购订单生成与下单前校验：金额、MOQ、单位、币种、交期与审批阈值 |
| `ecom-roi-review` | 数据复盘 — ROAS/ACOS/TACOS 核算、分组环比、异常归因与复盘周报 |

## 工作流分层

| 层 | 阶段 | 技能 | 主要产物 |
|---|---|---|---|
| 总控层 | 全链路 | `crossborder-ecom-ops` | 阶段路由、交接字段、卡点清单、SOP 与 Prompt 模板 |
| 数据底座 | ① 规则信息搜集 | `ecom-rules-fee` | 合规费率对照表、逐单费用与净利明细、扣费风险清单 |
| 数据底座 | ② 表格数据整理 | `ecom-data-prep` | 干净结构化表、字段覆盖率、隔离行与清洗台账 |
| 数据底座 | ②B 手写单据台账 | `ecom-receipt-ledger` | 电子化采购/销售台账、日结与月结、算账差异清单、凭证照片回链 |
| 决策层 | ③ 选品利润测算 | `ecom-selection-profit` | 逐行测算明细、站点汇总、保本价与目标售价 |
| 增长层 | ④ 视频素材生产 | `ecom-video-creative` | 分镜脚本、生成提示词、前三秒检查、多语种语速预算 |
| 增长层 | ⑤ 广告投放 | `ecom-ads-plan` | 投放结构表、出价预算表、止损判优阈值表 |
| 履约层 | ⑥ PO 单制作 | `ecom-po-build` | PO 单、校验报告、待人工确认清单 |
| 复盘层 | ⑦ ROI 数据复盘 | `ecom-roi-review` | 分组复盘表、环比变化、归因链与下周动作 |

串联顺序：`规则 → 数据 → 选品 → 素材 → 投流 → PO → 复盘`，复盘结论回流修正下一轮的选品参数与素材方向。① 与 ② 可并行，④ 与 ⑥ 可并行；②B 单据台账是独立支线，随时可跑，产出的标准品名台账可以直接喂给 ③ 与 ⑦。完整编排说明见 [workflow-orchestration.md](skills/crossborder-ecom-ops/references/workflow-orchestration.md)。

**一次真实任务按什么顺序跑、每一步吃什么进吐什么出、在哪里必须停下来等人**，见 [docs/run-chain.md](docs/run-chain.md)（技能运行链路）：含入口判断表、链路全景图、逐段运行卡片，以及「新品上线 / 门店闭店 / 周度复盘」三种真实跑法。

## 安装

```bash
git clone https://github.com/xianglouw/ecom-agent-skills.git

# 安装全部技能
cp -r ecom-agent-skills/skills/* ~/.codex/skills/

# 只安装某一个（每个技能都是自包含文件夹，可以单独拿走）
cp -r ecom-agent-skills/skills/ecom-selection-profit ~/.codex/skills/
```

开发时用软链更方便，改完立即生效、不用重复复制：

```bash
ln -s "$(pwd)/ecom-agent-skills/skills/ecom-selection-profit" ~/.codex/skills/ecom-selection-profit
```

其他支持 Agent Skills 约定的工具（`SKILL.md` + YAML frontmatter）把技能文件夹放进对应的 skills 目录即可。建议连 `crossborder-ecom-ops` 一起装——它负责跨阶段编排和团队口径沉淀。

**运行依赖**：Python 3.8+，只用标准库。所有技能脚本都不需要 pandas、openpyxl 这类第三方包。

## 数据表支持导出 Excel

所有带脚本的技能都能一键产出 Excel 工作簿，逐行明细、对照、测算类交付**直接给文件，不只给结论**：

```bash
# 任意一个阶段脚本都支持 --out-xlsx，多工作表输出
python3 scripts/selection_profit.py items.csv --freight freight.csv \
  --site-currency MX:MXN --fx MXN:18.5 \
  --out selection.csv --out-xlsx selection.xlsx --out-md selection.md
```

| 技能 | `--out-xlsx` 产出的工作表 |
|---|---|
| `ecom-rules-fee` | 费用明细 / 核算总计 / 未匹配订单 / 费率覆盖情况 |
| `ecom-data-prep` | 清洗结果 / 隔离行 / 字段覆盖率 / 清洗台账 |
| `ecom-receipt-ledger` | 单据明细 / 日结 / 月结 / 异常行 / 待映射简写 / 凭证索引 |
| `ecom-selection-profit` | 测算明细 / 站点汇总 / 亏损与低毛利 / 未测算 |
| `ecom-video-creative` | 素材总表 / 分镜 / 语速预算 / 问题清单 |
| `ecom-po-build` | PO 明细 / 订单信息 / 隔离行 |
| `ecom-roi-review` | 分组复盘 / 核心指标 / 环比变化 |

工作簿由内置写出器生成：表头加粗并冻结首行、列宽按内容自适应、长文本自动换行；**数字写成数值而不是文本**，打开就能直接求和、排序和做透视表。还支持**单元格超链接**（本地文件或云端地址）与**图片嵌入**——手写单据台账的凭证照片就是这样钉在每一行数据旁边的。Excel 和 WPS 都能直接打开，不需要装任何插件。

同一套工具也用来**读** `.xlsx`：输入文件可以是 Excel，`--sheet` 支持传工作表名（不只是序号）。

## 快速体验

每个技能自带示例数据和演示脚本，进对应目录跑一次即可（示例里刻意埋了脏数据，所以异常检测路径都会真实触发）：

```bash
cd ecom-agent-skills/skills/ecom-rules-fee/examples     && ./demo.sh   # 费率核算与扣费风险
cd ecom-agent-skills/skills/ecom-data-prep/examples     && ./demo.sh   # 表格清洗与隔离
cd ecom-agent-skills/skills/ecom-receipt-ledger/examples && ./demo.sh  # 手写单据日结与凭证回链
cd ecom-agent-skills/skills/ecom-selection-profit/examples && ./demo.sh # 选品利润测算
cd ecom-agent-skills/skills/ecom-video-creative/examples   && ./demo.sh # 素材分镜与前三秒检查
cd ecom-agent-skills/skills/ecom-po-build/examples      && ./demo.sh   # PO 单生成与校验
cd ecom-agent-skills/skills/ecom-roi-review/examples    && ./demo.sh   # ROI 复盘
```

产物统一写到各自的 `examples/out/`，都是能直接打开的表格（CSV 是 UTF-8 BOM，中文不乱码）和 Excel 工作簿。

### 示例里埋了哪些真问题

- **规则费率**：2 单未匹配费率规则、1 单单件净利 -108.76 USD，另外命中 2 条「类目用通配规则」提醒，高风险 6 项。
- **数据制表**：读入 7 行输出 5 行，去重 1 行、隔离 1 行；`"¥1,234.50"` 这类带符号千分位会被解析成数字。
- **选品测算**：3 个 SKU × 5 个拉美站点 × 零售/批发 = 30 行，4 行净利为负、平均毛利率 23.8%；运费表表头上方有一行说明（「299 比索以下卖家不包邮」），用 `--freight-header-row 2` 指定表头；巴西站运费写成欧式小数 `"10,84"`，脚本读成 10.84 而不是 1084。
- **视频素材**：7 个产品 × 7 个市场 = 14 条素材、70 行分镜，前三秒 8 条通过、6 条口播讲不完——钩子库里 H01/H03/H04/H05 的口播刻意写长了，语速拦截不是摆设；覆盖英、西、葡、越、日、泰六个目标语种，无高风险阻塞。
- **PO 单**：5 行明细合计 42940 USD，金额不符 1 行、重复行 1 组、低于 MOQ 1 行、超审批上限 1 项，高风险 3 项。
- **ROI 复盘**：3 个分组，ROAS 1.43、净利 -4423、保本 ROAS 2.92，4 项高风险待复核、7 项环比告警。
- **单据台账**：8 张手写单据照片、17 行明细，入账 16 笔（隔离 1 行）、5 天日结、净收益 1270；2 笔金额与「数量×单价」不符、1 笔单据没写金额、1 条简写没收录、1 行疑似重复、1 张照片没归档——每一类都有对应产物接住。

### 多语种覆盖

素材 brief 支持任意目标语种：示例数据覆盖西语、葡语、越南语、日语、泰语、英语六种，内置 53 个语种的语速上限与 400+ 种语种写法（短代码 `vi-VN`、英文名 `Vietnamese`、中文名「越南语」、平台后台原生写法 `Tiếng Việt`、`日本語`、`ภาษาไทย`、`العربية` 都认）。

`brief.md` 里带「本地化与语速预算」一节：逐市场给出「前 3 秒最多讲几个词 / 几个字符」，并把该语种的本地化交付清单一起列出来。语速预检会区分「还没本地化的中文草稿」和「已按目标语种写好的文案」——前者只做工作语言预检并提示预算，后者按目标语种真实上限判定，超长直接拦截。

## 所有技能共享的约定

- **只用 Python 标准库**，不引入第三方依赖，保证在任何装了 Python 3.8+ 的机器上都能跑。
- **统一 JSON 输出信封**：每个技能都输出 `task / status / confidence / data / flags / need_human_review / sources / assumptions / audit`，便于脚本串联、工单回写和事后追责。
- **统一产物参数**：`--out` 主表 CSV、`--out-xlsx` Excel 工作簿、`--out-md` Markdown 报告、`--quarantine` 问题行、`--out-json` 输出信封。CSV 一律 UTF-8 BOM。
- **风险分级**：高风险动作（涉及资金、退款、合规、平台设置）只输出判定、依据与待办清单，落地永远由人执行。
- **不编造数据**：规则、费率、成本必须带来源与生效日期，查不到就标 `unknown` 交给人工，不用经验值填坑。
- **判定可复算**：记录数据快照时间、规则版本与关键假设。
- **配置与阈值外置**：费率表、字段别名、告警阈值都放在数据文件或命令行参数里，不写死在提示词中。

## 仓库结构

```text
ecom-agent-skills/
├── README.md
├── LICENSE
├── CHANGELOG.md
├── docs/
│   └── run-chain.md                技能运行链路：入口判断、链路全景、逐段卡片与真实跑法
└── skills/
    ├── crossborder-ecom-ops/          总控层：阶段路由 + 端到端编排 + Prompt 工程方法
    │   ├── SKILL.md
    │   ├── agents/openai.yaml
    │   └── references/
    │       ├── prompt-contract.md         六段式 Prompt、封装可复用 Skill、Badcase 复盘
    │       └── workflow-orchestration.md  阶段边界、交接字段、卡点与回流
    ├── ecom-rules-fee/                阶段 1 规则费率
    ├── ecom-data-prep/                阶段 2 数据制表
    ├── ecom-receipt-ledger/           阶段 2B 手写单据台账（含示例单据照片 photos/）
    ├── ecom-selection-profit/         阶段 3 选品测算
    ├── ecom-video-creative/           阶段 4 视频素材
    ├── ecom-ads-plan/                 阶段 5 广告投放
    ├── ecom-po-build/                 阶段 6 PO 单
    └── ecom-roi-review/               阶段 7 数据复盘
```

每个阶段技能的结构一致，都是自包含的：

```text
ecom-<阶段>/
├── SKILL.md             技能入口：何时用、怎么跑、输出契约、风险与人工边界
├── agents/openai.yaml   UI 元数据
├── references/          按需加载的业务手册
├── scripts/             确定性计算脚本（含共用的 sheetio.py 表格读写工具）
└── examples/            示例数据 + demo.sh
```

一个技能 = 一个自包含文件夹，只包含 `SKILL.md` 与它实际需要的资源。技能内部的相对路径不依赖仓库根目录，可以单独复制走。`sheetio.py`（CSV/Excel 读写与信封工具）在各技能里各带一份副本，就是为了保证这一点。

## 新增一个技能

1. 在 `skills/` 下新建文件夹，命名用小写连字符，例如 `ads-budget-guard`。
2. 写 `SKILL.md`，frontmatter 只需要 `name` 和 `description`——description 要写清「做什么 + 什么时候该用」，因为它决定技能会不会被自动选中。
3. 按需加 `references/`（业务手册、字段字典、口径说明）、`scripts/`（确定性计算）、`examples/`（示例数据 + `demo.sh`）。
4. 如果涉及跨阶段流转，沿用上面的统一输出信封与风险分级，并在总控技能的路由表里加一行。
5. 在根 README 的技能清单与工作流分层表里各加一行。

写技能的通用方法（六段式 Prompt 框架、业务入参字段约束、把一次成功作业封装成可复用模板、Badcase 复盘与 A/B 版本对照）见 [prompt-contract.md](skills/crossborder-ecom-ops/references/prompt-contract.md)。

## 贡献

欢迎 issue 和 PR。提 PR 时说明：解决什么真实场景的问题、是否用示例数据验证过、是否影响既有输出字段。新增或修改脚本请保持只用标准库。

## License

[MIT](LICENSE)

## English

A collection of agent skills for cross-border e-commerce operations, split by workflow stage so each one can be installed and used on its own. Every skill bundles its own playbooks, dependency-free Python scripts, and human-in-the-loop risk rules.

| Skill | What it does |
|---|---|
| `crossborder-ecom-ops` | Orchestration — seven-stage routing, hand-off contracts, human-in-the-loop boundaries, prompt engineering playbook |
| `ecom-rules-fee` | Rules & fees — multi-platform fee/compliance lookup, rate tables, per-order charge and margin checks |
| `ecom-data-prep` | Data prep — header normalization, dedup, validation, quarantine, clean structured tables |
| `ecom-receipt-ledger` | Receipt ledger — handwritten receipt capture into structured rows, alias normalization, auto-reconciliation, daily purchase/sale close with photo evidence |
| `ecom-selection-profit` | Selection & pricing — per-site, multi-currency profit modeling, breakeven and target price |
| `ecom-video-creative` | Video creative — storyboards, text-to-video prompts, first-3-second retention checks, any target language |
| `ecom-ads-plan` | Ads planning — campaign structure, bids and budgets, breakeven ROAS, scale-up and stop-loss rules |
| `ecom-po-build` | Purchase orders — PO generation plus pre-order validation (amount, MOQ, unit, currency, lead time) |
| `ecom-roi-review` | ROI review — ROAS/ACOS/TACOS, period-over-period deltas, attribution and weekly review |

```bash
git clone https://github.com/xianglouw/ecom-agent-skills.git
cp -r ecom-agent-skills/skills/* ~/.codex/skills/
cd ecom-agent-skills/skills/ecom-selection-profit/examples && ./demo.sh
```

Every script that produces a table also writes a multi-sheet `.xlsx` workbook via `--out-xlsx` (bold frozen header, auto column widths, numbers stored as numbers). Reading `.xlsx` is supported too. Requires Python 3.8+, no third-party packages. MIT licensed.
