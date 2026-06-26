#!/usr/bin/env python3
"""贾维斯语音助手 — VAD静音检测 + 火山引擎流式ASR + tmux Hermes"""
import sys, os, time, json, wave, struct, signal, asyncio, base64, tempfile, gzip, uuid
import urllib.request
import pyaudio
from edge_tts import Communicate
import websockets

# ── 火山引擎流式ASR ──
VOLC_KEY = os.environ.get("VOLC_KEY", "")
VOLC_RESOURCE = "volc.seedasr.sauc.duration"
VOLC_ENDPOINT = "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async"
ASR_CHUNK_BYTES = 3200  # 100ms @ 16kHz 16bit mono

# 阿里云 Qwen Omni（备用）
DASHSCOPE_KEY = "sk-d39310db9780471fad49693989382fde"
DASHSCOPE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"

# ── Volcengine ASR binary protocol ──
HDR_FULL_CLIENT = bytes([0x11, 0x10, 0x11, 0x00])
HDR_AUDIO       = bytes([0x11, 0x20, 0x01, 0x00])
HDR_AUDIO_LAST  = bytes([0x11, 0x22, 0x01, 0x00])

def volc_frame(header, payload):
    payload = gzip.compress(payload)
    return header + struct.pack(">I", len(payload)) + payload

def volc_parse(data):
    if isinstance(data, str):
        data = data.encode("latin-1")
    msg_type = data[1] >> 4
    flags = data[1] & 0x0F
    compressed = (data[2] & 0x0F) == 0x01
    off = 4
    if msg_type == 0x0F:
        code = struct.unpack(">I", data[off:off+4])[0]; off += 4
        size = struct.unpack(">I", data[off:off+4])[0]; off += 4
        body = data[off:off+size]
        if compressed or body[:2] == b"\x1f\x8b":
            body = gzip.decompress(body)
        return {"_error": code, "message": body.decode("utf-8", "replace")}
    if flags & 0x01:
        off += 4
    size = struct.unpack(">I", data[off:off+4])[0]; off += 4
    body = data[off:off+size]
    if compressed:
        body = gzip.decompress(body)
    obj = json.loads(body) if body else {}
    obj["_flags"] = flags
    return obj

def volc_config():
    return json.dumps({
        "user": {"uid": "jarvis-mac", "platform": "macOS"},
        "audio": {"format": "pcm", "codec": "raw", "rate": 16000, "bits": 16, "channel": 1},
        "request": {
            "model_name": "bigmodel", "enable_itn": True, "enable_punc": True,
            "enable_ddc": False, "show_utterances": True, "result_type": "single",
        },
    }, ensure_ascii=False).encode()

async def volc_asr_async(audio_bytes):
    """火山引擎流式ASR：发送音频返回转写文字"""
    if len(audio_bytes) < 2000:
        return ""
    try:
        headers = {
            "X-Api-Key": VOLC_KEY,
            "X-Api-Resource-Id": VOLC_RESOURCE,
            "X-Api-Request-Id": str(uuid.uuid4()),
        }
        async with websockets.connect(VOLC_ENDPOINT, additional_headers=headers, max_size=10_000_000) as ws:
            # 发送配置
            await ws.send(volc_frame(HDR_FULL_CLIENT, volc_config()))
            ack = volc_parse(await ws.recv())
            if "_error" in ack:
                raise RuntimeError(f"config rejected: {ack}")

            # 分块发送音频（按100ms块，快速发送）
            chunks = [audio_bytes[i:i+ASR_CHUNK_BYTES] for i in range(0, len(audio_bytes), ASR_CHUNK_BYTES)]
            for i, chunk in enumerate(chunks):
                is_last = (i == len(chunks) - 1)
                await ws.send(volc_frame(HDR_AUDIO_LAST if is_last else HDR_AUDIO, chunk))

            # 收集结果
            result = ""
            async for msg in ws:
                r = volc_parse(msg)
                if "_error" in r:
                    print(f"[⚠️ 火山ASR错误] {r}")
                    break
                res = r.get("result")
                if res:
                    text = res.get("text", "") if isinstance(res, dict) else res[0].get("text", "")
                    if text:
                        result = text
                if (r.get("_flags", 0) & 0b0010):
                    break
            return result.strip()
    except Exception as e:
        print(f"[⚠️ 火山ASR] {e}")
        return ""

