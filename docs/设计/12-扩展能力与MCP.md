# 12 · 扩展能力（Skill / MCP / Tool）

> 状态：**Phase 1、Phase 2 均已实现**（能力中心 + 智能体绑定 + MCP 运行时）
> 关联：`04-智能体管理模块.md`（工具绑定与版本）、`09-前端交互设计.md`、`08-监控与可观测性.md`（tool span）
> 实现备注：MCP 客户端用 `mcp==2.2.0`——http 入口为 `streamable_http_client`（headers 经 `create_mcp_http_client` 注入），失败回退 `sse_client`；stdio 用 `stdio_client` 拉子进程（stderr 需带 fileno 的流）。`probe` 会缓存每个 tool 的 `input_schema`，运行时据此构造 function calling 的 `parameters`；模型看到的函数名为 `mcp__{server}__{tool}`，执行时映射回真实 server 配置。请求头明文存库、仅返回给所有者。

## 12.1 背景与目标

当前系统只有一套内置工具 `TOOL_REGISTRY`（`time_now`、`kb_search`），启动时 `sync_tools()` 同步进 `tools` 表，智能体通过 `agent_tools` 绑定。系统没有 skill、也没有 MCP 概念。

目标：

1. 新增「扩展能力」一级页面，用三个标签页展示当前系统所拥有的 **Skill / MCP / Tool**，每个都有简介与使用方式。
2. MCP 可**手动新建**：选择连接方式（http / stdio）、填 url 与请求头（或命令/参数/环境变量），有「测试连接」按钮，通过该 MCP 的 tools 列表验证连通性与可用性。
3. 智能体创建/编辑时可选择自己的 **skill、mcp、tool**，MCP 精确到 tool 粒度。
4. 智能体能**真实调用 MCP tool**；绑定的 skill 以指令包形式注入 system prompt。

## 12.2 概念定义

| 概念 | 定义 | 来源 | 可变性 |
|---|---|---|---|
| **Tool** | 内置函数工具（openai function calling） | 代码 `TOOL_REGISTRY`，启动同步进 `tools` 表 | 代码定义，只读 |
| **Skill** | 指令包：一段注入 system prompt 的说明 + 展示元数据 + 推荐工具 | 代码静态清单 `app/ai/skills.py` | 代码定义，只读 |
| **MCP** | 外部 MCP Server，暴露若干 tool | 用户在页面新建，存 `mcp_servers` 表 | 用户可增删改 |

设计取舍：skill 不入库（纯代码清单），避免"代码改了库里还留着旧 skill"的同步问题；tool 沿用现有入库同步机制；mcp 是用户数据，必须入库。

## 12.3 范围分期

### Phase 1 —— 能力中心（可独立验收）

- 后端：`mcp_servers` 表 + 迁移；MCP 客户端探测服务；MCP CRUD + 测试连接 API；静态 skill 清单 + 查询 API；`/tools` 补充 `input_schema`。
- 前端：`/capabilities` 一级页面（Skill / MCP / Tool 三标签）；MCP 新建/编辑表单 + 测试连接；侧栏入口。
- 不含：智能体绑定、运行时调用。

### Phase 2 —— 绑定与运行时

- 后端：`agent_skills`、`agent_mcp_tools` 表；绑定 API；发布快照/回滚纳入；运行时 skill 注入 + MCP 工具调用。
- 前端：智能体编辑器改标签页布局，新增「扩展能力」标签（skill / mcp / tool 选择）。
- 依赖 Phase 1 的实体（skills、mcp_servers）。

## 12.4 数据模型（Phase 1 建 `mcp_servers`）

```
mcp_servers
  id              uuid pk
  user_id         uuid FK users.id ondelete CASCADE, indexed
  name            varchar(64)
  transport       varchar(16)   -- 'http' | 'stdio'
  url             varchar(512)  null          -- http
  headers         jsonb default {}            -- http，键值对
  command         varchar(256)  null          -- stdio
  args            jsonb default []            -- stdio
  env             jsonb default {}            -- stdio
  enabled         bool default true
  status          varchar(16) default 'unknown'  -- unknown | ok | error
  last_error      text null
  tools           jsonb default []            -- 最近一次探测到的 [{name, description}]
  last_checked_at timestamptz null
  created_at      timestamptz not null default now()
  updated_at      timestamptz not null default now()
  unique (user_id, name)
```

