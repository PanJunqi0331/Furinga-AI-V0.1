import asyncio
import os
import subprocess
import time
import socket
import random
import requests
import aioconsole
import atexit
from logger_utils import setup_logger

# 🛡️ 启动日志 & 防代理
setup_logger()
os.environ["NO_PROXY"] = "127.0.0.1,localhost"

from config import (
    ACTIONS, SOVITS_ROOT, VTS_EXE_PATH, SOVITS_API_URL, VTS_PORT,
    INPUT_TIMEOUT, DEFAULT_BACKGROUND, SCENE_MAP
)
from vts_utils import VTSController
# ✅ 引入 BGMManager
from audio_utils import AudioManager, BGMManager
from brain_utils import Brain
from memory_utils import MemoryManager
from sentiment_utils import SentimentEngine

# ================= ⚙️ 全局变量 =================
CURRENT_SPEAK_TASK = None
last_interaction_time = time.time()
global_memory_mgr = None


# ================= 📨 输入缓冲管理器 =================
class InputBufferManager:
    def __init__(self, timeout=1.5):
        self.buffer = []
        self.last_time = 0
        self.timeout = timeout
        self.is_processing = False

    def add_message(self, text):
        if not text.strip(): return
        self.buffer.append(text)
        self.last_time = time.time()
        print(f"👂 (收到碎片: {text}...)")

    def has_finished_speaking(self):
        if not self.buffer: return False
        if self.is_processing: return False
        return (time.time() - self.last_time) > self.timeout

    def pop_full_message(self):
        if not self.buffer: return None
        full_text = "，".join(self.buffer)
        self.buffer = []
        return full_text


# ================= 🕵️‍♂️ 工具函数 =================
def is_process_running(process_name):
    try:
        return process_name in subprocess.getoutput(f'tasklist /FI "IMAGENAME eq {process_name}"')
    except:
        return False


def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex(('127.0.0.1', port)) == 0


def launch_services():
    """
    🚀 启动服务 (带独立进程检查)
    """
    print("\n--------------- 🚀 正在初始化数字人环境 ---------------")

    # 1. 检查并启动 VTube Studio
    if is_process_running("VTube Studio.exe"):
        print("✅ [检测] VTube Studio 已在运行，跳过启动。")
    elif os.path.exists(VTS_EXE_PATH):
        print("🚀 [启动] 正在唤醒 VTube Studio...")
        subprocess.Popen(f'"{VTS_EXE_PATH}"', shell=True, close_fds=True)
        time.sleep(5)
    else:
        print("⚠️ [警告] 找不到 VTube Studio 路径，请手动启动。")

    # 等待 VTS 端口就绪
    if not is_port_in_use(VTS_PORT):
        print("⏳ 等待 VTube Studio API 就绪...")
        for i in range(15):
            if is_port_in_use(VTS_PORT): break
            time.sleep(1)

    # 2. 检查并启动 GPT-SoVITS
    if is_port_in_use(9880):
        print("✅ [检测] GPT-SoVITS 服务已在线，跳过启动。")
    else:
        print("🚀 [启动] 正在启动语音服务 (GPT-SoVITS)...")
        python_exe = os.path.join(SOVITS_ROOT, "runtime", "python.exe")
        try:
            cmd = f'start /min "" "{python_exe}" api_v2.py -c fufu.yaml'
            subprocess.Popen(cmd, shell=True, cwd=SOVITS_ROOT)

            print("⏳ 等待 TTS 服务加载 (约8秒)...")
            time.sleep(8)
        except Exception as e:
            print(f"❌ [错误] 无法启动 SoVITS: {e}")

    # 3. 最后的连通性测试 (预热)
    try:
        requests.post(f"{SOVITS_API_URL}/tts", json={"text": "。", "text_lang": "zh", "ref_audio_path": "dummy.wav"},
                      timeout=5)
    except:
        pass
    print("--------------- 环境检查完毕 ---------------")


