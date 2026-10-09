# GPT-AndroidOS｜正式在线升级链路（SSOT）

## 状态和边界
- 公共仓库负责**公开 ClawGUI 源码**的 APK 构建及指定的 AndroidOS 正式发布；不拉取私有源码。
- 自动运行的 `gpt-androidos-agent.yml` **仅用于 Debug/烟测**，不得用其签名或上传正式包。
- 正式链路单独使用 `gpt-androidos-production-release.yml`，仅主分支、仅手动启动，签名步骤处于受保护的 `androidos-production` 环境。
- 专用 AndroidOS 发布签名 JKS **仅作为 GitHub 环境加密 Secret 保存**，不提交 Git；禁止复用其他 App、服务器、设备、模型的密钥。由于仓库公开，**必须**设环境审批人和只允许 main 分支部署；否则禁止配置密钥或启动生产工作流。
- 签名固定：签名证书指纹与环境变量 `ANDROIDOS_CERT_SHA256` 不一致时立即失败。版本号必须严格递增。不能因编译成功就视为真机升级验证通过。
- 普通 Android 的安装器仍需用户确认，禁止 Root 静默安装。
- 发布后的 `stable.json` 不应手工编辑。流程**先构建、签名、校验、发布 GitHub Release 文件，再更新更新清单**；任何中途失败不会给用户推送一个未准备好的新版本。

## 只需做一次的人工初始化
1. 在可信本地设备安装 JDK，创建**唯一且长期不变**的 AndroidOS 发布用 keystore（**不要把 keystore、私钥或密码发到聊天、Issue、普通日志**）：
   `keytool -genkeypair -v -keystore androidos-release.jks -alias androidos -keyalg RSA -keysize 3072 -validity 10000`
   自行设置强随机的 keystore 和 key 密码。将 keystore 加密备份到两个安全地点；**密钥丢失将破坏未来覆盖升级**。
2. 运行 `keytool -list -v -keystore androidos-release.jks -alias androidos`，记录 **SHA256** 证书指纹（去掉冒号、转小写，是 64 个十六进制字符）。
3. GitHub → `Sharkecho/Public-Build-Farm` → Settings → Environments → 创建 `androidos-production`。**设置 Required reviewers，并限制 deployment branches 为 main**；仅可信管理员可审批；确认 GitHub Actions 对本仓库允许 `contents: write` 的令牌权限。
4. 在该 Environment 中配置以下 **Secrets**（不是 Variables）：
   - `ANDROIDOS_SIGNING_KEYSTORE_B64`：JKS 二进制的 Base64（Windows PowerShell：`[Convert]::ToBase64String([IO.File]::ReadAllBytes('androidos-release.jks'))`；Linux/macOS：`base64 < androidos-release.jks | tr -d '\\n'`）
   - `ANDROIDOS_SIGNING_STORE_PASSWORD`
   - `ANDROIDOS_SIGNING_KEY_PASSWORD`
   - `ANDROIDOS_SIGNING_KEY_ALIAS`（示例 `androidos`）
   在该 Environment 中配置以下 **Variable**：`ANDROIDOS_CERT_SHA256`（上一步证书 SHA-256 指纹）。
5. 在 Actions → `GPT-AndroidOS Signed Production Release` → Run workflow，选择 `main`，第一次输入 `version_code=3`；审批受保护环境。**不得通过将明文私钥提交到仓库来绕过环境配置**。

## 每次发布自动执行的质量门禁
1. `unittest`：更新清单格式、递增版本、防回滚。
2. 精确检出固定上游提交，并应用/反向核对补丁。
3. Android Release 构建（无需 8GB 本地电脑全量编译）。
4. `zipalign`、`apksigner` 使用专用 JKS 签名；核对证书指纹、包名 `com.clawgui.ng`、`versionCode`、`versionName`、ZIP 完整性与 SHA-256。
5. 发布不可变的 GitHub Release `gpt-androidos-v<versionCode>` / `gpt-androidos.apk`。
6. 带并发/旧文件 SHA 防冲突写入 `updates/gpt-androidos/stable.json`。旧客户端检查此固定地址；下载校验 SHA-256、包名、版本号和安装包签名后才打开 Android 安装确认界面。

