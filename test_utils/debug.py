import asyncio
import websockets
import json

# 端口号
PORT = 8001
URI = f"ws://127.0.0.1:{PORT}"


async def debug_vts():
    print(f"🔌 正在连接端口 {PORT}...")

    async with websockets.connect(URI) as ws:
        print("✅ 连接成功！发送修正后的请求...")

        # 👇 关键修改：这里必须是 "VTubeStudioPublicAPI"
        token_req = {
            "apiName": "VTubeStudioPublicAPI",  # <--- 改了这里！
            "apiVersion": "1.0",
            "requestID": "token_final_fix",
            "messageType": "AuthenticationTokenRequest",
            "data": {
                "pluginName": "Furina_Fixed_v1",  # 新名字
                "pluginDeveloper": "User"
            }
        }
        await ws.send(json.dumps(token_req))

        print("\n" + "=" * 40)
        print("🚨🚨🚨 请看 VTube Studio 屏幕！必须弹窗！ 🚨🚨🚨")
        print("🚨🚨🚨 点击【Allow / 允许】！ 🚨🚨🚨")
        print("=" * 40 + "\n")

        # 死等 Token
        while True:
            resp = await ws.recv()
            data = json.loads(resp)

            if "authenticationToken" in data.get("data", {}):
                token = data["data"]["authenticationToken"]
                print("🎉🎉🎉 拿到 Token 了！！！")
                print("👇 快把下面这串乱码复制到 token.txt 里：")
                print(token)

                # 自动保存
                with open("token.txt", "w") as f:
                    f.write(token)
                print("💾 已自动保存到 token.txt")
                break
            elif "errorID" in data.get("data", {}):
                print(f"❌ 还是报错: {data['data']['message']}")
                break


if __name__ == "__main__":
    asyncio.run(debug_vts())