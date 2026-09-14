# 仓库 About 与 Topics 设置参考

这个文件是给维护者用的。GitHub 的 **About**（仓库简介）和 **Topics**（主题标签）只能在网页端设置，把下面内容复制粘贴过去即可，改完立刻生效、不需要重新提交代码。

## 一、About 描述（推荐版）

```
跨境电商多平台运营 Agent 技能集｜7 阶段 AI 工作流：规则费率检索 → 表格清洗 → 选品测算 → 视频素材 → 广告投流 → PO 单制作 → ROI 复盘。Cross-border e-commerce agent skills for Amazon, Shopee, TikTok Shop, Temu, Lazada, Wayfair, Mercado Libre. Python 标准库，一键导出 Excel。
```

215 字符，未超 GitHub 的 350 字符上限。

**为什么这么写**：GitHub 仓库搜索会同时匹配仓库名、About 描述、Topics 和 README 正文。这段话里压了三类搜索词——品类词（跨境电商 / cross-border e-commerce）、场景词（选品 / 投流 / PO 单 / ROI 复盘 / data cleaning）、平台词（Amazon / Shopee / TikTok Shop / Temu / Lazada / Wayfair / Mercado Libre），中文用户和英文用户都能命中。

## 二、备选版本

**英文优先**（想多吸引海外开发者与 Agent 生态流量时用，280 字符）：

```
Cross-border e-commerce agent skills: a 7-stage AI workflow — platform rules & fees, data cleaning, product selection, video creative, ads planning, PO build, ROI review. 跨境电商多平台运营技能集，支持 Amazon / Shopee / TikTok Shop / Temu / Lazada / Wayfair / Mercado Libre，Python 标准库一键导出 Excel。
```

**精简版**（首屏更像一句话卖点，200 字符）：

```
跨境电商多平台运营 Agent 技能集：规则费率、表格清洗、选品测算、视频素材、广告投流、PO 单、ROI 复盘，7 阶段可独立调用也可串成流水线。Cross-border e-commerce agent skills · Amazon · Shopee · TikTok Shop · Temu · Lazada · Wayfair · Mercado Libre · Excel export.
```

**概念版**（151 字符）：

```
把跨境电商运营全链路拆成 7 个可独立安装、可串成流水线的 Agent 技能：规则费率、数据制表、选品测算、视频素材、广告投流、PO 单、ROI 复盘。Dependency-free Python scripts, Excel export, human-in-the-loop risk rules.
```

## 三、Topics 标签（20 个，整行粘贴）

```
cross-border-ecommerce, ecommerce, ecommerce-automation, agent-skills, ai-agent, llm, prompt-engineering, amazon, shopee, tiktok-shop, temu, lazada, wayfair, mercado-libre, roas, data-cleaning, excel, python, openai-codex, human-in-the-loop
```

分三类覆盖不同搜索意图：

| 类别 | 标签 | 命中谁 |
| --- | --- | --- |
| 业务品类 | `cross-border-ecommerce` `ecommerce` `ecommerce-automation` | 搜跨境电商 / 电商自动化的人 |
| 平台 | `amazon` `shopee` `tiktok-shop` `temu` `lazada` `wayfair` `mercado-libre` | 按平台名搜索的运营 |
| 场景与指标 | `roas` `data-cleaning` `excel` `human-in-the-loop` | 按具体痛点搜索的人 |
| 技术生态 | `agent-skills` `ai-agent` `llm` `prompt-engineering` `openai-codex` `python` | 找 Agent 技能 / 提示词工程的开发者 |

> GitHub 单个 Topics 上限 20 个，这里刚好用满。如果要腾位子，优先替换 `human-in-the-loop` 或 `excel`。

## 四、怎么设置

1. 打开 https://github.com/xianglouw/ecom-agent-skills
2. 右侧 **About** 一栏点齿轮图标
3. **Description** 粘贴上面推荐版；**Website** 可留空
4. 勾选 **Releases** / **Packages** 视需要，建议至少勾 **Releases**
5. 同一个弹窗里的 **Topics** 粘贴第三节那一整行（GitHub 会自动按逗号拆成标签）
6. 保存

## 五、社交预览图（Social preview）

同一个弹窗里有 **Social preview → Upload an image**，建议传一张 1280×640 的图（仓库名 + 七阶段流水线示意），分享到群、公众号或 Twitter 时会显示这张图而不是默认头像。没有图片时 GitHub 会退化显示仓库名的纯色卡片，不影响功能。

## 六、曝光自查清单

- [ ] About 描述已填，且包含「跨境电商」「Agent」「Excel」三个词
- [ ] Topics 至少填满 15 个
- [ ] README 第一屏有中英双语一句话说明（已具备）
- [ ] 每个技能的 `SKILL.md` description 写清「做什么 + 什么时候用」（决定技能会不会被自动选中）
- [ ] 打一个 `v0.1.0` tag 并发布 Release，仓库会多一个 Releases 入口
- [ ] 仓库设为 Public
