#!/Users/qhdh/.hermes/hermes-agent/venv/bin/python3
"""贾维斯 HUD — HTML Canvas 炫光版 HTTP 服务"""
import json, os, threading, webbrowser, time
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

HOST = "127.0.0.1"
PORT = 18326
STATE_FILE = "/tmp/jarvis_viz_state.json"
HTML_FILE = os.path.join(os.path.dirname(__file__), "jarvis_hud.html")

class ThreadingServer(ThreadingMixIn, HTTPServer):
    allow_reuse_address = True
    daemon_threads = True

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/state":
            try:
                with open(STATE_FILE) as f:
                    data = json.load(f)
            except:
                data = {"mode": "idle"}
            self.send_response(200)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Type", "application/json")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(json.dumps(data).encode())
        elif self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html;charset=utf-8")
            self.send_header("Connection", "close")
            with open(HTML_FILE, "rb") as f:
                data = f.read()
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_response(404)
            self.send_header("Connection", "close")
            self.end_headers()
    def log_message(self, *a): pass

def open_browser():
    time.sleep(0.5)
    webbrowser.open(f"http://{HOST}:{PORT}")

if __name__ == "__main__":
    t = threading.Thread(target=open_browser, daemon=True)
    t.start()
    server = ThreadingServer((HOST, PORT), Handler)
    server.serve_forever()
