# Time Agent：迁移到 Linux 新机器部署指南

本文用于将当前运行在 Windows + Docker Desktop 上的 Time Agent 迁移到一台新的
Linux 服务器，并把既有公网域名（例如 `steward.example.com`）切换到新机器。

目标部署拓扑：

```text
Browser / Android App
        │ HTTPS
Cloudflare ── Cloudflare Tunnel ── cloudflared (Linux systemd)
                                         │ HTTP, loopback only
                                      127.0.0.1:8080
                                         │
                         Nginx → Frontend / Django / Celery / PostgreSQL / Redis
```

Cloudflare Tunnel 只建立出站连接，因此不需要向公网开放 80、443、5432、6379 或
9090。只应保留 SSH 的受控访问；PostgreSQL、Redis 和 Prometheus 继续仅在 Docker
内部网络或本机回环地址可达。

> 本文以 Ubuntu 24.04 LTS（x86_64）为例。Debian 12 的流程相同，但 Docker 与
> `cloudflared` 的安装命令应按对应发行版官方文档调整。

## 0. 迁移原则与准备清单

在切换窗口内，**旧机器和新机器不能同时接受业务写入**，否则最终备份之后写入的
日程、提醒、用户、会话和订阅会丢失。推荐先在新机进行一次演练恢复，正式切换时再
短暂停止旧站，制作最终备份并恢复。

准备以下内容，但不要提交到 Git、聊天记录或截图：

- 当前仓库的 Git 地址和要部署的 commit/tag；
- 当前 `.env`；
- 当前 `backend/config/agent.yaml`；
- `frontend/.env.production.local`（APK/Web 前端构建用的公网 API 地址）；
- 最终 PostgreSQL custom-format 备份；
- Cloudflare Zero Trust 账户的操作权限；
- 现有的 `DJANGO_SECRET_KEY`、模型/邮件密钥、SMTP 密码、Web Push VAPID 密钥。

其中 PostgreSQL 备份保存用户、业务数据、ActionProposal、通知投递记录、聊天与
LangGraph 持久化（当 `LANGGRAPH_DATABASE_URL` 为空时）。请保留相同的 VAPID
密钥对，否则已存在的 Web Push 订阅不能继续按原身份投递。

## 1. 在旧 Windows 机器制作最终备份

先进行普通演练备份，确认新机器可以恢复。正式切换时再重复一次：停止旧站公网入口
或停止整套 Compose 服务，使最后一次备份期间不再有新写入。

在仓库根目录的 PowerShell 中执行：

```powershell
# 演练或正式最终备份
.\scripts\backup-postgres.ps1

# 查看生成的归档；文件在 Git 忽略的 backups\ 目录
Get-ChildItem .\backups\*.dump | Sort-Object LastWriteTime -Descending
```

正式切换建议顺序：

1. 在 Cloudflare 页面暂时移除旧 Tunnel 的生产 Public Hostname，或停止旧
   `cloudflared` 服务，告知用户进入短暂维护；
2. 等待正在进行的写请求结束；
3. 再执行一次备份脚本，标记为最终归档；
4. 通过 `scp` 或受控的加密传输把最终 `.dump` 和上述三个配置文件传到新机；
5. 新机验证通过后再把生产域名指向新 Tunnel。

不要复制 Docker 的 PostgreSQL volume 目录；使用 `pg_dump`/`pg_restore` 才能可靠地
跨主机、跨 Docker 版本迁移。

## 2. 初始化 Linux 主机

以拥有 `sudo` 的运维账号登录。建议系统时区使用 UTC，应用仍会根据每位用户的
IANA 时区显示和解析时间：

```bash
sudo timedatectl set-timezone UTC
sudo apt update
sudo apt install -y ca-certificates curl git openssh-client
```

按照 Docker 官方的 Ubuntu 安装文档配置 Docker apt 仓库并安装
`docker-ce`、`docker-ce-cli`、`containerd.io`、`docker-buildx-plugin` 与
`docker-compose-plugin`。不要使用发行版中陈旧的 `docker.io` / `docker-compose`
包，也不要在生产机使用仅适合测试的 convenience script。

安装完成后启用 Docker 并验证：

```bash
sudo systemctl enable --now docker
sudo docker run --rm hello-world
docker compose version
```