Phase 2 追加：

```
agent_skills
  agent_id    uuid FK agents.id ondelete CASCADE, pk
  skill_slug  varchar(64), pk
  primary key (agent_id, skill_slug)

agent_mcp_tools
  agent_id       uuid FK agents.id ondelete CASCADE, pk
  mcp_server_id  uuid FK mcp_servers.id ondelete CASCADE, pk
  tool_name      varchar(128), pk
  primary key (agent_id, mcp_server_id, tool_name)
```

约定：`tests/conftest.py` 的 `clean_tables` TRUNCATE 列表必须同步加入新表，否则用例间数据串扰。

## 12.5 后端设计

### 12.5.1 MCP 客户端服务 `app/services/mcp_service.py`

- `probe(config) -> ProbeResult`：按 transport 连接 → `initialize` → `list_tools` → 返回 `{ok, tools, error, latency_ms}`。
  - http：官方 SDK `streamablehttp_client(url, headers=...)`；失败可回退 `sse_client`。
  - stdio：`StdioServerParameters(command, args, env)` + `stdio_client`。
  - 统一 15s 超时；异常转可读中文（连接失败 / 超时 / 协议错误），截断长度。
  - `tools` 归一化为 `[{name, description}]`。
- `call_tool(config, name, args) -> (text, status)`：调用 `session.call_tool`，把返回内容拼成文本；异常转错误结果（不抛给上层）。
- 依赖：`pyproject.toml` 增加 `mcp`。

### 12.5.2 API

`app/api/v1/mcp_servers.py`（prefix `/mcp-servers`，全部 `get_current_user`）：

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/mcp-servers` | 当前用户的 MCP 列表（含缓存的 status/tools） |
| POST | `/mcp-servers` | 新建 |
| PATCH | `/mcp-servers/{id}` | 修改 |
| DELETE | `/mcp-servers/{id}` | 删除，204 |
| POST | `/mcp-servers/test` | body 为配置，探测但不落库（表单"测试连接"用） |
| POST | `/mcp-servers/{id}/test` | 探测已保存项，写回 status/tools/last_checked_at |

- 越权一律 404（沿用 `agent_service.get_owned_agent` 的写法）。
- 校验：`name` 必填且 `(user_id,name)` 唯一；`http` 要求 `url` 以 `http(s)://` 开头；`stdio` 要求 `command` 非空。
- 请求头仅返回给本人（明文，见 12.8）。

`app/api/v1/capabilities.py`：`GET /capabilities/skills` 返回静态清单（无需登录数据隔离，仍要求登录）。

`tools.py`：`ToolOut` 增加 `input_schema`。

### 12.5.3 Skill 静态清单 `app/ai/skills.py`

字段：`slug / name / icon / summary / usage / instructions / examples / recommended_tools`。

初版 5 条（内容可迭代）：

| slug | 名称 | instructions 作用 |
|---|---|---|
| `kb_qa` | 知识库问答 | 优先检索知识库、按引用作答、注明来源 |
| `relay` | @ 接力协作 | 说明何时把任务交给被 @ 的智能体、交接格式 |
| `vision` | 图片理解 | 结合图片内容作答的注意事项 |
| `deep_thinking` | 深度思考 | 先分析再给结论、暴露关键推理 |
| `model_switch` | 模型热切换 | 说明多模型协同与切换时的期望行为 |

### 12.5.4 运行时（Phase 2）

- `EffectiveConfig` 增加 `skill_slugs` 与 `mcp_bindings`（server 配置 + tool 白名单）。
- `build_agent_config` 组装绑定；system prompt 在变量替换后追加「已启用能力」段落，写入各 skill 的 `instructions`。
- tools payload = `tools_payload(cfg.tool_slugs)` + 选中 MCP tools，命名 `mcp__{server}__{tool}`（slug 化、限长 64、冲突去重映射）。
- `_execute_tool` 增加 MCP 分支：命中前缀 → `mcp_service.call_tool`，与内置工具同样回填结果、记 `tool` span、失败不中断整轮。
- 单次调用建立一个 MCP 会话（简单优先）；连接失败只跳过该 server 的工具。

