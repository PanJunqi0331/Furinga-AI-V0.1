import asyncio
import os
import subprocess
import time
import socket
import random
import requests
import aioconsole
import atexit
import json
from logger_utils import setup_logger
from sentiment_utils import SentimentEngine, handle_level_change

# 🛡️ 启动日志 & 防代理
setup_logger()
os.environ["NO_PROXY"] = "127.0.0.1,localhost"

from config import (
    ACTIONS, SOVITS_ROOT, VTS_EXE_PATH, SOVITS_API_URL, VTS_PORT,
    INPUT_TIMEOUT, DEFAULT_BACKGROUND, SCENE_MAP
)
from vts_utils import VTSController
from audio_utils import AudioManager
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
    """🚀 启动服务 (带独立进程检查)"""
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

    try:
        requests.post(f"{SOVITS_API_URL}/tts", json={"text": "。", "text_lang": "zh", "ref_audio_path": "dummy.wav"},
                      timeout=5)
    except:
        pass
    print("--------------- 环境检查完毕 ---------------")


# 🔥 打印状态条 (显示当前活动)
def print_status_prompt(username, memory_mgr, sentiment_engine):
    user_state = memory_mgr.get_user_state_obj()
    global_state = sentiment_engine.get_global_state()

    mood = global_state["mood"]
    energy = global_state["energy"]
    # 🔥 这里就是你在 global_state.json 里看到的 "current_activity"
    current_act = global_state.get("current_activity", "未知")

    if len(current_act) > 10: current_act = current_act[:9] + "..."

    mood_icon = "😐"
    if mood >= 80:
        mood_icon = "😆"
    elif mood <= 20:
        mood_icon = "😡"
    elif mood <= 40:
        mood_icon = "😞"

    energy_icon = "⚡"
    if energy < 30: energy_icon = "🪫"

    status_bar = f"\n[💖 {int(user_state.affection)} | 📅 {current_act} | {energy_icon} {int(energy)} | {mood_icon} {int(mood)}] 👤 {username}: "
    print(status_bar, end="", flush=True)


def emergency_save():
    if global_memory_mgr:
        print("\n🚨 [紧急存档] 检测到程序异常中断，正在尝试强制保存...")
        global_memory_mgr.save()
        print("✅ [紧急存档] 数据已写回磁盘。")


atexit.register(emergency_save)


