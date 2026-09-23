# Time Agent 测试模块

## 测试目录

当前项目已有两套专门的测试目录：

- `backend/tests/`：Django/pytest 后端单元、服务、API、数据库和 Agent fixture 测试。
- `frontend/tests/`：Vitest/React Testing Library 前端测试，以及 `frontend/tests/e2e/` 下的 Playwright 桌面端、移动端和真实后端验收用例。

本文件是两套测试目录的统一说明入口；测试命令和测试范围以各自目录及项目开发文档为准。

## 手工验收账号

生产环境已创建一个专门用于手工验收的普通账号：

- 登录邮箱：`time-agent-test@example.invalid`
- 显示名称：Time Agent 测试用户
- 权限：普通用户；非 staff、非 superuser
- 用途：网页端、PWA 和 Android APK 的功能及界面验收
- 邮箱：使用保留的 `.invalid` 域名，不用于真实邮件投递

密码不写入仓库、README、日志或测试 fixture；创建后的临时密码通过安全的任务交接渠道单独提供。不要在该账号中录入真实个人资料、密钥、Token 或生产敏感数据。

手工测试产生的日程、任务、提醒和聊天记录应使用明显的 `TEST-` 前缀，测试完成后清理，避免与真实业务数据混淆。

## 当前发布环境

- 网页入口：<https://steward.uresofa.me/>
- Android 下载：<https://steward.uresofa.me/releases/timeagent-1.1.8.apk>

收到明确测试指令后，再按指令执行对应的手工或自动化测试；不默认运行真实模型、通知投递或其他可能产生外部副作用的测试。
