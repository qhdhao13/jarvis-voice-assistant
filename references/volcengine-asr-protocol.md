# 火山引擎流式ASR WebSocket 协议

官方文档：`https://www.volcengine.com/docs/6561/1354869`（需JS渲染，curl不可读）

## 连接信息

- **Endpoint:** `wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async`（优化版本，推荐）
- **备用:** `wss://openspeech.bytedance.com/api/v3/sauc/bigmodel`（双向流式，每包返回）
- **采样率:** 16kHz / 16bit / mono PCM
- **单包大小:** 100-200ms（推荐200ms = 3200 bytes）
- **认证:** WebSocket HTTP headers

## 认证 Header

新版控制台（2025+）：
```
X-Api-Key: <your-api-key>
X-Api-Resource-Id: volc.seedasr.sauc.duration  # 豆包2.0小时版
```

旧版控制台（需同时传）：
```
X-Api-App-Key: <appid>
X-Api-Access-Key: <token>
X-Api-Resource-Id: volc.bigasr.sauc.duration  # 豆包1.0小时版
```

Resource ID:
- 豆包1.0 小时版: `volc.bigasr.sauc.duration`
- 豆包1.0 并发版: `volc.bigasr.sauc.concurrent`
- 豆包2.0 小时版: `volc.seedasr.sauc.duration`
- 豆包2.0 并发版: `volc.seedasr.sauc.concurrent`

## 二进制协议

每个消息 = `4字节固定头 + [4字节seq] + 4字节payload长度 + payload(gzip)`

### 固定头 (4 bytes)

| byte | 含义 |
|------|------|
| byte0 | protocol_version<<4 \| header_size (固定 `0x11`) |
| byte1 | message_type<<4 \| flags |
| byte2 | serialization<<4 \| compression |
| byte3 | reserved |

### message_type (byte1 high 4 bits)

| 值 | 含义 |
|----|------|
| 0x1 | FullClientRequest (配置) |
| 0x2 | Audio (音频数据) |
| 0xF | Error |

### flags (byte1 low 4 bits)

| 位 | 含义 |
|---|-------|
| 0b0001 | 有sequence字段 |
| 0b0010 | 最后一条(last) |
| 0b0011 | 最后一条+负seq |

### compression (byte2 low 4 bits)

- `0x01` = gzip compressed
- `0x00` = raw

### 预定义 Header 常量

```python
HDR_FULL_CLIENT = bytes([0x11, 0x10, 0x11, 0x00])  # type=1, JSON+gzip
HDR_AUDIO       = bytes([0x11, 0x20, 0x01, 0x00])  # type=2, raw+gzip
HDR_AUDIO_LAST  = bytes([0x11, 0x22, 0x01, 0x00])  # type=2, last, raw+gzip
```

### 消息构造

```python
def volc_frame(header, payload):
    payload = gzip.compress(payload)
    return header + struct.pack(">I", len(payload)) + payload
```

## 配置 Payload (FullClientRequest)

```json
{
    "user": {"uid": "jarvis-mac", "platform": "macOS"},
    "audio": {
        "format": "pcm", "codec": "raw",
        "rate": 16000, "bits": 16, "channel": 1
    },
    "request": {
        "model_name": "bigmodel",
        "enable_itn": true,
        "enable_punc": true,
        "enable_ddc": false,
        "show_utterances": true,
        "result_type": "single"
    }
}
```

参数说明:
- `enable_itn`: 逆文本正则化（数字/日期/金额转文字）
- `enable_punc`: 添加标点
- `result_type`: "single"=单句结果, "full"=完整结果

## 响应解析

```python
def volc_parse(data):
    if isinstance(data, str):
        data = data.encode("latin-1")
    compressed = (data[2] & 0x0F) == 0x01
    off = 4
    msg_type = data[1] >> 4
    if msg_type == 0x0F:  # error
        code = struct.unpack(">I", data[off:off+4])[0]; off += 4
        size = struct.unpack(">I", data[off:off+4])[0]; off += 4
        body = data[off:off+size]
        if compressed or body[:2] == b"\\x1f\\x8b":
            body = gzip.decompress(body)
        return {"_error": code, "message": body.decode("utf-8", "replace")}
    if data[1] & 0x01:  # has seq
        off += 4
    size = struct.unpack(">I", data[off:off+4])[0]; off += 4
    body = data[off:off+size]
    if compressed:
        body = gzip.decompress(body)
    obj = json.loads(body) if body else {}
    obj["_flags"] = data[1] & 0x0F
    return obj
```

响应结果结构:
```json
{
    "result": [
        {"text": "今天天气怎么样"}
    ],
    "added_num": 0
}
```

flags bit 0b0010 (last) 或 _seq < 0 表示语音结束。

## 性能

- **流式输入模式（非双向）:** 平均5s音频，300-400ms返回
- **双向流式模式:** 每输入一包返回一包，更快但准确率略低
- **优化版本 (`bigmodel_async`):** 仅在结果变化时返回，rtf和首字尾字时延更优

## 参考实现

完整 Python 实现见 `talky` 项目：
```
https://github.com/archibate/talky
```

核心流程：
1. 建立 WebSocket 连接（带 auth headers）
2. 发送 FullClientRequest 配置帧
3. 等待配置确认（解析返回的第一帧）
4. 循环发送音频帧（HDR_AUDIO），最后一帧用 HDR_AUDIO_LAST
5. 异步收集返回结果，flags 含 0b0010 或 seq<0 时结束
6. 关闭连接，返回最终文字
