import asyncio
from vts_utils import VTSController


async def test_bg_switch():
    # 1. 初始化控制器
    vts = VTSController(port=8001)

    print("🚀 [测试] 正在连接 VTS...")

    # 2. 连接并自动认证 (会读取 token.txt 或请求新 token)
    if await vts.connect():
        print("✅ [测试] 认证通过！准备发送切换指令...")

        # 3. 发送切换背景指令
        # ⚠️ 请确保 VTube Studio/StreamingAssets/Backgrounds 文件夹里真的有这张图！
        target_image = "palais_tea.jpg"

        await vts.set_background(target_image)
        print(f"📡 [测试] 指令已发送: {target_image}")

        # 等待几秒看看效果
        await asyncio.sleep(2)

        # 断开连接
        await vts.close()
        print("👋 [测试] 测试结束")
    else:
        print("❌ [测试] 连接或认证失败，请检查 VTS 是否开启或 token 是否有效")


if __name__ == "__main__":
    asyncio.run(test_bg_switch())