# 🔥 核心优化：打印实时状态条 (增加当前活动显示)
def print_status_prompt(username, memory_mgr, sentiment_engine):
    # 1. 个人状态
    user_state = memory_mgr.get_user_state_obj()

    # 2. 全局状态
    global_state = sentiment_engine.get_global_state()
    mood = global_state["mood"]
    energy = global_state["energy"]

    # 🔥 新增：获取当前活动，并截断过长的文本，让你知道她在干嘛
    current_act = global_state.get("current_activity", "未知")
    if len(current_act) > 10: current_act = current_act[:9] + "..."

    # 图标映射
    mood_icon = "😐"
    if mood >= 80:
        mood_icon = "😆"
    elif mood >= 60:
        mood_icon = "😊"
    elif mood <= 20:
        mood_icon = "😡"
    elif mood <= 40:
        mood_icon = "😞"

    energy_icon = "⚡"
    if energy < 30: energy_icon = "🪫"

    # 构造状态条 (增加 📅 活动显示)
    status_bar = f"\n[💖 {int(user_state.affection)} | 📅 {current_act} | {energy_icon} {int(energy)} | {mood_icon} {int(mood)}] 👤 {username}: "
    print(status_bar, end="", flush=True)


# ================= 💾 强制退出保护钩子 =================
def emergency_save():
    if global_memory_mgr:
        print("\n🚨 [紧急存档] 检测到程序异常中断，正在尝试强制保存...")
        global_memory_mgr.save()
        print("✅ [紧急存档] 数据已写回磁盘。")


atexit.register(emergency_save)

# ================= 🕰️ 后台监视任务 =================
current_bg_file = ""


async def update_scene_logic(activity_text, vts):
    global current_bg_file

    target_bg = DEFAULT_BACKGROUND

    # 遍历关键词寻找匹配的背景
    for keyword, filename in SCENE_MAP.items():
        if keyword in activity_text:
            target_bg = filename
            break

    if target_bg != current_bg_file:
        print(f"🖼️ [场景切换] 检测到活动 '{activity_text}' -> 切换背景: {target_bg}")
        await vts.set_background(target_bg)
        current_bg_file = target_bg


# ================= 🕰️ 后台监视任务 (V22.0 剧情推进版) =================
async def monitor_idle_status(vts, audio_mgr, brain, memory_mgr, sentiment_engine, bgm_mgr, input_mgr):
    global last_interaction_time, CURRENT_SPEAK_TASK

    IDLE_START_TIME = 30
    PROACTIVE_TALK_THRESHOLD = 120  # 2分钟不说话触发

    last_idle_action_time = 0
    has_triggered_talk = False
    idle_talk_sequence = 0

    last_detected_activity = sentiment_engine.get_global_state().get("current_activity", "")

    while True:
        await asyncio.sleep(1)

        if input_mgr.is_processing:
            last_interaction_time = time.time()
            continue

        user_state = memory_mgr.get_user_state_obj()
        g_state = sentiment_engine.get_global_state()
        current_energy = g_state["energy"]
        current_mood = g_state["mood"]
        current_act = g_state.get("current_activity", "")

        await update_scene_logic(current_act, vts)
        if bgm_mgr: bgm_mgr.update_state(current_mood, current_energy, current_act)

        if user_state.affection <= -50 or current_energy < 10:
            continue

        if CURRENT_SPEAK_TASK and not CURRENT_SPEAK_TASK.done():
            last_interaction_time = time.time()
            continue

        now = time.time()
        idle_duration = now - last_interaction_time

        if idle_duration < 2:
            idle_talk_sequence = 0
            has_triggered_talk = False
            last_detected_activity = current_act

        if idle_duration > IDLE_START_TIME and (now - last_idle_action_time) > 15:
            if current_energy > 20:
                safe_actions = list(ACTIONS.keys())
                if safe_actions:
                    await vts.trigger_action(random.choice(safe_actions))
            last_idle_action_time = now

        is_scene_changed = (current_act != last_detected_activity) and (current_act != "")

        if is_scene_changed or (idle_duration > PROACTIVE_TALK_THRESHOLD and not has_triggered_talk):
            if current_energy >= 30:
                idle_talk_sequence += 1

                injection = f"【系统提示】用户已经沉默了 {int(idle_duration)} 秒。"
                if is_scene_changed:
                    injection += f"\n⚠️【场景切换】你的活动刚刚从“{last_detected_activity}”变成了“{current_act}”。"
                    injection += "\n💡【回复指引】请结合“用户长时间不理你”这个事实，表现出傲娇或不满。"
                    injection += "\n例如：“哼，既然你半天都不说话，那本芙宁娜要去（新活动）了，不陪你发呆了！”"
                    print(f"🎬 [剧情推进] 检测到场景切换: {last_detected_activity} -> {current_act}")
                else:
                    print(f"👀 [观察] 用户沉默，尝试第 {idle_talk_sequence} 次搭话...")

                reply = brain.think(
                    memory_mgr,
                    sentiment_injection=injection,
                    is_proactive=True,
                    proactive_stage=idle_talk_sequence
                )

                dirty_phrases = ["喂！让我把话说完！", "让我把话说完"]
                for phrase in dirty_phrases: reply = reply.replace(phrase, "")
                if "[" not in reply: reply = f"[傲娇] {reply}"

                print(f"\n🎭 芙宁娜(主动): {reply}")
                memory_mgr.add_history("assistant", reply)
                memory_mgr.save()
                CURRENT_SPEAK_TASK = asyncio.create_task(audio_mgr.speak(reply, vts))
                print_status_prompt(memory_mgr.current_user, memory_mgr, sentiment_engine)

            last_interaction_time = time.time()
            has_triggered_talk = True
            last_detected_activity = current_act


