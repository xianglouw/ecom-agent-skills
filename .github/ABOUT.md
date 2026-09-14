# 仓库 About 与 Topics 设置参考

这个文件是给维护者用的。GitHub 的 **About**（仓库简介）和 **Topics**（主题标签）只能在网页端设置，把下面内容复制粘贴过去即可，改完立刻生效、不需要重新提交代码。

## 一、About 描述（推荐版）

```
帮跨境电商卖家把重复的运营活交给 AI：查规则和费率、清理后台乱表、手写单据拍照记账、算选品利润和定价、写广告脚本和视频提示词、做采购单、出复盘报告。每步都输出能直接打开的 Excel 表格，涉及钱和合规的环节留给人确认。覆盖 Amazon、Shopee、TikTok Shop、Temu、Lazada、美客多等平台。
```

159 字符，未超 GitHub 的 350 字符上限。

**为什么这么写**：不写「Agent 技能集」「工作流编排」「输出信封」这类词——看仓库的人大部分是运营和老板，不是工程师。开头一句「把重复的运营活交给 AI」直接说清它是干嘛的，后面用七个动词短语列清楚能替人做哪些事，最后补一句「输出能直接打开的 Excel」和「钱与合规留给人确认」——这两句是运营最关心的：**给我能用的东西，别让我担风险**。末尾的平台名是为了搜索命中。

前面提到过的技术向版本（含 `Agent 技能集`、`8 段工作流` 等表述）仍然可用，见下方备选。

## 二、备选版本

**问题清单式**（开头就把痛点摆出来，124 字符）：

```
跨境电商运营里最耗人的几件事，交给 AI 做：规则费率查得慢、后台导出的表要手动清、手写单据要一笔笔敲、选品定价算不清、广告脚本和视频提示词写不出来、下单怕错、复盘没时间写。每一步都输出能直接打开的 Excel 表格，涉及钱和合规的环节留给人确认。
```

**中英混合**（想同时吸引海外流量，206 字符）：

```
帮跨境电商卖家把重复的运营活交给 AI：查规则费率、清理后台乱表、手写单据拍照记账、算选品利润、写广告脚本、做采购单、出复盘报告，每步都输出能直接打开的 Excel。AI operations assistant for cross-border e-commerce sellers. Amazon · Shopee · TikTok Shop · Temu · Lazada · Mercado Libre.
```

**技术向精简版**（面向开发者与 Agent 生态，200 字符）：

```
跨境电商多平台运营 Agent 技能集：规则费率、表格清洗、手写单据拍照记账、选品测算、视频素材、广告投流、PO 单、ROI 复盘，9 个技能可独立调用也可串成流水线。Cross-border e-commerce agent skills · Amazon · Shopee · TikTok Shop · Temu · Lazada · Mercado Libre · Excel export.
```

## 三、这套技能是做什么的（大白话版）

> **用来做什么**
> 帮跨境电商卖家把每天重复的运营活交给 AI 干：查平台规则和费率、清理后台导出的表格、把手写采购销售单据拍照录成电子台账、算选品利润和定价、写广告脚本和视频提示词、做采购单、跑投放数据复盘。
>
> **解决什么问题**
> 平台规则和费率太散，查一次要一两小时，还容易漏，漏了就是违规扣费；后台导出的表口径不一，每次都要手动整理；手写单据要一笔笔敲进 Excel，算错一个数当天的账就对不上；选品定价靠拍脑袋，运费关税把利润吃掉才发现；广告素材做不出来，做出来前三秒留不住人；下单金额、起订量、交期容易出错；复盘靠回忆，说不清为什么亏。
>
> **能输出什么**
> 能直接打开的 Excel 表格（每份含多张工作表）、可读的复盘与对账报告、带风险标记和待办清单的结构化结论。涉及花钱、退款、合规的环节只给判定和依据，落地由人来执行。

这一段可以直接贴在仓库介绍、群分享、公众号推文或 Release 说明里，不带技术词。

## 四、Topics 标签（20 个，整行粘贴）

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

> GitHub 单个 Topics 上限 20 个，这里刚好用满。本轮用 `ocr`、`bookkeeping` 换掉了原来的 `wayfair`、`human-in-the-loop`：平台名已经够多，而「拍照记账 / 单据识别」是另一批完全不同的搜索人群。想换回来就用第四节的任意标签替换末尾两个。

## 五、技能运行链路（一段话，可贴到任何需要介绍的地方）

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

## 六、怎么设置

1. 打开 https://github.com/xianglouw/ecom-agent-skills
2. 右侧 **About** 一栏点齿轮图标
3. **Description** 粘贴第一节的推荐版（想吸引海外流量就用英文优先版）；**Website** 可留空
4. 勾选 **Releases** / **Packages** 视需要，建议至少勾 **Releases**
5. 同一个弹窗里的 **Topics** 粘贴第三节那一整行（GitHub 会自动按逗号拆成标签）
6. **Social preview** 上传仓库里的 `docs/social-preview.png`
7. 保存

## 七、社交预览图（Social preview）

同一个弹窗里有 **Social preview → Upload an image**，传仓库里现成的那张：

```
docs/social-preview.png
```

1280×640，202 KB（GitHub 上限 1 MB），深色卡片，内容是大白话标题「把重复的运营活交给 AI」+ 八个阶段色块 + 一行输出说明。分享到群、公众号或社交媒体时会显示这张图而不是默认头像；没有图片时 GitHub 会退化显示仓库名的纯色卡片，不影响功能。

需要改文案时重跑生成脚本即可（图形由 Pillow 直接绘制，改字不用重排版）。

## 八、仓库文件索引（给来访者指路）

| 想了解什么 | 看哪个文件 |
| --- | --- |
| 整体是什么、怎么装 | [README.md](../README.md) |
| **技能按什么顺序跑、每段吃什么吐什么、哪里要停下来等人** | [docs/run-chain.md](../docs/run-chain.md) |
| 阶段边界、交接字段、卡点与回流的完整定义 | [skills/crossborder-ecom-ops/references/workflow-orchestration.md](../skills/crossborder-ecom-ops/references/workflow-orchestration.md) |
| 六段式 Prompt 框架、把一次作业封装成可复用 Skill、Badcase 复盘 | [skills/crossborder-ecom-ops/references/prompt-contract.md](../skills/crossborder-ecom-ops/references/prompt-contract.md) |
| 每个版本改了什么 | [CHANGELOG.md](../CHANGELOG.md) |
| 最新版本的发布说明（可直接贴到 Release） | [docs/release-notes-v0.1.0.md](../docs/release-notes-v0.1.0.md) |
| 仓库社交预览图 | [docs/social-preview.png](../docs/social-preview.png) |

## 九、曝光自查清单

- [ ] About 描述已填，且包含「跨境电商」「Agent」「Excel」「台账 / 单据」四类词
- [ ] Topics 至少填满 15 个
- [ ] README 第一屏有中英双语一句话说明（已具备）
- [ ] README 里有指向 `docs/run-chain.md` 的入口（已具备）
- [ ] 每个技能的 `SKILL.md` description 写清「做什么 + 什么时候用」（决定技能会不会被自动选中）
- [ ] 打一个 tag 并发布 Release，仓库会多一个 Releases 入口
- [ ] 仓库设为 Public
