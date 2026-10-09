# CodingOS Agent Canvas on Public Build Farm

This repository can build approved private projects on GitHub-hosted runners. CodingOS is now an explicit project in that allowlist.

## Manual dispatch

Workflow: [CodingOS Agent Canvas Build](../actions/workflows/codingos-agent-canvas.yml)

Inputs:

- `source_sha`: a required full 40-character commit SHA from `Sharkecho/CodingOS-AgentCanvas`.
- `test_scope`: `targeted` runs lint, the CodingOS Vitest path, and the app build; `extended` additionally runs `build:lib`.
- `publish_artifacts`: off by default; when enabled, only redacted build metadata is uploaded.

The workflow does not accept a repository, branch, or shell command as input. It checks out the fixed approved repository at the requested full SHA with `BUILD_FARM_SOURCE_TOKEN`, verifies that `git rev-parse HEAD` matches the requested SHA, and writes the actual SHA and step outcomes to a redacted metadata report. The token must have Contents:Read access to CodingOS only (alongside the other explicitly approved repositories).

## Onboarding additional projects

“All projects” means all projects explicitly approved and added to the allowlist. Each project must get:

1. a dedicated workflow with a fixed `repository:` value;
2. fixed, reviewable build commands;
3. a policy validator covering permissions, refs, artifacts, and secrets;
4. a separate read-only repository grant on `BUILD_FARM_SOURCE_TOKEN`, or a separate token;
5. a documented rollback that disables only that project's workflow.

Do not replace the mapping with a user-supplied repository name or arbitrary command input. This public repository's artifacts are public; never upload source trees, credentials, private logs, or production evidence.

AI Translator v101 remains on its existing path until its owner separately approves migration after this workflow pattern has passed acceptance.