### 12.5.5 绑定 API 与版本（Phase 2）

- `GET/PUT /api/v1/agents/{id}/skills`（slug 列表，替换语义）。
- `GET/PUT /api/v1/agents/{id}/mcp-tools`（`[{mcp_server_id, tool_name}]`，替换语义；写前校验 server 归属与 tool 名在缓存列表中）。
- `agent_service._snapshot` / `rollback_agent` 纳入 `skill_slugs` 与 MCP 绑定。

## 12.6 前端设计

### Phase 1

- 路由 `/capabilities`，侧栏新增一级入口「🧩 扩展能力」（`SessionSidebar` 底部导航区）。
- 页面 `CapabilitiesPage.tsx`：标题 + 三个标签（本地 state，不引新 UI 库）。
  - **Skill 标签**：卡片列表，展示 图标 / 名称 / 简介 / 使用方式 / 示例 / 推荐工具。
  - **Tool 标签**：复用 `useTools()`，展示 名称 / slug / 分类 / 简介 / 参数 schema / 绑定调用说明。
  - **MCP 标签**：
    - 列表卡片：名称、transport、状态徽章（未测试/正常/失败）、tool 数、可展开 tools、上次测试时间；行内「测试」「编辑」「删除」。
    - 「新建 MCP」打开内联表单（非弹窗，仓库无 Dialog 组件）：名称；transport 单选 http/stdio；http → url + 请求头键值对编辑器；stdio → command / args(每行一个) / env(键值对)；「测试连接」显示结果（成功/失败原因 + tools + 耗时）；「保存」。
- 新增 `src/api/capabilities.ts`、`src/api/mcp.ts`。

### Phase 2

- `AgentEditorPage` 改为标签页：**基础信息 | 扩展能力 | 知识库**。
- 「扩展能力」标签内三块：Skill（勾选，展示将注入的说明）、MCP（先选 server，再勾该 server 下具体 tool）、Tool（沿用 `ToolsMatrix`）。分块保存，交互与现有「保存工具绑定」一致。

## 12.6b 模型工具能力提示（补充）

绑定工具/MCP 后模型不调用，最常见的原因是**模型不支持（或实际不产生）工具调用**。为此：

- `GET /api/v1/models` 增加 `capabilities`（来自 Ollama `/api/show`，进程内 60s TTL 缓存），如 `["completion","tools","thinking"]`。
- 前端 `AgentForm` 在模型下拉下方提示：
  - 未声明 `tools` → 红色警告「绑定的工具 / MCP 不会被调用」，并在下拉项后标注「（不支持工具）」。
  - 声明 `tools` → 提示注意：**个别推理模型会声明 tools 却实际不调用**。
  - 探测不到（Ollama 不可用/模型未安装）→ 提示"无法判断"。
- 实测结论（2026-09-16，Ollama + 本机模型）：`deepseek-r1:latest` 的 `capabilities` 含 `tools`，但给 8 个 MCP 工具时**不产生 `tool_calls`**（只在正文里反问用户）；`qwen2.5:7b-instruct-q4_K_M` 正常调用。**需要工具调用时优先用 qwen2.5 这类模型**。

## 12.6c 工具结果里的链接与图片（补充）

工具返回值里常有 URL（搜索结果的 `url`、图片直链等），但 `tool_result` 的 `preview` 只截 200 字，URL 常被截断。

- 后端 `runtime.extract_tool_links(text)`：对**完整结果**做正则提取，把图片与普通链接分流；去重保序、各限 5 条；剥掉末尾标点。
  - 图片判定：先看扩展名（png/jpg/jpeg/webp/gif/svg/bmp/ico），再看路径/查询语义（`qrcode`、`/image|img|photo|avatar|thumbnail|poster`、`?format=png`）——二维码接口常返回 `image/*` 却没有后缀（如 `open.lkcoffee.com/transfer/qrcode?token=…`）。
  - 可点击 scheme 白名单：`http(s)`、`weixin`、`alipay(s)`、`tel`、`mailto`；其余（`javascript:`、`data:`、`file:`）**不提取**，避免把不可信的工具输出变成注入面。
