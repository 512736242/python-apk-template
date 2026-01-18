[app]

# 应用名称
title = 示例计算器应用

# 包名
package.name = python2apkexample
package.domain = com.jay

# 源代码目录
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json,txt

# 版本号
version = 1.0.0

# 依赖 (Kivy 是必须的，其他按需添加)
requirements = python3,kivy

# 如需添加其他库，用逗号分隔，例如:
# requirements = python3,kivy,requests,numpy

# Android 配置
android.permissions = INTERNET
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
warn_on_root = 1
