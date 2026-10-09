# GPT-AndroidOS — safe online updates

**Development status:** In-app Settings -> About -> Check for updates is implemented in the public ClawGUI-derived build, but a **signed stable APK has not yet been published**. The public channel at `updates/gpt-androidos/stable.json` currently advertises version 0 (no stable release).

## What the button does

1. Read public `stable.json` over HTTPS and compare `version_code` to the installed app.
2. Allow downloading only an APK from the fixed public GitHub Releases path.
3. Validate the SHA-256, exact Android package `com.clawgui.ng`, and expected newer version.
4. Open Android's system APK installer. On ordinary devices the user **must confirm**. On Android 8+ the user may need to approve this app as an update-installation source once.
5. Existing app data stays in place only when package ID and signing certificate match and install succeeds.

A new native Android release always requires replacing the installed APK; it is not possible to silently hot-swap arbitrary Kotlin or C++ code inside a normal Android app.

## Required permanent release signing: one-time setup

**Never use the GitHub-hosted runner's ephemeral debug signing key for production OTA upgrades.**

Generate a dedicated keystore on a trusted workstation and back it up offline:

```powershell
keytool -genkeypair -keystore "$env:USERPROFILE\GPT-AndroidOS-release.jks" -alias gptandroidos -keyalg RSA -keysize 3072 -validity 10000
```

Keep its passwords private. In **Public-Build-Farm -> Settings -> Secrets and variables -> Actions**, configure **four** repository Secrets:

| Secret | Value |
| --- | --- |
| `GPT_ANDROIDOS_KEYSTORE_B64` | Base64-encoded bytes of the dedicated JKS |
| `GPT_ANDROIDOS_STORE_PASSWORD` | JKS password |
| `GPT_ANDROIDOS_KEY_ALIAS` | `gptandroidos` (or the actual alias) |
| `GPT_ANDROIDOS_KEY_PASSWORD` | Private-key password |

PowerShell command to copy the Base64 JKS value locally (paste **only in GitHub Secret**, never in chat):

```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("$env:USERPROFILE\GPT-AndroidOS-release.jks")) | Set-Clipboard
```

Then manually run `GPT-AndroidOS Signed Release` workflow on `main`, first stable `version_code=3`, `confirm_public_release=true`. It fails closed when any key secret is missing; builds the same **public-only** Agent source; signs with the persistent key; verifies APK signature and SHA-256; creates an immutable GitHub Release; updates the public stable manifest. Subsequent releases must increase `version_code` and use the exact same signing key.

**IMPORTANT:** Existing Debug APKs have ephemeral build-time certificates. First migration to a stable-signed APK may require backing up and uninstalling the Debug APK. Never uninstall without protecting settings/data first; once stable-signed v3 is installed, v4+ can be installed as an upgrade without uninstalling.

## Source privacy boundary

This is a PUBLIC channel. It must contain only public ClawGUI-based Android Agent code and generic patches. Do not push private audio, kernel, ROM, models, user configuration or logs. If private native components are added, change to a **private authenticated update channel** before releasing; never leak them through this repository.

The update flow is **not** device-tested yet: successful Gradle compilation does not validate unknown-sources permission prompts, Android package installer behavior or signer continuity.
