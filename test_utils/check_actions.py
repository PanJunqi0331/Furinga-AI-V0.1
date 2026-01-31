import asyncio
import pyvts
import json

# 配置信息
plugin_info = {
    "plugin_name": "Digital_Human_Inspector",
    "developer": "MyName",
    "authentication_token_path": "./token.txt"
}


async def main():
    vts = pyvts.vts(plugin_info=plugin_info)

    print("⏳ 正在连接 VTube Studio...")
    try:
        await vts.connect()
    except ConnectionRefusedError:
        print("❌ 连接失败！请检查 VTube Studio 是否开启了 API 开关 (端口8001)")
        return

    # 鉴权
    print("🔑 正在验证权限...")
    await vts.request_authenticate_token()
    await vts.request_authenticate()

    # === 修正点在这里：requestHotKeyList ===
    print("🔍 正在读取模型自带的动作...")
    response = await vts.request(vts.vts_request.requestHotKeyList())

    # 解析结果
    if 'data' in response and 'availableHotkeys' in response['data']:
        hotkeys = response['data']['availableHotkeys']
        print(f"\n✅ 成功！检测到 {len(hotkeys)} 个可用动作：")
        print("=" * 40)
        for hk in hotkeys:
            # 打印动作名称和ID
            print(f"名称: {hk['name']}")
            print(f"ID:   {hk['hotkeyID']}")
            print(f"按键: {hk.get('keyCombination', '无按键绑定')}")
            print("-" * 20)

        print("\n💡 提示：要把这些ID复制下来，下一步代码里要用！")
    else:
        print("⚠️ 奇怪，这个模型好像没有预设热键 (Hotkeys)。")
        print("你可能需要去 VTube Studio 设置 -> 热键设置 -> 手动添加几个动作。")

    await vts.close()


if __name__ == "__main__":
    asyncio.run(main())