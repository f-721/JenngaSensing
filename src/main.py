import RPi.GPIO as GPIO
from time import sleep
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
import os
import json
import random
from datetime import datetime

# モーターピン定義
motorPin = (18, 23, 24, 25)
stepsPerRevolution = 2048

# データ保存用辞書
heart_rate_map = {}
heart_rate_history = {}
device_direction = {}
device_previous_bpm = {}

# パラメータ
SCALE = 1.7
MAX_RPM = 180
MIN_RPM = 10
MIN_STEPSPEED = 0.003

# モーター初期化
def setup_motor():
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    for pin in motorPin:
        GPIO.setup(pin, GPIO.OUT)

# モーター回転制御
def rotary(direction, stepSpeed):
    for j in range(4):
        for i in range(4):
            if direction == 'c':
                GPIO.output(motorPin[i], 0x99 >> j & (0x08 >> i))
            else:
                GPIO.output(motorPin[i], 0x99 << j & (0x80 >> i))
            sleep(stepSpeed)

# メインループ（回転だけ行う）
def motor_loop():
    while True:
        if not heart_rate_map:
            sleep(0.1)
            continue

        snapshot = heart_rate_map.copy()
        for device_id, bpm in snapshot.items():
            rpm = max(min(bpm * SCALE, MAX_RPM), MIN_RPM)
            stepSpeed = (60 / rpm) / stepsPerRevolution
            safe_stepSpeed = max(stepSpeed * 4, MIN_STEPSPEED)
            rotary(device_direction[device_id], safe_stepSpeed)

        sleep(0.05)

# HTTPサーバ部分
class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            if self.path in ["/", "/index.html"]:
                path = "index.html"
            elif self.path == "/graph.html":
                path = "graph.html"
            elif self.path == "/graph-data":
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps(heart_rate_history).encode('utf-8'))
                return
            elif self.path == "/api":
                self.send_response(200)
                self.send_header('Content-type', 'text/plain; charset=utf-8')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                if heart_rate_map:
                    response = "\n".join(f"{k}:{v}" for k, v in heart_rate_map.items())
                    self.wfile.write(response.encode('utf-8'))
                else:
                    self.wfile.write("心拍数データがない".encode('utf-8'))
                return
            else:
                self.send_response(404)
                self.end_headers()
                self.wfile.write("ページが見つかりません".encode('utf-8'))
                return

            with open(path, "rb") as f:
                self.send_response(200)
                self.send_header('Content-type', 'text/html; charset=utf-8')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(f.read())
        except FileNotFoundError:
            self.send_response(404)
            self.end_headers()
            self.wfile.write("ファイルが見つかりません".encode('utf-8'))

    def do_POST(self):
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length).decode('utf-8').strip().strip('\'"')
            print(f"[POST受信] 内容: {repr(post_data)}")

            if ':' not in post_data:
                raise ValueError("形式不正（コロンが含まれていません）")

            device_id, bpm_str = post_data.split(":")
            bpm = int(float(bpm_str))

            # デバイス登録
            if device_id not in device_direction:
                device_direction[device_id] = 'c'
                device_previous_bpm[device_id] = 0
                print(f"[初期化] {device_id} を登録")

            # 70以上なら抽選処理（POSTごとに1回）
            if bpm >= 70:
                if random.random() < 0.5:
                    prev_dir = device_direction[device_id]
                    device_direction[device_id] = 'a' if prev_dir == 'c' else 'c'
                    print(f"[反転] {device_id}: {prev_dir} → {device_direction[device_id]} (bpm={bpm})")
                else:
                    print(f"[維持] {device_id}: {device_direction[device_id]} のまま (bpm={bpm})")

            heart_rate_map[device_id] = bpm
            heart_rate_history.setdefault(device_id, []).append(bpm)
            heart_rate_history[device_id] = heart_rate_history[device_id][-50:]

            self.send_response(200)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write('心拍数を受信しました'.encode('utf-8'))

        except Exception as e:
            print("エラー:", e)
            self.send_response(400)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write('無効なデータ形式です（例: device01:85）'.encode('utf-8'))

# サーバ起動
def run_web_server(port=8080):
    os.chdir(os.path.dirname(__file__))
    httpd = HTTPServer(('', port), SimpleHandler)
    print(f"HTTP Server running on port {port}")
    httpd.serve_forever()

if __name__ == '__main__':
    setup_motor()

    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()

    print("Motor loop starting...")

    try:
        motor_loop()
    except KeyboardInterrupt:
        GPIO.cleanup()