[app]
title           = PhantomDroid
package.name    = phantomdroid
package.domain  = org.mrpsycho
source.dir      = .
source.include_exts = py,png,jpg,kv,atlas,txt,json,sh,conf
version         = 3.0.0

requirements    = python3,kivy,flask,requests,rich,colorama

orientation     = portrait

[buildozer]
log_level = 2
warn_on_root = 1
build_dir = .buildozer
bin_dir = bin

[app:android]
android.permissions = \
    INTERNET,\
    ACCESS_WIFI_STATE,\
    CHANGE_WIFI_STATE,\
    ACCESS_NETWORK_STATE,\
    CHANGE_NETWORK_STATE,\
    ACCESS_FINE_LOCATION,\
    ACCESS_COARSE_LOCATION,\
    TRANSMIT_IR,\
    BLUETOOTH,\
    BLUETOOTH_ADMIN,\
    BLUETOOTH_SCAN,\
    BLUETOOTH_CONNECT,\
    BLUETOOTH_ADVERTISE

android.api         = 33
android.minapi      = 24
android.ndk         = 25b
android.sdk         = 33
android.archs       = arm64-v8a, armeabi-v7a
android.allow_backup = True
android.release_artifact = apk
android.debug       = 0
