#!/usr/bin/env python3
"""Apply only public, GUI-level Android Agent customization to pinned ClawGUI.

This script is deliberately independent of any private GPT-AndroidOS repo,
audio model, Android ROM, token or hardware API. It is idempotent.
"""
from __future__ import annotations

import argparse
from pathlib import Path

ALIASES = (
    '        "声音工作站" to "com.note9.uac2",',
    '        "USB 音频控制" to "com.note9.uac2",',
    '        "Note9 LiveAudio" to "com.note9.uac2",',
)
ANCHOR = "        // Social & Messaging"
PROMPTS_ANCHOR = '    val list: List<PromptCard> = listOf('
AUDIO_QUICK_CARDS = '''        PromptCard(
            id = "gpt_audio_health",
            emoji = "\\uD83C\\uDFA7",
            title = "音频系统自检",
            subtitle = "检查 USB、变声及连接状态",
            prompt = "/gui 打开声音工作站，只查看 USB 连接、音频源和当前变声模型状态，报告真实屏幕上的信息。不要修改参数或切换音频路由。若未安装，请明确说明。",
            accentHue = 165,
        ),
        PromptCard(
            id = "gpt_agent_health",
            emoji = "\\uD83D\\uDD0D",
            title = "设备状态检查",
            subtitle = "查看系统设置与设备信息",
            prompt = "/gui 打开系统设置，查看当前 Android 版本和设备信息，只读取并汇报，不修改任何系统设置。",
            accentHue = 215,
        ),
'''
WELCOME_OLD = 'text = "Hi, 我是 ClawGUI ✨",'
WELCOME_NEW = 'text = "GPT-AndroidOS · 智能工作台",'
SUBTITLE_OLD = 'text = "挑一张卡片快速开始,或直接告诉我你想做什么。",'
SUBTITLE_NEW = 'text = "音频 · 设备 · 自动任务\\n选择任务卡片，或直接输入你的指令。",'

OLD_LABEL = '<string name="app_name">ClawGUI</string>'
NEW_LABEL = '<string name="app_name">GPT-AndroidOS</string>'


def update_file(path: Path, old: str, new: str, verify_only: bool) -> None:
    data = path.read_text(encoding="utf-8")
    if old not in data and new not in data:
        raise RuntimeError(f"upstream patch anchor missing: {path}")
    if new in data:
        if old in data and old not in new:
            raise RuntimeError(f"ambiguous partial patch: {path}")
        return
    if data.count(old) != 1:
        raise RuntimeError(f"upstream patch anchor not unique: {path}")
    if verify_only:
        raise RuntimeError(f"patch not applied: {path}")
    path.write_text(data.replace(old, new, 1), encoding="utf-8")


