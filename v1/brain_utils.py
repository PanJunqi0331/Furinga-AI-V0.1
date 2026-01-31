import time
import random
import datetime
from openai import OpenAI
from config import DEEPSEEK_API_KEY, BASE_INSTRUCTIONS, LORE_BASE, LORE_FULL


class Brain:
    def __init__(self):
        self.client = OpenAI(
            api_key=DEEPSEEK_API_KEY,
            base_url="https://api.deepseek.com"
        )
        print("🧠 [大脑] 神经元连接完毕")
        self.last_proactive_activity = None

    def generate_dynamic_welcome(self, memory_mgr, current_mood, current_energy, current_activity,
                                 current_location):
        try:
            username = memory_mgr.current_user
            summary = memory_mgr.data.get("summary", "")
            recent_history = memory_mgr.get_recent_history(limit=6)
            _, relation_title, _ = memory_mgr.calculate_status()
            last_active = memory_mgr.data.get("last_interaction_timestamp", 0)

            if last_active == 0:
                hours_passed = 0
                time_desc = "未知的时长"
            else:
                hours_passed = (time.time() - last_active) / 3600
                if hours_passed > 48:
                    time_desc = "好几天没见了"
                elif hours_passed > 12:
                    time_desc = "隔了一整晚"
                elif hours_passed > 1:
                    time_desc = "隔了一会儿"
                else:
                    time_desc = "刚刚才分开"

            # 🔥 修复 Point 1: 填补时间漏洞 & 结合活动 🔥
            now_h = datetime.datetime.now().hour

            # 基础时间段描述 (完整覆盖 0-24 点)
            is_early_morning = 5 <= now_h < 9  # 5-9点
            is_morning = 9 <= now_h < 11  # 9-11点
            is_noon = 11 <= now_h < 14  # 11-14点
            is_afternoon = 14 <= now_h < 18  # 14-18点
            is_evening = 18 <= now_h < 22  # 18-22点
            is_late_night = (22 <= now_h or now_h < 5)  # 22-5点 (填补了之前的漏洞)

            time_period_prompt = ""
            if is_early_morning:
                time_period_prompt = "现在是【清晨】。"
            elif is_morning:
                time_period_prompt = "现在是【上午】。"
            elif is_noon:
                time_period_prompt = "现在是【中午】。"
            elif is_afternoon:
                time_period_prompt = "现在是【下午】。"
            elif is_evening:
                time_period_prompt = "现在是【晚上】。"
            else:
                time_period_prompt = "现在是【深夜/凌晨】。"

            if not summary and not recent_history: return None

            state_desc = ""
            if current_energy < 20:
                state_desc += "【极度困倦】"
            elif current_energy < 30:
                state_desc += "【有点累】"
            else:
                state_desc += "【精力充沛】"

            if current_mood < 20:
                state_desc += " 且 【心情极差/崩溃】"
            elif current_mood > 80:
                state_desc += " 且 【心情极好】"

            context_text = ""
            if summary: context_text += f"📜 【关键回忆】: {summary}\n"
            if recent_history:
                context_text += "💬 【上次对话片段】:\n"
                for msg in recent_history:
                    role = "芙宁娜" if msg['role'] == 'assistant' else username
                    context_text += f"{role}: {msg['content']}\n"

            # 🔥🔥🔥 核心修改：基于活动生成 Prompt 🔥🔥🔥
            prompt = f"""
{BASE_INSTRUCTIONS}
{context_text}
---
### 🎬 开场白生成指令
你是芙宁娜。对话对象：**【{username}】**。
距离上次聊天：{time_desc}。
当前状态：{state_desc}。
{time_period_prompt}

**重要：你当前正在【{current_location}】进行【{current_activity}】。**

请生成一句开场白（30字以内）。
**要求**：
1. **必须结合当前的活动来开启话题！** - 如果在睡觉，表现出被吵醒或迷糊。
   - 如果在泡澡，可以提到水温或被打扰的害羞。
   - 如果在吃东西，可以邀请用户一起。
   - 如果在看风景，可以聊聊景色。
2. 只有当你在睡觉且被打扰时，才用 [困] 或 [揉眼] 开头。
3. 如果上次是不欢而散，语气要带有尴尬、歉意或试探。
"""
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "system", "content": prompt}],
                max_tokens=100,
                temperature=1.0,
            )
            return response.choices[0].message.content.strip()

        except Exception as e:
            print(f"⚠️ 欢迎语生成失败: {e}")
            return None

    def think(self, memory_mgr, user_input=None, sentiment_injection="", is_proactive=False, proactive_stage=0):
        try:
            short_term_memory = memory_mgr.get_recent_history(limit=10)
            long_term_memory = memory_mgr.data.get("summary", "暂无重要回忆")

            username = memory_mgr.current_user
            relation_title, base_attitude = memory_mgr.get_relationship_base_desc()
            state = memory_mgr.get_user_state_obj()
            current_score = state.affection
            interaction_count = len(memory_mgr.data.get("chat_history", []))
            global_events = memory_mgr.get_recent_global_events()

            current_lore = LORE_FULL if (interaction_count < 30 or current_score >= 400) else LORE_BASE
            current_time_str = datetime.datetime.now().strftime("%H:%M")

            CORE_INSTRUCTIONS = f"""
你现在是【芙宁娜·德·枫丹】。
对话对象是：【{username}】。
当前现实时间：【{current_time_str}】。

### 核心认知
1. **人际关系处理**：查阅名册，如果好感度 > 500，必须承认关系亲密。
2. **场景反应**：如果提示【场景切换】，必须在回复中提到新地点！
3. **话语简练**：每句不超过 40 字。
4. **动作描写**：必须用 [动作] 开头。
"""

            dynamic_system_prompt = f"""
{CORE_INSTRUCTIONS}

---
### 📘 基础设定
{current_lore}

---
### 🌟 关系状态
* **对象**: {username} ({relation_title})
* **私人回忆**: {long_term_memory}
* **世界见闻(含人际名册)**: 
{global_events}

{base_attitude}

---
### 🔥 实时状态注入
{sentiment_injection}
"""
            messages = [{"role": "system", "content": dynamic_system_prompt}]
            messages.extend(short_term_memory)

            current_temp = 0.85

            if is_proactive:
                current_temp = 1.15
                # 🔥🔥🔥 Point 3: 主动报备逻辑 🔥🔥🔥
                proactive_prompt = f"""
【系统指令 - 主动搭话模式】
**情况 A：场景刚刚切换** (看上面的注入信息)
必须告诉用户你换地方了！例如：“时间到了，我现在要去吃晚餐了，下次再聊？”或者“我要去睡觉了，晚安。”
**情况 B：普通挂机**
抱怨被冷落，或者找话题。
"""
                messages.append({"role": "system", "content": proactive_prompt})

            elif user_input:
                messages.append({"role": "user", "content": user_input})
                if any(k in user_input for k in ["故事", "讲讲", "长一点", "经历", "剧本"]):
                    messages.append({"role": "system", "content": "【导演指令】请讲一个完整的故事，字数300字以上。"})

            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=messages,
                max_tokens=300,
                temperature=current_temp,
                frequency_penalty=0.6,
                presence_penalty=0.6,
                stop=["\nUser:", "User:", "\n\n"]
            )

            reply = response.choices[0].message.content.strip()

            if reply.startswith("芙宁娜:"):
                reply = reply.replace("芙宁娜:", "").strip()

            if not reply:
                reply = "[动作] (看着你发呆)..."

            return reply

        except Exception as e:
            print(f"🧠 [大脑] 思考短路: {e}")
            return "[汗] 唔...剧本好像被我不小心当下午茶垫了。"

    def _is_repeating(self, new_text, history):
        if not new_text: return True
        assistant_msgs = [msg['content'] for msg in history if msg['role'] == 'assistant'][-3:]
        for old_msg in assistant_msgs:
            if len(new_text) > 8 and (new_text in old_msg or old_msg in new_text):
                return True
        return False

    def summarize_memory(self, history_chunk, current_summary):
        try:
            dialogue_text = ""
            for msg in history_chunk:
                role = "芙宁娜" if msg['role'] == 'assistant' else "用户"
                dialogue_text += f"{role}: {msg['content']}\n"
            prompt = f"请总结关键信息:\n原记忆:{current_summary}\n新对话:{dialogue_text}"
            response = self.client.chat.completions.create(
                model="deepseek-chat", messages=[{"role": "user", "content": prompt}],
                max_tokens=500, temperature=0.3
            )
            return response.choices[0].message.content
        except:
            return current_summary

    def extract_public_event(self, history_chunk, username):
        try:
            dialogue_text = ""
            for msg in history_chunk:
                role = "芙宁娜" if msg['role'] == 'assistant' else username
                dialogue_text += f"{role}: {msg['content']}\n"

            prompt = f"""
请分析以下对话，判断是否发生了【值得写入日记的特殊事件】。
对话内容：
{dialogue_text}
判定标准：收到礼物、去特殊地点、情绪冲突、有趣话题。
如果是普通闲聊，回复 "None"。
核心要求：必须明确写出是【{username}】发生的。用第三人称简练概括。
"""
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=50,
                temperature=0.1
            )
            result = response.choices[0].message.content.strip()
            if "None" in result or len(result) < 5: return None
            print(f"🗞️ [世界新闻] 提取到新事件: {result}")
            return result
        except Exception as e:
            print(f"⚠️ 提取公共事件失败: {e}")
            return None

    def summarize_global_diary(self, old_entries, current_summary):
        try:
            entries_text = "\n".join([f"- {e['date']} ({e['user']}): {e['content']}" for e in old_entries])
            prompt = f"""
你正在整理芙宁娜的【世界日记】。
请将【旧日记条目】合并到【现有总结】中，生成新的历史摘要。
【现有总结】：
{current_summary}
【待合并】：
{entries_text}
要求：保留人名和关键事件，去除琐碎信息，500字以内。
"""
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=600,
                temperature=0.3
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"⚠️ 日记整理失败: {e}")
            return current_summary