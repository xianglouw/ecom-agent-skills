# 仓库 About 与 Topics 设置参考

这个文件是给维护者用的。GitHub 的 **About**（仓库简介）和 **Topics**（主题标签）只能在网页端设置，把下面内容复制粘贴过去即可，改完立刻生效、不需要重新提交代码。

## 一、About 描述（推荐版）

```
帮跨境电商卖家把重复的运营活交给 AI：查规则费率、清理后台乱表、手写单据拍照记账、算选品利润定价、写广告脚本与生图/视频提示词、直连 Seedance / Veo / Sora / 可灵等 12 家视频大模型出片、做采购单、跑投放复盘。每步都输出能直接打开的 Excel 表格；花钱、退款、合规只给判定与依据，落地由人执行。覆盖 Amazon、Shopee、TikTok Shop、Temu、Lazada、美客多等平台。
```

211 字符，未超 GitHub 的 350 字符上限。

**为什么这么写**：不写「Agent 技能集」「工作流编排」「输出信封」这类词——看仓库的人大部分是运营和老板，不是工程师。开头一句「把重复的运营活交给 AI」直接说清它是干嘛的，中间用一串动词短语列清楚能替人做哪些事，其中「直连 12 家视频大模型出片」是这一版的新增能力，也是运营最想省掉的环节（写完提示词不用再一个个平台手动传），最后补一句「输出能直接打开的 Excel」和「花钱、退款、合规由人执行」——这两句是运营最关心的：**给我能用的东西，别让我担风险**。末尾的平台名是为了搜索命中。

把视频大模型的名字写进 Description（Seedance / Veo / Sora / 可灵）是因为它们是搜索热词：有人搜「Seedance 怎么用」「Veo 出片」时，Description 会被 GitHub 搜索索引到。

前面提到过的技术向版本（含 `Agent 技能集`、`8 段工作流` 等表述）仍然可用，见下方备选。

## 二、备选版本

**问题清单式**（开头就把痛点摆出来，136 字符）：

```
跨境电商运营里最耗人的几件事，交给 AI 做：规则费率查得慢、后台导出的表要手动清、手写单据要一笔笔敲、选品定价算不清、广告脚本和视频提示词写不出来、出片要一个个平台手动传、下单怕错、复盘没时间写。每一步都输出能直接打开的 Excel 表格，涉及钱和合规的环节留给人确认。
```

**中英混合**（想同时吸引海外流量，229 字符）：

```
帮跨境电商卖家把重复的运营活交给 AI：查规则费率、清理后台乱表、手写单据拍照记账、算选品利润、写广告脚本、生图与视频提示词直连 12 家视频大模型出片、做采购单、出复盘报告，每步都输出能直接打开的 Excel。AI operations assistant for cross-border e-commerce sellers. Amazon / Shopee / TikTok Shop / Temu / Lazada / Mercado Libre.
```

**技术向精简版**（面向开发者与 Agent 生态，216 字符）：

```
跨境电商多平台运营 Agent 技能集：规则费率、表格清洗、手写单据拍照记账、选品测算、视频素材（直连 12 家视频大模型出片）、广告投流、PO 单、ROI 复盘，9 个技能可独立调用也可串成流水线。Cross-border e-commerce agent skills / Amazon / Shopee / TikTok Shop / Temu / Lazada / Mercado Libre / Excel export.
```

## 三、这套技能是做什么的（大白话版）

> **用来做什么**
> 帮跨境电商卖家把每天重复的运营活交给 AI 干：查平台规则和费率、把手写采购销售单据拍照录成电子台账（字迹潦草也认得出，认不准就不入账）、清理后台导出的表格、算选品利润和定价、写广告脚本和生图/视频素材提示词（写完可以直接连上视频大模型出片）、做采购单、跑投放数据复盘。
>
> **解决什么问题**
> 平台规则和费率太散，查一次要一两小时，还容易漏，漏了就是违规扣费；后台导出的表口径不一，每次都要手动整理；手写单据要一笔笔敲进 Excel，算错一个数当天的账就对不上，字迹一笔潦草就更没法录；选品定价靠拍脑袋，运费关税把利润吃掉才发现；广告素材做不出来，做出来前三秒留不住人，好不容易写好提示词还要一个个平台手动传、等出片；下单金额、起订量、交期容易出错；复盘靠回忆，说不清为什么亏。
>
> **能输出什么**
> 能直接打开的 Excel 表格（每份含多张工作表，单据台账里还带照片回链和标红标黄）、可读的复盘与对账报告、写明「哪张照片哪一行哪一格要重拍」的补拍清单、带风险标记和待办清单的结构化结论；素材侧还能直接给出成片文件与生成台账（哪条提示词、投了哪个平台哪个模型、什么时候出片、失败原因是什么，一行一条）。涉及花钱、退款、合规的环节只给判定和依据，落地由人来执行。

