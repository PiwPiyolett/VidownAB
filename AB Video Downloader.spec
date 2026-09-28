# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:/Users/advan/Documents/Project/Tools Install Video Youtube, Tiktok/video_downloader.py'],
    pathex=[],
    binaries=[('C:/Users/advan/AppData/Local/Temp/claude/C--Users-advan-Documents-Project-Tools-Install-Video-Youtube--Tiktok/e03e70e6-f0f7-43fa-ac99-15b886c8cc48/scratchpad/ffmpeg.exe', '.')],
    datas=[('C:/Users/advan/Documents/Project/Tools Install Video Youtube, Tiktok/app_icon.ico', '.')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='AB Video Downloader',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['C:\\Users\\advan\\Documents\\Project\\Tools Install Video Youtube, Tiktok\\app_icon.ico'],
)