# [main.py]
# [main.py] 中的 monitor_idle_status 函数
async def monitor_idle_status(vts, audio_mgr, brain, memory_mgr, sentiment_engine, input_mgr):
    global last_interaction_time, CURRENT_SPEAK_TASK

    IDLE_START_TIME = 30
    PROACTIVE_TALK_THRESHOLD = 120  # 120秒不说话触发常规搭话

    last_idle_action_time = 0
    has_triggered_talk = False
    idle_talk_sequence = 0

    last_detected_activity = sentiment_engine.get_global_state().get("current_activity", "")

    while True:
        await asyncio.sleep(1)

        # 1. 忙碌跳过
        if input_mgr.is_processing:
            last_interaction_time = time.time()
            continue

        # ================= 生活流自动切换 =================
        is_switched, new_act, new_loc = sentiment_engine.attempt_auto_switch(last_interaction_time)
        if is_switched:
            for key, bg_file in SCENE_MAP.items():
                if key in new_act:
                    await vts.set_background(bg_file)
                    break
        # =================================================

        # 2. 获取当前状态
        user_state = memory_mgr.get_user_state_obj()
        g_state = sentiment_engine.get_global_state()
        current_energy = g_state["energy"]
        current_act = g_state.get("current_activity", "")  # 再次确认最新状态

        # 3. 极低好感/精力不说话
        if user_state.affection <= -50 or current_energy < 10:
            last_detected_activity = current_act
            continue

        # 4. 正在说话跳过
        if CURRENT_SPEAK_TASK and not CURRENT_SPEAK_TASK.done():
            last_interaction_time = time.time()
            continue

        # 5. 计算沉默时间
        now = time.time()
        idle_duration = now - last_interaction_time

        # 重置逻辑
        if idle_duration < 2:
            idle_talk_sequence = 0
            has_triggered_talk = False
            last_detected_activity = current_act

        # 6. 闲置动作 (VTS)
        if idle_duration > IDLE_START_TIME and (now - last_idle_action_time) > 15:
            if current_energy > 20:
                safe_actions = list(ACTIONS.keys())
                if safe_actions:
                    await vts.trigger_action(random.choice(safe_actions))
            last_idle_action_time = now

        # 7. 🔥 主动搭话逻辑 (防复读 + 报备式) 🔥
        should_talk = is_switched or (idle_duration > PROACTIVE_TALK_THRESHOLD and not has_triggered_talk)

        if should_talk:
            if current_energy >= 30:
                idle_talk_sequence += 1

                # A. 构造触发语境
                if is_switched:
                    user_text_simulated = f"(芙宁娜的生活流推进：从【{last_detected_activity}】切换到了【{current_act}】)"
                    # 切换场景时：稍微罗嗦一点，交代前因后果
                    injection = f"""
                    ⚠️【生活流转场】你刚刚结束了上一项活动，现在开始了新活动。
                    请用自言自语的方式：
                    1. 简单抱怨或感叹一下上一件事（比如“终于做完了”）。
                    2. 描述现在要做的事。
                    """
                    print(f"🎬 [生活流] 状态切换: {last_detected_activity} -> {current_act}")
                else:
                    # 闲置搭话：纯报备，不强求对话
                    user_text_simulated = "(用户在忙，芙宁娜自己在做自己的事)"

                    # 🔥 修复2：加入随机切入点，防止大脑死循环生成同一句话
                    focus_points = [
                        "抱怨某个具体的细节",
                        "对环境的感官描写（声音/气味/光线）",
                        "突然想起的一件往事",
                        "对自己身体状态的感受（累/饿/困）",
                        "对未来的一个小期待",
                        "哼一段旋律或拟声词"
                    ]
                    current_focus = random.choice(focus_points)

                    injection = f"""
                                        ⚠️【闲置报备】用户现在没空理你。
                                        **不要向用户提问！不要试图开启新话题！**
                                        你正在【{current_act}】。

                                        请**必须**从这个角度切入：【{current_focus}】。

                                        要求：简短地嘟囔一句（20字以内）。
                                        不要重复之前说过的话！
                                        """
                    print(f"👀 [观察] 用户沉默，尝试第 {idle_talk_sequence} 次自言自语 (切入点: {current_focus})...")

                # B. 准备数据
                current_snapshot = {
                    "location": g_state.get("current_location", "卧室"),
                    "activity": current_act,  # 确保传给大脑的是最新活动
                    "item": g_state.get("current_item", "无"),
                    "energy": g_state["energy"],
                    "mood": g_state["mood"]
                }

                history_str = memory_mgr.get_formatted_history(limit=10)
                try:
                    last_chat_info_str = memory_mgr.get_last_chat_info()

                    decision_result = brain.unified_decision_maker(
                        user_text=user_text_simulated,
                        current_state_dict=current_snapshot,
                        sentiment_injection=injection,
                        history_str=history_str,
                        memory_long_term=memory_mgr.data.get("summary", ""),
                        memory_global=memory_mgr.get_global_activity_log(limit=3),  # 记得这里也要跟进之前的修改
                        relationship_info=f"- 名字: {memory_mgr.current_user}",
                        social_context="暂无",
                        last_chat_info=last_chat_info_str
                    )

                    final_text = decision_result["reply_text"]

                    # 🔥🔥🔥 防复读检测核心逻辑 🔥🔥🔥
                    # 1. 检查最近 5 条记录
                    recent_history = memory_mgr.get_recent_history(limit=5)
                    is_duplicate = False
                    for h in recent_history:
                        # 如果是芙宁娜说的，且内容包含现在的回复
                        if h["role"] == "assistant" and final_text in h["content"]:
                            is_duplicate = True
                            break

                    # 2. 分情况处理
                    if is_duplicate:
                        print(f"🔇 [系统] 检测到复读机行为，已拦截: {final_text}")
                        # ⚠️ 关键策略：被拦截后，只回退一点时间（例如让它以为已经过了110秒）
                        # 这样 10 秒后 (120 - 110 = 10) 她就会再次尝试搭话，而不是重新等 120 秒
                        last_interaction_time = time.time() - (PROACTIVE_TALK_THRESHOLD - 10)

                    else:
                        # ✅ 正常播放逻辑
                        new_user_state, _ = sentiment_engine.apply_decision_and_update(
                            "无", user_state, decision_result
                        )
                        memory_mgr.save_user_state(new_user_state)

                        print(f"\n🎭 芙宁娜(主动): {final_text}")
                        memory_mgr.add_history("assistant", final_text)
                        memory_mgr.save()
                        CURRENT_SPEAK_TASK = asyncio.create_task(audio_mgr.speak(final_text, vts))
                        print_status_prompt(memory_mgr.current_user, memory_mgr, sentiment_engine)

                        # ⚠️ 只有成功说话了，才彻底重置计时器和状态！
                        last_interaction_time = time.time()
                        has_triggered_talk = True
                        last_detected_activity = current_act

                except Exception as e:
                    print(f"⚠️ 主动搭话失败: {e}")
                    # 出错也暂时重置，防止死循环刷报错
                    last_interaction_time = time.time()

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
    # ❌ 删除了 BGMManager，防止报错

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
        welcome = f"[傲娇] 咳咳！初次见面，{username}！我是芙宁娜·德·枫丹！"
    elif user_state.affection <= -100:
        welcome = "[生气] ……（无视）"
    else:
        welcome = f"[傲娇] 又是你啊，{username}。"
        if user_state.affection >= 300:
            print("🤔 (芙芙正在回忆上次聊了什么...)")
            dynamic_welcome = brain.generate_dynamic_welcome(
                memory_mgr, g_state['mood'], g_state['energy'], g_state.get('current_activity', '发呆'),
                g_state.get('current_location', '家里')
            )
            if dynamic_welcome: welcome = dynamic_welcome

    print(f"🎭 芙宁娜: {welcome}")
    if user_state.affection > -100:
        memory_mgr.add_history("assistant", welcome)

    CURRENT_SPEAK_TASK = asyncio.create_task(audio_mgr.speak(welcome, vts))

    # 🔥🔥🔥 修复点：这里彻底删除了 bgm_mgr 参数，解决你的截图报错 🔥🔥🔥
    monitor_task = asyncio.create_task(
        monitor_idle_status(vts, audio_mgr, brain, memory_mgr, sentiment_engine, input_mgr))

    listen_task = asyncio.create_task(listen_loop(input_mgr, username))
    print_status_prompt(username, memory_mgr, sentiment_engine)

    try:
        while True:
            await asyncio.sleep(0.1)
            memory_mgr.data["last_interaction_timestamp"] = time.time()

            if input_mgr.has_finished_speaking():
                user_input = input_mgr.pop_full_message()

                # --- 🆕 新增：打断检测逻辑 (补全截图功能) ---
                if CURRENT_SPEAK_TASK and not CURRENT_SPEAK_TASK.done():
                    print("🛑 [系统] 检测到用户打断！")

                    # 1. 物理打断：停止当前语音
                    audio_mgr.stop()
                    CURRENT_SPEAK_TASK.cancel()

                    # 2. 情感反应：获取生气/被打断的反应
                    # check_blacklist_state 是黑名单，这里应该用 get_interruption_reaction
                    mood_penalty, emo_icon, anger_reply = sentiment_engine.get_interruption_reaction()

                    # 3. 输出反应
                    print(f"{emo_icon} 芙宁娜(被打断): {anger_reply}")
                    memory_mgr.add_history("assistant", anger_reply)  # 写入记忆，让她记得自己生气了

                    # 4. 立即播放生气的语音
                    CURRENT_SPEAK_TASK = asyncio.create_task(audio_mgr.speak(anger_reply, vts))

                    # 5. 打印状态条并跳过本次正常的 AI 思考
                    print_status_prompt(username, memory_mgr, sentiment_engine)
                    last_interaction_time = time.time()
                    input_mgr.is_processing = False
                    continue  # <--- 跳过后续的 deepseek 思考，直接进入下一轮循环
                # ---------------------------------------------

                if user_input.lower() in ["quit", "exit", "退出", "再见", "拜拜"]:
                    print("\n💾 [系统] 正在整理记忆并生成日记，请稍候...")
                    # 这里的 brain 参数是主程序里初始化的那个 brain 对象
                    memory_mgr.archive_session(brain)
                    break

                input_mgr.is_processing = True
                last_interaction_time = time.time()
                print(f"\n📝 [用户] {user_input}")

                # ============================================
                # 🚀 V35.0 核心：注入状态 + 统一决策 (优化延迟)
                # ============================================

                # ✅✅✅ 关键修复：在这里先获取 user_state，防止 UnboundLocalError ✅✅✅
                current_user_state = memory_mgr.get_user_state_obj()

                # 1. 准备所有状态 (心情、地点、精力)
                g_state = sentiment_engine.get_global_state()
                current_snapshot = {
                    "location": g_state.get("current_location", "卧室"),
                    "activity": g_state.get("current_activity", "发呆"),
                    "item": g_state.get("current_item", "无"),
                    "energy": g_state["energy"],
                    "mood": g_state["mood"]
                }

                history_str = memory_mgr.get_formatted_history(limit=20)
                memory_long_term = memory_mgr.data.get("summary", "暂无特殊回忆")
                memory_global = memory_mgr.get_global_activity_log(limit=5)

                # 🔥🔥🔥 V35.2 新增：提取关系与八卦数据 🔥🔥🔥
                # A. 获取好感度描述 (标题+基础态度)
                rel_title, rel_base_desc = memory_mgr.get_relationship_base_desc()
                user_aff = current_user_state.affection  # ✅ 现在这里可以正常运行了

                # 组装关系字符串
                relationship_info_str = f"""
                                - 名字: {username}
                                - 好感度: {user_aff}
                                - 等级: 【{rel_title}】
                                - 基础态度: {rel_base_desc}
                                """

                # B. 获取关于该用户的社交八卦
                social_context_str = memory_mgr.get_social_context(username)

                related_memories_str = ""
                # 1. 获取所有认识的人的名单
                all_contacts = memory_mgr.get_known_users()
                found_contacts = []

                # 2. 遍历名单，看用户这句“话”里有没有提到谁
                for name in all_contacts:
                    # 排除自己，只查别人
                    if name in user_input and name != username:
                        memo = memory_mgr.get_person_brief(name)
                        if memo:
                            found_contacts.append(memo)
                            print(f"🔍 [联想] 芙芙想起了: {name}")

                if found_contacts:
                    related_memories_str = "你忽然想起了关于这些人的记忆：\n" + "\n".join(found_contacts)
                else:
                    related_memories_str = "（话语中未提及其他熟人）"

                    # ✅【修正后】逻辑跳出了 else，无论有没有提到人，都会执行下面的思考逻辑

                    # 🔥🔥🔥 V37.0 新增：获取上次聊天情报 🔥🔥🔥
                last_chat_info_str = memory_mgr.get_last_chat_info()
                print(f"⏰ [记忆] 上次互动: {last_chat_info_str.replace(chr(10), ' | ')}")

                rag_memories_str = ""
                if len(user_input) > 2:
                    print("🔦 [记忆] 正在翻阅旧日记...")
                    rag_memories_str = memory_mgr.search_relevant_memories(user_input)
                    if not rag_memories_str:
                        rag_memories_str = "(未找到相关往事)"

                # 3. 🧠 调用统一决策机
                print("⏳ (芙宁娜正在思考与行动...)")
                decision_result = brain.unified_decision_maker(
                    user_text=user_input,
                    current_state_dict=current_snapshot,
                    sentiment_injection="",
                    history_str=history_str,
                    memory_long_term=memory_long_term,
                    memory_global=memory_global,
                    relationship_info=relationship_info_str,
                    social_context=social_context_str,
                    related_memories=related_memories_str,
                    last_chat_info=last_chat_info_str,
                    rag_context=rag_memories_str
                )

                final_text = decision_result["reply_text"]
                print(
                    f"🧠 [状态] {decision_result['next_state']['activity']} @ {decision_result['next_state']['location']}")

                # 4. 后处理：更新数值
                # [A] 记录旧的好感度
                old_affection = current_user_state.affection

                # [B] 执行更新
                new_user_state, current_act = sentiment_engine.apply_decision_and_update(
                    user_input,
                    current_user_state,
                    decision_result
                )

                # [C] 记录新的好感度
                new_affection = new_user_state.affection

                # [D] 强制更新最后活跃时间
                import datetime
                new_user_state.last_active_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

                memory_mgr.save_user_state(new_user_state)

                # 5. 输出 & 播放
                memory_mgr.add_history("assistant", final_text)
                memory_mgr.save()
                print(f"\r🎭 芙宁娜: {final_text}")

                CURRENT_SPEAK_TASK = asyncio.create_task(audio_mgr.speak(final_text, vts))

                # 🔥🔥🔥 [核心插入点] 检查等级变化 🔥🔥🔥
                # 必须放在 speak 之后，利用异步任务去检查，不卡顿主流程
                asyncio.create_task(handle_level_change(
                    vts, audio_mgr, brain, memory_mgr,
                    username,  # 传入当前的用户名
                    old_affection,  # 旧好感
                    new_affection  # 新好感
                ))

                # 6. 八卦提取 (异步不阻塞)
                known_users = memory_mgr.get_known_users()
                gossip, gender_list = brain.extract_social_gossip(user_input, username, known_users)
                if gossip:
                    t, r, c = gossip
                    memory_mgr.update_social_relation(username, t, r, c)
                    print(f"🕸️ [八卦] 记住了 {username} {r} {t}")

                if "带回去" in user_input or "收养" in user_input:
                    fact = brain.extract_important_fact(f"芙宁娜决定：{final_text}", username)
                    if fact:
                        print(f"📝 [记忆] 记录重要事实: {fact}")
                        # 强制追加到 summary 里，这样她永远不会忘！
                        memory_mgr.data["summary"] += f"\n- {fact} ({time.strftime('%Y-%m-%d')})"
                        memory_mgr.save()
                last_interaction_time = time.time()
                input_mgr.is_processing = False
                print_status_prompt(username, memory_mgr, sentiment_engine)

    except KeyboardInterrupt:
        print("\n🛑 强制退出...")
    finally:
        if vts: await vts.close()
        if hasattr(memory_mgr, "save"): memory_mgr.save()
        print("👋 程序已关闭")


if __name__ == "__main__":
    asyncio.run(main())