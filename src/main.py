import RPi.GPIO as GPIO
from time import sleep
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
import os
import json
import random

# モーターピン定義
motorPin = (18, 23, 24, 25)
stepsPerRevolution = 2048

# データ保存用辞書
heart_rate_map = {}
heart_rate_history = {}
device_direction = {}
rpm_map = {}

# ゲーム開始状態
game_running = False

# パラメータ
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
    for _ in range(8):
        for j in range(4):
            for i in range(4):
                if direction == 'c':
                    GPIO.output(motorPin[i], (0x99 >> j) & (0x08 >> i))
                else:
                    GPIO.output(motorPin[i], (0x99 << j) & (0x80 >> i))
            sleep(stepSpeed)

# メインループ
def motor_loop():
    print("[モーターループ起動]")
    while True:
        if not game_running or not heart_rate_map:
            sleep(0.1)
            continue

        snapshot = heart_rate_map.copy()
        for device_id, bpm in snapshot.items():
            rpm = rpm_map.get(device_id, 15)
            direction = device_direction.get(device_id, 'c')
            stepSpeed = (60 / rpm) / stepsPerRevolution
            safe_stepSpeed = max(stepSpeed * 4, MIN_STEPSPEED)
            rotary(direction, safe_stepSpeed)

# HTTPサーバ
class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            if self.path in ["/", "/index.html"]:
                with open("index.html", "rb") as f:
                    body = f.read()
                self.send_response(200)
                self.send_header('Content-type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(body)
                return

            elif self.path == "/graph.html":
                with open("graph.html", "rb") as f:
                    body = f.read()
                self.send_response(200)
                self.send_header('Content-type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(body)
                return

            elif self.path == "/api":
                status = {
                    "running": game_running,
                    "heart_rates": heart_rate_map,
                    "rpm_map": rpm_map,
                    "directions": device_direction
                }
                body = json.dumps(status).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            else:
                self.send_response(404)
                self.end_headers()

        except Exception as e:
            print("GETエラー:", e)

    def do_POST(self):
        global game_running
        try:
            if self.path == "/start":
                game_running = True
                print("[ゲーム開始受信] 回転を開始します")
                self.send_response(200)
                self.end_headers()
                self.wfile.write("ゲーム開始".encode("utf-8"))
                return

            if self.path == "/stop":
                game_running = False
                print("[ゲーム終了受信] 回転を停止します")
                self.send_response(200)
                self.end_headers()
                self.wfile.write("ゲーム終了".encode("utf-8"))
                return

            # ゲーム中じゃなければ心拍数POSTを無視
            if not game_running:
                print("[心拍数POST受信] でもゲーム停止中なので無視")
                self.send_response(200)
                self.end_headers()
                self.wfile.write("ゲーム停止中なので心拍数無視".encode("utf-8"))
                return

            # 心拍数受信
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length).decode('utf-8').strip().strip('"')
            print(f"[心拍数POST受信] {repr(post_data)}")

            if ':' not in post_data:
                raise ValueError("形式不正（コロンが含まれていません）")

            device_id, bpm_str = post_data.split(":")
            bpm = int(float(bpm_str))

            if device_id not in device_direction:
                device_direction[device_id] = 'c'
                print(f"[初期化] {device_id} を登録")

            # BPMによるRPM設定
            if bpm <= 70:
                rpm = 5
            elif bpm <= 80:
                rpm = 15
                if random.random() < 0.5:
                    prev = device_direction[device_id]
                    device_direction[device_id] = 'a' if prev == 'c' else 'c'
                    print(f"[反転] {device_id}: {prev} → {device_direction[device_id]}")
            else:
                rpm = 30
                if random.random() < 0.5:
                    prev = device_direction[device_id]
                    device_direction[device_id] = 'a' if prev == 'c' else 'c'
                    print(f"[反転] {device_id}: {prev} → {device_direction[device_id]}")

            rpm_map[device_id] = rpm
            heart_rate_map[device_id] = bpm
            heart_rate_history.setdefault(device_id, []).append(bpm)
            heart_rate_history[device_id] = heart_rate_history[device_id][-50:]

            self.send_response(200)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write('心拍数を受信しました'.encode('utf-8'))

        except Exception as e:
            print("POSTエラー:", e)
            self.send_response(400)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write('無効なデータ形式です（例: device01:85）'.encode('utf-8'))

# サーバ起動
def run_web_server(port=8080):
    os.chdir(os.path.dirname(__file__))
    httpd = HTTPServer(('', port), SimpleHandler)
    print(f"[HTTP Server running on port {port}]")
    httpd.serve_forever()

if __name__ == '__main__':
    setup_motor()
    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()
    print("[Motor loop starting...]")
    try:
        motor_loop()
    except KeyboardInterrupt:
        GPIO.cleanup()
