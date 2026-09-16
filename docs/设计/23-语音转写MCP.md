# 23 · 语音转文字（音频附件 → ASR MCP）

> 状态：已实施并端到端验证（本地 faster-whisper large-v3）
> 关联：`12-扩展能力与MCP.md`（MCP 机制）、`13-MinerU与联网搜索MCP.md`（外部服务 + 宿主/容器部署先例）、`18-联网搜索开关.md`（部署级合成 MCP 槽位 `McpSlot`）、`20-OCR识别MCP.md`（同类外部能力槽位）
> 参考实现：`gjsk_wiseagent_ai/mcp_new/src/mcp_voice2text/`（另一平台的 voice2text MCP）

## 23.1 背景与目标

用户上传一段音频，希望平台把它转成文字，然后模型基于文字作答/整理。平台目前**完全没有音频能力**：附件只区分 `image` / `document`，错误信息里连音频扩展名都没列。

目标：

1. 附件支持音频（`kind="audio"`），带类型/大小/魔数校验；
2. 音频经**外部 ASR MCP** 转写为简体中文，转写文本以"附件数据"身份注入本轮对话；
3. MCP 不可用时**降级**（提示转写不可用），不中断生成；
4. 转写结果落成消息块，前端可见。

## 23.2 决策（已确认）

| 事项 | 决策 | 理由 |
|---|---|---|
| ASR 形态 | 封装成 **MCP 服务**，平台作为 **MCP 客户端**调用 | 与 `13`/`20` 一致：ASR 模型独立部署，不塞进 `ModelManager`（单槽位 LLM 管理器，会抢显存、加生命周期负担） |
| **谁调用** | **平台**（`runtime` 在生成前确定性调用），**不把该工具暴露给模型** | 音频是二进制，无法经 function-call 参数传给模型；让模型拿到路径再"决定要不要转写"只会多一次往返且可能传错参。转写的产物是**文本**，模型只需要文本 |
| 输入形态 | 默认 **base64**（`ASR_INPUT_MODE`）；共享卷时可用 `path` | 参考实现用 `storageKey`（对象存储），本项目没有；Whisper 为 3GB 模型跑在**宿主机**，读不到容器内路径，故把字节随请求发出 |
| 失败降级 | 探测/调用失败 → 记 warning，注入"转写不可用"提示，**生成继续** | 与 MinerU 回退同一口径 |
| 转写超时 | 单独用 `ASR_TIMEOUT_S`（默认 300s） | CPU 上 large-v3 单条语音数十秒，MCP 默认 15s 连接超时会把长任务掐死 |
| ASR 引擎 | **仓库自带 MCP 服务 + 本地 faster-whisper**（`mcp_servers/voice_asr/`） | 本机已装 `faster-whisper-large-v3`（HF 缓存，离线可用）；参考项目的 MCP 是调远程 GPUStack 网关的，不适用 |
| 转写文本优先级 | 与文档附件一致：以 **user 角色数据块**注入，并声明"不是指令" | 防提示注入 |
| 结果落库 | 用户消息上追加 `{"type":"transcript", ...}` 块 | 前端可见，且历史可回看 |

## 23.3 与参考实现的关系

参考实现（`mcp_voice2text`）的**工具契约**：

- `transcribe_audio_by_storage_key_tool(storage_keys: list[str]) -> list[dict]`
- `detect_audio_type_tool(sources: list[str]) -> list[dict]`
- `health() -> "ok"`，`FastMCP("voice-asr")` + `streamable-http`，默认端口 10001

**可直接复用**：magic bytes 签名表（含 m4a/aac 的坑）、`OpenCC("t2s")` 繁转简、Whisper 调用与错误处理、批量并行与保序。

**本项目不沿用它**：它是**远程 GPUStack 网关 + 对象存储**的组合；本机没有该网关，也没有对象存储。因此仓库自带一个等价的本地版 MCP（`mcp_servers/voice_asr/`，见 §23.4.2.1），入参改为 base64 / 本地路径。

## 23.4 设计

### 23.4.1 配置（`app/core/config.py`）

| 变量 | 默认 | 说明 |
|---|---|---|
| `ASR_MCP_URL` | 空 | 为空=不支持音频转写。示例：`http://host.docker.internal:10001/mcp`（后端在容器、MCP 在宿主机） |
| `ASR_MCP_TOOL` | 空 | 工具名覆盖；为空时自动选**探测到的名字里含 `transcribe` 的第一个工具** |
| `ASR_INPUT_MODE` | `base64` | `base64`：把音频字节随请求发出（MCP 与平台不同文件系统时用）；`path`：只传路径（要求共享 uploads 卷） |
| `ASR_TIMEOUT_S` | 300 | 转写超时；`mcp_service.call_tool` 默认 15s 会掐死长转写 |
| `ASR_MAX_BYTES` | 20971520 | 单个音频大小上限（20MB） |

