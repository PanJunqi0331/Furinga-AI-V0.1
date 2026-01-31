import asyncio
import websockets
import json
import os

# === 配置 ===
# 必须和你刚才测试成功的一样！
VTS_URI = "ws://127.0.0.1:8001"

# 插件信息
PLUGIN_NAME = "Fufu_Manual_Inspector"
DEVELOPER = "MyName"


async def main():
    print(f"🔌 正在直连 VTube Studio ({VTS_URI})...")

    async with websockets.connect(VTS_URI) as ws:
        print("✅ 连接成功！")

        # 1. 请求 Token (鉴权)
        # ------------------------------------------------
        print("\n👉 【请看 VTS 屏幕！】点击弹窗的 'Allow' (允许)...")

        # 构造鉴权请求
        auth_request = {
            "apiName": "VTubeStudioPublicAPI",
            "apiVersion": "1.0",
            "requestID": "auth_token_req",
            "messageType": "AuthenticationTokenRequest",
            "data": {
                "pluginName": PLUGIN_NAME,
                "pluginDeveloper": DEVELOPER
            }
        }
        await ws.send(json.dumps(auth_request))

        # 等待回复
        response = await ws.recv()
        resp_json = json.loads(response)

        if "data" not in resp_json or "authenticationToken" not in resp_json["data"]:
            print(f"❌ 鉴权失败/拒绝: {resp_json}")
            return

        token = resp_json["data"]["authenticationToken"]
        print("🔑 拿到 Token 了！正在登录...")

        # 2. 使用 Token 登录
        # ------------------------------------------------
        login_request = {
            "apiName": "VTubeStudioPublicAPI",
            "apiVersion": "1.0",
            "requestID": "auth_login_req",
            "messageType": "AuthenticationRequest",
            "data": {
                "pluginName": PLUGIN_NAME,
                "pluginDeveloper": DEVELOPER,
                "authenticationToken": token
            }
        }
        await ws.send(json.dumps(login_request))
        await ws.recv()  # 接收登录确认（通常是 authenticated: true）
        print("✅ 登录成功！")

        # 3. 获取动作列表 (Hotkeys)
        # ------------------------------------------------
        print("\n🔍 正在读取动作...")
        hotkey_req = {
            "apiName": "VTubeStudioPublicAPI",
            "apiVersion": "1.0",
            "requestID": "get_hotkeys",
            "messageType": "HotkeysInCurrentModelRequest"
        }
        await ws.send(json.dumps(hotkey_req))

        hk_response = await ws.recv()
        hk_json = json.loads(hk_response)

        # 4. 打印结果
        # ------------------------------------------------
        if 'data' in hk_json and 'availableHotkeys' in hk_json['data']:
            hotkeys = hk_json['data']['availableHotkeys']
            print(f"\n🎉 成功！找到了 {len(hotkeys)} 个动作：")
            print("=" * 50)
            for hk in hotkeys:
                print(f"动作名称: {hk['name']}")
                print(f"动作 ID : {hk['hotkeyID']}")
                print("-" * 20)
            print("=" * 50)

            # 顺便把 token 保存下来，方便以后用
            with open("token.txt", "w") as f:
                f.write(token)
            print("💾 Token 已保存到 token.txt")

        else:
            print("⚠️ 这个模型好像没有设置按键动作 (Hotkeys)。")
            print("请去 VTube Studio -> 设置 -> 第四个图标(按键) -> 绑定几个表情。")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"❌ 发生错误: {e}")