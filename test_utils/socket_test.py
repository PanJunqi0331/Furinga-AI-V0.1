import asyncio
import websockets
import json


async def test_connection():
    # 这里的端口必须和你 VTS 设置里的一模一样！
    uri = "ws://127.0.0.1:8002"

    print(f"🕵️ 正在尝试连接 VTube Studio: {uri} ...")

    try:
        # 尝试建立连接
        async with websockets.connect(uri) as websocket:
            print("🎉【连接成功】！握手通过！")
            print("这意味着网络完全没问题，是之前的代码库(pyvts)设置有误。")

            # 发送一个问候包，看看 VTS 回不回复
            msg = {
                "apiName": "VTubeStudioPublicAPI",
                "apiVersion": "1.0",
                "requestID": "test_123",
                "messageType": "APIStateRequest"
            }
            await websocket.send(json.dumps(msg))
            response = await websocket.recv()
            print(f"📩 收到 VTS 回复: {response}")

    except ConnectionRefusedError:
        print("❌【连接被拒绝】端口不通！")
        print("原因可能是：VTS 没开、端口填错了、或者被防火墙拦截。")
    except Exception as e:
        print(f"❌【连接中断】错误详情: {e}")
        print("💡 如果这里报错 'Invalid HTTP response' 或 'EOFError'：")
        print("👉 100% 是 VTS 的 'Allowed IPs' 白名单没加 127.0.0.1！")


if __name__ == "__main__":
    # 如果报错说没有 websockets 库，请运行: pip install websockets
    asyncio.run(test_connection())