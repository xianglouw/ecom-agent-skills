# 生成侧：把提示词接到视频生成平台

阶段 4 的「生成侧」负责一件事：**把 `video_brief.py` 产出的分镜提示词，交给用户选定的视频生成大模型，换回真实可投放的镜头片段**。

脚本 `scripts/video_render.py` + 配置 `scripts/providers.json` 一起干这件事。本技能只负责**把提示词写对**和**把链路接通**；用哪个平台、花多少钱，由用户决定。

## 分工：谁选模型

| 环节 | 谁负责 |
|---|---|
| 写画面描述、镜头语言、字幕口播、前三秒留存检查 | 本技能（`video_brief.py`，确定性计算，不调模型） |
| 挑哪个多模态模型、用哪个模型版本 | **用户决定**，脚本提供清单与默认值 |
| 把提示词按该平台的参数名组装成请求 | `video_render.py` 按 `providers.json` 组装 |
| 提交、轮询、取回成片、记台账 | `video_render.py` |
| 花多少钱、放多少量 | **用户决定**，脚本只做硬上限与显式确认 |

## 三步走

```bash
# 第一步：看有哪些平台可选、各自要哪个环境变量、默认用哪个模型
python3 scripts/video_render.py --list-providers

# 第二步：验凭据（不生成、不花钱）
python3 scripts/video_render.py storyboard.csv --provider ark --check

# 第三步：先试跑看请求体，确认后再真跑
python3 scripts/video_render.py storyboard.csv --provider ark --assets SKU-101_MX_H01_9x16_15s_v1 \
  --shots 1 --first-frame-dir frames --print-request
python3 scripts/video_render.py storyboard.csv --provider ark --max-clips 8 --confirm \
  --outdir renders --out renders.csv --out-xlsx renders.xlsx --out-json renders.json
```

**不加 `--confirm` 一个请求都不会发出去。** `--confirm` 是唯一会花钱的开关。

## 支持的平台

`providers.json` 里预置了 12 个平台，选平台只改 `--provider` 一个词：

| 平台 id | 名称 | 能力 | 环境变量 | 默认模型 |
|---|---|---|---|---|
| `mock` | 离线演示 | 文生 / 图生 | 不需要 | `mock-video-1` |
| `ark` | 火山方舟 Seedance / 豆包视频 | 文生 / 图生 | `ARK_API_KEY` | `doubao-seedance-1-0-pro-250528` |
| `dashscope` | 阿里云百炼 通义万相 | 文生 / 图生 | `DASHSCOPE_API_KEY` | `wan2.1-t2v-turbo` |
| `kling` | 可灵 文生视频 | 文生 | `KLING_ACCESS_KEY` + `KLING_SECRET_KEY` | `kling-v1` |
| `kling-i2v` | 可灵 图生视频 | 图生 | `KLING_ACCESS_KEY` + `KLING_SECRET_KEY` | `kling-v1` |
| `minimax` | 海螺 AI MiniMax 视频 | 文生 / 图生 | `MINIMAX_API_KEY` | `MiniMax-Hailuo-02` |
| `gemini` | Google Veo（Gemini API） | 文生 / 图生 | `GEMINI_API_KEY` | `veo-3.0-generate-preview` |
| `openai` | OpenAI Sora | 文生 | `OPENAI_API_KEY` | `sora-2` |
| `runway` | Runway Gen 系列 | 图生 | `RUNWAY_API_KEY` | `gen4_turbo` |
| `luma` | Luma Dream Machine | 文生 / 图生 | `LUMA_API_KEY` | `ray-2` |
| `replicate` | Replicate 托管模型 | 文生 / 图生 | `REPLICATE_API_TOKEN` | `google/veo-3-fast` |
| `fal` | fal.ai 托管模型 | 文生 / 图生 | `FAL_KEY` | `fal-ai/veo3` |

默认跑 `mock`：不联网、不花钱，只走通「提交 → 轮询 → 下载 → 记台账」，用来看产物长什么样。换真平台就是换个 `--provider`。

## 各平台注意事项

