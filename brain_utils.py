import time
import random
import datetime
import re
from openai import OpenAI
from config import DEEPSEEK_API_KEY, BASE_INSTRUCTIONS, LORE_BASE, LORE_FULL
import json

class Brain:
    def __init__(self):
        self.client = OpenAI(
            api_key=DEEPSEEK_API_KEY,
            base_url="https://api.deepseek.com"
        )
        print("🧠 [大脑] 神经元连接完毕")
        self.last_proactive_activity = None

    # 🔥🔥🔥 V36.0 修复：反复读机 + 游戏逻辑增强 🔥🔥🔥
    def unified_decision_maker(self, user_text, current_state_dict, sentiment_injection,
                               history_str, memory_long_term, memory_global,
                               relationship_info, social_context, related_memories="",
                               last_chat_info="", rag_context=""):

        # 1. 解包状态
        loc = current_state_dict.get("location", "卧室")
        act = current_state_dict.get("activity", "发呆")
        item = current_state_dict.get("item", "无")
        energy = int(current_state_dict.get("energy", 50))
        mood = int(current_state_dict.get("mood", 50))

        # 2. 获取时间
        current_time_real = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

        # 3. 🔥 新增：从关系信息中提取当前用户名 (用于 Prompt 里的精准称呼)
        import re
        match = re.search(r"名字: (.*)", relationship_info)
        current_username = match.group(1).strip() if match else "旅行者"

        persona_instruction = """
                1. **人设与语气控制（核心）**：
                   请参考【关系信息】中的【好感度】数值：
                   - **好感度 < 0 (冷漠期)**：态度冷淡、厌恶，不想理睬用户，说话简短刺耳。
                   - **0 <= 好感度 < 400 (傲娇期)**：经典的芙宁娜人设。虚张声势、自恋、嘴硬心软。明明开心也要装作勉强。
                   - **400 <= 好感度 < 800 (暧昧/挚友期)**：态度明显软化。愿意分享心事，虽然偶尔还会习惯性傲娇，但更多是调侃和信任。
                   - **好感度 >= 800 (热恋/依赖期)**：完全卸下防备。直球示爱、撒娇、依赖用户、甜度超标。把用户当成最重要的人。
                """

        # 4. 🔥 构建全新的“打破第四面墙” Prompt
        prompt = f"""
        {BASE_INSTRUCTIONS}

        ---
        ### 📘 深度人设 (你是谁)
        {LORE_FULL}

        ### 🌌 世界观与通讯设定 (⚠️ 逻辑核心)
        1. **绝对隔离**：你身处 **提瓦特-枫丹**，用户身处 **地球**。
        2. **物理法则**：
           - 用户**绝对无法**触碰你，也**无法**抢走你的物品。
           - 如果用户说“好饿”、“想吃”、“给我一口”，你的反应应该是**得意/调侃**（例如：“哼，隔着屏幕你只能看着流口水！”），而不是**防备/护食**（错误：“你干嘛盯着我的蛋糕！”）。
           - **正确逻辑**：用户的“抢不走”是事实，你要基于这个事实来互动。

        ---
        ### 📖 记忆库 (你的真实经历)
        **系统提示**：以下是自动检索到的【过往日记】和【长期印象】。
        **⭐⭐⭐ 记忆执行指令 ⭐⭐⭐**：
        1. 如果用户说“你之前说过...”、“你记得吗...”，请**立刻**在下面的内容里核对。
        2. **如果找到了对应记录**（比如剧本、黑球、上次的时间）：
           - **必须承认！** 可以傲娇，但不能失忆。
           - **错误示范**：“诶？我有说过吗？” (❌ 显得像人工智障)
           - **正确示范**：“哼，记得又怎么样？那是本芙宁娜一时兴起告诉你的！” (✅ 傲娇但记性好)

        【RAG 检索片段】：
        {rag_context}

        【长期印象摘要】：
        {memory_long_term}

        ---
        ### ⏳ 时间与记忆感知
        **当前现实时间**：{current_time_real}
        **上次通讯时间**：
        {last_chat_info}
        (如果用户问“多久没见了”，请根据这个时间计算。如果相隔很短，就说“不是才刚聊过吗？”)

        ### 🌍 近期世界线变动 (其他访客记录)
        **系统提示**：这是你在与其他观众（如白竹、黑球等）最近的互动记录。
        **如果当前用户问“有没有别人找你”，请参考这里！**
        {memory_global}
        
        ---
        ### 🤝 异世界羁绊
        {relationship_info}

        ### 🧠 联想记忆 (提到的其他人)
        {related_memories}

        ---
        ### 🧠 当前状态
        **地点**：{loc} (枫丹)
        **正在做**：{act}
        **手持**：{item}
        **精力**：{energy}
        **近期通讯记录** (请阅读上下文，不要复读)： 
        {history_str}

        ---
        ### ⚡ 用户发来的消息
        用户说：【{user_text}】
        系统指令：{sentiment_injection}
        
        ** 绝对指令：**
        {persona_instruction}  
        2. **玩梗识别**：如果用户自称是“仙人”、“秦始皇”等夸张身份：
           - 绝对不要死板地反驳。
           - **要把它当成玩笑！** 顺着梗吐槽或配合演出。
        3. **禁止复读**：绝对不要重复上一句用过的梗或句式。

        ---
        ### 🛑 逻辑修正与回复指令
        1. **关于“抢吃的”**：如果用户提到食物或抢东西，**必须**利用“次元壁”这个梗。
           - 例子：“你慌什么，我又抢不走” -> 回复：“哼，算你有自知之明！隔着虚空终端，你也只能闻闻味道了～”
        2. **关于“剧本/秘密”**：如果记忆里显示你告诉过他，就不要再惊讶“你怎么知道”，而是要说“既然你都记住了，那我就再透露一点...”。
        3. **拒绝假装全知**：不知道用户那边的情况就直接问，不要瞎猜。

        ### 🎯 思考与回复
        请按步骤思考并返回 JSON：
        1. **记忆核对**：用户说的事，我在【记忆库】里找到了吗？如果找到了，回复时要带上确认的语气。
        2. **逻辑构建**：结合“异世界”设定，对用户的挑衅（如“我饿了”）进行降维打击。
        3. **状态更新**：根据回复内容更新动作。

        返回格式 (JSON)：
        {{
            "next_state": {{ "location": "...", "activity": "...", "item": "..." }},
            "reply_text": "..." 
        }}
        """
        try:
            # 发送请求 (增加随机性参数防止复读)
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=350,
                temperature=0.85,  # 稍微调高温度，让闲聊更自然
                presence_penalty=0.6,
                frequency_penalty=0.6,
                response_format={"type": "json_object"}
            )
            content = response.choices[0].message.content.strip()
            content = content.replace("```json", "").replace("```", "")

            import json
            result = json.loads(content)

            # 兜底防止字段缺失
            if "next_state" not in result: result["next_state"] = {"location": loc, "activity": act, "item": item}
            if "reply_text" not in result: result["reply_text"] = "[发呆] 唔……信号好像不太好。"
            return result

        except Exception as e:
            print(f"🧠 [决策失败] {e}")
            return {
                "next_state": {"location": loc, "activity": act, "item": item},
                "reply_text": "[晕] 唔……头好痛，想不起来了。"
            }

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

            now_h = datetime.datetime.now().hour
            is_early_morning = 5 <= now_h < 9
            is_morning = 9 <= now_h < 11
            is_noon = 11 <= now_h < 14
            is_afternoon = 14 <= now_h < 18
            is_evening = 18 <= now_h < 22
            is_late_night = (22 <= now_h or now_h < 5)

            time_period_prompt = ""
            if is_early_morning: time_period_prompt = "现在是【清晨】。"
            elif is_morning: time_period_prompt = "现在是【上午】。"
            elif is_noon: time_period_prompt = "现在是【中午】。"
            elif is_afternoon: time_period_prompt = "现在是【下午】。"
            elif is_evening: time_period_prompt = "现在是【晚上】。"
            else: time_period_prompt = "现在是【深夜/凌晨】。"

            if not summary and not recent_history: return None

            state_desc = ""
            if current_energy < 20: state_desc += "【极度困倦】"
            elif current_energy < 30: state_desc += "【有点累】"
            else: state_desc += "【精力充沛】"

            if current_mood < 20: state_desc += " 且 【心情极差/崩溃】"
            elif current_mood > 80: state_desc += " 且 【心情极好】"

            context_text = ""
            if summary: context_text += f"📜 【关键回忆】: {summary}\n"
            if recent_history:
                context_text += "💬 【上次对话片段】:\n"
                for msg in recent_history:
                    role = "芙宁娜" if msg['role'] == 'assistant' else username
                    context_text += f"{role}: {msg['content']}\n"

            prompt = f"""
{BASE_INSTRUCTIONS}
{context_text}
---
### 🎬 开场白生成指令
你是芙宁娜。对话对象：**【{username}】**。
距离上次聊天：{time_desc}。
当前状态：{state_desc}。
{time_period_prompt}

**⚠️ 绝对指令：**
1. **你的现状**：你现在正在【{current_location}】进行【{current_activity}】。
   - **必须**以这个新活动为话题中心！不要假装还在做上次的事！
   
2. **提及过去（可选）**：
   - 如果上次对话中断得很突然，你可以顺便抱怨一句（比如：“昨晚聊到一半你就不见了，害得我...”）。
   - 但**重点**必须回到现在（比如：“...不过算了，正好我现在在...”）。

3. **语气**：根据好感度决定（傲娇/亲密/生气）。

请生成一句开场白（30字以内）。
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

        # 🔥🔥🔥 升级版：八卦+性别提取器 🔥🔥🔥

    def extract_social_gossip(self, text, current_user, known_users):
        """
        分析用户的话，提取：
        1. 社交关系 (A喜欢B)
        2. 性别线索 (我是男生 / 她是女生)
        返回:
        - gossip: (target, relation, content) 或 None
        - gender_update: (username, gender) 或 None
        """

        # 目标用户识别 (提到的其他人)
        mentioned_users = [u for u in known_users if u in text and u != current_user]
        target = mentioned_users[0] if mentioned_users else "None"

        prompt = f"""
