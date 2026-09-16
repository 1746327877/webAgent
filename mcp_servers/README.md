# mcp_servers — 本地 MCP 服务集合

本机运行的 MCP 服务，结构对齐 `mcp_new/`：**一个工程装多个子服务，统一入口 + 一键启动**。

当前包含：

| 服务 | 端口 | 工具 | 说明 |
|---|---|---|---|
| `mcp_voice2text` | 10001 | `transcribe`、`health` | 本地 faster-whisper 语音转文字（CPU/GPU 均可） |

## 目录结构

```
mcp_servers/
├── src/
│   ├── config.py            # 公共配置（env/.env 加载，新增配置只改这里）
│   ├── logger.py            # 公共日志
│   ├── main.py              # 统一入口（按 MCP_SERVICE 选服务）
│   └── mcp_voice2text/      # 语音转文字服务
│       ├── server.py        # MCP 入口（streamable-http）
│       ├── voice_tool.py    # 工具层（批量/保序/失败隔离）
│       └── asr_local.py     # faster-whisper 封装（懒加载单例）
├── requirements.txt
└── .env.example
```

## 一键启动（Windows）

```powershell
.\scripts\start-mcp.ps1 -Install     # 首次：建 venv + 装依赖
.\scripts\start-mcp.ps1              # 启动 mcp_voice2text（默认 large-v3）
.\scripts\start-mcp.ps1 -Service all # 启动全部服务
.\scripts\start-mcp.ps1 -Stop        # 停止全部
```

## 手动运行

```powershell
cd mcp_servers
.\.venv\Scripts\python.exe -m src.main                          # 用 .env 里的 MCP_SERVICE
$env:MCP_SERVICE="mcp_voice2text"; .\.venv\Scripts\python.exe -m src.main
.\.venv\Scripts\python.exe -m src.mcp_voice2text.server          # 直接启某个服务
```

## 平台接入

后端 `.env`：

```
ASR_MCP_URL=http://host.docker.internal:10001/mcp   # 后端在 Docker
ASR_INPUT_MODE=base64                                # 宿主机 MCP 读不到容器内路径
```

## 新增一个本地 MCP 服务

1. 在 `src/` 下建子包 `mcp_<名字>/`，放 `server.py`（`FastMCP` 实例 + `@mcp.tool()`）；工具逻辑单独放 `<名字>_tool.py` 便于单测；
2. `src/config.py` 加端口等配置字段；
3. `src/main.py` 的 `SERVICES` 里追加一行 `名称 → (模块路径, 端口字段)`；
4. 需要就 `scripts/start-mcp.ps1` 的 `$Services` 里加一项。

设计文档见 `docs/设计/23-语音转写MCP.md`。
