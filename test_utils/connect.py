import asyncio
import websockets
import json
import os
import random

# 端口号 (跟你截图里的一样)
VTS_PORT = 8001
VTS_URI = f"ws://127.0.0.1:{VTS_PORT}"

# 🔥 随机生成一个新名字，强迫 VTS 弹窗！
random_id = random.randint(1000, 9999)
PLUGIN_NAME = f"Furina_User_{random_id}"
DEVELOPER = "MyAI_Project"


async def get_token():
    print(f"🔌 正在连接端口 {VTS_PORT}...")

    async with websockets.connect(VTS_URI) as ws:
        print(f"✨ 已连接！正在以新身份【{PLUGIN_NAME}】敲门...")

        # 发送 token 请求
        req = {
            "apiName": "VTS",
            "apiVersion": "1.0",
            "requestID": "token_req",
            "messageType": "AuthenticationTokenRequest",
            "data": {
                "pluginName": PLUGIN_NAME,
                "pluginDeveloper": DEVELOPER
            }
        }
        await ws.send(json.dumps(req))

        print("\n" + "=" * 40)
        print(f"👉 请看 VTube Studio 屏幕！")
        print(f"👉 名字叫: {PLUGIN_NAME}")
        print(f"👉 必须点【Allow / 允许】！")
        print("=" * 40 + "\n")

        # 死循环等待
        while True:
            resp = await ws.recv()
            data = json.loads(resp)

            if data.get("messageType") == "AuthenticationTokenResponse":
                token = data.get("data", {}).get("authenticationToken")
                if token:
                    print("🎉🎉🎉 拿到 Token 了！")
                    with open("token.txt", "w") as f:
                        f.write(token)
                    print(f"💾 已保存到 token.txt (长度: {len(token)})")
                    print("🚀 现在去运行 main.py 吧！")
                    return
                else:
                    print("❌ 你点击了拒绝，或者请求超时。请重新运行！")
                    return


if __name__ == "__main__":
    if os.path.exists("token.txt"):
        os.remove("token.txt")  # 删掉旧的，重新来
    try:
        asyncio.run(get_token())
    except Exception as e:
        print(f"❌ 出错: {e}")