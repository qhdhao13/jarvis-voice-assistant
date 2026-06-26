# HTML Canvas HUD — Implementation Notes

## Critical: ThreadingHTTPServer

The HUD server **MUST** use `ThreadingMixIn`. Stock `HTTPServer` is single-threaded — a single Chrome keep-alive connection blocks all subsequent requests, causing blank page.

```python
from socketserver import ThreadingMixIn
class ThreadingServer(ThreadingMixIn, HTTPServer):
    allow_reuse_address = True
    daemon_threads = True
```

Also set `Connection: close` on every HTTP response.

## Critical: JavaScript Syntax

Use `var` NOT `const`. Using `const` in the HTML script tag causes "Unexpected end of input" errors because the browser's script parser fails on the `const` declarations. Always declare with:

```javascript
var MODE_INFO = { ... };
var Perlin = function() { ... };
```

## Critical: Validate Braces

Before writing the HTML file, count braces in the JS script:

```bash
# In Python, before write_file:
code = js_script
assert code.count('{') == code.count('}'), f"Unclosed brace: {code.count('{')} vs {code.count('}')}"
```

An unclosed `{` causes the script to silently fail — no error output, but nothing renders.

## State Communication

`jarvis_wake.py` writes `{"mode": "idle|listening|thinking|speaking"}` to `/tmp/jarvis_viz_state.json`.
HUD polls `/state` every 200ms. States map to colors:

| Mode | Color | Purpose |
|------|-------|---------|
| idle | Ice Blue | Waiting for wake word |
| listening | Gold | Recording audio |
| thinking | Rose | Processing with Hermes |
| speaking | Emerald | Playing TTS response |

## CSS Legend Animation

```css
#legend{opacity:0;transition:opacity 0.6s,transform 0.6s}
#legend.show{opacity:1}
```

To re-trigger animation: remove class, `void el.offsetWidth`, add class.