### 23.4.2 目标 MCP 契约

```
工具名：transcribe（或任意含 "transcribe" 的名字）
入参  ：{"audios": [{"name": "a.mp3", "data_base64": "<base64 字节>"}]}    # base64 模式（默认）
        或 {"paths": ["/data/uploads/<uuid>.mp3"]}                        # path 模式
返回  ：[{"path": str, "success": bool, "text": str, "error": str|null}]
```

兼容性（客户端侧做，避免 MCP 端二选一）：

- 返回若是 **JSON 字符串** → `json.loads` 后按列表解析（FastMCP 对非字符串返回值通常序列化为 JSON 文本）；
- 返回若只有一段裸文本 → 视为**单文件**转写结果（`paths[0]`）；
- 返回项里若出现 `storage_key` 而非 `path`，也接受（对齐参考实现）；
- base64 模式下 MCP 通常回填**文件名**而非容器路径，客户端按**入参顺序**兜底对齐。

### 23.4.2.1 仓库自带的 MCP 服务（`mcp_servers/voice_asr/`）

| 文件 | 职责 |
|---|---|
| `asr_local.py` | faster-whisper 懒加载单例 + `vad_filter` 去静音 + 繁转简（`opencc` 可选）；`bytes` 统一包成 `BytesIO`——**faster-whisper 不接受裸 bytes**，会报 `no read() method` |
| `server.py` | FastMCP `voice-asr`（streamable-http，`VOICE_PORT` 默认 10001）；工具 `transcribe(audios?, paths?)`、`health()`；`VOICE_MAX_PARALLEL` 控制并发（CPU 上 Whisper 很吃算力） |
| `requirements.txt` | `fastmcp` / `faster-whisper` / `opencc-python-reimplemented` |
| `scripts/start-voice-asr.ps1` | 一键建 venv + 装依赖 + 启动（`-Install` 只装不启，`-Model` 可切小模型先验链路） |

**实测（本机 CPU，8 秒中文语音，含模型加载）**：`large-v3` 32.9s → 识别为「线程池的核心参数包括核心线程数和最大线程数。」（完全正确）；`base` 24.4s。模型从本地 HF 缓存加载，**离线可用**。

### 23.4.3 客户端（新增 `app/ai/asr.py`）

复用 `McpSlot`（`18`/`20` 已建立的部署级槽位：URL → 探测缓存 → 合成绑定），额外提供一个**调用**函数：

```python
async def transcribe(paths: list[str]) -> list[dict]:   # 抛 AsrError 由调用方降级
def is_enabled() -> bool
def reset_cache() -> None
```

- 工具名选择：`settings.asr_mcp_tool` 优先；否则取探测工具里名字含 `transcribe` 的第一个；都没有则抛 `AsrError`。
- 调用走 `mcp_service.call_tool(config, tool_name, {"paths": paths})`。
- 结果解析见 §23.4.2；解析不出内容时抛 `AsrError`，不返回"看似成功"的空结果。

### 23.4.4 附件（`app/core/upload_rules.py` + `api/v1/attachments.py`）

- `AUDIO_EXTS = {"mp3","wav","m4a","mp4","aac","flac","ogg","webm","amr"}`；`AUDIO_MIME_BY_EXT`。
- **魔数校验**（对齐参考实现的签名表）比扩展名可靠，尤其是浏览器录制的 `webm` 常被改名成 `.mp3`。
- 大小上限 `ASR_MAX_BYTES`（默认 20MB，与文档一致）；错误文案更新为"仅支持 图片 / 文档 / 音频"。
- `Attachment.kind = "audio"`（列宽 `String(16)`，**无需迁移**）。

### 23.4.5 运行时（`app/ai/runtime.py`）

```
post_message: 附件按 kind 分三路 → image_paths / document_files / audio_files
run_generation(audio_files=[(path, original_name), ...])
  └─ 在创建用户消息之前：transcribe(paths)
       ├─ 成功 → transcript 块 + 注入文本
       └─ 失败 → 错误提示块 + "转写不可用"文本（生成继续）
  └─ 用户消息 blocks = [text, *transcript_blocks]
  └─ 注入文本 = 转写文本 + 文档文本（统一走 _frame_attachment_data）
```

- 转写**在检索之前**完成，因此知识库检索也能基于音频内容。
- 转写文本同样受 `MAX_DOCUMENT_CONTEXT_CHARS` 截断约束。