## 安装迁移（必须特别说明）
- 手机当前 `0.2.0-gpt.2` 为 GitHub Runner 临时 **Debug 签名**；首次发布的长期签名 APK **不能直接覆盖安装**该版本。
- 老客户端若发现不同签名，会在下载后阻止直接安装，并提示先备份配置后迁移，这是正确的安全行为。
- **首次正式版迁移需要用户在确认已备份账号/密钥/配置之后，卸载旧版并安装正式版；卸载可能删除现有应用数据。** 不要承诺零损数据迁移。可另行开发经测试的导出/导入向导。
- **从首次正式签名版起**，只要发布证书保持一致，就可以在应用内“检查更新 → 立即升级 → 系统确认安装”覆盖升级。

## 运维、错误和回滚
- 不能强制取消 GitHub 环境审批或自动静默签名。若主分支被恶意修改，保护规则必须阻止读取证书 Secret。
- 若 APK 已发布但写 `stable.json` 失败，旧客户端仍看旧版；**不得人为上传未签名包、不得修改已发布包**。核对现有 Release/manifest 后，由维护者恢复发布流程。
- 回滚**不降低** `versionCode`：恢复旧代码但使用更高版本号、同一证书重新发布；不要回滚线上 manifest 指向较低版本。
- 关键信息：可在 Actions 查看构建和签名 SHA/指纹的一致性，但不应记录密钥字节或口令。
- 正式上线验证包括：首次正式 APK 安装、真实安卓真机检查更新、签名一致覆盖升级、模拟无网络/损坏 APK/签名不一致/版本回滚、权限不足、安装取消恢复。没有真机结果只能标记 `BUILD_VERIFIED`，不能标记 `DEVICE_VERIFIED`。

## 一键本地初始化（推荐；不需要手动填写五个密钥栏）
- 安全起见，**不要**在聊天云容器生成签名密钥；应让 `keytool` 在用户自己的 Windows 电脑上运行。需要安装 JDK 17+、GitHub CLI 且 `gh auth login` 已登录 Sharkecho。
- 本仓库脚本：`scripts/agent-update/init-production-signing.ps1`。在此仓库目录用 PowerShell 运行：
  `powershell -NoProfile -ExecutionPolicy Bypass -File .\\scripts\\agent-update\\init-production-signing.ps1`
- 脚本先核验 GitHub 环境有审批人、禁止管理员绕过、只允许 `main`；然后在用户电脑的 `~/.gpt-androidos-signing/` 创建或复用 `androidos-release.p12`。它生成独立强随机口令，使用当前 Windows 用户的 DPAPI 加密本地密码文件 `password.dpapi`，并通过 `gh secret set --env androidos-production` 直接写入加密 Secret（不将秘钥写入命令参数、日志或源码）。
- 自动录入四个 Environment Secrets 和一个 Environment Variable `ANDROIDOS_CERT_SHA256`；已有不同签名指纹立即中止，禁止误轮换生产签名密钥。
- **务必离线备份** `.p12` 和可跨电脑恢复的密码副本（保险箱或密码管理器）。`password.dpapi` 仅当前 Windows 用户/机器可解密，复制它不构成有效异机备份；没有密钥+密码备份，今后无法保证恢复续签能力。
- 首次正式生产发行从 `version_code=3` 开始。可在 GitHub Actions 手动执行生产流水线，或者通过经审核的主分支请求触发；受保护环境的人工审批**不可绕过**。
- 若首次正式签名 APK 与手机现有临时 Debug 签名不兼容，必须先备份应用配置，并进行一次手动正式版迁移。今后同签名版本可使用 APP 内更新入口。

