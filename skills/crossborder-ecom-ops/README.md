# crossborder-ecom-ops

面向跨境电商多平台运营的 Agent Skill：**规则检索 → 表格数据整理 → 广告视频投流 → PO 单制作 → ROI 数据复盘**，把零散的人工重复作业变成标准化、可复算、带风险兜底的人机协作工作流。

适用平台：Amazon、Shopee、TikTok Shop、Temu、Lazada、Wayfair、独立站等。

## 解决什么问题

| 业务痛点 | 本技能的做法 |
|---|---|
| 平台规则碎片化，跨平台查一次要一两个小时 | 五阶段里的「规则检索」阶段把费率、税务、物流、政策归一成可检索的对照表，查询压到分钟级 |
| 重复性作业量大（算费、算 ROI、做单） | 四个 Python 脚本做确定性核算，不靠模型心算 |
| 没有标准 SOP，各人一套口径 | 六段式 Prompt 框架 + 统一 JSON 输出契约，团队口径写进文件 |
| 数据复盘低效易错 | 指标口径先声明再计算，异常阈值自动标记，直接产出复盘表格 |
| 合规扣费 / 资金风险 | 风险分级 + 多级兜底：高风险只出判定与待办，钱和平台设置永远由人执行 |

## 五个阶段

| 阶段 | 做什么 | 读什么 | 跑什么 |
|---|---|---|---|
| 1 规则信息搜集 | 合规规则、费率、政策、物流规范的结构化与检索 | [references/rules-research.md](references/rules-research.md) | `scripts/fee_check.py` |
| 2 表格数据整理 | 多来源表头归一、清洗去重、口径统一、结构化落表 | [references/data-prep.md](references/data-prep.md) | `scripts/clean_table.py` |
| 3 广告视频投流 | 投放结构、素材分镜脚本、出价预算、测品与止损规则 | [references/ads-video.md](references/ads-video.md) | — |
| 4 PO 单制作 | 需求表/报价表 → 可执行的采购订单 + 下单前校验 | [references/po-creation.md](references/po-creation.md) | `scripts/po_build.py` |
| 5 ROI 数据复盘 | 指标核算、分组对比、归因、周报与下周动作 | [references/roi-review.md](references/roi-review.md) | `scripts/roi_review.py` |

跨阶段共用的东西在 [references/prompt-contract.md](references/prompt-contract.md)：六段式 Prompt 框架、统一入参字段、输出 Schema、把一次成功作业封装成可复用 Skill 的模板、Badcase 复盘与 A/B 对照方法。

## 安装

```bash
git clone https://github.com/xianglouw/ecom-agent-skills.git

# Codex：只装这一个技能
cp -r ecom-agent-skills/skills/crossborder-ecom-ops ~/.codex/skills/

# 或者开发时用软链，改完立即生效
ln -s "$(pwd)/skills/crossborder-ecom-ops" ~/.codex/skills/crossborder-ecom-ops
```

其他支持 Agent Skills 约定的工具（SKILL.md + YAML frontmatter）把文件夹放进对应的 skills 目录即可，本技能只依赖 `name` 与 `description` 两个字段。

**运行依赖：Python 3.8+，只用标准库**，不需要 pandas / openpyxl，`.xlsx` 由内置读取器直接解析。

## 快速上手

```bash
cd examples && ./demo.sh
```

这个脚本用示例数据把四个阶段各跑一次，能看到所有异常路径都真的会触发：

```text
[1/4] 费率核算与扣费风险标记 -> out/fee.csv
      核算 6 单，未匹配规则 2 单
      high  negative_margin       A-006 单件净利 -99.57 USD（收入 128.00 − 费用 27.57 − 成本 200.00）
      high  rule_missing          Amazon/DE/户外 未在费率表中匹配到规则
[2/4] 表格清洗与结构化 -> out/clean.csv
      读入 7 行 → 输出 5 行；去重 1 行，隔离 1 行
[3/4] PO 单生成与校验 -> out/PO.csv
      high  amount_mismatch       1 行金额与数量×单价不一致，最大差异 100.00
      medium duplicate_line       SKU b101 规格 白中号 出现 2 行
      high  over_approval_limit   PO 总额 42940.00 USD 超过审批上限 20000.00
[4/4] ROI 复盘 -> out/review.md
      high  below_breakeven       TT_US_放量_户外 ROAS 0.57 低于保本线 2.92
      medium threshold_breach     TT_US_测品_家居 spend 环比 +106.2%
```

## 四个脚本