如需由当前登录用户运行 Docker，可执行下面命令后重新登录。注意 `docker` 用户组
实质上拥有主机级权限，只应授予受信任的运维账号：

```bash
sudo usermod -aG docker "$USER"
```

Docker 官方安装与 Compose Plugin 文档：

- [Install Docker Engine on Ubuntu](https://docs.docker.com/engine/install/ubuntu/)
- [Install the Docker Compose plugin](https://docs.docker.com/compose/install/linux/)

## 3. 获取代码与私有运行配置

以下示例将项目放在 `/opt/time-agent`；按团队实际 Git 地址替换。

```bash
sudo mkdir -p /opt/time-agent
sudo chown "$USER":"$USER" /opt/time-agent
git clone <YOUR_GIT_REPOSITORY_URL> /opt/time-agent
cd /opt/time-agent
git checkout <DEPLOY_COMMIT_OR_TAG>
mkdir -p backups
```

从旧机安全复制的文件放在以下位置：

```text
/opt/time-agent/.env
/opt/time-agent/backend/config/agent.yaml
/opt/time-agent/frontend/.env.production.local
/opt/time-agent/backups/time-agent-FINAL.dump
```

配置文件应只允许部署账号读取：

```bash
chmod 600 .env backend/config/agent.yaml frontend/.env.production.local
chmod 700 backups
chmod 600 backups/*.dump
```

至少核对 `.env` 的生产项（不要在终端或工单中粘贴真实值）：

```env
COMPOSE_PROJECT_NAME=time-agent
DJANGO_SETTINGS_MODULE=config.settings.production
DJANGO_DEBUG=false
DJANGO_ALLOWED_HOSTS=steward.example.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://steward.example.com
SESSION_COOKIE_SECURE=true
CSRF_COOKIE_SECURE=true
SECURE_SSL_REDIRECT=false
SECURE_HSTS_SECONDS=0
TIME_AGENT_CONFIG_PATH=config/agent.yaml
```

`SECURE_SSL_REDIRECT=false` 是当前 Tunnel 终止 TLS、再以 HTTP 转发到本机 Nginx 的
配套设置。先确认公网 HTTPS 全链路稳定，再单独评估是否开启 HSTS；错误的 HSTS 配置
可能让浏览器长期无法访问站点。

`frontend/.env.production.local` 必须包含实际公网地址，例如：

```env
VITE_API_BASE_URL=https://steward.example.com
```

它在前端镜像构建时被 Vite 写入静态产物；更改该值后必须重建 `frontend` 镜像。它不应
包含密钥。

## 4. 先恢复 PostgreSQL，再启动完整应用

以下命令会在**新机器的目标数据库**中用归档内容替换已有对象。确认 `.dump` 路径和
目标环境无误后再执行；不要对仍承载生产写入的旧数据库执行。

```bash
cd /opt/time-agent

# 仅先启动数据依赖。
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d postgres redis

# 等待 postgres 显示 healthy 后恢复最终备份。
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T postgres \
  sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner' \
  < backups/time-agent-FINAL.dump

# 启动应用、异步任务和本机 Prometheus（最后一份 overlay 是可选的）。
docker compose \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  -f docker-compose.observability.yml \
  up -d --build
```

初始化或版本升级后执行 Django 与 LangGraph 迁移：

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  exec django python manage.py migrate --noinput
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  exec django python manage.py setup_langgraph
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  exec django python manage.py check --deploy
```

本机验收（应返回 database 与 redis 都为 `ok`）：

```bash
curl --fail http://127.0.0.1:8080/health/ready
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  logs --tail=100 django nginx celery-worker celery-beat
```

Prometheus 若启用，只绑定 `127.0.0.1:9090`。需要查看时用 SSH 端口转发，而不要给
Tunnel 添加该端口：

```bash
ssh -L 9090:127.0.0.1:9090 <USER>@<SERVER_IP>
```

随后在本机浏览器打开 `http://127.0.0.1:9090`。

## 5. 在新机安装并运行 Cloudflare Tunnel

推荐创建一个新的、远程管理的 Tunnel，例如 `time-agent-linux`，而不是复制旧 Windows
机器上的凭证文件。域名仍是同一个域名；迁移的是“哪个 Tunnel 将该域名转发到哪台
机器”的路由关系。

在 Cloudflare Zero Trust：

1. 进入 **Networks → Tunnels**，创建 `time-agent-linux`；
2. 根据页面给出的 Linux 安装方式安装 `cloudflared`；
3. 复制此 Tunnel 的安装 token；token 只在服务器终端使用，不能写入仓库；
4. 在 Linux 上安装为 systemd 服务：

```bash
sudo cloudflared service install <TUNNEL_TOKEN>
sudo systemctl enable --now cloudflared
sudo systemctl status cloudflared --no-pager
```

5. 在新 Tunnel 添加一个**临时测试 hostname**，服务 URL 填
   `http://localhost:8080`，先验证 Linux 站点；
6. 测试成功后，将生产 hostname（例如 `steward.example.com`）的 Public Hostname
   路由从旧 Tunnel 改为新 Tunnel，服务 URL 同样填 `http://localhost:8080`；
7. 在外网执行：

```bash
curl --fail https://steward.example.com/health/ready
```

Cloudflare 负责 HTTPS；此处的 Service URL 必须是 **`http://localhost:8080`**，不能
写 `https://`，因为 Linux 本地 Nginx 没有配置 TLS。Cloudflare 官方 Tunnel 设置和
Linux systemd 服务说明：

- [Set up Cloudflare Tunnel](https://developers.cloudflare.com/tunnel/setup/)
- [Run cloudflared as a Linux service](https://developers.cloudflare.com/tunnel/advanced/local-management/as-a-service/linux/)

确认新生产域名已返回健康检查、登录、聊天 SSE、提醒/邮件与简报均正常后，才停止旧
Windows 的 `cloudflared` 和 Compose 服务。保留旧机与最终切换前的备份一段时间，便于
回滚。

## 6. 回滚方案

若新机验收失败：

1. 在 Cloudflare 将生产 Public Hostname 改回旧 Windows Tunnel；
2. 确认 `https://steward.example.com/health/ready` 已回到旧站；
3. 不要把新机产生的数据直接覆盖旧数据库；先判断是否发生了写入，并按业务需要迁移；
4. 保存新机日志与 PostgreSQL 备份后再排障。

因此，正式切换最好设置一个短暂维护窗口，并且先在临时 hostname 上完成新机验收。

## 7. 自启动、日常更新与验收

Compose 中所有长期服务已使用 `restart: unless-stopped`；Docker daemon 和
`cloudflared` systemd 服务启用后，服务器重启会自动带起它们。首次部署后、每次内核
升级或迁移后都做一次重启演练：

```bash
sudo systemctl is-enabled docker cloudflared
sudo reboot

# 重新 SSH 登录后
cd /opt/time-agent
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
curl --fail http://127.0.0.1:8080/health/ready
curl --fail https://steward.example.com/health/ready
```

日常发布建议固定为：备份 → 拉取指定提交 → 构建 → 迁移 → 健康检查。

```bash
cd /opt/time-agent
git fetch --tags origin
git checkout <NEW_DEPLOY_COMMIT_OR_TAG>
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  exec django python manage.py migrate --noinput
curl --fail http://127.0.0.1:8080/health/ready
```

如果更新了 `backend/config/agent.yaml`、`.env` 或任一后端共享代码，同时重建
`django`、`celery-worker` 和 `celery-beat`；若 Nginx 上游容器重建，执行
`docker compose restart nginx` 以重新解析上游容器地址。

## 8. 最终验收清单

- [ ] `docker compose ... ps` 中 django 为 healthy，PostgreSQL、Redis 为 healthy；
- [ ] 本机和公网 `/health/ready` 都返回 200；
- [ ] 管理员和普通用户均能登录；
- [ ] 一次聊天 SSE、一次审批恢复、一次简报均能完成；
- [ ] Celery Beat/Worker 日志无持续错误；
- [ ] 邮件与 Web Push 以非敏感测试数据做过一次投递；
- [ ] Android APK 的 `VITE_API_BASE_URL` 仍指向生产 HTTPS 域名；
- [ ] `docker` 与 `cloudflared` 都是 enabled；
- [ ] PostgreSQL 备份已复制到独立、加密且具有保留策略的存储。