### 23.4.6 前端

- `Composer.ATTACH_ACCEPT` 增加音频扩展名；`kind="audio"` 的附件按文档 chip 渲染（无预览）。
- `BlockRenderer` 支持 `transcript` 块：显示文件名 + 转写文本（错误时显示原因）。

### 23.4.7 能力状态

`GET /capabilities/asr` → `{enabled, url, healthy, tools, error}`，复用 `capabilities._mcp_slot_status`（`20` 已抽出）。

## 23.5 测试

| 层 | 用例 |
|---|---|
| `tests/test_asr.py`（新增） | 未配置 → 降级；自动选中含 transcribe 的工具名；`ASR_MCP_TOOL` 覆盖；无匹配工具报错；调用失败报错；JSON 列表 / 裸文本 / `storage_key` 三种返回解析；`/capabilities/asr` 两种状态；音频附件 `kind="audio"`、非音频内容 415、超限 413；webm 改名成 mp3 仍识别为音频 |
| `tests/test_asr_runtime.py`（新增） | 音频回合：转写文本以"附件数据"注入并落 `transcript` 块；MCP 失败仍能生成且提示不可用；未配置 `ASR_MCP_URL` 时同样降级 |

## 23.6 部署：跑在宿主机（推荐）

Whisper large-v3 约 3GB，且本机无 CUDA（CPU 推理），因此 MCP 与模型都放宿主机：

```powershell
.\scripts\start-voice-asr.ps1 -Install    # 首次：建 venv + 装依赖（几百 MB）
.\scripts\start-voice-asr.ps1             # 启动，默认 large-v3 / CPU / int8
.\scripts\start-voice-asr.ps1 -Model Systran/faster-whisper-base   # 先验链路更快
```

`.env`：

```
ASR_MCP_URL=http://host.docker.internal:10001/mcp   # 后端在 Docker 时
ASR_INPUT_MODE=base64                               # 宿主机读不到容器内路径
```

本地开发（后端跑在宿主机）用 `ASR_MCP_URL=http://localhost:10001/mcp`。

**为什么默认 base64**：Docker named volume 里的 `/data/uploads/...` 在宿主机没有稳定可见路径；把 3GB 模型 bind-mount 进容器又慢、且没有 GPU。base64 让 MCP 完全不碰文件系统。

**替代方案（容器内 MCP）**：把 voice-asr 做成 compose 服务并挂 `uploads:/data/uploads:ro`，再设 `ASR_INPUT_MODE=path`。代价：Windows bind-mount 读 3GB 模型很慢，且要么让容器重新下载模型、要么把宿主 HF 缓存也挂进去。

## 23.7 已知限制

- **不把 ASR 工具暴露给模型**：模型无法对"对话里出现的其它音频"（URL、工具产出文件）按需转写；需要时再补一个可被模型调用的工具。
- **base64 有约 33% 传输开销**：20MB 上限对应约 27MB 请求体；语音消息通常远小于此，但超长录音不适合。
- **CPU 推理慢**：本机无 CUDA，`large-v3` 约 4x 实时（8 秒语音 ~33 秒）。长音频体验差；有 GPU 时把 `WHISPER_DEVICE=cuda` + `WHISPER_COMPUTE_TYPE=float16` 即可。
- **模型是进程内单例**：多开 MCP 进程会各加载一份 3GB；生产建议单实例 + 队列。
- **不做时间戳/分角色**：只取纯文本；"点文字跳回音频"需要 MCP 端返回分段与时间戳。
- **长音频**：分段/时长上限由 MCP 端负责（当前靠 `vad_filter` 去静音），平台侧只限字节数。
- 转写文本与音频本身一样**不受信任**，按数据块注入（已声明不是指令）。

## 23.8 决策记录

- 走 MCP（用户确认）；**由平台确定性调用**而非模型自主调用（二进制不可入 function-call 参数）。
- ASR 引擎改为**仓库自带 MCP + 本地 faster-whisper**（参考项目的 MCP 调远程 GPUStack 网关，本机没有该网关）。
- 入参默认 **base64**（宿主机跑 Whisper、后端在容器），`path` 模式保留给共享卷部署。
- 转写单独用 `ASR_TIMEOUT_S`（默认 300s）：`mcp_service.call_tool` 的默认 15s 会掐死长转写。
- 转写结果落 `transcript` 块并注入 user 数据块，与文档附件同一处理路径。
- 端到端实测：上传 wav → `kind=audio` → MCP 返回正确中文 → 用户消息落 `transcript` 块（`status=ok`）。
