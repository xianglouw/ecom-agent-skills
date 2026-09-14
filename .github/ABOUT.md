# 仓库 About 与 Topics 设置参考

这个文件是给维护者用的。GitHub 的 **About**（仓库简介）和 **Topics**（主题标签）只能在网页端设置，把下面内容复制粘贴过去即可，改完立刻生效、不需要重新提交代码。

## 一、About 描述（推荐版）

```
跨境电商多平台运营 Agent 技能集｜9 个技能串成 8 段工作流：规则费率检索 → 表格清洗 → 手写单据/拍照记账台账 → 选品测算 → 广告视频素材 → 投流结构 → PO 单 → ROI 复盘。Cross-border e-commerce agent skills for Amazon, Shopee, TikTok Shop, Temu, Lazada, Wayfair, Mercado Libre. Python 标准库，一键导出 Excel。
```

232 字符，未超 GitHub 的 350 字符上限。

**为什么这么写**：GitHub 仓库搜索会同时匹配仓库名、About 描述、Topics 和 README 正文。这段话里压了四类搜索词——品类词（跨境电商 / cross-border e-commerce）、场景词（选品 / 投流 / PO 单 / ROI 复盘 / 数据清洗 / 手写单据 / 拍照记账 / 台账）、平台词（Amazon / Shopee / TikTok Shop / Temu / Lazada / Wayfair / Mercado Libre）、交付物词（Excel / Python 标准库），中文用户和英文用户都能命中。

**英文优先版**（想多吸引海外开发者与 Agent 生态流量时用，329 字符）：

```
Cross-border e-commerce agent skills: 9 skills across an 8-stage AI workflow — platform rules & fees, data cleaning, handwritten-receipt OCR ledger, product selection, video creative, ads planning, PO build, ROI review. 跨境电商多平台运营技能集，支持 Amazon / Shopee / TikTok Shop / Temu / Lazada / Wayfair / Mercado Libre，Python 标准库一键导出 Excel。
```

## 二、备选版本

**精简版**（首屏更像一句话卖点，210 字符）：

```
跨境电商多平台运营 Agent 技能集：规则费率、表格清洗、手写单据拍照记账、选品测算、视频素材、广告投流、PO 单、ROI 复盘，9 个技能可独立调用也可串成流水线。Cross-border e-commerce agent skills · Amazon · Shopee · TikTok Shop · Temu · Lazada · Wayfair · Mercado Libre · Excel export.
```

**概念版**（150 字符）：

```
把跨境电商运营全链路拆成 9 个可独立安装、可串成流水线的 Agent 技能：规则费率、数据制表、手写单据台账、选品测算、视频素材、广告投流、PO 单、ROI 复盘。Dependency-free Python, Excel export, human-in-the-loop risk rules.
```

## 三、Topics 标签（20 个，整行粘贴）

```
cross-border-ecommerce, ecommerce, ecommerce-automation, agent-skills, ai-agent, llm, prompt-engineering, amazon, shopee, tiktok-shop, temu, lazada, mercado-libre, roas, data-cleaning, excel, ocr, bookkeeping, python, openai-codex
```

分四类覆盖不同搜索意图：

| 类别 | 标签 | 命中谁 |
| --- | --- | --- |
| 业务品类 | `cross-border-ecommerce` `ecommerce` `ecommerce-automation` | 搜跨境电商 / 电商自动化的人 |
| 平台 | `amazon` `shopee` `tiktok-shop` `temu` `lazada` `mercado-libre` | 按平台名搜索的运营 |
| 场景与指标 | `roas` `data-cleaning` `excel` `ocr` `bookkeeping` | 按具体痛点搜索的人（含拍照记账、单据识别） |
| 技术生态 | `agent-skills` `ai-agent` `llm` `prompt-engineering` `openai-codex` `python` | 找 Agent 技能 / 提示词工程的开发者 |

> GitHub 单个 Topics 上限 20 个，这里刚好用满。本轮用 `ocr`、`bookkeeping` 换掉了原来的 `wayfair`、`human-in-the-loop`：平台名已经够多，而「拍照记账 / 单据识别」是另一批完全不同的搜索人群。想换回来就用第三节里的任意标签替换末尾两个。

## 四、技能运行链路（一段话，可贴到任何需要介绍的地方）

