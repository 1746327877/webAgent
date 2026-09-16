# 20 · OCR 识别文字 MCP

> 状态：设计已定，已实施
> 关联：`13-MinerU与联网搜索MCP.md`（外部 MCP 接入模式）、`18-联网搜索开关.md`（部署级合成绑定）、`05-知识库RAG.md`（MinerU 的 OCR 边界）

## 20.1 背景与目标

现状：**平台没有独立的 OCR 能力**。扫描件的 OCR 只在知识库摄入时由 MinerU 完成；对话里上传的图片走视觉模型（`vision_model`），不会做逐字识别。想在对话中对扫描件/截图**取字**（而非理解）时没有工具可用。

目标：让模型在对话中能按需调用 OCR 取字；后端**不内置 OCR 引擎**，而是接入部署方自备的 OCR MCP 服务。

## 20.2 决策（假设，可返工）

| 事项 | 决策 | 理由 |
|---|---|---|
| 形态 | **部署级合成 MCP**（复用 `18` 的 `McpSlot` 模式），配置 `OCR_MCP_URL` | 与 web-search 一致；不 seed `mcp_servers` 表、不引重型 OCR 依赖 |
| 触发方式 | **有图片附件的回合自动挂载**该 MCP 的工具 | 用户没要求按钮；图片回合就是 OCR 的适用场景 |
| 引擎 | 不自研、不指定；由部署方提供（PaddleOCR / Tesseract / 商业服务封装的 http MCP 均可） | 避免引入 torch/paddle 等重量级依赖，也不替用户选型 |
| 与视觉模型的分工 | 视觉模型负责"理解图片"，OCR MCP 负责"逐字取字"；两者并存 | 需求不同，不应互相替代 |
| 与 MinerU 的分工 | MinerU 在**摄入流水线**里给 PDF 做 OCR；OCR MCP 在**对话**里按需取字 | 场景不同，互不替代 |
| 未配置时 | 不挂载、不报错；`GET /capabilities/ocr` 返回 `enabled=false` | 失败降级，生成不中断 |

## 20.3 设计

### 20.3.1 配置

| 变量 | 默认 | 说明 |
|---|---|---|
| `OCR_MCP_URL` | 空 | 为空=图片回合不挂 OCR 工具。compose 里 `OCR_MCP_URL: ${OCR_MCP_URL:-}` |

### 20.3.2 槽位（`app/ai/ocr.py`）

复用 `app/ai/mcp_slot.py` 的 `McpSlot`（与联网搜索共用同一套"按需合成绑定 + TTL 缓存"逻辑，避免孪生模块）：

```python
_slot = McpSlot("ocr", lambda: settings.ocr_mcp_url, SYNTHETIC_SERVER_ID)

def is_enabled() -> bool: ...
async def binding(): ...   # 未配置或探测失败 → None
def reset_cache() -> None: ...
```

### 20.3.3 运行时挂载（`app/ai/runtime.py`）

工具装配阶段：`if image_paths:` 且未绑定同名 server 时，把 `ocr.binding()` 合入本轮 `mcp_bindings`。之后与普通 MCP 工具完全一致（`build_mcp_tools` → 模型调用 → `mcp_service.call_tool`）。

### 20.3.4 状态查询（`app/api/v1/capabilities.py`）

`GET /capabilities/ocr` → `{enabled, url, healthy, tools, latency_ms, error}`；与 `/web-search` 共用 `_mcp_slot_status` 私有助手。

## 20.4 测试

`backend/tests/test_ocr.py`：
- 未配置 → `binding()` 为 None；探测失败 → None 且不抛；探测成功 → 合成绑定带 tools。
- **图片回合**：上传 png + 发送消息 → 视觉回合请求的工具载荷含 `mcp__ocr__ocr`。
- **纯文本回合**：不带 OCR 工具。
- `GET /capabilities/ocr` 的未配置/健康两种状态。

> 注意：会话未设标题时会追加一次"生成标题"调用，测试断言要按"含图片的请求"定位视觉回合，不能直接取 `requests[-1]`。

## 20.5 已知限制

- **不提供 OCR 服务本身**：没有配 `OCR_MCP_URL` 就等于没有 OCR；仓库不附带 OCR 引擎（有意为之，避免重型依赖）。
- 触发条件是"有图片附件"，无法在纯文本里 OCR 一个远程图片 URL。
- 合成 `server_id` 是固定 UUID，仅用于分组/去重，不代表数据库行。
- 与视觉模型的取舍由模型自行判断，平台不强制"先 OCR 再理解"。

## 20.6 决策记录

- 按用户"添加 OCR 识别文字的 MCP"的字面意图，实现为**可插拔的 OCR MCP 槽位**，而非内置 OCR 引擎；引擎选型留给部署方（假设，可返工）。
- 抽出 `McpSlot` 消除与 `18` 的重复实现（`AGENTS.md` §2.4）。
