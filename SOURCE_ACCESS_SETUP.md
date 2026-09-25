# One-time source access setup

The public build workflows are already deployed. They need one repository Actions secret to read the private source repositories at runtime.

## 1. Create a fine-grained PAT

GitHub account settings → Developer settings → Personal access tokens → Fine-grained tokens.

Recommended configuration:

- Resource owner: `Sharkecho`
- Repository access: **Only select repositories**
  - `MT3000`
  - `note9-liveos`
  - `ai-translator`
  - `CentoreOS`
- Repository permissions:
  - **Contents: Read-only**
  - everything else: No access / default

Do not grant write, administration, secrets, deployment, or package permissions.

## 2. Store it only in Public-Build-Farm Actions secrets

Repository: `Sharkecho/Public-Build-Farm`

Settings → Secrets and variables → Actions → New repository secret

Name:

`BUILD_FARM_SOURCE_TOKEN`

Value: the fine-grained PAT created above.

## 3. First verification order

Run only one small/fast public build first:

1. `AI Translator Android Build (public build farm)`, source_ref=`main`, publish_apk=false.
2. After PASS, run `CentoreOS Desktop Build`, publish_binary=false.
3. Then run Note9 baseline when needed.
4. Run MT3000 LiveOS base last because it is the longest build.

Do not enable automatic push/PR triggers after verification.

## 4. Public artifact warning

Public-Build-Farm is public. Any uploaded Actions artifact must be treated as publicly visible.

- AI Translator APK upload is OFF by default.
- CentoreOS EXE upload is OFF by default.
- MT3000/Note9 build artifacts are intended build outputs; never add source archives or private evidence bundles to uploads.