- **ark（火山方舟）**：首帧图放在 `content` 数组的 `image_url` 里，本地图片会自动转成内联 data URI 传过去；比例与时长按官方文档，可能支持写进 text 的 `--ratio` / `--dur` 参数。
- **dashscope（通义万相）**：需要 `X-DashScope-Async: enable` 头（配置里已带）；返回结构是 `output.task_id` / `output.task_status`，脚本两个层级都试。
- **kling / kling-i2v**：走 JWT 鉴权，要**同时**给 Access Key 与 Secret Key，脚本自动签 HS256。图生视频的 `image` 字段要**纯 base64、不带 `data:image` 前缀**，本地图片会自动转好；给的是网络地址时脚本会先取回来再转码。
- **minimax（海螺）**：查询返回的是 `file_id`，还要再调一次 `/v1/files/retrieve` 换下载地址，脚本已内置这一步。
- **gemini（Veo）**：用 `x-goog-api-key` 头传 Key 而不是 Authorization；完成与否看 `done` 布尔值，失败信息在 `error` 字段里（配置里已配 `error_path`，失败会立刻判定而不是干等超时）；返回的下载地址还要带同一个 Key 才能取，脚本已透传。
- **openai（Sora）**：提交后拿到的是视频 id，还要再取 `/v1/videos/{id}/content` 才是文件本体，脚本已内置。部分地区访问会返回 `unsupported_country_region_territory`。
- **runway**：必须带 `X-Runway-Version` 头（配置里已带）；`promptImage` 要传可公网访问的图片地址或 data URI。
- **luma**：状态字段是 `state`，完成值是 `completed`。
- **replicate**：模型名写成 `owner/name`，不同托管模型入参名不一样，不对就改 `providers.json` 里的 `create.body`。
- **fal**：鉴权头是 `Authorization: Key <FAL_KEY>`（不是 Bearer）；提交后返回 `status_url` 与 `response_url`，脚本优先用返回的地址轮询与取结果。

## 参数会变，以官方文档为准

各平台的参数名、模型名、计费口径都会随版本变化。**`providers.json` 里的配置是按 2026-09-14 的端点形状写下的，正式投产前必须核对一次**：

```bash
python3 scripts/video_render.py --list-providers        # 看平台与默认模型
python3 scripts/video_render.py storyboard.csv --provider ark --check         # 验凭据
python3 scripts/video_render.py storyboard.csv --provider ark --print-request # 看实际请求体
```

不对就改 `providers.json`（加平台、改模型名、改参数都只动这个文件），或用 `--provider-file 我的配置.json` 传一份覆盖配置，不动仓库里的文件。

## 花钱这件事

生成按条计费，**脚本不掌握各平台的实时单价**，所以它只做三件与钱有关的事：

1. **硬上限**：`--max-clips`（默认 10）截断本次提交数量。
2. **显式确认**：不加 `--confirm` 只试跑，一个字节都不发。
3. **可追溯**：每一笔的提交时间、完成时间、耗时、任务 ID 都进台账。

另外视频模型多按固定档位计费（常见 5 秒 / 10 秒一档），拿 3 秒的钩子镜头去跑 5 秒的档位是常态；`--use-shot-seconds` 按分镜秒数生成，但**只取更大的那个值**，不会短于 `--duration`。

## 首帧图怎么给

图生视频（`kling-i2v`、`runway`）必须有首帧图，其余平台有则更好——先出首帧再出视频比纯文生视频稳定得多。

查找顺序（三选一，命中即用）：

1. 分镜表里的 `first_frame` / `first_frame_path` 列写的地址（http(s)、`data:`、或本地路径）
2. `--first-frame-dir` 目录下的 `素材名_镜头号.png`
3. 同目录下的 `素材名.png`

也认 `.jpg` / `.jpeg` / `.webp`。本地图片按 `--max-image-mb`（默认 8MB）限制体积，超了会报出来让你先压缩。文件命名对不上时会明确告诉你**缺哪个文件名**，不会静默跳过。

## 断点续跑

已经成功、且成片文件还在的镜头，重跑时默认跳过，不重复花钱。台账里 `状态=ok` 且 `本地路径` 存在的行才算数；要全部重生成就加 `--overwrite`（比如换了模型想重出一版）。

## 产物

| 参数 | 产物 | 说明 |
|---|---|---|
| `--outdir` | 成片目录 | 按 `素材名_镜头号.mp4` 命名，和分镜表、投放端、复盘端对齐 |
| `--out` | 生成台账 CSV | 20 列：素材名 / SKU / 市场 / 语种 / 镜头 / 时段 / 时长 / 平台 / 模型 / 比例 / 任务ID / 状态 / 文件 / 本地路径 / 下载地址 / 提交时间 / 完成时间 / 耗时 / 重试 / 失败原因 |
| `--out-xlsx` | 生成台账 Excel | 「生成台账」+ 按状态分表，失败行标红底 |
| `--out-json` | JSON 信封 | 给下游脚本、工单系统读 |
| `--quarantine` | 未生成清单 CSV | 没跑成的镜头，带上当时的提示词，方便改完重投 |

## 常见坑

- **提示词描述画面，不描述数据**：`visual_prompt` 列是给模型看的，别把价格、SKU 号塞进去。
- **一次只生成一个镜头**：多镜头一次出的一般连不上、动作也乱，按分镜逐镜生成再剪。
- **别拿成品率当必然**：生成失败多半是命中平台审核或参数不合法，按平台报错改提示词再投，不要原样重投。
- **提示词里的 `{{待填:字段}}` 要先补完**：没补齐的素材属于半成品，进生成队列就是浪费钱。
- **超时不等于失败**：等超时了先到平台后台按任务 ID 查结果，别急着重跑。
