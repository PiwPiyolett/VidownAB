@echo off
title AB Video Downloader - YouTube ^& TikTok
cd /d "%~dp0"
python video_downloader.py
if errorlevel 1 (
    echo.
    echo Terjadi error. Pastikan Python dan yt-dlp sudah terpasang:
    echo     pip install -U yt-dlp
    echo.
    pause
)