| 脚本 | 做什么 | 典型用法 |
|---|---|---|
| `fee_check.py` | 按平台/站点/类目/价格阶梯匹配费率，算佣金、支付费、履约仓储、税费、净利与保本 ROAS | `fee_check.py orders.csv --rates 费率表.csv --summary` |
| `clean_table.py` | 表头中英文别名归一、金额与日期标准化、去重、必填校验、问题行隔离 | `clean_table.py raw.xlsx --out clean.csv --require sku,price --dedupe-on sku,date` |
| `po_build.py` | 需求表生成 PO 单，校验 MOQ、单位、金额、审批阈值与交期 | `po_build.py sourcing.csv --supplier "A" --currency USD --max-amount 5000` |
| `roi_review.py` | CTR/CVR/CPC/CPA/ROAS/ACOS/TACOS/净利/保本 ROAS + 环比对照 + 复盘表格 | `roi_review.py 投放.xlsx --group-by campaign --compare 上期.csv --out-md review.md` |

共同特性：

- 列名自动识别中英文别名（`花费` / `ad_spend` / `广告花费` 都能认出来），认不出时用 `--map 原列名=标准字段` 显式指定。
- 数值清洗能吃 `¥1,234.50`、`USD 800`、`15%`、`1.2万`、`(123)` 这类写法；日期能吃 `2026/9/1`、`2026年9月1日`、`09/02/2026`、Excel 序列号。
- 输出 CSV 一律 UTF-8 BOM，Excel 打开中文不乱码。
- 每个脚本只写 `--out*` 指定的文件，不调用任何平台接口，不碰你的原始数据。

## 输出契约

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

## 设计原则

- **不编造规则、费率、成本。** 每条费率必须带来源与生效日期，查不到就输出 `unknown` 并标记待人工确认，不用经验值填坑。
- **不自动动钱。** 改价、改预算出价、下单、付款、提交申诉、改店铺配置，只输出方案、校验结果与待办清单。
- **取数合规。** 优先官方公告、后台导出、供应商报价、你自己提供的文件；不绕过登录、验证码与风控，取不到就交付「人工取数清单」。
- **判定可复算。** 记录数据快照时间、规则版本与关键假设，事后能复现当时的结论。

## 目录结构

```text
ecom-agent-skills/                    仓库根目录
├── README.md
├── LICENSE
└── skills/
    └── crossborder-ecom-ops/         本技能
        ├── README.md                 本文件
        ├── SKILL.md                  技能入口：五阶段路由、输出契约、风险分级、人机边界
        ├── agents/openai.yaml        UI 元数据
        ├── references/               按需加载的阶段手册（6 份）
        ├── scripts/                  四个业务脚本 + 一个共用表格工具
        └── examples/                 开箱可跑的示例数据与 demo.sh
```

技能可以被单独复制走：`SKILL.md` 与 `references/`、`scripts/` 是自包含的，不依赖仓库根目录的任何文件。

## 改成你自己的业务

1. **换费率表**：按 `references/rules-research.md` 的字段结构维护你自己的合规费率对照表，`fee_check.py` 直接读，支持多个文件。
2. **加字段别名**：常见列名不够用时，在 `scripts/sheetio.py` 的 `ALIASES` 里补，或用 `--map` 临时指定。
3. **调阈值**：环比告警、费率有效期、低毛利提醒、审批金额上限都是命令行参数，不需要改代码。
4. **加阶段**：新建 `references/<阶段>.md`，在 `SKILL.md` 的路由表里加一行，按 `prompt-contract.md` 的模板定义入参、规则、输出与兜底。

## 贡献

欢迎 issue 和 PR。提 PR 时请说明：这个改动解决什么真实场景的问题、有没有用示例数据验证过、是否影响既有输出字段。新增或修改脚本请保持**只用 Python 标准库**。

## License

[MIT](LICENSE)

## English

An agent skill for cross-border e-commerce operations, covering five stages: platform rule & fee research, messy spreadsheet cleanup, video ad planning, purchase order (PO) generation with validation, and ROI/ROAS review.

Four dependency-free Python scripts do the deterministic work (no pandas or openpyxl required, `.xlsx` is parsed directly), while the Markdown references define the prompt framework, field contract, and human-in-the-loop risk boundaries. Every stage emits the same JSON envelope with `flags`, `sources`, and `need_human_review`.

```bash
cp -r crossborder-ecom-ops ~/.codex/skills/
cd examples && ./demo.sh
```

Requires Python 3.8+. Licensed under MIT.
