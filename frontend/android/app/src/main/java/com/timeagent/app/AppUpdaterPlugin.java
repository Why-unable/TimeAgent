package com.timeagent.app;

import android.content.Intent;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.content.pm.Signature;
import android.net.Uri;
import android.os.Build;
import android.provider.Settings;
import androidx.core.content.FileProvider;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.HashSet;
import java.util.Locale;
import java.util.Set;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

@CapacitorPlugin(name = "AppUpdater")
public class AppUpdaterPlugin extends Plugin {
    private static final long MAX_APK_BYTES = 250L * 1024L * 1024L;
    private final ExecutorService executor = Executors.newSingleThreadExecutor();

    @PluginMethod
    public void getInstalledAppInfo(PluginCall call) {
        try {
            PackageInfo info = getContext().getPackageManager().getPackageInfo(getContext().getPackageName(), 0);
            JSObject result = new JSObject();
            result.put("versionCode", longVersionCode(info));
            result.put("versionName", info.versionName == null ? "" : info.versionName);
            result.put("canRequestPackageInstalls", canRequestPackageInstalls());
            call.resolve(result);
        } catch (PackageManager.NameNotFoundException exception) {
            call.reject("无法读取当前应用版本。", "APP_INFO_UNAVAILABLE", exception);
        }
    }

    @PluginMethod
    public void openInstallPermissionSettings(PluginCall call) {
        Intent intent = new Intent(
            Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
            Uri.parse("package:" + getContext().getPackageName())
        );
        getActivity().startActivity(intent);
        call.resolve();
    }

    @PluginMethod
    public void downloadAndInstall(PluginCall call) {
        String downloadUrl = call.getString("downloadUrl", "");
        String expectedSha256 = call.getString("sha256", "").toLowerCase(Locale.ROOT);
        Integer expectedVersionCode = call.getInt("expectedVersionCode");
        String expectedVersionName = call.getString("expectedVersionName", "").trim();
        Long expectedSizeBytes = call.getLong("expectedSizeBytes");
        if (
            !downloadUrl.startsWith("https://")
                || !expectedSha256.matches("[0-9a-f]{64}")
                || expectedVersionCode == null
                || expectedVersionCode <= 0
                || expectedVersionName.isEmpty()
        ) {
            call.reject("更新清单无效。", "INVALID_UPDATE_MANIFEST");
            return;
        }
        if (!canRequestPackageInstalls()) {
            call.reject("请先允许 Time Agent 安装未知应用。", "INSTALL_PERMISSION_REQUIRED");
            return;
        }
        executor.execute(() -> {
            try {
                File updateDirectory = new File(getContext().getCacheDir(), "updates");
                if (!updateDirectory.exists() && !updateDirectory.mkdirs()) {
                    throw new IllegalStateException("无法创建更新缓存目录");
                }
                clearStaleUpdateFiles(updateDirectory);
                File apk = new File(
                    updateDirectory,
                    buildUpdateFilename(expectedVersionCode.longValue(), expectedSha256)
                );
                download(downloadUrl, apk, expectedSizeBytes == null ? -1L : expectedSizeBytes);
                verifyDigest(apk, expectedSha256);
                verifyPackage(apk, expectedVersionCode.longValue(), expectedVersionName);
                getActivity().runOnUiThread(() -> launchInstaller(apk, call));
            } catch (Exception exception) {
                call.reject("更新包下载或校验失败：" + exception.getMessage(), "UPDATE_VERIFICATION_FAILED", exception);
            }
        });
    }

    private boolean canRequestPackageInstalls() {
        return Build.VERSION.SDK_INT < Build.VERSION_CODES.O
            || getContext().getPackageManager().canRequestPackageInstalls();
    }

