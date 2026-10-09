# Public Build Farm 项目接入申请模板

```yaml
project: ""
source_repository: "OWNER/PRIVATE_REPOSITORY"
default_ref: "main"
source_visibility: "private"
build_system: "npm|python|rust|flutter|other"
runtime_version: ""
smoke_commands:
  - ""
full_commands:
  - ""
approved_artifacts:
  - ""
needs_private_checkout: true
keep_existing_runner_for_rollback: true
owner: ""
```

提交前确认：没有生产密钥、私钥、Token、完整环境变量或私有日志；`source_repository` 已由项目负责人确认；构建命令不依赖任意用户输入。
