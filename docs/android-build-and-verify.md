# Android APK 构建与验证指南

本指南面向在**本机**构建 Time Agent 的 Android APK，并验证核心目标：
**应用能申请通知权限、发送本地通知，且被后台杀死后仍按时弹出提醒。**

前置结论（已在代码侧完成）：

- 前端已用 Capacitor 套壳，`frontend/android/` 是生成的原生工程。
- 认证已支持 token（原生用 `Authorization: Token`，web 仍用 session）；
  原生 token 由 Android Keystore 加密保存，重新登录会轮换旧 token。
- 本地通知已接线：登录后拉取提醒 → 在设备上用 AlarmManager 预约 → 到点由系统弹出，**不依赖服务器推送、不依赖 VPN**。

---

## 1. 一次性环境准备

### 1.1 安装 JDK 21

当前 Capacitor 插件工具链需要 JDK 21。

- 下载 Temurin 21（https://adoptium.net）或用 Android Studio 自带的 JDK。
- 设置 `JAVA_HOME` 指向 JDK 17，并把 `%JAVA_HOME%\bin` 加入 PATH。
- 验证：`java -version` 应显示 21.x。

### 1.2 安装 Android Studio（含 Android SDK）

- 下载安装 Android Studio（https://developer.android.com/studio）。
- 首次启动按向导安装：Android SDK、SDK Platform（API 34+）、Android SDK Build-Tools、Platform-Tools（含 adb）。
- 设置环境变量：
  - `ANDROID_HOME` = SDK 路径（默认 `C:\Users\<你>\AppData\Local\Android\Sdk`）
  - 把 `%ANDROID_HOME%\platform-tools` 加入 PATH（提供 `adb`）。
- 验证：`adb --version` 有输出。

---

## 2. 构建 APK

所有命令在 `frontend/` 目录下执行。

### 2.1 指定后端地址并构建前端

APK 里的 WebView 从本地加载打包好的静态文件，但 API 请求要打到你的**公网后端**。通过 `VITE_API_BASE_URL` 指定：

```bash
cd frontend
# 换成你的公网后端源（含 https://，不要结尾斜杠）
VITE_API_BASE_URL=https://你的域名 npm run build
```

> 说明：不设 `VITE_API_BASE_URL` 时默认走同源（web 部署用）。APK 必须显式指定，否则请求会打到 `https://localhost` 而失败。

### 2.2 同步到原生工程并打开 Android Studio

```bash
npx cap sync android
npx cap open android
```

`cap sync` 把 `dist/` 拷进 `android/app/src/main/assets/public` 并更新插件。`cap open` 用 Android Studio 打开 `android/` 工程。

### 2.3 出 debug APK

方式 A（Android Studio，推荐首次）：
- 顶部菜单 Build → Build Bundle(s)/APK(s) → Build APK(s)。
- 完成后点弹窗的 "locate" 找到 APK，路径通常是
  `frontend/android/app/build/outputs/apk/debug/app-debug.apk`。

方式 B（命令行）：
```bash
cd frontend/android
./gradlew assembleDebug        # Windows: gradlew.bat assembleDebug
# 产物：app/build/outputs/apk/debug/app-debug.apk
```

### 2.4 装到手机

- 手机开启「开发者选项」→「USB 调试」，用数据线连电脑。
- `adb install -r frontend/android/app/build/outputs/apk/debug/app-debug.apk`
- 或把 APK 传到手机，用文件管理器点击安装（需允许「未知来源」）。

---

## 3. 验证核心目标

### 3.1 登录与通知权限

1. 打开 app，用你的账号登录（走 token 认证，登录态存在本地，冷启动不丢）。
2. 首次进入含提醒的页面时，系统会弹出通知权限请求 → 选择「允许」。
   - 若没弹出：进入系统「设置 → 应用 → Time Agent → 通知」手动开启。

### 3.2 精确闹钟权限（Android 12+）

部分机型对「精确闹钟」单独管控，不开会导致提醒延迟或不响：