这一段可以直接贴在仓库介绍、群分享、公众号推文或 Release 说明里，不带技术词。

## 四、Topics 标签（20 个，整行粘贴）

```
cross-border-ecommerce, ecommerce-automation, excel, ocr, bookkeeping, roas, advertising, ad-creative, ai-image-generation, text-to-video, ai-video-generator, amazon, shopee, tiktok-shop, temu, lazada, mercado-libre, agent-skills, ai-agent, prompt-engineering
```

### 逐条对照（含同类仓库数）

「同类仓库数」= 在 GitHub 上挂了同一个标签的仓库数量（2026-09 实测）。**数字大 = 大词、逛的人多但你也容易被淹没；数字小 = 精准词、同行少、更容易挂在该标签首页。**

**① 品类与场景（6 个）**

| 标签 | 中文 | 同类仓库数 |
| --- | --- | --- |
| `cross-border-ecommerce` | 跨境电商 | 109 |
| `ecommerce-automation` | 电商自动化 | 62 |
| `excel` | Excel 表格 | 22,609 |
| `ocr` | 拍照识字（手写单据识别） | 13,970 |
| `bookkeeping` | 记账 / 台账 | 604 |
| `roas` | 广告投产比 | 92 |

**② 素材与投流（5 个，本轮新增，直接对应新的出片能力）**

| 标签 | 中文 | 同类仓库数 | 为什么留它 |
| --- | --- | --- | --- |
| `advertising` | 广告投放 | 1,402 | 「广告投流」的通用词，卖家和投手都会搜 |
| `ad-creative` | 广告素材创意 | 50 | 精准小众词：全站只有 50 个仓库挂着，同行少、容易被人翻到 |
| `ai-image-generation` | AI 生图素材 | 578 | 「生图素材」：产品图、视频首帧图、封面图都归它 |
| `text-to-video` | 文生视频 | 1,095 | 视频生成的通用说法，对应「提示词 → 出片」这一步 |
| `ai-video-generator` | AI 视频生成 | 255 | 短视频素材工具类搜索词，投放人群常搜 |

**③ 平台（6 个）**

| 标签 | 中文 | 同类仓库数 |
| --- | --- | --- |
| `amazon` | 亚马逊 | 4,006 |
| `shopee` | 虾皮 | 216 |
| `tiktok-shop` | TikTok 小店 | 69 |
| `temu` | Temu（拼多多跨境） | 32 |
| `lazada` | Lazada（东南亚） | 60 |
| `mercado-libre` | 美客多（拉美） | 29 |

**④ Agent 与 AI 工程（3 个）**

| 标签 | 中文 | 同类仓库数 |
| --- | --- | --- |
| `agent-skills` | Agent 技能（技能包规范） | 23,043 |
| `ai-agent` | AI 智能体 | 31,138 |
| `prompt-engineering` | 提示词工程 | 18,220 |

### 为什么必须用英文

GitHub 的 Topics 只支持小写字母、数字和连字符，**中文写不进去**，也搜不到。实测：`topic:机器学习` 命中 0 个仓库，`topic:machine-learning` 命中 242,542 个；`topic:跨境电商` 命中 0 个，`topic:cross-border-ecommerce` 命中 109 个。所以这一栏只能填英文，中文关键词要靠 About 描述和 README 正文承载。

### 关于「再加标签」

GitHub 单个仓库的 Topics **硬上限 20 个**，这里已经用满，加不了第 21 个。想继续扩大关键词覆盖，只能靠另外三处，它们同样会被搜索索引：

- **About 描述**（第一节）
- **Release 标题与正文**（第五节）
- **README 正文**（已含痛点对照表与运行链路）

### 这一轮换掉了哪 5 个、为什么

这一版的新能力是「广告素材 + 生图 + 视频出片」，所以把 5 个泛 AI 词让给了 5 个素材投流词，总数仍是 20：

| 换掉 | 原同类仓库数 | 为什么换 |
| --- | --- | --- |
| `llm` | 131,420 | 全网最大的词之一，挂上去等于扔进海里，且已被 `ai-agent` 覆盖 |
| `ai-agents` | 91,404 | 与 `ai-agent` 是同义词，白占一个名额 |
| `vibe-coding` | 6,143 | 开发者圈的词，目标人群（卖家、投手）不会搜 |
| `data-cleaning` | 8,220 | 偏数据科学；仓库里的表格场景已由 `excel` 覆盖 |
| `workflow-automation` | 7,467 | 泛自动化词，精准度不如新增的 `advertising` / `ad-creative` |

### 备选词池（想再换，从这里挑，全部实测过）

