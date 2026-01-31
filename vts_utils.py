import asyncio
import websockets
import json
import os
import time
from config import ACTIONS


class VTSController:
    def __init__(self, port=8001):
        self.port = port
        self.uri = f"ws://127.0.0.1:{port}"
        self.ws = None
        self.token = None
        self.plugin_name = "Furina_Final"
        self.developer = "User"
        self.API_NAME = "VTubeStudioPublicAPI"

    async def connect(self):
        """连接 VTS (带心跳保活)"""
        print(f"🔌 [VTS] 正在连接端口 {self.port}...")
        try:
            self.ws = await websockets.connect(self.uri, ping_interval=20, ping_timeout=30)
            print("✅ [VTS] WebSocket 连接成功！")

            if os.path.exists("token.txt"):
                with open("token.txt", "r") as f:
                    self.token = f.read().strip()
                if await self.authenticate():
                    return True

            print("👋 [VTS] Token 无效，尝试重新申请...")
            await self.request_new_token()
            return await self.authenticate()

        except Exception as e:
            print(f"❌ [VTS] 连接失败: {e}")
            return False

    async def _safe_send(self, req):
        """🛡️ 安全发送函数 (自动重连)"""
        if not self.ws:
            print("⚠️ [VTS] 连接未建立，尝试连接...")
            if not await self.connect(): return

        try:
            await self.ws.send(json.dumps(req))
        except (websockets.exceptions.ConnectionClosedError, websockets.exceptions.ConnectionClosedOK, BrokenPipeError):
            print("🚨 [VTS] 检测到连接断开！正在紧急重连...")
            if await self.connect():
                print("🔄 [VTS] 重连成功！补发指令...")
                try:
                    await self.ws.send(json.dumps(req))
                except Exception as e:
                    print(f"❌ [VTS] 补发失败: {e}")
            else:
                print("❌ [VTS] 重连失败，放弃本次指令。")
        except Exception as e:
            print(f"⚠️ [VTS] 发送指令异常: {e}")

    async def request_new_token(self):
        req = {
            "apiName": self.API_NAME, "apiVersion": "1.0", "requestID": "token_req",
            "messageType": "AuthenticationTokenRequest",
            "data": {"pluginName": self.plugin_name, "pluginDeveloper": self.developer}
        }
        await self.ws.send(json.dumps(req))
        print("🚨 请在 VTS 点击 Allow...")
        while True:
            resp = json.loads(await self.ws.recv())
            if "authenticationToken" in resp.get("data", {}):
                self.token = resp["data"]["authenticationToken"]
                with open("token.txt", "w") as f: f.write(self.token)
                print("🎉 Token 获取成功！")
                break

    async def authenticate(self):
        req = {
            "apiName": self.API_NAME, "apiVersion": "1.0", "requestID": "auth",
            "messageType": "AuthenticationRequest",
            "data": {"pluginName": self.plugin_name, "pluginDeveloper": self.developer,
                     "authenticationToken": self.token}
        }
        if self.ws:
            await self.ws.send(json.dumps(req))
            resp = json.loads(await self.ws.recv())
            return resp.get("data", {}).get("authenticated")
        return False

    async def trigger_action(self, action_name):
        hotkey_id = ACTIONS.get(action_name)
        if not hotkey_id: return
        req = {
            "apiName": self.API_NAME, "apiVersion": "1.0", "requestID": f"act_{action_name}",
            "messageType": "HotkeyTriggerRequest",
            "data": {"hotkeyID": hotkey_id}
        }
        await self._safe_send(req)

    async def trigger_combo(self, action_list, delay=1.0):
        print(f"🤸 执行连招: {action_list}")
        for action in action_list:
            await self.trigger_action(action)
            if action != action_list[-1]:
                await asyncio.sleep(delay)

    async def move_eyes(self, x, y):
        req = {
            "apiName": self.API_NAME, "apiVersion": "1.0", "requestID": "EyeMove",
            "messageType": "InjectParameterDataRequest",
            "data": {
                "mode": "set",
                "parameterValues": [
                    {"id": "ParamEyeBallX", "value": x},
                    {"id": "ParamEyeBallY", "value": y}
                ]
            }
        }
        await self._safe_send(req)

    async def look_at_camera(self):
        await self.move_eyes(0, 0)

    async def look_thinking(self):
        await self.move_eyes(0.6, 0.8)

    async def look_shy(self):
        await self.move_eyes(0, -0.8)

    async def close(self):
        if self.ws: await self.ws.close()

    async def set_background(self, filename):
        """
        发送请求给 VTS 切换背景
        :param filename: 必须是 StreamingAssets/Backgrounds 下的完整文件名
        """
        # ✅ 修复：使用 self.ws 而不是 self.websocket
        if not self.ws: return

        req = {
            "apiName": "VTubeStudioPublicAPI",
            "apiVersion": "1.0",
            "requestID": f"BGChange_{int(time.time())}",
            "messageType": "ChangeBackgroundRequest",
            "data": {
                "backgroundName": filename
            }
        }
        # 使用 _safe_send 确保稳定
        await self._safe_send(req)