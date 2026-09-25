# AGENTS.md — Public Build Farm

This repository is PUBLIC and build-only.

## Mandatory rules

1. Never add product/private source code to this repository.
2. Heavy compilation belongs here; lightweight control-plane tests do not.
3. All private-source workflows must be manual (`workflow_dispatch`) unless the owner explicitly approves another trusted trigger.
4. Private checkout uses `BUILD_FARM_SOURCE_TOKEN`, read-only, with `persist-credentials: false`.
5. Never print tokens or production secrets.
6. Never add production deployment logic here.
7. Never use paid Larger Runners without explicit approval.
8. Public artifacts must not contain private source, raw private evidence, credentials, or private server/device configuration.
9. A copied workflow must be adapted so `github.sha`, `github.repository`, `GITHUB_TOKEN`, release/run lookups, and repository-relative paths refer to the private source correctly.
10. Keep the private workflow as manual fallback until the public path has a real PASS.

Global policy: https://github.com/Sharkecho/Sharkecho/blob/main/GLOBAL_BUILD_COMPUTE_POLICY.md
