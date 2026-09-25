# Public Build Farm

Public, build-only GitHub Actions repository for compute-heavy projects owned by `Sharkecho`.

## Purpose

Use **standard GitHub-hosted runners in this PUBLIC repository** for heavy compilation.
Product/source repositories remain PRIVATE.

| Private source | Public build target | Runner |
| --- | --- | --- |
| `Sharkecho/MT3000` | LiveOS/OpenWrt base firmware | `ubuntu-22.04` | deployed · awaiting first real run |
| `Sharkecho/note9-liveos` | Samsung Note9 kernel | `ubuntu-22.04` |
| `Sharkecho/ai-translator` | Flutter/Android APK validation build | `ubuntu-latest` | deployed · awaiting first real run |
| `Sharkecho/CentoreOS` | Tauri/Rust Windows desktop build | `windows-latest` | deployed · awaiting first real run |

## Security boundary

- Workflows are **manual only** (`workflow_dispatch`).
- No untrusted PR/push can trigger private-source access.
- Private source is checked out only at runtime with `persist-credentials: false`.
- Required secret: `BUILD_FARM_SOURCE_TOKEN`.
- The token must be fine-grained and read-only, scoped only to the private source repositories above.
- Do not put production SSH keys, model/API keys, server credentials, device secrets, or runtime secrets here.
- Production deployment / provider verification stays in the private repositories.
- Do not use paid Larger Runners.
- Do not copy private source into this repository.
- Only approved non-secret build outputs/manifests may be uploaded as public Actions artifacts.

## Source token permissions

Recommended `BUILD_FARM_SOURCE_TOKEN`:

- Repository access: only `MT3000`, `note9-liveos`, `ai-translator`, `CentoreOS`.
- **Contents: Read-only**.
- No write permissions.
- Note9 baseline→UAC2 artifact reads use this PUBLIC repository's built-in `GITHUB_TOKEN`, not the private-source token.

## Global policy

Account-level rules: `Sharkecho/Sharkecho/GLOBAL_BUILD_COMPUTE_POLICY.md`.

## Private fallback

The original private-repository workflows are retained as **manual fallback only** until each public build path is proven with a real successful run.
