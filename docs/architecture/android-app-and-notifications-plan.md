# Android app 与通知推送方案

状态：草案（2026-07-25）
目标：把现有 React 前端做成**可下载安装的 Android APK**，实现**在国内网络下也能可靠发送通知**，并支持 **app 内显示更新说明 / 自更新**。

---

## 0. 背景与已确认的事实

- 现有前端是 React 19 + Vite 6 + TS 的 SPA，后端是 Django 5.2 + DRF + Celery，部署在公网服务器。
- 曾用 **PWA + Web Push** 方案。实测现象：
  - 国内自带浏览器（小米/华为等）没有安装入口；
  - 勾选 Web Push 后报 `push service error`，收不到通知；
  - **打开 VPN 后提醒成功送达**。
- 根因已确认：安卓 Chrome 的 Web Push 绑定 **Google FCM**，国内网络直连不到 FCM。代码、VAPID 配置、后端投递链路本身都是健康的，堵点纯粹是网络/平台层面。
- 结论：PWA + Web Push 在国内安卓不可行，需要换承载方式，但**现有 React 代码可以 100% 复用**。

---

## 1. 关键概念：本地通知 vs 远程推送

| | 本地通知 (Local Notification) | 远程推送 (Remote Push) |
|---|---|---|
| 谁决定何时响 | app 在设备本地预约，OS 到点弹出 | 服务器决定，经推送通道下发 |
| 成本 | 完全免费，只需系统权限 | 小规模基本免费（免费额度），大规模/高级功能收费 |
| 需要网络 | 不需要 | 需要 |
| 需要 Google / VPN | 不需要 | FCM 需要；国内厂商通道不需要 |
| 适用场景 | 触发时间已知的定时提醒 | 服务器临时发起、跨设备、app 长期不开也要收到 |

**系统通知权限本身永远免费。** 之前收不到不是因为没付费，而是走了 FCM 这条国内不通的远程通道。

---

## 2. 承载方式：Capacitor 套壳