- `tool_result` block（以及对应的 SSE 事件）在非空时附带 `links` / `images` 数组，前端无需依赖 preview。
- 前端 `BlockRenderer`：`images` 渲染为缩略图（点击/新标签页打开），`links` 渲染为 `🔗` 链接列表。两者都放在 `tool_result` 的**折叠区之外**（该卡片默认折叠，结果是用户真正要的东西，不该藏在「展开」后面）；`preview` 纯文本里的 URL 也会被切成可点击片段（用户点到的往往是原文里那一个，而不是提取出来的清单）。
  - `http(s)` 链接带 `<a target="_blank" rel="noreferrer noopener">`，**普通点击、Ctrl/⌘+点击、中键**都能跳转；自定义协议（`weixin://`）**不加 `target`**，直接交给系统协议处理器唤起客户端（加了反而可能先弹空白标签页）。`<img src>` 只认 `http(s)`。
- 前端白名单过滤放在 `lib/linkify.ts`（与后端 `_URL_SCHEME` 对齐），代码块跳过逻辑抽到 `lib/plainText.ts`（与引用锚点 `lib/citations.ts` 共用）。**改 scheme 白名单时前后端两处都要改**。
- markdown 正文：`lib/linkify.ts` 的 `autolinkBareUrls` 把裸的自定义协议包成 CommonMark autolink（`<weixin://…>`）——GFM 的自动链接只认 `http(s)`/`www`/邮箱，智能体直接写出来的支付链接否则只是死文本；同时 `MarkdownContent` 传入自定义 `urlTransform`，因为 react-markdown 默认只放行 `https?|ircs?|mailto|xmpp`，会把 `weixin://` 的 href 清成空字符串（表现就是「点了没反应」）。
- 已知限制：图片是浏览器直连外链加载，不经过后端鉴权；要求鉴权的图片 URL 会加载失败（正文链接仍可点）。自定义协议能否唤起取决于本机是否装了对应客户端（微信未安装时点击无反应）。

## 12.7 测试

Phase 1 后端：`test_mcp_api.py`（CRUD、越权 404、唯一名、http/stdio 校验、`/test` monkeypatch `probe`、`/{id}/test` 写回状态）；`test_capabilities_api.py`（skills 端点字段完整、parser 状态、models 能力）；`test_tools_registry` 覆盖 `input_schema`。

Phase 1 前端：`CapabilitiesPage.test.tsx`（三标签切换、skill/tool 渲染、MCP 新建表单校验、测试连接成功与失败）。

Phase 2 后端：绑定 API、发布快照含新绑定、运行时 skill 注入 prompt、MCP tools payload 生成、`_execute_tool` 路由到 `call_tool`（mock）。

Phase 2 前端：`AgentEditorPage.test.tsx` 扩展能力标签选择与保存。

## 12.8 已知限制 / 本期不做

- MCP 请求头可能含 API Key，**明文存库**、仅返回给所有者本人，不做加密与掩码。
- MCP 每次调用单独建连，不做连接池/会话复用。
- stdio 要求运行环境内有对应命令；Docker 后端容器内没有宿主机命令，本机开发模式最顺，页面给出提示。
- 不做 MCP 的 resources / prompts，只使用 tools。
- 不做 MCP 的鉴权 OAuth 流程（只支持自定义请求头）。
- skill 为代码清单，页面只读，不支持用户自定义新增。

## 12.9 决策记录

- skill 语义：从"纯展示"升级为"指令包注入 prompt"（用户确认）。
- MCP 绑定粒度：精确到 tool（用户确认）。
- MCP 本期是否接入运行时：是（用户确认，故分两期把运行时放 Phase 2）。
- MCP 归属：按用户隔离（用户确认）。
- 页面位置：独立一级页 `/capabilities`（用户确认）。
- MCP 客户端：官方 `mcp` SDK（http + stdio），不手写 JSON-RPC。
