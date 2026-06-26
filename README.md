# 🎙️ Jarvis Voice Assistant — 贾维斯语音助手

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11%2B-blue)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-macOS-lightgrey)](https://www.apple.com/macos/)

**Always-on, wake-word-activated voice assistant for Mac.** No local ASR models. Pure cloud pipeline — Volcengine streaming ASR + Hermes Agent brain + edge-tts voice output. HTML Canvas desktop HUD.

> 说"贾维斯"，让它帮你查天气、放音乐、操作电脑、搜索信息……什么都能干。

## ✨ Features

- 🔥 **Wake word**: Say "贾维斯" (or "hi 贾维斯") to activate
- 🎯 **Natural speech**: No keyword required to end — silence detection auto-processes
- ☁️ **Cloud ASR**: Volcengine ByteDance streaming ASR (WebSocket, ~300ms latency)
- 🧠 **Hermes Agent brain**: Any command, any skill — not a limited voice assistant
- 🎵 **Music playback**: "贾维斯帮我放首歌" — searches and plays your music
- 💬 **Conversation mode**: 30s continuous conversation, no re-wake needed
- 🖥️ **Desktop HUD**: HTML Canvas holographic indicator (localhost:18326)
- 🔌 **System default audio**: No hardcoded device names — uses macOS settings

## 🏗️ Architecture

```
[System Mic] → VAD → [Volcengine ASR (WebSocket)] → [Wake Word Detection]
    → [Hermes Agent (tmux)] → [edge-tts → afplay]
    → [HTML HUD (localhost:18326)]
```

## 🚀 Quick Start

```bash
# 1. Clone
git clone https://github.com/qhdhao13/jarvis-voice-assistant.git
cd jarvis-voice-assistant

# 2. Install deps
pip install pyaudio edge-tts websockets
brew install portaudio ffmpeg tmux

# 3. Set API key (Volcengine)
export VOLC_KEY="your-api-key"
export DASHSCOPE_KEY="your-dashscope-key"

# 4. Start
python3 references/jarvis_wake.py
```

**Say "贾维斯今天天气怎么样"** to test.

## 🛠️ Tech Stack

| Component | Technology |
|-----------|------------|
| ASR | 火山引擎豆包流式语音识别 2.0 (WebSocket) |
| Fallback ASR | 阿里云 Qwen Omni Turbo |
| AI Brain | Hermes Agent (DeepSeek V4 Flash) |
| TTS | Microsoft edge-tts (XiaoxiaoNeural) |
| VAD | PyAudio, fixed RMS threshold (200) |
| HUD | HTML Canvas + Python ThreadingHTTPServer |
| Process Mgmt | macOS launchd (auto-restart on crash) |

## 📜 License

MIT
