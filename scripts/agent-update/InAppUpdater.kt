package com.clawgui.ng.runtime.update

import android.content.Context
import android.content.Intent
import android.net.Uri
import androidx.core.content.FileProvider
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream
import java.io.ByteArrayOutputStream
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest

/** A versioned, user-approved APK installer. Never performs a silent/root install. */
object InAppUpdater {
    const val METADATA_URL =
        "https://raw.githubusercontent.com/Sharkecho/Public-Build-Farm/main/updates/gpt-androidos/stable.json"
    private const val MAX_METADATA = 16 * 1024
    private const val MAX_APK = 100L * 1024 * 1024

    data class Release(
        val versionCode: Long,
        val versionName: String,
        val apkUrl: String,
        val sha256: String,
    )

    fun installedVersion(context: Context): Long {
        val info = context.packageManager.getPackageInfo(context.packageName, 0)
        return if (android.os.Build.VERSION.SDK_INT >= 28) info.longVersionCode
            else @Suppress("DEPRECATION") info.versionCode.toLong()
    }

    private fun connection(url: String): HttpURLConnection {
        val connection = (URL(url).openConnection() as HttpURLConnection)
        connection.connectTimeout = 12000
        connection.readTimeout = 20000
        connection.instanceFollowRedirects = true
        connection.setRequestProperty("User-Agent", "GPT-AndroidOS-Updater/1")
        connection.setRequestProperty("Accept", "application/json")
        return connection
    }

    suspend fun check(context: Context): Release? = withContext(Dispatchers.IO) {
        val conn = connection(METADATA_URL)
        try {
            require(conn.responseCode == 200) { "更新服务不可用：HTTP ${conn.responseCode}" }
            require(conn.contentLengthLong <= MAX_METADATA) { "更新清单超过大小限制" }
            val bytes = conn.inputStream.use { input ->
                val output = ByteArrayOutputStream()
                val buffer = ByteArray(4096)
                while (true) {
                    val count = input.read(buffer)
                    if (count < 0) break
                    require(output.size() + count <= MAX_METADATA) { "更新清单超过大小限制" }
                    output.write(buffer, 0, count)
                }
                output.toByteArray()
            }
            require(bytes.size <= MAX_METADATA) { "更新清单超过大小限制" }
            val metadata = JSONObject(String(bytes, Charsets.UTF_8))
            require(metadata.optInt("schema_version", 0) == 1) { "更新协议版本不支持" }
            val code = metadata.optLong("version_code", 0L)
            if (code <= installedVersion(context)) return@withContext null
            val tag = "gpt-androidos-v$code"
            val expectedUrl = "https://github.com/Sharkecho/Public-Build-Farm/releases/download/$tag/gpt-androidos.apk"
            val actualUrl = metadata.getString("apk_url")
            val checksum = metadata.getString("sha256").lowercase()
            require(actualUrl == expectedUrl) { "升级包地址不在受信范围" }
            require(Regex("[0-9a-f]{64}").matches(checksum)) { "升级包校验值无效" }
            Release(code, metadata.optString("version_name", tag).take(60), actualUrl, checksum)
        } finally {
            conn.disconnect()
        }
    }

    suspend fun download(context: Context, release: Release): File = withContext(Dispatchers.IO) {
        val dir = File(context.cacheDir, "updates")
        check(dir.isDirectory || dir.mkdirs()) { "无法建立下载缓存" }
        val temporary = File(dir, "next.apk.part")
        val verified = File(dir, "next.apk")
        temporary.delete()
        val digest = MessageDigest.getInstance("SHA-256")
        try {
            val conn = connection(release.apkUrl)
            try {
                require(conn.responseCode == 200) { "下载失败：HTTP ${conn.responseCode}" }
                require(conn.contentLengthLong <= MAX_APK) { "升级包超过体积限制" }
                var total = 0L
                conn.inputStream.use { input ->
                    FileOutputStream(temporary).use { output ->
                        val buffer = ByteArray(65536)
                        while (true) {
                            val n = input.read(buffer)
                            if (n == -1) break
                            total += n
                            require(total <= MAX_APK) { "升级包超过体积限制" }
                            digest.update(buffer, 0, n)
                            output.write(buffer, 0, n)
                        }
                    }
                }
                require(total > 0L) { "升级包为空" }
            } finally {
                conn.disconnect()
            }
            val hash = digest.digest().joinToString("") { "%02x".format(it) }
            require(hash == release.sha256) { "下载文件 SHA-256 校验失败" }

            @Suppress("DEPRECATION")
            val packageInfo = context.packageManager.getPackageArchiveInfo(temporary.absolutePath, 0)
                ?: throw IllegalArgumentException("升级包不是有效的 APK")
            require(packageInfo.packageName == context.packageName) { "升级包包名不匹配" }
            val apkCode = if (android.os.Build.VERSION.SDK_INT >= 28) packageInfo.longVersionCode
                else @Suppress("DEPRECATION") packageInfo.versionCode.toLong()
            require(apkCode == release.versionCode) { "升级包版本号不匹配" }
            verified.delete()
            check(temporary.renameTo(verified)) { "无法保存已验证的升级包" }
            verified
        } catch (ex: Exception) {
            temporary.delete()
            throw ex
        }
    }

    fun mayRequestInstall(context: Context): Boolean =
        android.os.Build.VERSION.SDK_INT < 26 || context.packageManager.canRequestPackageInstalls()

    fun openInstallPermission(context: Context) {
        val intent = Intent(
            android.provider.Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
            Uri.parse("package:${context.packageName}"),
        ).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        context.startActivity(intent)
    }

    /** Prompts the system installer; requires confirmation on normal Android phones. */
    fun requestInstall(context: Context, apk: File) {
        check(mayRequestInstall(context)) { "请先允许本应用安装更新" }
        val uri = FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", apk)
        val intent = Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(uri, "application/vnd.android.package-archive")
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        context.startActivity(intent)
    }
}