用 [Capacitor](https://capacitorjs.com)（Ionic 团队）把现有 React + Vite 前端装进原生 Android WebView 容器，产出真正的 APK。

- **复用 100% 现有 web 代码**：路由、TanStack Query、Zustand、UI 全不动。
- 提供原生桥：可调本地通知、推送 SDK、文件、安装等能力。
- **排除 TWA**：Trusted Web Activity 底层仍是 Chrome + FCM，解决不了国内推送问题。
- **排除 React Native 重写**：工作量巨大且丢弃现有代码，无必要。

WebView 里照常访问公网后端 `/api`（同现在的 web 行为）。需注意：APK 内是 `capacitor://` 或 `https://localhost` 源，跨源访问后端时后端 CORS/CSRF 配置需相应放行（见 §6 风险）。

---

## 3. 通知策略：本地为主，远程为辅（混合）

### 3.1 本地通知覆盖定时提醒（免费、零依赖，第一优先级）

TimeAgent 的核心是**定时提醒**——创建时触发时间已确定。这种场景本地通知完全胜任：

```
app 启动 / 前台恢复 / 数据变更
  └─ 从后端拉取未来的 Reminder 列表 (已有 /api)
       └─ Capacitor LocalNotifications 插件在设备上预约通知
            └─ 到点由 Android 系统弹出通知栏（app 关着也响）
```

- 插件：`@capacitor/local-notifications`。
- 权限：Android 13+ 需 `POST_NOTIFICATIONS`（运行时申请）；精确定时需 `SCHEDULE_EXACT_ALARM`。
- 免费、不需网络、不需 Google/VPN、断网也响。
- 需处理：预约上限（Android 对 pending alarm 有数量限制，通常滚动预约最近 N 条）、时区、提醒被取消/修改时同步取消本地预约。

### 3.2 远程推送补服务器主动发起的场景（第二优先级）

仅在以下情况必须用远程推送：
- 服务器临时决定通知（如 AI 生成的每日简报，app 事先不知内容/时间）；
- 提醒在别的设备创建，本机 app 长期未开、没机会同步；
- 需要 app 长期不开也保证送达。

国内可靠通道：**极光 JPush**（聚合厂商通道）。走小米/华为/OPPO/vivo 系统级推送，app 被杀也能到达，不依赖 FCM/VPN。

- 客户端：极光 Capacitor/Cordova 插件，注册得到 `registrationId`，上报后端。
- 服务端：极光 REST API。
- **厂商通道**是国内可靠送达的关键——需去各厂商开放平台注册拿 appkey 配到极光后台；不配则退化为极光自建长连接，国产 ROM 省电策略可能杀掉。

### 3.3 分工建议

| 场景 | 通道 |
|---|---|
| 用户在本机创建的定时提醒 | 本地通知（免费） |
| AI 每日简报 / 服务器主动通知 | 远程推送（极光） |
| 跨设备创建、本机未同步 | 远程推送（极光） |
| Email 兜底（所有场景） | 现有 EMAIL provider，国内最稳 |

---

## 4. 后端改动（加法，不动核心）

现有通知系统已是多渠道 provider 模式，新增通道与现有 `WebPushNotificationProvider` **完全同构**：

- **新增 channel 类型** `ANDROID_PUSH`（`NotificationChannelType`）。
- **新增 provider** `AndroidPushProvider`：实现 `send(message)`，调极光 REST API；沿用现有 transient/permanent 错误分类与 `ProviderSendResult`。注册进 `providers/registry.py`。
- **新增用户偏好字段** `reminder_android_push_enabled` / `briefing_android_push_enabled`（迁移 + `channels_for` 里加一项）。
- **新增设备注册端点**：`POST /api/notifications/device-tokens`，存 `registrationId` + 平台 + user，类似现有 `WebPushSubscription`。
- **Celery 调度、重试、审计、幂等链路完全不变**（`dispatch_due` → `send_notification_delivery` → provider）。

`app_version` OTA 端点见 §5。

---

## 5. app 内显示更新 / 自更新（OTA，侧载场景）

不走应用商店时更新靠自己：

- 后端新增 `GET /api/app/version`，返回 `{ latest_version, apk_url, changelog, min_supported }`。
- app 启动时拉取，与本地 `versionCode` 比对：
  - 有新版 → 弹窗显示 changelog（即"app 内显示更新"）；
  - 用户确认 → 下载 APK → 触发安装（需 `REQUEST_INSTALL_PACKAGES` 权限）。
  - `min_supported` 用于强制更新（低于此版本必须升级）。
- 可用现成 Capacitor 插件或自实现。

---

## 6. 风险与现实摩擦

- **厂商推送平台注册**：小米/华为/OPPO/vivo 开放平台各要注册，部分需企业资质/软著。极光本身注册简单。这是国内远程推送绕不开的门槛。
- **APK 签名**：MVP 自签即可；用户首次安装需允许"未知来源"。
- **CORS/CSRF**：APK 内 WebView 的源与网页不同，后端需放行；session cookie 的 `SameSite`/跨源携带需验证，可能需改用 token 认证或调整 cookie 策略（与现有 ADR-0009 会话认证有冲突点，需评估）。
- **应用商店上架**（可选后续）：国内商店需软著等资质，MVP 侧载 APK 即可。
- **本地通知的 OS 限制**：pending alarm 数量上限、Doze 模式对精确定时的影响，需在客户端处理滚动预约。

---

## 7. 分阶段落地

1. **Capacitor 接入，出可安装 APK**：验证现有前端在 WebView 跑起来、能连公网后端（含 CORS/CSRF 打通）。
2. **本地通知打通定时提醒**：`@capacitor/local-notifications` + 从 `/api` 同步提醒 → 本地预约。**这一步很可能已覆盖你 90% 的需求，且完全免费、不依赖任何外部服务。**
3. **（按需）远程推送**：后端加 `AndroidPushProvider` + 极光自建通道，跑通"服务器发→手机收"。
4. **（按需）配厂商通道**：各厂商平台注册，达到 app 被杀也能收的生产可靠性。
5. **OTA 自更新 + 更新说明**：`/api/app/version` + app 内检查更新弹窗。

**建议：先做 1→2。** 本地通知很可能让你在零成本、零外部依赖下就实现"自由发送提醒通知"，验证后再决定是否投入远程推送。

