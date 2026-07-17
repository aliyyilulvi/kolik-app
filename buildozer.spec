[app]

# Uygulama görünen adı
title = Kolik
# Paket adı / domain (Android package: org.kolik.app)
package.name = kolik
package.domain = org.kolik

# Kaynak kod dizini ve dahil edilecek dosya uzantıları
source.dir = .
source.include_exts = py,kv,csv,png,jpg,ttf,atlas

# Sürüm
version = 1.0.0

# Bağımlılıklar (requirements.txt ile senkron tutulmalı)
# NOT: numpy KASITLI OLARAK YOK - Android için cross-compile edilirken sık
# hata veriyor. Analiz motoru saf Python'dur.
# NOT: pyjnius EKLENDİ - data_fetcher.py'deki Android native DNS
# çözümleme fallback'i için garanti altına alındı.
requirements = python3,kivy==2.3.1,requests,certifi,urllib3,chardet,idna,pyjnius

# python-for-android dalı SABİTLENDİ: "master" Python 3.12'ye kadar kararlı
# test edilmiş durumda.
p4a.branch = master

# Uygulama ikonu / splash (opsiyonel - kendi görsellerinizi ekleyin)
# icon.filename = %(source.dir)s/data/icon.png
# presplash.filename = %(source.dir)s/data/presplash.png

# Ekran yönü
orientation = portrait

# Tam ekran mı?
fullscreen = 0

# ---------------------------------------------------------------------
# ANDROID AYARLARI
# ---------------------------------------------------------------------

[app:android]

# İnternet izni ZORUNLU: API'lerden veri çekmek için
android.permissions = INTERNET,ACCESS_NETWORK_STATE

# Minimum ve hedef API seviyesi
android.minapi = 24
android.api = 34
android.ndk = 25b
android.sdk = 34

# 64-bit ve 32-bit cihaz desteği
android.archs = arm64-v8a, armeabi-v7a

# Android Gradle dependency'lerini otomatik kabul et
android.accept_sdk_license = True

# APK mi AAB mi (Play Store için release'de aab tercih edilir)
android.release_artifact = apk

[buildozer]

# Log seviyesi: 0 = az, 1 = normal, 2 = ayrıntılı (hata ayıklarken 2 önerilir)
log_level = 2

# Root olarak build uyarısını kapat (CI ortamlarında gerekebilir)
warn_on_root = 1

# ---------------------------------------------------------------------
# DERLEME KOMUTU (bilgi amaçlı - terminalde çalıştırılır):
#
#   pip install buildozer cython
#   buildozer -v android debug
#
# İlk derleme Android SDK/NDK indireceği için uzun sürebilir (30-60 dk).
# Derleme sonunda APK dosyası ./bin/ klasöründe oluşur.
# ---------------------------------------------------------------------
