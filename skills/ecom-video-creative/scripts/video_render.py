#!/usr/bin/env python3
"""阶段 4（生成侧）：把分镜表里的生成提示词接到视频生成平台，产出真实投流素材。

用法：
  # 1. 先看有哪些平台、各自要用哪个环境变量放 Key
  python3 video_render.py --list-providers

  # 2. 验一把凭据对不对（不生成、不花钱）
  python3 video_render.py storyboard.csv --provider ark --check

  # 3. 看看会发出什么请求（默认就是试跑，不发请求）
  python3 video_render.py storyboard.csv --provider ark --assets A001 --shots 1 --print-request

  # 4. 确认无误再真跑（--confirm 是唯一会花钱的开关）
  python3 video_render.py storyboard.csv --provider ark --model doubao-seedance-1-0-pro-250528 \
    --max-clips 8 --confirm --outdir renders \
    --out renders.csv --out-xlsx renders.xlsx --out-json renders.json

设计取舍：
- 平台参数全部写在 providers.json，改模型名、改参数、加平台都不用改代码。
- 默认试跑。不加 --confirm 只打印将要发出的请求体，一个字节都不发出去。
- 生成要花钱，脚本没法替你核对单价，所以只做三件事：限总量（--max-clips）、
  显式确认（--confirm）、把每一笔的提交与耗时记进台账供追溯。
- 断点续跑：已经成功且文件还在的镜头默认跳过，避免重复付费。
- 只读分镜表，只写 --outdir 与 --out/--out-xlsx/--out-json 指定文件。
"""

import argparse
import base64
import hashlib
import hmac
import json
import mimetypes
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import unicodedata

import sheetio
from sheetio import clean_text, to_number

HERE = os.path.dirname(os.path.abspath(__file__))
PROVIDERS_FILE = os.path.join(HERE, "providers.json")

SHOT_FIELDS = ["asset_name", "sku", "product_name", "site", "language", "ratio", "duration_s",
               "hook_code", "hook_name", "shot_index", "timecode", "shot_seconds", "shot_type",
               "visual_prompt", "caption", "voiceover", "retention_note", "first_frame", "first_frame_path"]

MANIFEST_HEADERS = ["素材名", "SKU", "市场", "语种", "镜头", "时段", "时长(秒)", "平台", "模型",
                    "比例", "任务ID", "状态", "文件", "本地路径", "下载地址", "提交时间", "完成时间",
                    "耗时(秒)", "重试", "失败原因"]

RUNNING_STATES = {"running", "processing", "pending", "queued", "submitted", "in_progress", "in_queue"}
SECRET_PATTERN = re.compile(r"(sk-[A-Za-z0-9_\-]{6,}|[A-Za-z0-9_\-]{24,}\.[A-Za-z0-9_\-]{16,}\.[A-Za-z0-9_\-]{16,})")


# ---------------------------------------------------------------- 平台配置

