import websocket
import json

# 1. 웹소켓 접속 (sh-002 운동으로 접속 시도)
url = "ws://localhost:8018/api/v1/ws/coach/sh-002"
print(f"🔌 Connecting to {url} ...")

ws = websocket.create_connection(url)

# 2. 데이터 딱 하나만 받기
print("👀 Waiting for data packet...")
response = ws.recv()
data = json.loads(response)

# 3. 보기 좋게 출력
# 영상 데이터(base64)는 너무 기니까 잘라서 보여줌
if "jpeg_b64" in data:
    data["jpeg_b64"] = "(...이미지 데이터 생략...)"

print("\n" + "="*50)
print("📦 [Real-Time Data Packet]")
print("="*50)
print(json.dumps(data, indent=2, ensure_ascii=False))
print("="*50)

ws.close()