def cloud_asr(audio_bytes, sample_rate=16000):
    """转写：火山引擎优先 → 阿里云Qwen Omni备用"""
    # 火山引擎要求16kHz PCM
    if sample_rate != 16000:
        import math
        # 简单降采样（取整）
        ratio = sample_rate / 16000
        new_len = int(len(audio_bytes) / ratio / 2) * 2
        if new_len >= 2000:
            samples = struct.unpack(f'<{len(audio_bytes)//2}h', audio_bytes[:new_len*2])
            audio_bytes = struct.pack(f'<{len(samples)}h', *samples)
        else:
            audio_bytes = audio_bytes[:int(len(audio_bytes)/ratio/2)*2]

    text = asyncio.run(volc_asr_async(audio_bytes))
    if text:
        print(f"[☁️ 火山ASR] '{text}'")
        return text

    # 备用：阿里云 Qwen Omni
    if len(audio_bytes) < 2000: return ""
    try:
        tmp = tempfile.NamedTemporaryFile(suffix='.wav', delete=False).name
        try:
            with wave.open(tmp, 'wb') as wf:
                wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(16000)
                wf.writeframes(audio_bytes)
            with open(tmp, 'rb') as f:
                b64 = base64.b64encode(f.read()).decode()
        finally:
            try:
                os.unlink(tmp)
            except:
                pass
        body = json.dumps({
            "model": "qwen-omni-turbo",
            "messages": [{"role": "user", "content": [
                {"type": "input_audio", "input_audio": {"data": f"data:audio/wav;base64,{b64}", "format": "wav"}},
                {"type": "text", "text": "请转写这段语音为文字，只输出转写结果。"}
            ]}],
            "stream": True, "stream_options": {"include_usage": True}
        }).encode()
        req = urllib.request.Request(DASHSCOPE_URL, data=body,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {DASHSCOPE_KEY}"})
        resp = urllib.request.urlopen(req, timeout=10)
        buf = b""
        while True:
            chunk = resp.read(4096)
            if not chunk: break
            buf += chunk
        result = ""
        for line in buf.decode().split('\n'):
            if line.startswith('data: ') and 'DONE' not in line:
                try:
                    c = json.loads(line[6:]).get('choices', [{}])[0].get('delta', {}).get('content', '')
                    if c: result += c
                except: pass
        result = result.strip()
        if result and result != "。":
            print(f"[⚠️ 阿里云备用ASR] '{result}'")
            return result
    except Exception as e:
        print(f"[⚠️ 备用ASR] {e}")
    return ""

# ── HUD ──
VIZ_FILE = "/tmp/jarvis_viz_state.json"
def viz(mode):
    try:
        with open(VIZ_FILE, "w") as f: f.write(json.dumps({"mode": mode}))
    except: pass

# ── 配置 ──
WAKE_WORDS = {"贾维斯","jarvis","夹维斯","假维斯","加维斯","家维斯","亞維斯","吊維斯","調維斯","假威斯","小威斯","咖啡絲","小丽丝","小丽斯"}
WAKE_PREFIXES = ("贾","jar","jia","jav","假","加","家","亞","吊","調","咖","小","hi","嗨","嘿")
WAKE_CORE = ("维斯","維斯","威斯","啡絲","weis","weisi","斯。","A斯","意思","丽丝","丽斯")
CONVERSATION_TIMEOUT = 30
VAD_CHUNK_MS = 150
RMS_THRESHOLD = 200

# ── 全局状态 ──
conversation_active = False
last_wake_time = 0

def say(text):
    asyncio.run(Communicate(text, 'zh-CN-XiaoxiaoNeural').save('/tmp/jarvis_say.mp3'))
    os.system("afplay /tmp/jarvis_say.mp3 2>/dev/null")

def calc_rms(data):
    samples = struct.unpack(f'<{len(data)//2}h', data)
    if not samples: return 0
    return (sum(s*s for s in samples) / len(samples)) ** 0.5

def find_mic():
    try:
        p = pyaudio.PyAudio()
        info = p.get_default_input_device_info()
        idx = int(info['index']); name = info['name']; sr = int(info['defaultSampleRate'])
        if 'transcri' in name.lower() or 'text-to-speech' in name.lower():
            print("[⚠️] 默认设备是虚拟TTS，请切换真实麦克风")
            p.terminate(); return None, None
        print(f"[🎤] 系统默认: {name} ({sr}Hz)")
        return idx, info
    except Exception as e:
        print(f"[❌] 麦克风: {e}")
        return None, None
    finally:
        p.terminate()

def is_wake(text):
    if not text or len(text) < 2: return False
    t = text.lower().replace(" ","").replace("，","").replace(",","").replace("。","")[:10]
    for w in WAKE_WORDS:
        if w in t: return True
    for p in WAKE_PREFIXES:
        if t.startswith(p) and len(t) >= len(p)+1: return True
    for c in WAKE_CORE:
        if c in t: return True
    return False

def strip_wake(text):
    for w in WAKE_WORDS:
        if w in text: idx = text.index(w); return text[idx+len(w):].strip()
    for p in WAKE_PREFIXES:
        if text.lower().startswith(p): return text[min(len(p)+1,4):].strip()
    for c in WAKE_CORE:
        idx = text.find(c)
        if idx >= 0 and idx <= 4: return text[idx+len(c):].strip()
    return text

def brain(cmd):
    if not cmd: return "请说指令"
    try:
        import subprocess
        subprocess.run(["tmux","send-keys","-t","hermes-brain",cmd,"Enter"], capture_output=True, timeout=5)
        deadline = time.time() + 10
        last_out = ""
        while time.time() < deadline:
            time.sleep(0.3)
            r = subprocess.run(["tmux","capture-pane","-t","hermes-brain","-p"], capture_output=True, text=True, timeout=3)
            lines = [l for l in r.stdout.split('\n') if l.strip() and '❯' not in l and '──' not in l and '╭' not in l and '╰' not in l and '↑/↓' not in l]
            reply = [l for l in lines if '⚕' not in l and 'ctx' not in l and '│' not in l]
            if reply:
                latest = reply[-1].strip()
                if latest != last_out:
                    last_out = latest
        return last_out[:200] if last_out else "处理完成"
    except Exception as e:
        return "出错了"

def main():
    signal.signal(signal.SIGINT, lambda s, f: exit(0))
    print("="*50+"\n  贾维斯 · 语音助手 (火山引擎ASR)\n  说「贾维斯」唤醒，说完自动处理\n"+"="*50)

    mic_idx, mic_info = find_mic()
    if mic_idx is None:
        say("未检测到麦克风")
        while mic_idx is None:
            for _ in range(15): time.sleep(1)
            mic_idx, mic_info = find_mic()
        say("检测到麦克风")

    sr = int(mic_info['defaultSampleRate'])
    chunk_size = max(int(sr * VAD_CHUNK_MS / 1000), 800)
    print(f"[🔊] {sr}Hz, {chunk_size}帧 ({chunk_size/sr*1000:.0f}ms)")

    p = pyaudio.PyAudio()
    stream = p.open(format=pyaudio.paInt16, channels=1, rate=sr,
                    input=True, input_device_index=mic_idx,
                    frames_per_buffer=chunk_size)

    print("[⚡] 预热...", end="", flush=True)
    for _ in range(3): stream.read(chunk_size, exception_on_overflow=False)
    print(" 就绪\n[👂 等待唤醒...]")

    viz("idle")
    global conversation_active, last_wake_time

    buf = bytearray()
    recording = False
    silent_frames = 0
    cooldown = 0

    while True:
        if cooldown > 0:
            try: stream.read(chunk_size, exception_on_overflow=False)
            except: pass
            cooldown -= 1
            if cooldown == 0:
                buf.clear(); recording = False; silent_frames = 0
                viz("idle")
                print("[👂 等待唤醒...]")
            continue

        data = stream.read(chunk_size, exception_on_overflow=False)
        rms = calc_rms(data)
        is_speech = rms > RMS_THRESHOLD

        if not recording:
            if is_speech:
                recording = True; silent_frames = 0
                buf = bytearray(data[-chunk_size*2:])
                print(f"[🎤 说话] RMS={rms:.0f}")
                viz("listening")
            continue

        buf.extend(data)
        if is_speech:
            silent_frames = 0
        else:
            silent_frames += 1
            silence_needed = 2 if conversation_active and time.time() - last_wake_time < CONVERSATION_TIMEOUT else 5
            if silent_frames >= silence_needed and len(buf) >= sr // 2:
                audio = bytes(buf); buf.clear(); recording = False; silent_frames = 0

                text = cloud_asr(audio, sr)
                if not text or len(text) < 2:
                    viz("idle")
                    continue

                now = time.time()
                in_conv = conversation_active and (now - last_wake_time) < CONVERSATION_TIMEOUT
                is_wake_word = is_wake(text)

                if is_wake_word:
                    cmd = strip_wake(text)
                    print(f"[🔥 唤醒] {text}")
                    conversation_active = True; last_wake_time = now
                    if not cmd:
                        print("[请说指令]"); say("请说"); viz("listening")
                        continue
                    print(f"[📝] {cmd}")
                elif in_conv:
                    cmd = text
                    print(f"[💬 连续对话] {text}")
                    last_wake_time = now
                else:
                    print(f"[听] {text[:40]}")
                    viz("idle")
                    continue

                viz("thinking")
                reply = brain(cmd)
                print(f"[🤖] {reply}")
                viz("speaking")
                say(reply)
                cooldown = 8
                viz("idle")

if __name__ == "__main__":
    main()
