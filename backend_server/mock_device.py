import requests
import time
import random

# 你的 FastAPI 本地服务地址
API_URL = "http://127.0.0.1:8000/api/device/telemetry"


def send_mock_data():
    """模拟 ESP32 采集并发送数据"""
    # 生成带有一点随机波动的数据，模拟真实物理环境
    payload = {
        "device_id": "sensairshuttle_001",
        "timestamp": int(time.time()),
        "sensors": {
            "temperature": round(random.uniform(20.0, 35.0), 1),
            "humidity": round(random.uniform(40.0, 85.0), 1),
            "pressure": 101.2,
            "gas_resistance": random.randint(10000, 20000),
            "acc_x": 0.01,
            "acc_y": -0.02,
            "acc_z": 0.98,
            "gyro_x": 0.1,
            "gyro_y": 0.0,
            "gyro_z": -0.1,
            "mag_x": 12.3,
            "mag_y": 8.6,
            "mag_z": -35.1
        },
        "status": {
            "wifi": "connected",
            "mqtt": "disconnected",  # 当前走 HTTP 测试，暂时标为未连接
            "fan": random.choice([0, 1]),
            "pump": 0,
            "light": 0
        }
    }

    try:
        print(f"📡 正在发送模拟数据: 温度={payload['sensors']['temperature']}°C, 湿度={payload['sensors']['humidity']}%")
        response = requests.post(API_URL, json=payload, timeout=5)

        if response.status_code == 200:
            print(f"✅ 发送成功! 服务器响应: {response.json()}")
        else:
            print(f"❌ 发送失败! 状态码: {response.status_code}, 错误: {response.text}")

    except requests.exceptions.ConnectionError:
        print("🚨 连接被拒绝！请确认你的 uvicorn FastAPI 服务是否已在 8000 端口启动。")


if __name__ == "__main__":
    print("🚀 启动模拟端侧设备...")
    # 循环发送 5 次，每次间隔 2 秒
    for i in range(5):
        send_mock_data()
        time.sleep(2)
    print("🛑 模拟发送结束。")
    