    private void download(String source, File target, long expectedSize) throws Exception {
        HttpURLConnection connection = (HttpURLConnection) new URL(source).openConnection();
        connection.setConnectTimeout(15_000);
        connection.setReadTimeout(60_000);
        connection.setInstanceFollowRedirects(false);
        connection.setUseCaches(false);
        connection.setRequestProperty("Accept", "application/vnd.android.package-archive");
        connection.setRequestProperty("Cache-Control", "no-cache");
        int status = connection.getResponseCode();
        if (status != HttpURLConnection.HTTP_OK) throw new IllegalStateException("下载服务返回 HTTP " + status);
        long declaredSize = connection.getContentLengthLong();
        if (declaredSize > MAX_APK_BYTES) throw new IllegalStateException("安装包超过大小限制");
        long written = 0;
        try (InputStream input = connection.getInputStream(); FileOutputStream output = new FileOutputStream(target, false)) {
            byte[] buffer = new byte[64 * 1024];
            int count;
            while ((count = input.read(buffer)) != -1) {
                written += count;
                if (written > MAX_APK_BYTES) throw new IllegalStateException("安装包超过大小限制");
                output.write(buffer, 0, count);
            }
            output.getFD().sync();
        } finally {
            connection.disconnect();
        }
        if (expectedSize > 0 && written != expectedSize) throw new IllegalStateException("安装包大小与发布清单不一致");
    }

    private void verifyDigest(File apk, String expectedSha256) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (InputStream input = new java.io.FileInputStream(apk)) {
            byte[] buffer = new byte[64 * 1024];
            int count;
            while ((count = input.read(buffer)) != -1) digest.update(buffer, 0, count);
        }
        StringBuilder actual = new StringBuilder();
        for (byte value : digest.digest()) actual.append(String.format(Locale.ROOT, "%02x", value));
        if (!actual.toString().equals(expectedSha256)) throw new SecurityException("SHA-256 校验失败");
    }

    private void verifyPackage(File apk, long expectedVersionCode, String expectedVersionName) throws Exception {
        PackageManager manager = getContext().getPackageManager();
        int flags = Build.VERSION.SDK_INT >= Build.VERSION_CODES.P
            ? PackageManager.GET_SIGNING_CERTIFICATES
            : PackageManager.GET_SIGNATURES;
        PackageInfo candidate = manager.getPackageArchiveInfo(apk.getAbsolutePath(), flags);
        PackageInfo current = manager.getPackageInfo(getContext().getPackageName(), flags);
        if (candidate == null || !getContext().getPackageName().equals(candidate.packageName)) {
            throw new SecurityException("安装包应用标识不匹配");
        }
        long candidateVersion = longVersionCode(candidate);
        if (candidateVersion != expectedVersionCode || candidateVersion <= longVersionCode(current)) {
            throw new SecurityException("安装包版本号无效");
        }
        if (!expectedVersionName.equals(candidate.versionName)) {
            throw new SecurityException("安装包版本名称与发布清单不一致");
        }
        if (!signatureSet(candidate).equals(signatureSet(current))) {
            throw new SecurityException("安装包签名证书不匹配");
        }
    }

    private Set<String> signatureSet(PackageInfo info) throws Exception {
        Signature[] signatures;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            signatures = info.signingInfo == null ? new Signature[0] : info.signingInfo.getApkContentsSigners();
        } else {
            signatures = info.signatures == null ? new Signature[0] : info.signatures;
        }
        Set<String> result = new HashSet<>();
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        for (Signature signature : signatures) result.add(Arrays.toString(digest.digest(signature.toByteArray())));
        return result;
    }

    private long longVersionCode(PackageInfo info) {
        return Build.VERSION.SDK_INT >= Build.VERSION_CODES.P ? info.getLongVersionCode() : info.versionCode;
    }

    static String buildUpdateFilename(long versionCode, String sha256) {
        return String.format(Locale.ROOT, "timeagent-update-%d-%s.apk", versionCode, sha256.substring(0, 12));
    }

    private void clearStaleUpdateFiles(File updateDirectory) {
        File[] files = updateDirectory.listFiles();
        if (files == null) return;
        for (File file : files) {
            if (file.isFile() && file.getName().startsWith("timeagent-update")) file.delete();
        }
    }

    private void launchInstaller(File apk, PluginCall call) {
        Uri uri = FileProvider.getUriForFile(getContext(), getContext().getPackageName() + ".fileprovider", apk);
        Intent intent = new Intent(Intent.ACTION_VIEW);
        intent.setDataAndType(uri, "application/vnd.android.package-archive");
        intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_ACTIVITY_NEW_TASK);
        getActivity().startActivity(intent);
        JSObject result = new JSObject();
        result.put("started", true);
        call.resolve(result);
    }
}