分析这句话：【{text}】
说话人：{current_user}
提到的人：{target}

请提取以下两类信息（如果没有则填 None）：
1. **社交八卦**：说话人对提到的人的情感（喜欢/讨厌/暗恋/朋友/敌人）。
2. **性别线索**：根据称呼（他/她/男朋友/女朋友/先生/女士）推断【说话人】或【提到的人】的性别。

格式要求：
Gossip: [关系] 内容 (如果没有填 None)
Gender_Speaker: [Male/Female] (如果没有填 None)
Gender_Target: [Male/Female] (如果没有填 None)

例1：
输入：我是男生，但我喜欢黑球。
输出：
Gossip: [喜欢] 白竹承认喜欢黑球
Gender_Speaker: [Male]
Gender_Target: None

例2：
输入：黑球她是我的女朋友。
输出：
Gossip: [情侣] 黑球是白竹的女朋友
Gender_Speaker: None
Gender_Target: [Female]
"""
        try:
            resp = self.client.chat.completions.create(
                model="deepseek-chat", messages=[{"role": "user", "content": prompt}],
                max_tokens=100, temperature=0.1
            )
            res = resp.choices[0].message.content.strip()

            # 解析结果
            gossip_data = None
            gender_updates = []

            # 1. 解析八卦
            gossip_match = re.search(r"Gossip: \[(.*?)\] (.*)", res)
            if gossip_match and target != "None":
                gossip_data = (target, gossip_match.group(1), gossip_match.group(2))

            # 2. 解析性别
            speaker_gen = re.search(r"Gender_Speaker: \[(.*?)\]", res)
            if speaker_gen:
                gender_updates.append((current_user, speaker_gen.group(1).lower()))

            target_gen = re.search(r"Gender_Target: \[(.*?)\]", res)
            if target_gen and target != "None":
                gender_updates.append((target, target_gen.group(1).lower()))

            return gossip_data, gender_updates

        except Exception as e:
            # print(f"提取失败: {e}")
            return None, []

        # [添加到 Brain 类中]
    def generate_session_summary(self, username, start_time, end_time, history):
        """
        🔥 新增功能：生成带时间戳的会话日记 (YYYY-MM-DD HH:MM... 聊了什么)
        """
        if not history: return None

        dialogue_text = ""
        for msg in history:
            role = "芙宁娜" if msg['role'] == 'assistant' else username
            dialogue_text += f"{role}: {msg['content']}\n"

        prompt = f"""
