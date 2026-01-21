[app]

# 应用名称
title = BDSM论坛工具

# 包名
package.name = bdsmtool
package.domain = com.jaychou

# 源代码目录
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json,txt,ttf

# 版本号
version = 2.0.0

# 依赖 (Kivy 是必须的，其他按需添加)
requirements = python3,kivy,requests,urllib3,certifi,charset-normalizer,idna

# Android 配置
android.permissions = INTERNET,WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE,MANAGE_EXTERNAL_STORAGE
android.api = 33
android.minapi = 21
android.ndk = 25b
android.archs = arm64-v8a, armeabi-v7a

# 图标和启动画面 (可选，放在项目根目录)
# icon.filename = icon.png
# presplash.filename = presplash.png

# 屏幕方向: portrait, landscape, all
orientation = portrait

# 是否全屏
fullscreen = 0

# Android 特定
android.accept_sdk_license = True

# 生成 APK 而不是 AAB
android.release_artifact = apk

# ========== Release 签名配置 ==========
# 签名密钥会在 GitHub Actions 中自动生成
# 如需本地构建 Release，请创建密钥:
# keytool -genkey -v -keystore release.keystore -alias release -keyalg RSA -keysize 2048 -validity 10000
#
# android.keystore = release.keystore
# android.keyalias = release
# android.keystore_password = 123456
# android.keyalias_password = 123456

[buildozer]
log_level = 2
warn_on_root = 0