def load_providers(extra_files):
    """读内置 providers.json，再用 --provider-file 逐层覆盖，方便用户只写差异。"""
    try:
        with open(PROVIDERS_FILE, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as error:
        raise ValueError(f"读不到内置平台配置 {PROVIDERS_FILE}：{error}") from error
    providers = data.get("providers") or {}
    for path in extra_files:
        try:
            with open(path, encoding="utf-8") as handle:
                overlay = json.load(handle)
        except (OSError, ValueError) as error:
            raise ValueError(f"覆盖配置 {path} 读取失败：{error}") from error
        incoming = overlay.get("providers", overlay)
        for key, spec in incoming.items():
            if key in providers and isinstance(spec, dict):
                merged = dict(providers[key])
                merged.update(spec)
                providers[key] = merged
            else:
                providers[key] = spec
    return providers


def resolve(spec, *path):
    """按 a.b.c 逐层取值，支持数组按顺序取第一个命中的。"""
    for candidate in path:
        if isinstance(candidate, list):
            found = resolve(spec, *candidate)
            if found is not None:
                return found
            continue
        node = spec
        ok = True
        for piece in str(candidate).split("."):
            if isinstance(node, dict) and piece in node:
                node = node[piece]
            elif isinstance(node, list) and piece.isdigit() and int(piece) < len(node):
                node = node[int(piece)]
            else:
                ok = False
                break
        if ok and node is not None:
            return node
    return None


def render_template(node, context, drop_if_empty=()):
    """把 {占位符} 换掉；渲染后为空串的路径按 drop_if_empty 删掉，用来做可选参数。"""
    if isinstance(node, dict):
        out = {}
        for key, value in node.items():
            rendered = render_template(value, context, drop_if_empty)
            if isinstance(rendered, str) and rendered == "" and key in drop_if_empty:
                continue
            out[key] = rendered
        return out
    if isinstance(node, list):
        items = []
        for index, value in enumerate(node):
            rendered = render_template(value, context, drop_if_empty)
            if isinstance(rendered, str) and rendered == "" and index in drop_if_empty:
                continue
            items.append(rendered)
        return items
    if isinstance(node, str):
        def swap(match):
            key = match.group(1)
            value = context.get(key, "")
            return "" if value is None else str(value)

        text = re.sub(r"\{([a-z_][a-z0-9_]*)\}", swap, node)
        return text
    return node


def drop_paths(node, paths):
    """按 a.b.0.c 删掉渲染后仍为空的可选字段。"""
    for path in paths or []:
        pieces = str(path).split(".")
        parents, current = [], node
        ok = True
        for piece in pieces[:-1]:
            parents.append((current, piece))
            if isinstance(current, dict) and piece in current:
                current = current[piece]
            elif isinstance(current, list) and piece.isdigit() and int(piece) < len(current):
                current = current[int(piece)]
            else:
                ok = False
                break
        if not ok:
            continue
        last = pieces[-1]
        if isinstance(current, dict) and current.get(last) == "":
            current.pop(last, None)
        elif isinstance(current, list) and last.isdigit() and int(last) < len(current):
            if current[int(last)] == "":
                current.pop(int(last))


def auth_headers(spec):
    """按 auth 配置生成鉴权头；返回值里同时带上「用了哪个环境变量」便于报错。"""
    auth = spec.get("auth") or {"type": "none"}
    kind = auth.get("type", "none")
    if kind == "none":
        return {}, None, ""
    if kind == "bearer":
        env = auth.get("env", "")
        token = os.environ.get(env, "").strip()
        if not token:
            return None, env, f"环境变量 {env} 没有值"
        return {"Authorization": f"Bearer {token}"}, env, ""
    if kind == "header":
        env = auth.get("env", "")
        token = os.environ.get(env, "").strip()
        if not token:
            return None, env, f"环境变量 {env} 没有值"
        prefix = auth.get("prefix", "")
        return {auth.get("header", "Authorization"): f"{prefix}{token}"}, env, ""
    if kind == "jwt":
        env_ak = auth.get("env_ak", "")
        env_sk = auth.get("env_sk", "")
        ak = os.environ.get(env_ak, "").strip()
        sk = os.environ.get(env_sk, "").strip()
        if not ak or not sk:
            missing = "、".join(name for name, value in ((env_ak, ak), (env_sk, sk)) if not value)
            return None, f"{env_ak}+{env_sk}", f"环境变量 {missing} 没有值"
        now = int(time.time())
        header = {"alg": "HS256", "typ": "JWT"}
        payload = {"iss": ak, "exp": now + int(auth.get("ttl", 1800)), "nbf": now - 5}

        def encode(part):
            raw = json.dumps(part, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

        signing_input = f"{encode(header)}.{encode(payload)}"
        signature = hmac.new(sk.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256).digest()
        token = f"{signing_input}.{base64.urlsafe_b64encode(signature).rstrip(b'=').decode('ascii')}"
        return {"Authorization": f"Bearer {token}"}, f"{env_ak}+{env_sk}", ""
    return None, "", f"未识别的鉴权方式 {kind}"


# ---------------------------------------------------------------- HTTP

class HttpError(Exception):
    def __init__(self, status, body, url):
        super().__init__(f"HTTP {status}")
        self.status = status
        self.body = body
        self.url = url


def mask(text):
    """日志里不出现密钥：命中疑似密钥的长串一律打码。"""
    if not isinstance(text, str):
        return text
    masked = SECRET_PATTERN.sub("***", text)
    for value in os.environ.values():
        if value and len(value) >= 12 and value in masked:
            masked = masked.replace(value, "***")
    return masked


def _size_text(size):
    """把字节数写成人能读的大小，KB 以下也写得出来。"""
    if size >= 1048576:
        return f"{size / 1048576:.1f}MB"
    if size >= 1024:
        return f"{size / 1024:.0f}KB"
    return f"{size}字节"


def http_json(method, url, headers, payload=None, timeout=60, retries=3, sleep=2.0):
    """发 JSON 请求并解析响应。429/5xx 退避重试，其余错误直接抛，不吞掉。"""
    data = None
    request_headers = dict(headers or {})
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")
    last_error = None
    for attempt in range(retries + 1):
        request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read().decode("utf-8", "replace")
                return json.loads(body) if body.strip() else {}
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", "replace")
            if error.code in (429, 500, 502, 503, 504) and attempt < retries:
                last_error = HttpError(error.code, body, url)
                time.sleep(sleep * (attempt + 1))
                continue
            raise HttpError(error.code, body, url) from error
        except (urllib.error.URLError, TimeoutError, ssl.SSLError) as error:
            if attempt < retries:
                last_error = error
                time.sleep(sleep * (attempt + 1))
                continue
            raise
    raise last_error


def http_download(url, dest, headers, timeout=300):
    """下载成片。部分平台的下载地址也要带鉴权头，所以把同一套头透传过去。"""
    request = urllib.request.Request(url, headers=headers or {}, method="GET")
    os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
    with urllib.request.urlopen(request, timeout=timeout) as response, open(dest, "wb") as handle:
        while True:
            chunk = response.read(1 << 16)
            if not chunk:
                break
            handle.write(chunk)
    return os.path.getsize(dest)


# ---------------------------------------------------------------- 镜头与上下文

def load_shots(path, sheet, header_row, mapping):
    headers, body = sheetio.read_table(path, sheet=sheet, header_row=header_row)
    if mapping:
        headers = [mapping.get(sheetio.norm_key(header), header) for header in headers]
    columns = sheetio.column_map(headers, SHOT_FIELDS)
    for required in ("asset_name", "shot_index", "visual_prompt"):
        if required not in columns:
            raise ValueError(f"分镜表缺少 {required} 列，先跑 video_brief.py 生成分镜表再回来")
    shots = []
    for index, raw in enumerate(body, start=2):
        def cell(field):
            position = columns.get(field)
            if position is None or position >= len(raw):
                return ""
            return clean_text(raw[position])

        shot_index = sheetio.to_int(cell("shot_index"))
        if shot_index is None:
            continue
        shots.append({
            "row": index,
            "asset_name": cell("asset_name"), "sku": cell("sku"), "product_name": cell("product_name"),
            "site": cell("site"), "language": cell("language"), "ratio": cell("ratio"),
            "duration_s": to_number(cell("duration_s")), "hook_name": cell("hook_name"),
            "shot_index": shot_index, "timecode": cell("timecode"),
            "shot_seconds": to_number(cell("shot_seconds")), "shot_type": cell("shot_type"),
            "visual_prompt": cell("visual_prompt"), "caption": cell("caption"),
            "voiceover": cell("voiceover"), "retention_note": cell("retention_note"),
            "first_frame": cell("first_frame") or cell("first_frame_path"),
        })
    return shots


def pick_shots(shots, assets, index_list, shot_types):
    wanted_assets = {piece.strip() for piece in assets if piece.strip()}
    wanted_shots = set(index_list)
    wanted_types = {piece.strip() for piece in shot_types if piece.strip()}
    picked = []
    for shot in shots:
        if wanted_assets and shot["asset_name"] not in wanted_assets:
            continue
        if wanted_shots and shot["shot_index"] not in wanted_shots:
            continue
        if wanted_types and shot["shot_type"] not in wanted_types:
            continue
        picked.append(shot)
    return picked


def find_first_frame(shot, directory):
    """按顺序找这个镜头的首帧图：分镜表里写的地址 → 目录下「素材名_镜头号」→ 目录下「素材名」。

    返回 (来源, 取值, 说明)：
      url  —— 取值是可直接下发给平台的地址（http(s) 或 data: 内联）
      file —— 取值是本地图片路径，交给 first_frame_for 转成内联
      none —— 没找到，取值是空串；说明里写原因（没写原因就是压根没配首帧图）
    """
    inline = (shot.get("first_frame") or "").strip()
    if inline:
        if inline.startswith(("http://", "https://", "data:")):
            return "url", inline, ""
        if os.path.exists(inline):
            return "file", inline, ""
        return "none", "", f"分镜表里写的首帧图不存在：{inline}"
    if not directory:
        return "none", "", ""
    if not os.path.isdir(directory):
        return "none", "", f"首帧目录不存在：{directory}"
    for stem in (f"{shot['asset_name']}_{shot['shot_index']}", shot["asset_name"]):
        for ext in (".png", ".jpg", ".jpeg", ".webp"):
            path = os.path.join(directory, stem + ext)
            if os.path.exists(path):
                return "file", path, ""
    return "none", "", ""


def as_data_uri(path, max_bytes):
    size = os.path.getsize(path)
    if size > max_bytes:
        return "", (f"首帧图 {os.path.basename(path)} 有 {_size_text(size)}，"
                    f"超过上限 {_size_text(max_bytes)}")
    mime = mimetypes.guess_type(path)[0] or "image/png"
    with open(path, "rb") as handle:
        payload = base64.b64encode(handle.read()).decode("ascii")
    return f"data:{mime};base64,{payload}", ""


def fetch_image_bytes(url, max_bytes, timeout):
    """可灵图生视频这类平台只收纯 base64，而首帧图给的是网络地址时，先取回来。"""
    request = urllib.request.Request(url, headers={"User-Agent": "ecom-video-creative/0.1"},
                                     method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise ValueError(f"图片超过 {_size_text(max_bytes)} 上限")
    return raw


def first_frame_for(shot, directory, max_bytes, need_b64=False, timeout=60):
    """把一个镜头的首帧图准备成平台能用的形式，返回 (下发地址, 纯 base64, 说明)。

    - 网络地址：原样下发；平台只收 base64 时顺手取回来转码
    - 本地图片：转成内联 data URI，同时切出纯 base64
    - 找不到 / 图太大：两个值都为空，说明里写清原因，交给上层记 flag
    """
    kind, found, note = find_first_frame(shot, directory)
    if kind == "url":
        if found.startswith("data:"):
            return found, found.split(",", 1)[1], ""
        if need_b64:
            try:
                raw = fetch_image_bytes(found, max_bytes, timeout)
            except Exception as error:
                return found, "", f"首帧图是网络地址，取回转 base64 失败：{mask(str(error))[:120]}"
            return found, base64.b64encode(raw).decode("ascii"), ""
        return found, "", ""
    if kind == "file":
        uri, problem = as_data_uri(found, max_bytes)
        if problem:
            return "", "", problem
        return uri, uri.split(",", 1)[1], ""
    return "", "", note


def build_context(shot, provider, model, duration, first_frame_uri, first_frame_b64, seed, prompt):
    ratio = shot.get("ratio") or "9:16"
    ratio_map = provider.get("ratio_map") or {}
    return {
        "prompt": prompt,
        "model": model,
        "model_owner": model.split("/")[0] if "/" in model else model,
        "model_name": model.split("/", 1)[1] if "/" in model else model,
        "ratio": ratio,
        "size": ratio_map.get(ratio, ratio),
        "duration": duration,
        "seed": seed if seed is not None else "",
        "first_frame": first_frame_uri,
        "first_frame_url": first_frame_uri,
        "first_frame_base64": first_frame_b64,
        "asset_name": shot.get("asset_name", ""),
        "shot_index": shot.get("shot_index", ""),
        "shot_type": shot.get("shot_type", ""),
        "sku": shot.get("sku", ""),
        "site": shot.get("site", ""),
        "language": shot.get("language", ""),
        "caption": shot.get("caption", ""),
        "voiceover": shot.get("voiceover", ""),
    }


def compose_prompt(shot, extra, suffix):
    """模型提示词 = 分镜的画面描述（+ 可选补充）；带字幕时把字幕作为画面上屏文字要求写进去。"""
    parts = [shot.get("visual_prompt", "")]
    if extra:
        parts.append(extra)
    caption = (shot.get("caption") or "").strip()
    if caption and "{caption}" not in parts[0]:
        parts.append(f"画面上屏字幕（{shot.get('language') or '目标语种'}）：{caption}")
    if suffix:
        parts.append(suffix)
    return "\n".join(piece for piece in parts if piece).strip()


def build_request(provider, context, headers):
    create = provider.get("create") or {}
    body = render_template(create.get("body") or {}, context)
    drop_paths(body, create.get("drop_if_empty"))
    url = render_template(create.get("url", ""), context)
    request_headers = dict(create.get("headers") or {})
    request_headers.update(headers or {})
    if provider.get("api_version"):
        request_headers.setdefault("X-Runway-Version", provider["api_version"])
    return create.get("method", "POST"), url, request_headers, body


# ---------------------------------------------------------------- 提交 / 轮询 / 下载

def is_ok(provider, state):
    values = provider.get("ok_values") or []
    return any(str(state).lower() == str(value).lower() for value in values)


def is_failed(provider, state):
    values = provider.get("fail_values") or []
    return any(str(state).lower() == str(value).lower() for value in values)


def submit(provider, context, headers, timeout):
    method, url, request_headers, body = build_request(provider, context, headers)
    response = http_json(method, url, request_headers, body, timeout=timeout)
    task_id = resolve(response, provider.get("task_id_path") or ["id"])
    poll_url = ""
    if provider.get("poll_url_path"):
        poll_url = resolve(response, provider["poll_url_path"]) or ""
    result_url = ""
    if provider.get("result_url_path"):
        result_url = resolve(response, provider["result_url_path"]) or ""
    return {"task_id": task_id, "poll_url": poll_url, "result_url": result_url, "raw": response}


def poll_once(provider, job, headers, timeout):
    poll = provider.get("poll") or {}
    # 兜底轮询地址：平台没返回现成地址时，用配置里的模板拼（模型名在 context 里，不在 job 顶层）
    url = job.get("poll_url") or render_template(
        poll.get("url", ""),
        {"task_id": job.get("task_id") or "", "model": job.get("context", {}).get("model", "")})
    request_headers = dict(poll.get("headers") or {})
    request_headers.update(headers or {})
    response = http_json(poll.get("method", "GET"), url, request_headers, timeout=timeout)
    state = resolve(response, provider.get("status_path") or ["status"])
    video = resolve(response, provider.get("video_path") or [])
    failure = resolve(response, provider.get("error_path") or [])
    return state, video, failure, response


def download_asset(provider, job, video_ref, headers, dest_dir, stem, timeout):
    """把成片取回本地。各平台的取件方式不同，这里集中处理。"""
    mode = provider.get("download", "url")
    if mode == "openai_content":
        url = f"https://api.openai.com/v1/videos/{job['task_id']}/content"
        dest = os.path.join(dest_dir, f"{stem}.mp4")
        size = http_download(url, dest, headers, timeout=timeout)
        return dest, url, size
    if mode == "minimax_file":
        file_id = video_ref if isinstance(video_ref, str) else str(video_ref)
        query = f"https://api.minimaxi.com/v1/files/retrieve?file_id={urllib.parse.quote(file_id)}"
        info = http_json("GET", query, headers, timeout=timeout)
        url = resolve(info, "file.file_url", "file.download_url", "file_url") or ""
        if not url:
            raise ValueError(f"没有从 MiniMax 取到下载地址：{json.dumps(info, ensure_ascii=False)[:200]}")
        dest = os.path.join(dest_dir, f"{stem}.mp4")
        size = http_download(url, dest, headers, timeout=timeout)
        return dest, url, size
    if not video_ref:
        raise ValueError("平台返回里没有找到成片地址，检查 providers.json 的 video_path")
    url = video_ref if isinstance(video_ref, str) else str(video_ref)
    if url.startswith("data:"):
        raw = base64.b64decode(url.split(",", 1)[1])
        dest = os.path.join(dest_dir, f"{stem}.mp4")
        os.makedirs(dest_dir, exist_ok=True)
        with open(dest, "wb") as handle:
            handle.write(raw)
        return dest, "（内联返回）", len(raw)
    dest = os.path.join(dest_dir, f"{stem}.mp4")
    size = http_download(url, dest, headers, timeout=timeout)
    return dest, url, size


# ---------------------------------------------------------------- 离线演示

def mock_submit(context):
    return {"task_id": f"mock-{abs(hash(context['asset_name'] + str(context['shot_index']))) % 100000:05d}",
            "raw": {"id": "mock"}}


def mock_poll(job, ticks):
    """前两次返回排队中，第三次完成，用来验证轮询逻辑真的会等。"""
    job["ticks"] = job.get("ticks", 0) + 1
    if job["ticks"] < 3:
        return "queued" if job["ticks"] == 1 else "running"
    return "succeeded"


def mock_download(dest_dir, stem, context):
    """离线演示不产出视频：写一份说明文件，明确标注这不是真实素材。"""
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, f"{stem}.mock.txt")
    with open(dest, "w", encoding="utf-8") as handle:
        handle.write(
            "这是 ecom-video-creative 的离线演示产物，不是视频文件。\n"
            "用途：验证「提交 → 轮询 → 下载 → 记台账」这条链路本身是通的。\n"
            f"素材名：{context['asset_name']}    镜头：{context['shot_index']}\n"
            f"假如真跑，发给模型的提示词是：\n{context['prompt']}\n")
    return dest, "（mock）", os.path.getsize(dest)


# ---------------------------------------------------------------- 主流程

def _width(text):
    """中文、日文、韩文按两个字符宽算，用来对齐命令行表格。"""
    return sum(2 if unicodedata.east_asian_width(char) in "WF" else 1 for char in str(text))


def _pad(text, width):
    text = str(text)
    return text + " " * max(width - _width(text), 1)


def cmd_list_providers(providers, stream):
    stream.write(f"{_pad('平台 id', 12)}{_pad('名称', 40)}{_pad('能力', 24)}鉴权环境变量\n")
    stream.write("-" * 104 + "\n")
    for key in sorted(providers):
        provider = providers[key]
        auth = provider.get("auth") or {"type": "none"}
        if auth.get("type") == "jwt":
            env = f"{auth.get('env_ak', '')} + {auth.get('env_sk', '')}"
        elif auth.get("env"):
            env = auth["env"]
        else:
            env = "不需要"
        stream.write(f"{_pad(key, 12)}{_pad(provider.get('label', ''), 40)}"
                     f"{_pad('/'.join(provider.get('capabilities') or ['-']), 24)}{env}\n")
        if provider.get("note"):
            stream.write(f"{_pad('', 12)}└ {provider['note']}\n")
    stream.write("\n默认模型：\n")
    for key in sorted(providers):
        provider = providers[key]
        stream.write(f"  {_pad(key, 12)}{_pad(provider.get('default_model', '-'), 30)}"
                     f"可选：{'、'.join(provider.get('models') or [])}\n")
    stream.write("\n正式投产前先用 --check 验凭据、用 --print-request 看请求体，"
                 "再对照各平台文档核对参数名；不对就改 providers.json，或用 --provider-file 覆盖。\n")


def cmd_check(provider, key, headers, timeout):
    """只验凭据，不生成。拿轮询接口敲一下：401/403 说明 Key 不对，其它状态说明凭据有效。"""
    if provider.get("engine") == "mock":
        return True, "mock 平台不需要凭据"
    if headers is None:
        return False, f"缺少鉴权环境变量（{key}）"
    poll = provider.get("poll") or {}
    url = render_template(poll.get("url", ""), {"task_id": "check-0000", "model": provider.get("default_model", "")})
    headers = dict(poll.get("headers") or {})
    headers.update(auth_headers(provider)[0] or {})
    try:
        http_json(poll.get("method", "GET"), url, headers, timeout=timeout, retries=0)
        return True, "凭据有效（接口正常响应）"
    except HttpError as error:
        if error.status in (401, 403):
            return False, f"凭据被拒（HTTP {error.status}）：{mask(error.body)[:160]}"
        if error.status in (404, 400):
            return True, f"凭据有效（探测请求返回 HTTP {error.status}，属于预期）"
        return False, f"接口返回异常 HTTP {error.status}：{mask(error.body)[:160]}"
    except Exception as error:  # 网络问题不算凭据问题
        return False, f"请求失败：{mask(str(error))[:200]}"


def load_previous(out_path):
    """读上一次的台账，用于断点续跑：已成功且文件还在的镜头不重复提交。"""
    if not out_path or not os.path.exists(out_path):
        return {}
    try:
        with open(out_path, encoding="utf-8-sig") as handle:
            import csv
            done = {}
            for row in csv.DictReader(handle):
                if row.get("状态") == "ok" and row.get("本地路径") and os.path.exists(row["本地路径"]):
                    done[f"{row.get('素材名')}|{row.get('镜头')}"] = row
            return done
    except (OSError, ValueError):
        return {}


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="把分镜表的生成提示词接到视频生成平台，产出真实投流素材并记台账")
    parser.add_argument("input", nargs="?", help="分镜表：video_brief.py 产出的 storyboard.csv")
    parser.add_argument("--list-providers", action="store_true", help="列出所有平台、能力与所需环境变量")
    parser.add_argument("--provider", default="mock", help="平台 id，默认 mock（离线演示，不联网）")
    parser.add_argument("--provider-file", action="append", default=[], metavar="覆盖配置",
                        help="自定义平台配置，可重复传；同名平台按字段覆盖内置配置")
    parser.add_argument("--model", default="", help="模型名，默认取平台的 default_model")
    parser.add_argument("--check", action="store_true", help="只验凭据，不生成")
    parser.add_argument("--assets", default="", help="只跑这些素材名，逗号分隔")
    parser.add_argument("--shots", default="", help="只跑这些镜头号，逗号分隔，如 1,5")
    parser.add_argument("--shot-types", default="", help="只跑这些镜头类型，逗号分隔，如 钩子")
    parser.add_argument("--duration", type=int, default=5,
                        help="单镜头生成秒数，默认 5。视频模型多按固定档位计费，按平台文档指定")
    parser.add_argument("--use-shot-seconds", action="store_true",
                        help="按分镜表的镜头秒数生成（四舍五入，且不会短于 --duration）")
    parser.add_argument("--first-frame-dir", default="", help="首帧图目录：找 素材名_镜头号.png / 素材名.png")
    parser.add_argument("--max-image-mb", type=float, default=8.0, help="首帧图体积上限，默认 8MB")
    parser.add_argument("--prompt-extra", default="", help="追加到每条提示词后面的全局要求")
    parser.add_argument("--prompt-suffix", default="", help="追加到每条提示词末尾的通用约束")
    parser.add_argument("--seed", type=int, default=None, help="随机种子，部分平台支持")
    parser.add_argument("--max-clips", type=int, default=10,
                        help="本次最多生成几个镜头，默认 10。这是花钱的硬上限，调大请谨慎")
    parser.add_argument("--confirm", action="store_true",
                        help="真正提交任务。不加这个参数只试跑，一个请求都不发")
    parser.add_argument("--print-request", action="store_true", help="打印将要发出的请求体（已打码）")
    parser.add_argument("--outdir", default="renders", help="成片保存目录，默认 renders")
    parser.add_argument("--overwrite", action="store_true", help="忽略已有台账，全部重新生成")
    parser.add_argument("--continue-on-error", action="store_true", help="单个镜头失败不中断整批")
    parser.add_argument("--poll-interval", type=float, default=10.0, help="轮询间隔秒数，默认 10")
    parser.add_argument("--poll-timeout", type=float, default=900.0, help="单镜头等待上限秒数，默认 900")
    parser.add_argument("--http-timeout", type=float, default=60.0, help="单次 HTTP 超时秒数")
    parser.add_argument("--out", default=None, help="台账 CSV")
    parser.add_argument("--out-xlsx", default=None, help="台账 Excel 工作簿")
    parser.add_argument("--out-json", default=None, help="输出信封 JSON")
    parser.add_argument("--quarantine", default=None, help="未生成的镜头清单 CSV")
    parser.add_argument("--map", action="append", default=[], metavar="原列名=标准字段")
    parser.add_argument("--sheet", default=1, help="分镜表工作表序号或名称，默认第 1 个")
    parser.add_argument("--header-row", type=int, default=1, help="分镜表表头行号")
    args = parser.parse_args(argv)

    try:
        providers = load_providers(args.provider_file)
    except ValueError as error:
        sheetio.emit(sheetio.make_envelope("video_render", "blocked", 0.0, {"error": str(error)},
                                           [sheetio.flag("high", "provider_config_error", str(error),
                                                         "检查 --provider-file 指向的 JSON")]),
                     out_json=args.out_json)
        return 2

    if args.list_providers:
        cmd_list_providers(providers, sys.stdout)
        return 0

    if not args.input:
        sheetio.emit(sheetio.make_envelope("video_render", "blocked", 0.0, {"error": "缺少分镜表"},
                                           [sheetio.flag("high", "input_error", "没有传分镜表",
                                                         "先跑 video_brief.py 生成 storyboard.csv，"
                                                         "或用 --list-providers 看支持的平台")]),
                     out_json=args.out_json)
        return 2

    provider = providers.get(args.provider)
    if not provider:
        sheetio.emit(sheetio.make_envelope(
            "video_render", "blocked", 0.0, {"error": f"未知平台 {args.provider}"},
            [sheetio.flag("high", "unknown_provider", f"平台配置里没有 {args.provider}",
                          "用 --list-providers 看可用平台，或在 providers.json 里加一个")]),
            out_json=args.out_json)
        return 2

    model = args.model or provider.get("default_model", "")
    headers, key_source, key_problem = auth_headers(provider)
    flags = []

    if provider.get("engine", "http") != "mock" and not (provider.get("ok_values") or []):
        sheetio.emit(sheetio.make_envelope(
            "video_render", "blocked", 0.0, {"error": f"{args.provider} 缺少完成状态配置"},
            [sheetio.flag("high", "provider_config_incomplete",
                          f"平台 {args.provider} 没配 ok_values，脚本无法判断任务什么时候算完成",
                          "在 providers.json 里给这个平台补上 status_path / ok_values / fail_values，"
                          "参照同类型平台的写法")]),
            out_json=args.out_json)
        return 2

    if args.check:
        ok, message = cmd_check(provider, key_source, headers, args.http_timeout)
        level = "low" if ok else "high"
        flags.append(sheetio.flag(level, "credential_check", message,
                                  "确认环境变量已导出到当前 shell（export ARK_API_KEY=...）"))
        sheetio.emit(sheetio.make_envelope("video_render", "ok" if ok else "blocked",
                                           0.9 if ok else 0.0,
                                           {"provider": args.provider, "model": model,
                                            "auth_source": key_source, "check": ok},
                                           flags), out_json=args.out_json)
        return 0 if ok else 2

    try:
        shots = load_shots(args.input, args.sheet, args.header_row, sheetio.apply_mapping(args.map))
    except (OSError, ValueError) as error:
        sheetio.emit(sheetio.make_envelope("video_render", "blocked", 0.0, {"error": str(error)},
                                           [sheetio.flag("high", "input_error", str(error),
                                                         "确认分镜表路径与列名")]),
                     out_json=args.out_json)
        return 2

    def split(value):
        return [piece.strip() for piece in str(value).replace("，", ",").split(",") if piece.strip()]

    index_list = []
    for piece in split(args.shots):
        number = sheetio.to_int(piece)
        if number is not None:
            index_list.append(number)
    picked = pick_shots(shots, split(args.assets), index_list, split(args.shot_types))

    if not picked:
        flags.append(sheetio.flag("high", "no_shot_selected",
                                  f"分镜表里有 {len(shots)} 个镜头，但筛选条件没选中任何一个",
                                  "检查 --assets / --shots / --shot-types 是否写对"))
        sheetio.emit(sheetio.make_envelope("video_render", "blocked", 0.0,
                                           {"shots_in_file": len(shots), "selected": 0}, flags),
                     out_json=args.out_json)
        return 2

    if len(picked) > args.max_clips:
        flags.append(sheetio.flag("medium", "clip_cap_applied",
                                  f"选中 {len(picked)} 个镜头，按 --max-clips {args.max_clips} 截断",
                                  "要全部生成就调大 --max-clips；视频生成按条计费，先小批验证"))
        picked = picked[:args.max_clips]

    if not args.use_shot_seconds:
        wanted = sorted({int(round(shot["shot_seconds"])) for shot in picked if shot.get("shot_seconds")})
        if wanted and wanted != [args.duration]:
            flags.append(sheetio.flag("low", "shot_seconds_ignored",
                                      f"分镜表这几个镜头标的是 {'、'.join(str(value) for value in wanted)} 秒，"
                                      f"本次统一按 {args.duration} 秒生成",
                                      "要按分镜的秒数出片就加 --use-shot-seconds"
                                      "（它只取更大的那个值，不会短于 --duration）"))

    engine = provider.get("engine", "http")
    if engine != "mock" and headers is None:
        flags.insert(0, sheetio.flag("high", "credential_missing", key_problem,
                                     f"把 Key 导出到环境变量后重跑：export {key_source.split('+')[0]}=你的Key"))

    needs_b64 = "{first_frame_base64}" in json.dumps(provider.get("create") or {}, ensure_ascii=False)
    needs_frame = bool(provider.get("requires_first_frame"))
    if needs_frame and not args.first_frame_dir and not any(s.get("first_frame") for s in picked):
        flags.append(sheetio.flag("high", "first_frame_required",
                                  f"平台 {args.provider} 是图生视频，但没找到首帧图",
                                  "用 --first-frame-dir 指定首帧图目录，或改用支持文生视频的平台"))
    if provider.get("capabilities") and "image2video" not in provider["capabilities"]:
        if args.first_frame_dir:
            flags.append(sheetio.flag("medium", "first_frame_ignored",
                                      f"平台 {args.provider} 只支持文生视频，首帧图不会被使用",
                                      "要按首帧出片就换 kling-i2v / runway / luma 这类平台"))

    already = {} if args.overwrite else load_previous(args.out)
    if already:
        flags.append(sheetio.flag("low", "resume_from_ledger",
                                  f"上次台账里有 {len(already)} 个镜头已成功，本次跳过不重复生成",
                                  "要重新生成就加 --overwrite"))

    dry_run = not args.confirm
    if dry_run:
        flags.append(sheetio.flag("medium", "dry_run",
                                  f"试跑模式：选中 {len(picked)} 个镜头，未发出任何请求",
                                  "确认提示词与参数无误后加 --confirm 真正提交；生成按条计费，脚本无法替你核对单价"))

    records = []
    submit_plan = []
    frame_notes = []
    for shot in picked:
        stem = f"{shot['asset_name']}_{shot['shot_index']}"
        if stem in already:
            records.append({**already[stem], "状态": "ok", "_skip": True})
            continue
        prompt = compose_prompt(shot, args.prompt_extra, args.prompt_suffix)
        first_uri, first_b64, frame_note = first_frame_for(
            shot, args.first_frame_dir, int(args.max_image_mb * 1048576),
            need_b64=needs_b64, timeout=args.http_timeout)
        if not first_uri and not frame_note and args.first_frame_dir:
            frame_note = (f"首帧目录里没有 {shot['asset_name']}_{shot['shot_index']}.png，"
                          f"也没有 {shot['asset_name']}.png")
        if frame_note:
            frame_notes.append(f"{stem}：{frame_note}")
        duration = args.duration
        if args.use_shot_seconds and shot.get("shot_seconds"):
            duration = max(int(round(shot["shot_seconds"] + 0.5)), args.duration)
        context = build_context(shot, provider, model, duration, first_uri, first_b64, args.seed, prompt)
        job = {"shot": shot, "stem": stem, "context": context,
               "task_id": "", "submit_at": "", "done_at": "", "tries": 0}
        submit_plan.append(job)

    if frame_notes:
        shown = "；".join(frame_notes[:5])
        rest = f"（另有 {len(frame_notes) - 5} 个镜头同样没找到）" if len(frame_notes) > 5 else ""
        flags.append(sheetio.flag("medium", "first_frame_missing", f"{shown}{rest}",
                                  "文件名按「素材名_镜头号.png」放，或用 --first-frame-dir 指定目录"))
    if needs_b64 and any(not job["context"]["first_frame_base64"] for job in submit_plan):
        if not any(flag["level"] == "high" and flag["type"].startswith("first_frame") for flag in flags):
            flags.append(sheetio.flag("high", "first_frame_base64_missing",
                                      f"平台 {args.provider} 的首帧图只收纯 base64，但这次没能备好图",
                                      "把图片放本地并让 --first-frame-dir 指过去；"
                                      "图太大就压到 --max-image-mb 以内"))

    if args.print_request and submit_plan:
        method, url, request_headers, body = build_request(provider, submit_plan[0]["context"], headers or {})
        safe_headers = {name: ("***" if name.lower() in ("authorization", "x-goog-api-key") else value)
                        for name, value in request_headers.items()}
        safe_headers["Authorization"] = "***" if "Authorization" in request_headers else safe_headers.get("Authorization", "")
        sys.stdout.write(f"将发出的请求（以第一条为例，共 {len(submit_plan)} 条）：\n")
        sys.stdout.write(f"{method} {url}\n")
        for name, value in safe_headers.items():
            if value:
                sys.stdout.write(f"  {name}: {value if name != 'Authorization' else '***'}\n")
        sys.stdout.write(json.dumps(body, ensure_ascii=False, indent=2)[:4000] + "\n\n")

    if dry_run:
        for job in submit_plan:
            records.append(_record(job, args, provider, model, "skipped",
                                   "试跑未提交", "", "", "", 0))
    else:
        for job in submit_plan:
            shot = job["shot"]
            try:
                if engine == "mock":
                    job.update(mock_submit(job["context"]))
                else:
                    result = submit(provider, job["context"], headers, args.http_timeout)
                    job["task_id"] = result["task_id"] or ""
                    job["poll_url"] = result["poll_url"]
                    job["result_url"] = result["result_url"]
                    if not job["task_id"] and not job.get("poll_url"):
                        raise ValueError("提交成功但没解析到任务 id，检查 providers.json 的 task_id_path")
                job["submit_at"] = _now()
            except HttpError as error:
                flags.append(sheetio.flag("high", "submit_failed",
                                          f"{job['stem']} 提交失败 HTTP {error.status}：{mask(error.body)[:200]}",
                                          "先 --check 验凭据；参数名不对就改 providers.json"))
                records.append(_record(job, args, provider, model, "failed",
                                       f"提交失败 HTTP {error.status}", "", "", "", 0))
                if not args.continue_on_error:
                    break
            except Exception as error:
                flags.append(sheetio.flag("high", "submit_failed",
                                          f"{job['stem']} 提交失败：{mask(str(error))[:200]}",
                                          "检查网络与 providers.json 配置"))
                records.append(_record(job, args, provider, model, "failed",
                                       f"提交失败 {type(error).__name__}", "", "", "", 0))
                if not args.continue_on_error:
                    break

        pending = [job for job in submit_plan if job.get("submit_at")]
        started = {job["stem"]: time.time() for job in pending}
        while pending:
            still = []
            for job in pending:
                waited = time.time() - started[job["stem"]]
                if waited > args.poll_timeout:
                    flags.append(sheetio.flag("high", "poll_timeout",
                                              f"{job['stem']} 等待超过 {args.poll_timeout:.0f} 秒仍未完成",
                                              "到平台后台按任务 id 查结果；超时未必等于失败，别急着重跑"))
                    records.append(_record(job, args, provider, model, "timeout",
                                           "轮询超时", "", job.get("task_id", ""), "", 0))
                    continue
                try:
                    if engine == "mock":
                        state, video, failure = mock_poll(job, []), "", ""
                    else:
                        state, video, failure, _ = poll_once(provider, job, headers, args.http_timeout)
                except HttpError as error:
                    job["tries"] = job.get("tries", 0) + 1
                    if job["tries"] > 3:
                        flags.append(sheetio.flag("high", "poll_failed",
                                                  f"{job['stem']} 查询失败 HTTP {error.status}",
                                                  "检查任务 id 与网络，稍后重试"))
                        records.append(_record(job, args, provider, model, "failed",
                                               f"查询失败 HTTP {error.status}", "", job.get("task_id", ""), "", 0))
                        continue
                    still.append(job)
                    continue
                if is_failed(provider, state) or failure:
                    detail = (f"平台返回 {state}" if is_failed(provider, state)
                              else f"平台报错：{mask(str(failure))[:160]}")
                    records.append(_record(job, args, provider, model, "failed",
                                           detail, "", job.get("task_id", ""), "", 0))
                    flags.append(sheetio.flag("high", "render_failed",
                                              f"{job['stem']} 生成失败：{detail}",
                                              "多半是提示词命中审核或参数不合法，按平台报错改提示词"))
                    continue
                if not is_ok(provider, state):
                    still.append(job)
                    continue
                try:
                    if engine == "mock":
                        dest, url, _ = mock_download(args.outdir, job["stem"], job["context"])
                    else:
                        dest, url, _ = download_asset(provider, job, video, headers,
                                                      args.outdir, job["stem"], args.http_timeout)
                    elapsed = round(time.time() - started[job["stem"]], 1)
                    records.append(_record(job, args, provider, model, "ok", "", dest, url,
                                           job.get("task_id", ""), elapsed))
                except Exception as error:
                    flags.append(sheetio.flag("high", "download_failed",
                                              f"{job['stem']} 已生成但下载失败：{mask(str(error))[:200]}",
                                              "任务已完成，到平台后台直接下载，别重复提交"))
                    records.append(_record(job, args, provider, model, "download_failed",
                                           f"下载失败 {type(error).__name__}", "", job.get("task_id", ""), "", 0))
                job["done_at"] = _now()
            if not still:
                break
            pending = still
            if engine == "mock":
                continue
            time.sleep(args.poll_interval)

    ok_count = sum(1 for item in records if item.get("状态") == "ok" and not item.get("_skip"))
    skipped = sum(1 for item in records if item.get("_skip"))
    failed = sum(1 for item in records if item.get("状态") not in ("ok", "skipped"))
    for item in records:
        item.pop("_skip", None)

    if failed:
        flags.append(sheetio.flag("high", "clips_failed",
                                  f"{failed} 个镜头没跑成（成功 {ok_count}，跳过 {skipped}）",
                                  "看台账「失败原因」列逐个处理；已成功的不受影响"))
    levels = {item["level"] for item in flags}
    confidence = 0.95
    if "high" in levels:
        confidence = 0.4
    elif "medium" in levels:
        confidence = 0.75

    status = "blocked" if (headers is None and engine != "mock") else ("partial" if flags else "ok")
    if dry_run:
        status = "partial"

    products = {
        "provider": args.provider, "provider_label": provider.get("label", ""),
        "model": model, "engine": engine, "dry_run": dry_run,
        "auth_source": key_source, "selected": len(picked), "submitted": len(submit_plan),
        "outdir": args.outdir,
        "cost_notice": "生成按条计费，脚本不掌握各平台实时单价，请自行确认单价后再放开 --max-clips",
    }
    if args.out:
        sheetio.write_csv(args.out, MANIFEST_HEADERS,
                          [[item.get(header, "") for header in MANIFEST_HEADERS]
                           for item in sorted(records, key=lambda r: (str(r.get("素材名")), r.get("镜头") or 0))])
    if args.out_xlsx:
        by_status = {}
        for item in records:
            row = [item.get(header, "") for header in MANIFEST_HEADERS]
            by_status.setdefault(item.get("状态", ""), []).append(row)
        sheets = [{"name": "生成台账", "headers": MANIFEST_HEADERS,
                   "rows": [[item.get(header, "") for header in MANIFEST_HEADERS] for item in records],
                   "highlights": [{"ref": f"{sheetio.col_letter(MANIFEST_HEADERS.index('失败原因') + 1)}{index + 2}",
                                   "level": "alert"}
                                  for index, item in enumerate(records) if item.get("状态") not in ("ok", "skipped")],
                   "column_widths": {13: 40, 15: 34, 20: 40}}]
        for name, rows in sorted(by_status.items()):
            if name:
                sheets.append({"name": f"状态-{name}"[:28], "headers": MANIFEST_HEADERS, "rows": rows})
        sheetio.write_xlsx(args.out_xlsx, sheets)
    if args.quarantine:
        bad = [item for item in records if item.get("状态") not in ("ok", "skipped")]
        sheetio.write_csv(args.quarantine,
                          ["素材名", "镜头", "状态", "失败原因", "任务ID", "提示词"],
                          [[item.get("素材名", ""), item.get("镜头", ""), item.get("状态", ""),
                            item.get("失败原因", ""), item.get("任务ID", ""),
                            next((job["context"]["prompt"] for job in submit_plan
                                  if job["stem"] == f"{item.get('素材名')}_{item.get('镜头')}"), "")]
                           for item in bad])

    sheetio.emit(sheetio.make_envelope("video_render", status, confidence, products, flags,
                                       sources=[{"ref": args.input + "（分镜表）", "as_of": ""},
                                                {"ref": f"providers.json · {args.provider}", "as_of": "2026-09-14"}],
                                       assumptions=[
                                           f"平台参数取自 providers.json 的 {args.provider} 配置，"
                                           "参数名以该平台最新文档为准，不对就改配置",
                                           f"单镜头时长 {args.duration} 秒；视频模型多按固定档位计费",
                                           "提示词来自分镜表 visual_prompt，脚本不改写创意内容",
                                       ]),
                 out_json=args.out_json)

    if not dry_run:
        sys.stderr.write(f"平台 {args.provider}（{model}）：成功 {ok_count}、跳过 {skipped}、失败 {failed}\n")
        if args.outdir:
            sys.stderr.write(f"成片目录：{os.path.abspath(args.outdir)}\n")
    else:
        sys.stderr.write(f"试跑：选中 {len(picked)} 个镜头，未发出任何请求。"
                         f"确认无误后加 --confirm 真正生成（生成会花钱）\n")
    return 0 if not failed else 1


def _now():
    import datetime
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def _record(job, args, provider, model, state, reason, dest, url, task_id, elapsed):
    shot = job["shot"]
    label = {"ok": "ok", "failed": "failed", "timeout": "timeout",
             "download_failed": "download_failed", "skipped": "skipped"}.get(state, state)
    return {
        "素材名": shot.get("asset_name", ""), "SKU": shot.get("sku", ""),
        "市场": shot.get("site", ""), "语种": shot.get("language", ""),
        "镜头": shot.get("shot_index", ""), "时段": shot.get("timecode", ""),
        "时长(秒)": job["context"].get("duration", ""),
        "平台": provider.get("label", ""), "模型": model,
        "比例": shot.get("ratio", ""), "任务ID": task_id or job.get("task_id", ""),
        "状态": label, "文件": os.path.basename(dest) if dest else "",
        "本地路径": dest or "", "下载地址": url or "",
        "提交时间": job.get("submit_at", ""), "完成时间": job.get("done_at", "") or _now(),
        "耗时(秒)": elapsed, "重试": job.get("tries", 0), "失败原因": reason,
    }


if __name__ == "__main__":
    sys.exit(main())
