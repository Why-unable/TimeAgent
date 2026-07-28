# ADR 0014：Android 原生认证与本地提醒边界

状态：已采纳  
日期：2026-07-26

## 背景

Time Agent 的浏览器客户端使用同源 Session 与 CSRF。Capacitor Android
应用从 `https://localhost` 加载打包资源，必须跨源访问公网 Django API，
不能依赖浏览器会话 Cookie。同时，国内 Android 环境中的 Web Push
依赖并不稳定，已知触发时间的提醒应优先由设备本地调度。

## 决策

1. 浏览器继续使用 Session Authentication，不改变现有 CSRF 边界。
2. Android 客户端使用独立的 DRF Token Authentication 通道。
3. Token 的签发、轮换和撤销必须经过 `AccountService`；API View 不直接
   写认证模型。每次原生登录轮换旧 Token，退出时撤销当前 Token。
4. Android Token 只保存到由 Android Keystore 保护的安全存储，不使用
   Local Storage 或 Capacitor Preferences；应用数据不得参与系统备份。
5. CORS 只开放 Capacitor WebView 的明确来源和实际使用的请求头。
6. 未来、待处理的提醒由 Android 本地通知调度。调度器只管理带有
   `reminderId` 标记的通知，并根据 ID、标题和触发时间执行增量对账，
   不得取消简报等其他功能拥有的通知。
7. 精确闹钟使用 `SCHEDULE_EXACT_ALARM`。未获得特殊权限时，Capacitor
   自动降级为非精确闹钟；产品说明应引导确实需要准点提醒的用户在系统
   设置中开启“闹钟和提醒”权限。

## 结果与限制

- App 进程被终止后，已经同步到设备的提醒仍可由系统触发。
- 别的设备刚创建的提醒，只有在本机下次启动、回到前台或轮询成功后才会
  进入本地调度；跨设备实时到达仍需后续接入独立远程推送 Provider。
- 当前 DRF Token 模型每个用户只有一个原生 Token，重新登录会使旧设备
  Token 失效。多设备独立会话需要后续引入带设备标识、哈希存储和过期
  策略的认证模型，不在本次 Android MVP 范围内。
