---
name: macos-voice-assistant-cloud
description: 贾维斯语音助手 — Mac mini 纯云端版。火山引擎流式ASR + VAD静音检测 + tmux持久Hermes + edge-tts + HTML Canvas HUD。支持音乐播放、连续对话。
version: 3.0.0
author: qhdh
---

# macOS Voice Assistant — 贾维斯 (Cloud-Only, v3.0)

Always-on wake-word voice assistant for Mac. **火山引擎豆包流式ASR** (WebSocket, 300-400ms latency), natural speech flow (no keyword required to end), continuous conversation mode, music playback capability. All commands routed through Hermes Agent for maximum flexibility.

## Architecture

```
[系统默认麦克风]
  ↓ PyAudio continuous stream (VAD loop, 150ms chunks)
  ↓ fixed RMS threshold (200), simple VAD
  ↓ silence detection ends recording (750ms normal / 300ms conv mode)
  ↓
  cloud_asr()  ← 火山引擎豆包流式ASR (WebSocket, 首选)
  │  wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async
  │  Volcengine Seed ASR 2.0 (volc.seedasr.sauc.duration)
  │  Binary protocol: gzip(JSON config) + gzip(PCM audio chunks)
  │  ↓ fallback
  │  阿里云 Qwen Omni Turbo (HTTP, 备用)
  │  dashscope.aliyuncs.com, model: qwen-omni-turbo
  │
  ↓ is_wake() → strip_wake()
  ↓ brain(cmd) → tmux send-keys → Hermes Agent
  ↓ say() → edge-tts → afplay (系统默认输出)
  ↓ viz(mode) → HTML HUD (localhost:18326)
```

## 🔑 Key Specs

| Item | Value |
|------|-------|
| ASR Engine | 火山引擎豆包流式语音识别 2.0 (首选) / 阿里云 Qwen Omni Turbo (备用) |
| ASR Latency | 300-400ms (Volcengine streaming) / 1-3s (Qwen Omni batch) |
| Audio Format | 16kHz, 16bit, mono PCM |
| Protocol | WebSocket binary (gzip frames) |
| VAD | Fixed threshold RMS 200, no adaptive noise floor |
| Silence Detection | 5 frames (750ms) normal / 2 frames (300ms) conversation mode |
| Minimum Audio | 0.5 seconds |
| TTS Cooldown | 8 frames (~1.2s) discard after speaking |
| Wake Word | "贾维斯" + variants (hi/嗨/嘿 prefix) |
| Conversation Mode | 30s timeout, no wake word needed |
| HUD | HTML Canvas (localhost:18326), ThreadingHTTPServer |

## 📁 File Layout

```
~/.hermes/scripts/
├── jarvis_wake.py            # 守护进程 (VAD + 火山ASR + tmux Hermes + TTS + HUD)
├── jarvis_visualizer.py      # HTTP服务器 (ThreadingHTTPServer, port 18326)
├── jarvis_hud.html           # Canvas HUD (Perlin噪声, 粒子, 色变说明)
├── com.qhdh.jarvis.wake.plist  # Launchd: 唤醒守护
└── com.qhdh.jarvis.viz.plist   # Launchd: HUD服务器

~/.hermes/logs/
├── jarvis_wake.log           # stdout
└── jarvis_wake.err           # stderr
```

## 🎙️ Usage

```
"贾维斯今天天气怎么样"   ← 唤醒 + 查天气
"明天呢"                  ← 连续对话，300ms静音即处理
"帮我找一首歌播放"         ← 搜索音乐并播放
"用Apple Music放歌"       ← 打开音乐App
"停止播放"                ← 停止音乐
"给我讲个故事"             ← 聊天模式
```

## 🧠 Hermes Agent Integration

All voice commands are forwarded to Hermes Agent via tmux persistent session. This means Jarvis can do anything Hermes can do:

- **File operations**: search, read, write
- **Music playback**: afplay (background) or open -a Music
- **Web search**: via Hermes tools
- **Stock queries**: via A-share skills
- **System control**: terminal commands
- **Custom workflows**: any skill loaded in Hermes

## ⚙️ Launchd Services

```bash
launchctl list | grep jarvis
launchctl kickstart gui/$(id -u)/com.qhdh.jarvis.wake  # Restart wake
launchctl kickstart -k gui/$(id -u)/com.qhdh.jarvis.viz  # Restart HUD
```

## 🛠️ Pitfalls

1. **No built-in mic on Mac mini** — External audio input required (USB/BT)
2. **Volcengine API key** — Must be valid and have resource quota
3. **WebSocket protocol** — Uses custom binary framing (gzip compressed)
4. **TTS echo** — 1.2s cooldown discards audio after speaking
5. **Conversation timeout** — 30s of silence resets to wake-only mode

## 📝 Changelog

- v3.0.0 (2026-06-26): Volcengine streaming ASR (WebSocket). Music playback. Faster conversation mode (300ms silence).
- v2.0.0 (2026-06-26): Simplified VAD + silence detection. No over/OK keyword. Clean viz() management.
- v1.0.0 (2026-06-26): Initial cloud-only. Qwen Omni ASR. HTML Canvas HUD.