# ================= 🎧 异步监听循环 =================
async def listen_loop(input_mgr, username):
    print("🎤 [系统] 监听服务已启动 (输入 'exit' 退出)...")
    while True:
        try:
            text = await aioconsole.ainput("")
            input_mgr.add_message(text)
        except asyncio.CancelledError:
            break
        except Exception as e:
            await asyncio.sleep(1)


# ================= 🎬 主程序 =================
async def main():
    global CURRENT_SPEAK_TASK, last_interaction_time, global_memory_mgr

    print("\n📚 === 芙宁娜的记忆殿堂 ===")
    username = input("请输入你的名字 (读取存档): ").strip()
    if not username: username = "旅行者"

    launch_services()

    vts = VTSController(port=VTS_PORT)
    audio_mgr = AudioManager()
    bgm_mgr = BGMManager()
    brain = Brain()
    memory_mgr = MemoryManager()
    global_memory_mgr = memory_mgr
    sentiment_engine = SentimentEngine()
    input_mgr = InputBufferManager(timeout=INPUT_TIMEOUT)

    memory_mgr.load_user(username)
    user_state = memory_mgr.get_user_state_obj()
    g_state = sentiment_engine.get_global_state()

    if not await vts.connect(): return

    lvl, title, _ = memory_mgr.calculate_status()
    print(f"\n🎉 === 芙宁娜 & {username} ===")
    print(f"💖 好感度: {user_state.affection} | 🎭 等级: {title}")
    print(f"⚡ 精力值: {int(g_state['energy'])}/100 | 😊 心情: {int(g_state['mood'])}/100")
    print("==============================\n")

    chat_history = memory_mgr.data.get('chat_history', [])
    summary = memory_mgr.data.get("summary", "")
    is_new_user = (len(chat_history) == 0) and (not summary)

    welcome = ""

    if is_new_user:
        welcome = f"[傲娇] 咳咳！初次见面！我是芙宁娜·德·枫丹！"
    elif user_state.affection <= -100:
        welcome = "[生气] ……（无视）"
    else:
        welcome = f"[傲娇] 又是你啊，{username}。"
        if user_state.affection >= 300:
            print("🤔 (芙芙正在回忆上次聊了什么...)")
            # 🔥 修复：使用 get 安全传入当前活动和地点
            dynamic_welcome = brain.generate_dynamic_welcome(
                memory_mgr,
                g_state['mood'],
                g_state['energy'],
                g_state.get('current_activity', '发呆'),
                g_state.get('current_location', '家里')
            )
            if dynamic_welcome:
                welcome = dynamic_welcome
            else:
                welcome = f"[笑] {username}！你终于来了，我等你好久了！"

    print(f"🎭 芙宁娜: {welcome}")
    if user_state.affection > -100:
        memory_mgr.add_history("assistant", welcome)

    import datetime
    now_h = datetime.datetime.now().hour
    if 22 <= now_h or now_h < 7:
        await vts.trigger_action("困")
    else:
        await vts.trigger_action("摊手")

    CURRENT_SPEAK_TASK = asyncio.create_task(audio_mgr.speak(welcome, vts))

    monitor_task = asyncio.create_task(
        monitor_idle_status(vts, audio_mgr, brain, memory_mgr, sentiment_engine, bgm_mgr, input_mgr))
    listen_task = asyncio.create_task(listen_loop(input_mgr, username))

    print_status_prompt(username, memory_mgr, sentiment_engine)

    try:
        while True:
            await asyncio.sleep(0.1)
            memory_mgr.data["last_interaction_timestamp"] = time.time()

            g_state = sentiment_engine.get_global_state()
            current_act_text = g_state.get("current_activity", "")
            if bgm_mgr:
                bgm_mgr.update_state(g_state['mood'], g_state['energy'], current_act_text)

            if input_mgr.has_finished_speaking():
                user_input = input_mgr.pop_full_message()

                if user_input.lower() in ["quit", "exit", "退出", "再见", "拜拜"]:
                    print("💾 用户请求退出...")
                    break

                input_mgr.is_processing = True
                last_interaction_time = time.time()
                print(f"\n📝 [用户] {user_input}")

                current_user_state = memory_mgr.get_user_state_obj()
                new_user_state, prompt_injection, instant_action, reply_override = sentiment_engine.analyze(user_input,
                                                                                                            current_user_state)
                memory_mgr.save_user_state(new_user_state)

                is_stop, bl_reply, bl_action = sentiment_engine.check_blacklist_state(new_user_state)
                if is_stop:
                    if bl_reply:
                        CURRENT_SPEAK_TASK = asyncio.create_task(audio_mgr.speak(bl_reply, vts))
                    elif bl_action:
                        await vts.trigger_action(bl_action)
                    input_mgr.is_processing = False
                    print_status_prompt(username, memory_mgr, sentiment_engine)
                    continue

                if instant_action:
                    print(f"⚡ [动作触发] {instant_action}")
                    await vts.trigger_action(instant_action)

                is_interrupting = False
                ignore_interrupt_list = ["哈哈", "嗯", "嗯嗯", "对", "是", "哦", "啊", "tql", "666", "确实", "好",
                                         "继续"]
                is_short_reply = len(user_input) < 4 or any(w in user_input for w in ignore_interrupt_list)

                if audio_mgr.voice_channel.get_busy() and not is_short_reply:
                    is_interrupting = True
                    audio_mgr.stop()
                elif CURRENT_SPEAK_TASK and not CURRENT_SPEAK_TASK.done() and not is_short_reply:
                    CURRENT_SPEAK_TASK.cancel()

                if is_short_reply and audio_mgr.voice_channel.get_busy():
                    print("🔇 [系统] 检测到短回复，不打断芙芙说话。")

                if reply_override:
                    final_text = reply_override
                else:
                    print("⏳ (大脑思考中...)")
                    final_text = brain.think(memory_mgr, user_input, sentiment_injection=prompt_injection)

                if is_interrupting:
                    int_score, int_msg, int_phrase = sentiment_engine.get_interruption_reaction()
                    memory_mgr.update_affection(int_score)
                    print(f"\n💢 触发打断: {int_phrase}")
                    final_text = f"{int_phrase} {final_text}"
                    audio_mgr.stop()
                    try:
                        await CURRENT_SPEAK_TASK
                    except:
                        pass

                memory_mgr.add_history("assistant", final_text)
                memory_mgr.save()
                print(f"\r🎭 芙宁娜: {final_text}")

                CURRENT_SPEAK_TASK = asyncio.create_task(audio_mgr.speak(final_text, vts))
                asyncio.create_task(memory_mgr.compress_memory_if_needed(brain))

                last_interaction_time = time.time()
                input_mgr.is_processing = False
                print_status_prompt(username, memory_mgr, sentiment_engine)

    except KeyboardInterrupt:
        print("\n\n🛑 [系统] 检测到强制退出信号...")

    finally:
        print("\n📝 正在进行散场整理 (归档记忆中)...")
        if 'monitor_task' in locals() and not monitor_task.done():
            monitor_task.cancel()
        if 'listen_task' in locals() and not listen_task.done():
            listen_task.cancel()
        try:
            if hasattr(memory_mgr, "archive_session"):
                memory_mgr.archive_session(brain)
            else:
                memory_mgr.save()
        except Exception as e:
            print(f"⚠️ 归档过程出现错误: {e}")
        if vts:
            await vts.close()
        print("👋 芙宁娜: 下次演出再见啦！(程序已关闭)")


if __name__ == "__main__":
    asyncio.run(main())