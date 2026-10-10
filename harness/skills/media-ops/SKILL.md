---
name: media-ops
description: >-
  Standardized native stream acquisition and high-throughput media transformation runbook for yt-dlp and ffmpeg.
  Use when acquiring video or audio streams, overcoming CDN bot/TLS challenges, performing lossless transforms,
  or flipping and rotating video files.
---

# PSL Media Operations: yt-dlp & ffmpeg Native Runbook

This skill establishes empirical, tool-native runbooks for media stream acquisition and video transformation within Google Antigravity environments.

---

## 1. Stream Acquisition (`yt-dlp`) Escalation Ladder

Always proceed progressively through native flags before analyzing extractor code or writing custom scripts:

### Level 1: Standard Accelerated Fragment Download
For HLS/DASH fragmented streams, use concurrent fragment workers to avoid slow single-threaded fragment bottlenecks:
```bash
yt-dlp -N 16 --socket-timeout 30 "<URL>"
```

### Level 2: Anti-Bot & TLS Fingerprint Alignment
When CDNs (e.g., Cloudflare, CloudFront, Dailymotion, YouTube) return `HTTP 403 Forbidden` or reset TLS handshakes:
```bash
# Impersonate browser TLS fingerprint (requires curl_cffi)
yt-dlp --impersonate chrome -N 16 --socket-timeout 30 "<URL>"
```

### Level 3: Transient Network & Fragment Recovery
When encountering high packet loss or sporadic CDN drops on edge IPs:
```bash
yt-dlp --impersonate chrome -N 16 --extractor-retries 10 --fragment-retries 10 --socket-timeout 30 "<URL>"
```

### Level 4: Authenticated Browser Session
When streams require user authentication or cookies:
```bash
yt-dlp --cookies-from-browser chrome "<URL>"
```

---

## 2. Native Media Transformation (`ffmpeg`)

### 2.1 Video Flips & Rotations
Always preserve original audio tracks losslessly using `-c:a copy` unless audio transformation is explicitly requested:

```bash
# Vertical Flip (Upside Down)
ffmpeg -y -i input.mp4 -vf "vflip" -c:v libx264 -crf 20 -preset faster -c:a copy output_vflip.mp4

# Horizontal Flip (Mirror)
ffmpeg -y -i input.mp4 -vf "hflip" -c:v libx264 -crf 20 -preset faster -c:a copy output_hflip.mp4

# 90° Clockwise Rotation
ffmpeg -y -i input.mp4 -vf "transpose=1" -c:v libx264 -crf 20 -preset faster -c:a copy output_rot90.mp4
```

### 2.2 Hardware Acceleration Detection
Probe available hardware encoders before software transcoding high-resolution streams:
```bash
# Check NVENC (Nvidia)
ffmpeg -encoders 2>/dev/null | grep nvenc

# Check VAAPI (Intel/AMD)
ffmpeg -encoders 2>/dev/null | grep vaapi
```
If available, substitute `-c:v h264_nvenc` or `-c:v h264_vaapi` for ultra-fast rendering.