> 一条主链路、一条支线、九个技能：**① 规则费率 → ② 表格清洗 → ③ 选品测算 → ④ 广告视频素材 → ⑤ 投流结构 → ⑦ ROI 复盘** 是主链路，**⑥ PO 单** 从 ③ 分叉、和 ⑤ 汇合进 ⑦；**②B 手写单据台账** 是独立支线，任何时候都能跑，产出的标准品名台账与采销数据可以喂给 ③ 补货、⑥ 下单、⑦ 核成本。复盘结论沿虚线回流，修正下一轮的选品参数与素材方向，形成闭环。① 与 ② 可并行，④ 与 ⑥ 可并行。每个环节都交付「表格 + 结构化信封 + 待办清单」，有高风险标记就停下来等人。

完整运行链路（含每段的触发条件、命令、产物、交接字段与人工卡点，以及三种真实跑法）见 [docs/run-chain.md](../docs/run-chain.md)。

| 阶段 | 技能 | 一句话 | 关键产物 |
| --- | --- | --- | --- |
| ① 规则费率 | `ecom-rules-fee` | 把多平台零散规则变成可检索对照表，逐单核算实际到手 | 费率对照表、逐单费用明细、扣费风险清单 |
| ② 表格清洗 | `ecom-data-prep` | 后台导出的乱表统一口径，异常行隔离不硬跑 | 干净结构化表、字段覆盖率、隔离行 |
| ②B 单据台账 | `ecom-receipt-ledger` | 手写单据拍照录入，简写标准化 + 自动算账 + 采销日结 | 电子台账、日结月结、差异清单、凭证照片回链 |
| ③ 选品测算 | `ecom-selection-profit` | 多站点多币种算净利，反算保本价与目标售价 | 逐行测算、站点汇总、亏损组合清单 |
| ④ 视频素材 | `ecom-video-creative` | 出分镜与生成提示词，前三秒留存逐条检查，任意语种本地化 | 分镜表、模型提示词、语速预算、问题清单 |
| ⑤ 投流结构 | `ecom-ads-plan` | 定投放结构、预算出价、放量节奏与止损判优阈值 | 投放结构表、出价预算表、止损阈值表 |
| ⑥ PO 单 | `ecom-po-build` | 需求转成可下发的采购订单，下单前全套校验 | PO 单、校验报告、待人工确认清单 |
| ⑦ ROI 复盘 | `ecom-roi-review` | 算 ROAS/ACOS/净利，分组环比定位异常，出下周动作 | 分组复盘表、环比变化、归因链与周报 |

## 五、怎么设置

1. 打开 https://github.com/xianglouw/ecom-agent-skills
2. 右侧 **About** 一栏点齿轮图标
3. **Description** 粘贴第一节的推荐版（想吸引海外流量就用英文优先版）；**Website** 可留空
4. 勾选 **Releases** / **Packages** 视需要，建议至少勾 **Releases**
5. 同一个弹窗里的 **Topics** 粘贴第三节那一整行（GitHub 会自动按逗号拆成标签）
6. 保存

## 六、社交预览图（Social preview）

同一个弹窗里有 **Social preview → Upload an image**，建议传一张 1280×640 的图（仓库名 + 八段流水线示意），分享到群、公众号或 Twitter 时会显示这张图而不是默认头像。没有图片时 GitHub 会退化显示仓库名的纯色卡片，不影响功能。

## 七、仓库文件索引（给来访者指路）

| 想了解什么 | 看哪个文件 |
| --- | --- |
| 整体是什么、怎么装 | [README.md](../README.md) |
| **技能按什么顺序跑、每段吃什么吐什么、哪里要停下来等人** | [docs/run-chain.md](../docs/run-chain.md) |
| 阶段边界、交接字段、卡点与回流的完整定义 | [skills/crossborder-ecom-ops/references/workflow-orchestration.md](../skills/crossborder-ecom-ops/references/workflow-orchestration.md) |
| 六段式 Prompt 框架、把一次作业封装成可复用 Skill、Badcase 复盘 | [skills/crossborder-ecom-ops/references/prompt-contract.md](../skills/crossborder-ecom-ops/references/prompt-contract.md) |
| 每个版本改了什么 | [CHANGELOG.md](../CHANGELOG.md) |

## 八、曝光自查清单

- [ ] About 描述已填，且包含「跨境电商」「Agent」「Excel」「台账 / 单据」四类词
- [ ] Topics 至少填满 15 个
- [ ] README 第一屏有中英双语一句话说明（已具备）
- [ ] README 里有指向 `docs/run-chain.md` 的入口（已具备）
- [ ] 每个技能的 `SKILL.md` description 写清「做什么 + 什么时候用」（决定技能会不会被自动选中）
- [ ] 打一个 tag 并发布 Release，仓库会多一个 Releases 入口
- [ ] 仓库设为 Public