| 方向 | 可选标签（同类仓库数） |
| --- | --- |
| 投流向 | `ads` 1,459 · `marketing-automation` 1,530 · `meta-ads` 340 · `ugc` 220 · `tiktok-ads` 66 · `video-ads` 40 · `ecommerce-marketing` 4（极冷门，挂上就能排在该标签前排） |
| 素材向 | `image-generation` 6,254 · `ai-video` 1,610 · `short-video` 307 |
| 电商向 | `dropshipping` 198 |
| 换回旧词 | `llm` 131,420 · `ai-agents` 91,404 · `data-cleaning` 8,220 · `workflow-automation` 7,467 · `vibe-coding` 6,143 |

**取舍原则**：真正能带来电商人群的是 `cross-border-ecommerce`、`ecommerce-automation`、`excel` 加 6 个平台词，这 9 个别动；② 里的 5 个素材投流词是这一版的卖点，也别动；真要腾位置，从 ④ 里再让一个 AI 词出来。想换别的就用本节的标签互替，保持 20 个即可。

## 五、Release 标题（发布时用）

Release 标题会被 GitHub 搜索索引，也是 Releases 列表里唯一可见的一行，所以按「版本号 + 品类词 + 规模 + 场景词」来排。

**主推（99 字，关键词与可读性平衡）**

```
v0.1.0 首发 — 跨境电商运营 Agent 技能集：9 个 AI 技能 / 8 段工作流，覆盖规则费率 · 表格清洗 · 拍照记账 · 选品测算 · 广告投流 · PO 采购 · ROI 复盘
```

**精简版**（42 字，适合不想标题太长时）：

```
v0.1.0 — 跨境电商运营 Agent 技能集首发：9 个技能 / 8 段工作流
```

**结果导向版**（59 字，突出改造成效）：

```
v0.1.0 — 9 个 Agent 技能接管跨境电商重复运营：规则检索分钟级、PO 与退款自动核、人力耗时降 55%
```

**中英双语版**（86 字，想同时吃英文搜索流量时）：

```
v0.1.0 首发 — 跨境电商运营 Agent 技能集 · Cross-border E-commerce Agent Skills：9 个 AI 技能 / 8 段工作流
```

> Release 标题不像 Topics 有 20 个上限，可以放心把关键词写全；正文同样会被索引，把「选品 / 投流 / 采购 / 复盘 / 拍照记账」这类词自然写进正文比堆在标题里更耐看。

**想突出这一版的素材直连能力**（已发布的 v0.1.0 也能改，见下方说明）：

```
v0.1.0 — 跨境电商运营 Agent 技能集：9 个技能 / 8 段工作流，广告素材直连 12 家视频大模型出片（Seedance · Veo · Sora · 可灵 · 通义万相）
```

> **已经发布的 Release 想换标题不用重新打包**：打开仓库的 Releases 页面 → 该版本的 **Edit** → 改标题 → Update release，立刻生效。视频大模型的名称（Seedance / Veo / Sora / 可灵 / 通义万相）本身就是搜索热词，写进标题能多接一批搜模型的流量。

## 六、技能运行链路（一段话，可贴到任何需要介绍的地方）

> 一条主链路、一条支线、九个技能：**① 规则费率 → ② 表格清洗 → ③ 选品测算 → ④ 广告视频素材 → ⑤ 投流结构 → ⑦ ROI 复盘** 是主链路，**⑥ PO 单** 从 ③ 分叉、和 ⑤ 汇合进 ⑦；**②B 手写单据台账** 是独立支线，任何时候都能跑，产出的标准品名台账与采销数据可以喂给 ③ 补货、⑥ 下单、⑦ 核成本。复盘结论沿虚线回流，修正下一轮的选品参数与素材方向，形成闭环。① 与 ② 可并行，④ 与 ⑥ 可并行。每个环节都交付「表格 + 结构化信封 + 待办清单」，有高风险标记就停下来等人。

完整运行链路（含每段的触发条件、命令、产物、交接字段与人工卡点，以及三种真实跑法）见 [docs/run-chain.md](../docs/run-chain.md)。

