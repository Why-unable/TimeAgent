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
- 设置 `JAVA_HOME` 指向 JDK 21，并把 `%JAVA_HOME%\bin` 加入 PATH。
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
- **简报通知**：已支持确定性的定时晚报系统通知；模型编辑和外部推送供应商仍不在当前闭环内。
- **滚动窗口**：一次最多预约最近的 60 条提醒（`MAX_SCHEDULED`），避免触达系统闹钟数量上限；更远的会在后续同步时补排。

---

## 5. 发布正式包

### 5.1 当前生产签名（兼容性关键）

当前生产签名链（包括 `1.1.7`）实际使用以下签名；后续版本除非完成经过验证的签名迁移，也必须保持一致：

- keystore：`/home/hyj/.android/debug.keystore`
- alias：`androiddebugkey`
- 证书 SHA-256：`e7fb9f63eff74b44c3ec32dafdcb2c726ff2d031c5c7614f70dda486916a783e`
- 凭据：Android debug keystore 的常规默认值（store/key password 均为 `android`）

文件名虽然是 `debug.keystore`，但对当前生产安装而言，它已经成为不可替换的发布身份。应用内覆盖更新必须继续使用同一文件；删除、重新生成或改用新 keystore 都会导致 Android 拒绝覆盖安装。应立即将该文件备份到仓库外的加密存储，限制文件权限，并定期验证备份可读取。不得把 keystore 本体提交到 Git。

构建前必须将当前线上 APK 与 keystore 的证书指纹进行比对：

```bash
keytool -list -v \
  -keystore /home/hyj/.android/debug.keystore \
  -storepass android \
  -alias androiddebugkey

/home/hyj/Android/Sdk/build-tools/36.0.0/apksigner \
  verify --print-certs releases/timeagent-<当前版本>.apk
```

两边的 SHA-256 指纹必须完全一致，才能继续发布。

### 5.2 构建兼容更新包

先提高 `frontend/android/app/build.gradle` 中的 `versionCode` 和 `versionName`，再执行：

```bash
cd /home/hyj/Project/TimeAgent/frontend
VITE_API_BASE_URL=https://steward.uresofa.me npm run build
npx cap sync android

cd android
TIME_AGENT_ANDROID_KEYSTORE_PATH=/home/hyj/.android/debug.keystore \
TIME_AGENT_ANDROID_KEYSTORE_PASSWORD=android \
TIME_AGENT_ANDROID_KEY_ALIAS=androiddebugkey \
TIME_AGENT_ANDROID_KEY_PASSWORD=android \
./gradlew assembleRelease
```

产物为 `frontend/android/app/build/outputs/apk/release/app-release.apk`。构建脚本会在缺少任一签名变量时拒绝生成 release 包。

对于尚未发布过 APK 的全新部署，应在第一次发布前生成专用 release keystore，并离线备份；不要照搬本项目的历史 debug 签名。已经安装当前 APK 的部署不能直接切换新证书。

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

包含应用内更新能力的 APK 需要先由用户手动安装一次。之后每个版本必须提高 `frontend/android/app/build.gradle` 的 `versionCode`，并使用 5.1 中同一份 keystore 签名。将 APK 放到 HTTPS 静态地址后计算：

```bash
sha256sum app-release.apk
stat -c %s app-release.apk
```

