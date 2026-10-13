---
name: audio-ops
description: >-
  Standardized PipeWire, WirePlumber, Bluetooth audio, and ffmpeg loudness normalization runbook.
  Use when diagnosing workstation audio sinks and sources via wpctl, recovering unresponsive
  PipeWire/WirePlumber user daemons, pairing and managing Bluetooth audio headsets/codecs,
  applying EBU R128 loudnorm audio filters, or fixing VLC and ffmpeg split-package codec mismatches.
---
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# PSL Audio Operations: PipeWire, WirePlumber & Audio Transformation Runbook

This skill establishes empirical, tool-native runbooks for modern Linux audio stacks (PipeWire & WirePlumber), Bluetooth audio pairing, audio codec troubleshooting, and EBU R128 loudness normalization.

---

## 1. PipeWire & WirePlumber User-Space Diagnostics (`wpctl`)

PipeWire manages real-time audio and video routing. WirePlumber serves as its session and policy manager.

### Step 1.1: Audio Graph & Endpoint Status
Inspect all active audio inputs, outputs, sinks, sources, and streams:
```bash
wpctl status
```
In `wpctl status`, the active default sink/source is marked with an asterisk (`*`).

### Step 1.2: Inspect Node Details
Query properties, codecs, and routing parameters for a specific device ID:
```bash
wpctl inspect <ID>
```

### Step 1.3: Set Default Audio Sink & Source
Set default audio output device (speakers, DAC, headset):
```bash
wpctl set-default <SINK_ID>
```
Set default audio input device (microphone):
```bash
wpctl set-default <SOURCE_ID>
```

### Step 1.4: Volume & Mute Controls
Adjust output volume (bounded 0.0 to 1.0 or stepped):
```bash
# Set volume to 65%
wpctl set-volume <SINK_ID> 0.65

# Increase volume by 5% (capped at 100%)
wpctl set-volume -l 1.0 <SINK_ID> 5%+

# Toggle mute (1 = mute, 0 = unmute)
wpctl set-mute <SINK_ID> toggle
```

---

## 2. PipeWire & WirePlumber Daemon Recovery

### Invariant: User-Space Execution Hierarchy
PipeWire and WirePlumber run exclusively under the **user systemd instance** (`systemctl --user`). Never invoke `sudo systemctl restart pipewire` — doing so will fail or corrupt socket ownership.

### Step 2.1: Inspect Daemon Status
```bash
systemctl --user status pipewire pipewire-pulse wireplumber --no-pager
```

### Step 2.2: Graceful User Daemon Restart
When audio stops, sinks disappear, or latency degrades:
```bash
systemctl --user restart pipewire pipewire-pulse wireplumber
```

### Step 2.3: Nuclear Socket Reset (Broken IPC Recovery)
If PipeWire daemon hangs or IPC sockets become unresponsive:
```bash
systemctl --user stop pipewire pipewire-pulse wireplumber
rm -f /run/user/$(id -u)/pipewire-0*
systemctl --user start pipewire pipewire-pulse wireplumber
```

---

## 3. Bluetooth Audio Pairing & Codec Negotiation

### Step 3.1: Bluetooth Daemon & Controller Check
Verify host Bluetooth service and controller status:
```bash
systemctl status bluetooth --no-pager
rfkill list bluetooth
```

### Step 3.2: Discover and Connect Headset via `bluetoothctl`
Automate or verify pairing sequence:
```bash
bluetoothctl power on
bluetoothctl agent on
bluetoothctl default-agent
bluetoothctl scan on
# Wait for device MAC discovery, then:
bluetoothctl pair <MAC_ADDRESS>
bluetoothctl trust <MAC_ADDRESS>
bluetoothctl connect <MAC_ADDRESS>
```

### Step 3.3: High-Fidelity Codec Negotiation (A2DP vs HFP)
WirePlumber dynamically negotiates Bluetooth profiles (A2DP for high quality music, HFP/HSP for bidirectional voice).
- Verify active Bluetooth profile in `wpctl status`.
- Query supported routes and switch to LDAC, AptX-HD, or AAC via `wpctl`:
```bash
wpctl inspect <BLUETOOTH_NODE_ID>
```

---

## 4. Audio Loudness Normalization (`ffmpeg loudnorm`)

Standardize audio tracks to the broadcast-standard EBU R128 loudness specification using `ffmpeg`.

### 4.1 Single-Pass Fast Normalization
For quick normalization targeting standard streaming integrated loudness (-16 LUFS):
```bash
ffmpeg -y -i input.wav -af "loudnorm=I=-16:TP=-1.5:LRA=11" -c:a libmp3lame -b:a 320k output_normalized.mp3
```

### 4.2 Two-Pass Precision Normalization (Audiophile / Broadcast Quality)
#### Pass 1: Analysis Pass
Run first pass to calculate measured loudness values:
```bash
ffmpeg -i input.wav -af "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json" -f null - 2>&1 | tail -n 15
```
Output will contain measured parameters:
```json
{
    "input_i": "-24.12",
    "input_tp": "-6.10",
    "input_lra": "8.50",
    "input_thresh": "-34.50",
    "target_offset": "0.12"
}
```

#### Pass 2: Exact Normalization Application
Apply measured parameters for linear, distortion-free gain correction:
```bash
ffmpeg -y -i input.wav -af "loudnorm=I=-16:TP=-1.5:LRA=11:measured_I=-24.12:measured_TP=-6.10:measured_LRA=8.50:measured_thresh=-34.50:offset=0.12:linear=true" -c:a flac output_normalized.flac
```

---

## 5. VLC & ffmpeg Split-Package Resolution

### The Issue
On Arch Linux and modular Linux distributions, VLC plugins and ffmpeg codecs are packaged in split packages (`vlc-plugin-ffmpeg`, `vlc-plugins-base`, `vlc-plugins-all`). When system `ffmpeg` undergoes a major shared library soname bump (e.g. `libavcodec.so.60` to `libavcodec.so.61`), VLC may silently drop audio/video decoding or crash on startup.

### Step 5.1: Verify Installed VLC & ffmpeg Packages
```bash
pacman -Qs vlc
pacman -Qs ffmpeg
```

### Step 5.2: Install Required Split Packages
Ensure the ffmpeg decoding plugin is installed alongside VLC:
```bash
sudo pacman -S --needed vlc vlc-plugin-ffmpeg ffmpeg
```

### Step 5.3: Regenerate VLC Plugin Cache
Rebuild the plugin cache if codecs are not recognized after an update:
```bash
sudo /usr/lib/vlc/vlc-cache-gen -f /usr/lib/vlc/plugins
# Reset user-specific cache and configuration if playback remains broken
rm -rf ~/.config/vlc ~/.cache/vlc
```