| 阶段 | 技能 | 一句话 | 关键产物 |
| --- | --- | --- | --- |
| ① 规则费率 | `ecom-rules-fee` | 把多平台零散规则变成可检索对照表，逐单核算实际到手 | 费率对照表、逐单费用明细、扣费风险清单 |
| ② 表格清洗 | `ecom-data-prep` | 后台导出的乱表统一口径，异常行隔离不硬跑 | 干净结构化表、字段覆盖率、隔离行 |
| ②B 单据台账 | `ecom-receipt-ledger` | 手写单据拍照录入，潦草字迹加固 + 简写标准化 + 自动算账 + 采销日结 | 电子台账、日结月结、差异清单、补拍清单（一行一个待办）、价格核对、凭证照片回链 |
| ③ 选品测算 | `ecom-selection-profit` | 多站点多币种算净利，反算保本价与目标售价 | 逐行测算、站点汇总、亏损组合清单 |
| ④ 视频素材 | `ecom-video-creative` | 出分镜与生成提示词，前三秒留存逐条检查，任意语种本地化；提示词可直连 12 家视频生成大模型接口出真实镜头片段 | 分镜表、模型提示词、语速预算、问题清单、（直连时）成片文件与生成台账 |
| ⑤ 投流结构 | `ecom-ads-plan` | 定投放结构、预算出价、放量节奏与止损判优阈值 | 投放结构表、出价预算表、止损阈值表 |
| ⑥ PO 单 | `ecom-po-build` | 需求转成可下发的采购订单，下单前全套校验 | PO 单、校验报告、待人工确认清单 |
| ⑦ ROI 复盘 | `ecom-roi-review` | 算 ROAS/ACOS/净利，分组环比定位异常，出下周动作 | 分组复盘表、环比变化、归因链与周报 |

## 七、怎么设置

1. 打开 https://github.com/xianglouw/ecom-agent-skills
2. 右侧 **About** 一栏点齿轮图标
3. **Description** 粘贴第一节的推荐版（想同时吸引海外流量就用第二节的中英混合版）；**Website** 可留空
4. 勾选 **Releases** / **Packages** 视需要，建议至少勾 **Releases**
5. 同一个弹窗里的 **Topics** 粘贴 **第四节** 那一整行（GitHub 会自动按逗号拆成标签）
6. **Social preview** 上传仓库里的 `docs/social-preview.png`
7. 保存

## 八、社交预览图（Social preview）

同一个弹窗里有 **Social preview → Upload an image**，传仓库里现成的那张：

```
docs/social-preview.png
```

1280×640，115 KB（GitHub 上限 1 MB），深色卡片，内容是大白话标题「把重复的运营活交给 AI」+ 八个阶段色块（规则费率 / 表格清洗 / 单据台账 / 选品测算 / 素材生产 / 投流结构 / PO 采购单 / 数据复盘）+ 两行卖点：

- 广告素材直连 12 家视频大模型：Seedance / Veo / Sora / 可灵 / 通义万相，写完提示词就出片
- 每步都输出能直接打开的 Excel 表格；花钱、退款、合规只给判定与依据，落地由人执行

分享到群、公众号或社交媒体时会显示这张图而不是默认头像；没有图片时 GitHub 会退化显示仓库名的纯色卡片，不影响功能。

需要改文案时改脚本顶部的文字常量、重跑即可（图形由 Pillow 直接绘制，改字不用重排版）：

```
python3 .github/make_social_preview.py
```

## 九、仓库文件索引（给来访者指路）

| 想了解什么 | 看哪个文件 |
| --- | --- |
| 整体是什么、怎么装 | [README.md](../README.md) |
| **技能按什么顺序跑、每段吃什么吐什么、哪里要停下来等人** | [docs/run-chain.md](../docs/run-chain.md) |
| 阶段边界、交接字段、卡点与回流的完整定义 | [skills/crossborder-ecom-ops/references/workflow-orchestration.md](../skills/crossborder-ecom-ops/references/workflow-orchestration.md) |
| 六段式 Prompt 框架、把一次作业封装成可复用 Skill、Badcase 复盘 | [skills/crossborder-ecom-ops/references/prompt-contract.md](../skills/crossborder-ecom-ops/references/prompt-contract.md) |
| 每个版本改了什么 | [CHANGELOG.md](../CHANGELOG.md) |
| 最新版本的发布说明（可直接贴到 Release） | [docs/release-notes-v0.1.0.md](../docs/release-notes-v0.1.0.md) |
| 仓库社交预览图 | [docs/social-preview.png](../docs/social-preview.png) |
| 想改社交预览图上的文字 | [.github/make_social_preview.py](make_social_preview.py) |

## 十、曝光自查清单

- [ ] About 描述已填，且包含「跨境电商」「Agent」「Excel」「台账 / 单据」「素材 / 投流」五类词
- [ ] 素材与投流类标签已填（`advertising`、`ad-creative`、`ai-image-generation`、`text-to-video`、`ai-video-generator`），这是这一版最该被搜到的词
- [ ] Topics 至少填满 15 个
- [ ] README 第一屏有中英双语一句话说明（已具备）
- [ ] README 里有指向 `docs/run-chain.md` 的入口（已具备）
- [ ] 每个技能的 `SKILL.md` description 写清「做什么 + 什么时候用」（决定技能会不会被自动选中）
- [ ] 打 tag 并发布 Release，仓库多一个 Releases 入口；标题用第五节的推荐版（关键词会被搜索索引）
- [ ] 仓库设为 Public