当前主机的 `/home/hyj/Project/TimeAgent` 就是运行中的生产 Compose checkout，不需要先寻找远程 SSH 主机。仓库网关将主机 `releases/` 只读发布到 `/releases/<文件名>.apk`，不提供目录列表。先执行 `install -d -m 0755 releases`，确保 Nginx 可以遍历只读挂载目录；再将正式签名包复制到 `releases/timeagent-<版本>.apk`，并保持 APK 为 `0644`。把版本号、`https://steward.uresofa.me/releases/...` URL、SHA-256、字节数、发布时间和更新说明写入服务器 `.env` 的 `ANDROID_UPDATE_*`，重建 Django、前端和 Nginx：

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  up -d --build django frontend nginx
```

随后确认 Django 已加载新版本、Nginx 挂载文件的 SHA-256 与 `.env` 一致，并检查 `/health/ready`。App 会在“应用设置 → 检查更新”中通过认证后的 `/api/v1/app-updates/android/latest/` 读取清单。Android 仍要求用户授权“安装未知应用”并确认安装，这是系统安全边界，不能静默绕过。

## 8. 最近一次仓库内验证

2026-08-25 在 JDK/Android SDK 已配置的本机为 `1.1.7`（`versionCode 11`）执行：

```bash
cd frontend
VITE_API_BASE_URL=https://steward.uresofa.me npm run build
npx cap sync android
cd android
TIME_AGENT_ANDROID_KEYSTORE_PATH=/home/hyj/.android/debug.keystore \
TIME_AGENT_ANDROID_KEYSTORE_PASSWORD=android \
TIME_AGENT_ANDROID_KEY_ALIAS=androiddebugkey \
TIME_AGENT_ANDROID_KEY_PASSWORD=android \
./gradlew testDebugUnitTest lintDebug assembleRelease
```

结果为 `BUILD SUCCESSFUL`，release APK 位于
`frontend/android/app/build/outputs/apk/release/app-release.apk`，大小为 `4,165,146` 字节，SHA-256 为
`4b637e4c3eaa1fec21f413166f09827c9561dd8f37342698567694349435069b`。APK 使用 v2 签名、通过
zipalign，签名证书 SHA-256 与 `1.1.6` 一致。正式文件已发布为 `releases/timeagent-1.1.7.apk`；从
`https://steward.uresofa.me/releases/timeagent-1.1.7.apk` 重新下载后，manifest 为 `1.1.7 / 11`，字节数、文件 SHA-256 和签名证书均保持一致。
生产更新清单已加载 `1.1.7 / 11`，Django、前端和 Nginx 已切换，`/health/ready` 返回 database/Redis `ok`。
这些证据证明构建、发布和下载链路成立，不代表真机行为已经验收。

### 8.1 旧安装器版本显示缓存事件

2026-08-25 收到真机反馈：App 已展示可下载 `1.1.6`，但系统安装界面仍显示 `1.1.5`。复查确认本地发布文件和公网回下载文件的
manifest 均为 `1.1.6 / 10`，大小、SHA-256 和签名也一致，因此没有证据表明服务器实际发布了 1.1.5。旧更新器会把每次下载都覆盖到
`cache/updates/timeagent-update.apk`，并始终向系统安装器提供相同的 FileProvider URI；系统安装器复用该 URI 的旧包元数据是当前最符合证据的
解释，但在取得设备日志前仍属于推断。

`1.1.7 / 11` 已将缓存文件名改为 `timeagent-update-<versionCode>-<sha256-prefix>.apk`，下载前清理旧更新文件并禁用 HTTP 连接缓存；
校验边界从包名、versionCode、SHA-256、签名扩展为同时校验 versionName。这样每个发布版本获得不同的 content URI，避免后续升级复用旧
安装元数据。由于 1.1.5/1.1.6 中仍运行旧更新器，若首次升级的系统安装界面继续显示旧版本，应取消安装，使用浏览器直接下载
`https://steward.uresofa.me/releases/timeagent-1.1.7.apk` 后安装，或清除 Time Agent 的应用缓存后重新下载；不得在版本显示不正确时继续确认安装。

执行 `adb devices -l` 时没有发现已连接设备，因此以下场景仍标记为 **NOT VERIFIED**：进程被杀后到点通知、通知按钮重复点击、离线动作重放、重启后重排以及失败反馈。必须按第 3 节在真机或模拟器上留下设备型号、Android 版本、步骤和结果后，才能把原生通知动作改为 PASS。