def apply(root: Path, verify_only: bool, version_code: int = 2) -> None:
    if not (2 <= version_code <= 999999999):
        raise RuntimeError('version-code out of supported range')
    apps = root / "app/src/main/kotlin/com/clawgui/ng/runtime/phone/config/Apps.kt"
    strings = root / "app/src/main/res/values/strings.xml"
    data = apps.read_text(encoding="utf-8")
    existing = [alias in data for alias in ALIASES]
    if all(existing):
        pass
    elif any(existing):
        raise RuntimeError("partially patched Apps.kt; refusing to write")
    else:
        if data.count(ANCHOR) != 1:
            raise RuntimeError("upstream Apps.kt anchor not unique")
        if verify_only:
            raise RuntimeError("audio aliases not applied")
        apps.write_text(data.replace(ANCHOR, "\n".join(ALIASES) + "\n" + ANCHOR, 1), encoding="utf-8")
    update_file(strings, OLD_LABEL, NEW_LABEL, verify_only)
    prompts = root / "app/src/main/kotlin/com/clawgui/ng/data/PromptCards.kt"
    screen = root / "app/src/main/kotlin/com/clawgui/ng/ui/screens/ChatScreen.kt"
    update_file(prompts, PROMPTS_ANCHOR, PROMPTS_ANCHOR + "\n" + AUDIO_QUICK_CARDS, verify_only)
    update_file(screen, WELCOME_OLD, WELCOME_NEW, verify_only)
    update_file(screen, SUBTITLE_OLD, SUBTITLE_NEW, verify_only)

    # Online update is an optional user-confirmed APK upgrade, never a silent install.
    settings = root / "app/src/main/kotlin/com/clawgui/ng/ui/screens/SettingsScreen.kt"
    settings_src = settings.read_text(encoding="utf-8")
    widget_marker = "private fun InAppUpdateCard()"
    widget = '''
@androidx.compose.runtime.Composable
private fun InAppUpdateCard() {
    val context = androidx.compose.ui.platform.LocalContext.current
    val scope = androidx.compose.runtime.rememberCoroutineScope()
    var state by remember { mutableStateOf("可联网检查正式发布的新版本") }
    var pending by remember { mutableStateOf<com.clawgui.ng.runtime.update.InAppUpdater.Release?>(null) }
    var busy by remember { mutableStateOf(false) }

    Surface(
        shape = RoundedCornerShape(20.dp),
        color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.45f),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text("在线升级", style = MaterialTheme.typography.titleMedium)
            Text("当前版本：\u0024{com.clawgui.ng.runtime.update.InAppUpdater.installedVersion(context)}",
                style = MaterialTheme.typography.bodySmall)
            Text(state, style = MaterialTheme.typography.bodySmall)
            androidx.compose.material3.Button(
                enabled = !busy,
                onClick = {
                    val release = pending
                    if (release == null) {
                        scope.launch {
                            busy = true
                            state = "正在检查更新…"
                            try {
                                val available = com.clawgui.ng.runtime.update.InAppUpdater.check(context)
                                pending = available
                                state = if (available == null) "已经是最新正式版本"
                                else "发现版本 \u0024{available.versionName}，点击升级"
                            } catch (e: Exception) {
                                state = "检查失败：\u0024{e.message ?: "网络错误"}"
                            } finally { busy = false }
                        }
                    } else if (!com.clawgui.ng.runtime.update.InAppUpdater.mayRequestInstall(context)) {
                        state = "请允许本应用安装更新，然后再次点击升级"
                        com.clawgui.ng.runtime.update.InAppUpdater.openInstallPermission(context)
                    } else {
                        scope.launch {
                            busy = true
                            state = "正在下载并校验安装包…"
                            try {
                                val apk = com.clawgui.ng.runtime.update.InAppUpdater.download(context, release)
                                com.clawgui.ng.runtime.update.InAppUpdater.requestInstall(context, apk)
                                state = "请在安卓系统安装界面确认覆盖升级"
                            } catch (e: Exception) {
                                state = "升级失败：\u0024{e.message ?: "未知错误"}"
                            } finally { busy = false }
                        }
                    }
                },
            ) {
                Text(if (busy) "请稍候" else if (pending == null) "检查更新" else "立即升级")
            }
        }
    }
}
'''
    if widget_marker not in settings_src:
        if verify_only:
            raise RuntimeError("Update control not applied to SettingsScreen.kt")
        idx = settings_src.index("\n@Composable\nprivate fun SectionLabel")
        settings_src = settings_src[:idx] + "\n" + widget + settings_src[idx:]
        settings.write_text(settings_src, encoding="utf-8")
    update_file(settings,
                '        InfoCard("开源协议 Apache-2.0 · 仓库:github.com/ZJU-REAL/ClawGUI")',
                '        InfoCard("开源协议 Apache-2.0 · 仓库:github.com/ZJU-REAL/ClawGUI")\n        InAppUpdateCard()',
                verify_only)

    update_file(settings, 'SettingsRowSpec("关于", "版本、协议、项目",',
                'SettingsRowSpec("关于与在线升级", "检查更新、版本和协议",', verify_only)
    update_file(settings, 'data object About : SettingsPage("关于")',
                'data object About : SettingsPage("关于与在线升级")', verify_only)
    update_file(settings, 'Text("ClawGUI", style = MaterialTheme.typography.titleLarge,',
                'Text("GPT-AndroidOS", style = MaterialTheme.typography.titleLarge,', verify_only)
    update_file(settings, 'Text("v0.2.0 · NG", style = MaterialTheme.typography.labelMedium,',
                'Text("v${com.clawgui.ng.BuildConfig.VERSION_NAME} · Android Agent", style = MaterialTheme.typography.labelMedium,', verify_only)
    update_file(settings, 'Text("ClawGUI · NG", style = MaterialTheme.typography.headlineSmall)',
                'Text("GPT-AndroidOS", style = MaterialTheme.typography.headlineSmall)', verify_only)
    update_file(settings, 'Text("版本 0.2.0", style = MaterialTheme.typography.bodyMedium,',
                'Text("版本 ${com.clawgui.ng.BuildConfig.VERSION_NAME}", style = MaterialTheme.typography.bodyMedium,', verify_only)

    manifest = root / "app/src/main/AndroidManifest.xml"
    update_file(manifest,
                '    <uses-permission android:name="android.permission.INTERNET" />',
                '    <uses-permission android:name="android.permission.INTERNET" />\n    <uses-permission android:name="android.permission.REQUEST_INSTALL_PACKAGES" />',
                verify_only)
    provider_paths = root / "app/src/main/res/xml/file_provider_paths.xml"
    update_file(provider_paths, '</paths>',
                '    <cache-path name="app_updates" path="updates/" />\n</paths>',
                verify_only)
    updater_file = root / "app/src/main/kotlin/com/clawgui/ng/runtime/update/InAppUpdater.kt"
    update_template = Path(__file__).resolve().parent / "agent-update/InAppUpdater.kt"
    expected = update_template.read_bytes()
    if updater_file.exists():
        if updater_file.read_bytes() != expected:
            raise RuntimeError("Updater Kotlin source differs from pinned public template")
    elif verify_only:
        raise RuntimeError("Updater Kotlin source not applied")
    else:
        updater_file.parent.mkdir(parents=True, exist_ok=True)
        updater_file.write_bytes(expected)

    gradle = root / "app/build.gradle.kts"
    update_file(gradle, 'versionCode = 1', f'versionCode = {version_code}', verify_only)
    update_file(gradle, 'versionName = "0.2.0"', f'versionName = "0.2.0-gpt.{version_code}"', verify_only)

    check = apps.read_text(encoding="utf-8")
    label = strings.read_text(encoding="utf-8")
    if not all(a in check for a in ALIASES) or NEW_LABEL not in label:
        raise RuntimeError("post-patch validation failed")
    print("GUI_AUDIO_ALIAS=PASS")
    print("APP_NAME=GPT-AndroidOS")
    print("AGENT_HOME_QUICK_CARDS=2")
    print("IN_APP_UPDATE=USER_APPROVED_SIGNED_APK")
    print("REALTIME_AUDIO_UNCHANGED=YES")
    print("PRIVILEGED_AUDIO_BRIDGE=NOT_IMPLEMENTED")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--version-code", type=int, default=2)
    args = parser.parse_args()
    apply(args.source, args.verify_only, args.version_code)


if __name__ == "__main__":
    main()
