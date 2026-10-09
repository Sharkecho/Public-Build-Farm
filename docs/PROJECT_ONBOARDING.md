# Private Project → Public Build Farm 接入流程

本流程适用于所有新项目。Public-Build-Farm 是公开仓库和构建入口；项目源码必须留在项目自己的私有 GitHub 仓库中。

## 1. 创建或确认私有源码仓库

项目负责人先创建私有仓库，并确认：

- 仓库可见性为 Private；
- 默认分支和受保护分支已确定；
- 生产 Secrets 不提交到仓库；
- `.env`、私钥、部署凭据和本地工作目录已加入忽略规则；
- 项目已有本地构建命令和最小验证命令。

不要把源码复制到 Public-Build-Farm。仓库改名或迁移时，应先建立备份和回滚点，再更新白名单。

## 2. 填写接入申请

复制 `docs/project-onboarding-request.example.md`，提交以下信息：

- 准确的 `owner/repository`；
- 默认分支或允许的 commit ref；
- 构建系统和 Node/Python/Java/Rust/Flutter 版本；
- smoke/full 测试命令；
- 允许上传的非敏感 artifact；
- 是否允许访问私有源码；
- 是否保留旧 Runner 作为回滚路径。

## 3. 配置最小权限

为 Public-Build-Farm 使用的 fine-grained token 或 GitHub App 单独授权该私有仓库：

- `Contents: Read` only；
- 不授予写代码、管理仓库、Secrets、Deployments 或生产环境权限；
- 不复用项目生产密钥；
- 不把 token 写进 workflow 或日志。

每新增一个项目，都必须显式扩展 repository allowlist；禁止使用组织级通配授权。

## 4. 增加独立 workflow

每个项目有自己的固定 workflow：

- `workflow_dispatch` 默认触发；
- `repository:` 固定为批准的私有仓库；
- 输入只能选择受控 ref 和预定义验证范围；
- 构建命令写在 workflow 中，不接受 `command`、`shell` 或 `script` 输入；
- `persist-credentials: false`；
- 设置 timeout 和 concurrency；
- artifact 路径固定且只包含脱敏产物。

CodingOS 的参考实现是 `.github/workflows/codingos-agent-canvas.yml`。

## 5. 验证顺序

1. workflow 静态策略校验；
2. 私有仓库只读 checkout；
3. Hello World / smoke 构建；
4. 失败任务和日志回传；
5. full 测试和构建；
6. artifact 脱敏检查；
7. 仅在验收通过后考虑自动触发。

项目必须能单独失败、单独回滚，不能因一个项目失败而改变其他项目的 workflow 或 Runner。

## 6. 回滚

回滚顺序：禁用该项目 workflow → 恢复项目原有 CI/Runner → 保留构建日志和 commit SHA → 撤销该项目的只读授权。不得删除原仓库、原 Runner 或原密钥作为回滚动作。
