# Docker Compose 速查

## 服务与依赖

depends_on 只保证启动顺序，不保证被依赖服务"已经可用"。要等健康就配 healthcheck 并把依赖写成 condition: service_healthy。

## 网络与端口

同一条 compose 网络内可以用服务名互相访问，不必写 IP。只有需要从宿主机访问的服务才映射端口。

## 数据持久化

容器内的写入在重建后丢失，必须把数据目录挂成 volume 或 bind mount。

| 需求 | 做法 |
| --- | --- |
| 等服务就绪 | healthcheck + condition |
| 容器间互访 | 服务名 + 内部端口 |
| 数据不丢 | named volume |
| 只给宿主机用 | 不映射端口 |

## 环境变量

compose 文件里的 `${VAR:-默认值}` 会优先取宿主环境或 .env，取不到才用默认值。把密钥写进 compose 文件会随仓库泄露，应只提交 .env.example。