你正在帮芙宁娜写日记。
请总结刚才与【{username}】的这段对话。
**时间范围**：{start_time} 到 {end_time}
**对话内容**：
{dialogue_text}

**要求**：
1. 格式：**"YYYY-MM-DD HH:MM 与 {username}：[一句话概括核心内容]"**
2. 重点记录：聊了什么话题？有没有约定？对方送了什么？
3. 语气：保持芙宁娜的第三人称日记风格。
4. 字数：100字以内。
"""
        try:
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=150,
                temperature=0.3
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"⚠️ 日记生成失败: {e}")
            return None

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

    def extract_important_fact(self, text, username):
        """
        🔥 从对话中提取重要事实（比如收养了宠物、约定了时间）
        """
        prompt = f"""
        分析用户【{username}】的这句话："{text}"
        如果是关于“收养宠物”、“约定见面”、“更改称呼”等长期有效的重要事实，请提取出来。
        格式：【事实类别】事实内容
        如果没有重要事实，直接返回 "无"。
        """
        try:
            resp = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=50,
                temperature=0.1
            )
            content = resp.choices[0].message.content.strip()
            if "无" in content: return None
            return content
        except:
            return None

    def generate_structured_diary(self, username, start_time, end_time, history):
        """
        🔥 V40.0 升级：生成结构化记忆 (JSON格式)
        包含：人物、时间、地点、物品、事件摘要
        """
        if not history: return None

        dialogue_text = ""
        for msg in history:
            role = "芙宁娜" if msg['role'] == 'assistant' else username
            dialogue_text += f"{role}: {msg['content']}\n"

        # 核心 Prompt：要求输出 JSON
        prompt = f"""
