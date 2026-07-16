# Phase 0 架构

浏览器请求首先进入入口 Nginx。`/api/`、`/health/`、`/admin/` 和 `/static/` 转发至 Django，其余路径转发至前端静态容器。Django 使用 PostgreSQL 保存权威数据，Redis 作为 Celery Broker/Backend 和基础连通性依赖。Celery Worker 与 Beat 加载同一 Django 配置。

本阶段仅提供工程基础设施，不包含领域模型、业务 Service、Agent、提醒调度或简报工作流。

