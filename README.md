# ecom-agent-skills

跨境电商运营的 Agent 技能集。每个技能都自带业务手册、可执行的核算脚本和风险兜底规则，装进支持 Agent Skills 约定的工具里就能直接用。

## 技能列表

| 技能 | 解决什么 | 包含阶段 |
|---|---|---|
| [crossborder-ecom-ops](skills/crossborder-ecom-ops/) | 多平台运营全链路：规则碎片化、重复作业、无标准 SOP、复盘低效、扣费风险 | 规则检索 → 表格整理 → 视频投流 → PO 单 → ROI 复盘 |

每个技能的详细说明、参数与示例在自己的目录里，点技能名进去看 README。

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

用一套虚构的跨境电商数据把四个阶段各跑一次，输出写到 `examples/out/`。示例数据里刻意埋了脏数据，所以异常检测路径都会真实触发：

```text
[1/4] 费率核算  → 未匹配规则 2 单、负毛利 1 单
[2/4] 表格清洗  → 读入 7 行输出 5 行，去重 1 行、隔离 1 行
[3/4] PO 单     → 金额不符 1 行、重复行 1 组、超审批上限
[4/4] ROI 复盘  → ROAS 0.57 低于保本线 2.92、零转化花费 900
```

## 仓库结构

```text
ecom-agent-skills/
├── README.md
├── LICENSE
└── skills/
    └── crossborder-ecom-ops/
        ├── README.md              技能说明与用法
        ├── SKILL.md               技能入口：路由、输出契约、风险分级
        ├── agents/openai.yaml     UI 元数据
        ├── references/            按需加载的业务手册
        ├── scripts/               可直接执行的核算脚本
        └── examples/              示例数据与 demo.sh
```

一个技能 = 一个自包含文件夹。技能内部的相对路径不依赖仓库根目录，可以单独复制走。

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

Currently included: **crossborder-ecom-ops** — platform rule & fee research, messy spreadsheet cleanup, video ad planning, purchase order generation with validation, and ROI/ROAS review.

```bash
git clone https://github.com/xianglouw/ecom-agent-skills.git
cp -r ecom-agent-skills/skills/* ~/.codex/skills/
cd ecom-agent-skills/skills/crossborder-ecom-ops/examples && ./demo.sh
```

Requires Python 3.8+, no third-party packages. MIT licensed.