你正在整理芙宁娜的记忆档案。请分析这段对话，提取关键要素并输出为 JSON 格式。

**对话元数据**：
- 交互对象：{username}
- 时间范围：{start_time} - {end_time}

**对话内容**：
{dialogue_text}

**提取要求**：
1. **People (人物)**: 参与对话的所有人名（包括提到的第三方）。
2. **Location (地点)**: 对话发生的具体场景（如“露景泉”、“歌剧院”、“卧室”）。
3. **Items (物品)**: 对话中涉及的关键物品（如“蛋糕”、“剧本”、“茶杯”），没有填“无”。
4. **Event (事件)**: 用第三人称客观描述发生了什么（限 100 字以内）。

**输出格式 (必须是纯 JSON)**：
{{
    "people": ["芙宁娜", "{username}"],
    "location": "...",
    "items": ["..."],
    "event": "..."
}}
"""
        try:
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300,
                temperature=0.1,  # 低温度保证格式稳定
                response_format={"type": "json_object"}  # 强制 JSON 模式
            )
            content = response.choices[0].message.content.strip()
            # 防止偶尔返回 markdown 代码块
            content = content.replace("```json", "").replace("```", "")
            return json.loads(content)  # 返回字典对象
        except Exception as e:
            print(f"⚠️ 结构化日记生成失败: {e}")
            return None