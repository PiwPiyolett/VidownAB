<div align="center">

# 🎬 VidownAB · AB Video Downloader

**Aplikasi desktop untuk mengunduh video cukup dengan paste link.**

Mendukung YouTube, TikTok, dan ratusan situs lain (via [yt-dlp](https://github.com/yt-dlp/yt-dlp)), tersedia sebagai `.exe` mandiri, tanpa perlu membuka Python.

![Python](https://img.shields.io/badge/Python-3776AB?style=flat-square&logo=python&logoColor=white)
![yt-dlp](https://img.shields.io/badge/engine-yt--dlp-FF0000?style=flat-square&logo=youtube&logoColor=white)
![FFmpeg](https://img.shields.io/badge/FFmpeg-007808?style=flat-square&logo=ffmpeg&logoColor=white)
![Windows](https://img.shields.io/badge/Windows-0078D6?style=flat-square&logo=windows&logoColor=white)

<img src="Screenshot%202026-09-02%20133030.png" alt="VidownAB" width="480">

</div>

---

## ✨ Fitur

- 🔗 **Paste & unduh**, tempel link, thumbnail + judul + channel + durasi langsung muncul sebagai pratinjau.
- 🎞️ **Video (MP4) atau Audio (MP3)**, pilih jenis dan kualitas sesuai kebutuhan.
- 🌐 **Ratusan situs**, YouTube, TikTok, dan banyak lagi lewat mesin yt-dlp.
- 📊 **Progress bar animatif**, indikator unduhan dengan animasi shimmer.
- 📦 **`.exe` mandiri**, dibundel dengan PyInstaller, pengguna tidak perlu memasang Python.

## 🛠️ Tech Stack

**Bahasa:** Python
**Mesin unduh:** yt-dlp · FFmpeg (konversi/merge)
**Packaging:** PyInstaller (`.spec` disertakan)

## 🚀 Menjalankan dari source

```bash
# Pasang dependency
pip install yt-dlp

# Jalankan
python video_downloader.py
```

Pastikan `ffmpeg` tersedia di PATH untuk penggabungan video+audio dan konversi MP3.

### Build `.exe`

```bash
pip install pyinstaller
pyinstaller "AB Video Downloader.spec"
```

> File `.exe` hasil build (± 75 MB) sengaja **tidak** disertakan di repo agar ringan, silakan build sendiri, atau ambil dari halaman **Releases** bila tersedia.

---

<div align="center">

**Ariqo Banyusila Abrar** · [@PiwPiyolett](https://github.com/PiwPiyolett)

</div>
