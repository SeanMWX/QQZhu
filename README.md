# QQZhu（主播歌单）
前端+后端（aiohttp + sqlite）。支持前台展示、后台增删改、备份/恢复、首登设置后台 token。

## 本地启动
1) 准备环境：Python 3.10+，安装依赖
```bash
pip install -r requirements.txt
```
2) 配置：
- 复制 `config-sample.ini` 为 `config.ini`，按需修改端口/数据库路径（首次启动会自动创建 DB 和表）。
3) 启动：
```bash
python server.py
```
访问 `http://localhost:13897/`。若未设置后台口令，首次访问后台会跳转到 token 初始化页。

## Docker 启动
```bash
docker compose up -d
```
默认：
- 服务监听 13897（容器内 8080）
- 持久化 `./instance` 和 `./static/uploads`
- 内置健康检查（访问 `/healthz`）

修改端口：调整 `docker-compose.yml` 的 `ports`（如 `9000:8080`）。  
查看状态/日志：`docker compose ps`、`docker compose logs -f`。  

## 健康检查
- 路由：`GET /healthz`，返回 `ok`。
- Compose 已配置 healthcheck，可用于探活或负载均衡。