- 系统「设置 → 应用 → Time Agent → 闹钟和提醒」→ 允许。
- 国产 ROM（小米/华为/OPPO/vivo）还需：把 Time Agent 加入「自启动白名单」，电池策略设为「无限制 / 不优化」。否则系统可能拦截闹钟。

### 3.3 关键验证：杀死 app 后仍按时弹提醒

这是本次目标的核心，务必按此测：

1. 在 app 里（或网页端同账号）创建一条 **2~3 分钟后**触发的提醒。
2. 回到 app 的提醒页停留几秒，确保它已同步并预约（前台会自动同步）。
3. **从最近任务列表把 Time Agent 划掉，彻底关闭进程**（不是切后台）。
4. 锁屏，静置等待到触发时间。
5. **预期**：到点时通知栏弹出该提醒，标题为提醒内容，且 app 全程未运行。
6. 点击通知 → 应打开 app 并进入提醒页。

### 3.4 重启后仍有效（可选加测）

1. 创建一条 10 分钟后的提醒并同步。
2. 重启手机，不打开 app。
3. **预期**：到点仍弹出（插件自带 BootReceiver 会在开机后重排闹钟）。
   - 若不响：多为 ROM 自启动限制，回到 3.2 放开自启动。

---

## 4. 已知边界（当前范围内的正常表现）

- **只覆盖已同步的提醒**：本地通知基于「设备最后一次同步到的提醒」。在网页/别的设备刚创建、这台手机还没打开同步的提醒，不会响。跨设备实时性需后期的远程推送补足（已单独记录在
  [architecture/android-app-and-notifications-plan.md](architecture/android-app-and-notifications-plan.md)）。
- **简报通知**：本次未接入，属搁置项。
- **滚动窗口**：一次最多预约最近的 60 条提醒（`MAX_SCHEDULED`），避免触达系统闹钟数量上限；更远的会在后续同步时补排。

---

## 5. 发布正式包（后续）

debug APK 用自带 debug 签名，适合自测/侧载。要分发正式包：

1. 在仓库外生成并离线备份签名 keystore：`keytool -genkey -v -keystore timeagent.keystore -alias timeagent -keyalg RSA -keysize 2048 -validity 10000`
2. 在当前 shell 中设置 `TIME_AGENT_ANDROID_KEYSTORE_PATH`、`TIME_AGENT_ANDROID_KEYSTORE_PASSWORD`、`TIME_AGENT_ANDROID_KEY_ALIAS`、`TIME_AGENT_ANDROID_KEY_PASSWORD`。这些值不得写入仓库或项目 `.env`。
3. 执行 `./gradlew assembleRelease`。构建脚本会在缺少任一签名变量时拒绝生成 release 包，避免误发未签名或临时签名的 APK。

首次安装仍需用户允许「未知来源」。上应用商店需软著等资质，侧载则不需要。

---

## 6. 改了前端代码后如何更新 APK

```bash
cd frontend
VITE_API_BASE_URL=https://你的域名 npm run build
npx cap sync android
# 重新 assembleDebug 并安装
```

## 7. 应用内更新发布

包含应用内更新能力的 APK 需要先由用户手动安装一次。之后每个版本必须提高 `frontend/android/app/build.gradle` 的 `versionCode`，并使用同一份 release keystore 签名。将 APK 放到 HTTPS 静态地址后计算：

```bash
sha256sum app-release.apk
stat -c %s app-release.apk
```

仓库网关将主机 `releases/` 只读发布到 `/releases/<文件名>.apk`，不提供目录列表。先执行 `install -d -m 0755 releases`，确保 Nginx 可以遍历只读挂载目录；再将正式签名包复制到 `releases/timeagent-<版本>.apk`，并保持 APK 为 `0644`。把版本号、`https://steward.uresofa.me/releases/...` URL、SHA-256、字节数、发布时间和更新说明写入服务器 `.env` 的 `ANDROID_UPDATE_*`，重建或重启 Django 与 Nginx。App 会在“应用设置 → 检查更新”中读取清单。Android 仍要求用户授权“安装未知应用”并确认安装，这是系统安全边界，不能静默绕过。
