import json
import os
import time
import datetime
import asyncio
from sentiment_utils import UserState


class MemoryManager:
    def __init__(self, save_dir="saves"):
        self.save_dir = save_dir
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)

        self.current_user = None
        self.data = {}
        self.global_diary_path = os.path.join(save_dir, "global_diary.json")

        # 1. 初始化日记
        self._init_global_diary()

        self.POSITIVE_LEVELS = [
            (0, "路过的看客"), (10, "买票的观众"), (25, "前排的听众"),
            (45, "眼熟的路人"), (70, "试探的新粉"), (100, "活跃的粉丝"),
            (140, "后台熟人"), (190, "茶会嘉宾"), (250, "信赖的随从"),
            (320, "荣誉骑士候补"), (400, "专属护卫"), (490, "最好的搭档"),
            (590, "无话不谈的知己"), (700, "无法替代的存在"), (820, "沫芒宫座上宾"),
            (950, "灵魂共鸣者"), (1000, "永恒的契约者")
        ]
        self.NEGATIVE_LEVELS = [
            (0, "普通陌生人", "态度高傲"),
            (-10, "失礼的家伙", "态度不满"),
            (-20, "不受欢迎者", "态度冷漠"),
            (-60, "被驱逐的客人", "极其厌恶"),
            (-100, "黑名单", "完全无视")
        ]

        # 2. 🔥 启动时自动迁移旧数据结构 (将顶层 entries 拆分给个人)
        self.migrate_entries_structure()

        # 3. 同步老用户基本信息
        self.sync_legacy_users()

    def _load_json_or_reset(self, path, default_data):
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as f:
                json.dump(default_data, f, ensure_ascii=False, indent=4)
            return default_data
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.loads(f.read())
        except:
            return default_data

    def _init_global_diary(self):
        # 确保 relationships 存在
        default = {"summary": "", "relationships": {}}
        self._load_json_or_reset(self.global_diary_path, default)

    # 🔥🔥🔥 核心新增：数据迁移逻辑 (一次性整理旧日记) 🔥🔥🔥
    def migrate_entries_structure(self):
        """
        将旧版的顶层 entries 列表，拆分到每个用户的 relationships 字典中
        """
        try:
            data = self._load_json_or_reset(self.global_diary_path, {"relationships": {}})

            # 如果存在旧版的顶层 entries
            if "entries" in data and isinstance(data["entries"], list) and len(data["entries"]) > 0:
                print("📦 [系统] 检测到旧版日记格式，正在进行归档迁移...")
                count = 0

                if "relationships" not in data: data["relationships"] = {}

                for entry in data["entries"]:
                    user = entry.get("user", "未知")
                    # 确保该用户在名册中
                    if user not in data["relationships"]:
                        data["relationships"][user] = {
                            "affection": 0, "title": "路人",
                            "entries": [], "impression": ""
                        }

                    # 确保该用户的 entries 列表存在
                    if "entries" not in data["relationships"][user]:
                        data["relationships"][user]["entries"] = []

                    # 迁移条目 (保留原有内容)
                    data["relationships"][user]["entries"].append(entry)
                    count += 1

                # 迁移完成后，删除顶层 entries，防止冗余
                del data["entries"]

                with open(self.global_diary_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=4)
                print(f"✅ [系统] 迁移完成！已将 {count} 条日记归档到个人专属名册。")

        except Exception as e:
            print(f"❌ 数据迁移失败: {e}")

    def _get_title_by_score(self, score):
        if score < 0:
            for threshold, title, _ in reversed(self.NEGATIVE_LEVELS):
                if score <= threshold: return title
            return "普通陌生人"

        current_title = self.POSITIVE_LEVELS[0][1]
        for threshold, title in self.POSITIVE_LEVELS:
            if score >= threshold:
                current_title = title
            else:
                break
        return current_title

    def sync_legacy_users(self):
        try:
            diary_data = self._load_json_or_reset(self.global_diary_path, {"relationships": {}})
            changes_count = 0

            for filename in os.listdir(self.save_dir):
                if filename.endswith(".json") and not filename.startswith("global_"):
                    username = filename.replace(".json", "")
                    file_path = os.path.join(self.save_dir, filename)
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            user_data = json.load(f)

                        user_state = user_data.get("user_state", {})
                        affection = user_state.get("affection", 0)
                        summary = user_data.get("summary", "暂无记忆摘要")
                        title = self._get_title_by_score(affection)

                        # 如果不在名册里，初始化结构
                        if username not in diary_data["relationships"]:
                            diary_data["relationships"][username] = {
                                "affection": affection,
                                "title": title,
                                "last_interaction": datetime.datetime.fromtimestamp(
                                    user_data.get("created_at", time.time())).strftime("%Y-%m-%d %H:%M"),
                                "impression": summary,
                                "entries": []  # 🔥 初始化个人日记本
                            }
                            changes_count += 1
                    except Exception as e:
                        pass

            if changes_count > 0:
                with open(self.global_diary_path, "w", encoding="utf-8") as f:
                    json.dump(diary_data, f, ensure_ascii=False, indent=4)
                print(f"✅ [系统] 名册同步完成，补录 {changes_count} 人。")

        except Exception as e:
            print(f"❌ 人口普查失败: {e}")

    # 🔥🔥🔥 核心修改：写入个人专属 entries 🔥🔥🔥
    def add_global_event(self, username, content):
        try:
            default = {"summary": "", "relationships": {}}
            data = self._load_json_or_reset(self.global_diary_path, default)

            if "relationships" not in data: data["relationships"] = {}
            # 确保用户存在
            if username not in data["relationships"]:
                data["relationships"][username] = {"entries": []}
            if "entries" not in data["relationships"][username]:
                data["relationships"][username]["entries"] = []

            today = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            new_entry = {"date": today, "content": content}

            data["relationships"][username]["entries"].append(new_entry)

            with open(self.global_diary_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)

        except Exception as e:
            print(f"⚠️ 个人日记写入失败: {e}")

    def update_global_social_status(self, username, affection, title, summary):
        try:
            default = {"summary": "", "relationships": {}}
            data = self._load_json_or_reset(self.global_diary_path, default)

            if "relationships" not in data: data["relationships"] = {}

            # 确保不覆盖 entries，只更新属性
            if username not in data["relationships"]:
                data["relationships"][username] = {"entries": []}
            elif "entries" not in data["relationships"][username]:
                data["relationships"][username]["entries"] = []

            # 更新属性
            data["relationships"][username]["affection"] = affection
            data["relationships"][username]["title"] = title
            data["relationships"][username]["last_interaction"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            data["relationships"][username]["impression"] = summary

            with open(self.global_diary_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            print(f"🌍 [世界记忆] 已更新【{username}】的社交档案")
        except Exception as e:
            print(f"⚠️ 社交名册更新失败: {e}")

    # 暂时禁用全局压缩，防止打乱个人条目
    async def compress_global_diary_if_needed(self, brain):
        pass

    # 🔥🔥🔥 核心修改：读取逻辑升级 (优先读个人日记) 🔥🔥🔥
    def get_recent_global_events(self):
        try:
            default = {"summary": "", "relationships": {}}
            data = self._load_json_or_reset(self.global_diary_path, default)
            text = ""

            # 1. 历史总摘要
            if data.get("summary"):
                text += f"📜 【历史总集】:\n{data['summary']}\n\n"

            # 2. 🔥 提取所有人的近期大事 (只取每个人最近的 1 条，避免刷屏)
            if data.get("relationships"):
                text += "🆕 【近期见闻】:\n"
                has_news = False

                # 按好感度降序排序，重要的人排前面
                sorted_relationships = sorted(
                    data["relationships"].items(),
                    key=lambda item: item[1].get("affection", 0),
                    reverse=True
                )

                for name, info in sorted_relationships:
                    # 如果有个人日记 entries
                    entries = info.get("entries", [])
                    if entries:
                        # 取最近的一条展示
                        latest = entries[-1]
                        text += f"- 关于【{name}】: {latest['content']} ({latest['date']})\n"
                        has_news = True

                if not has_news: text += "(暂无)\n"
                text += "\n"

            # 3. 人际关系名册
            if data.get("relationships"):
                text += "👥 【人际关系名册】:\n"
                for name, info in sorted_relationships:
                    aff = info.get('affection', 0)
                    title = info.get('title', '陌生人')
                    impression = info.get('impression', '暂无详细记录')
                    entries_count = len(info.get("entries", []))

                    short_impression = impression[:30] + "..." if len(impression) > 30 else impression
                    text += f"- 【{name}】 ({title} | 💾 独家记忆:{entries_count}条): {short_impression}\n"

            return text if text else "生活很平静。"
        except:
            return "暂无新鲜事"

    def load_user(self, username):
        self.current_user = username
        file_path = os.path.join(self.save_dir, f"{username}.json")

        default_state = UserState().to_dict()
        default = {
            "username": username,
            "created_at": time.time(),
            "user_state": default_state,
            "summary": "",
            "chat_history": []
        }
        self.data = self._load_json_or_reset(file_path, default)

        if "user_state" not in self.data:
            self.data["user_state"] = default_state

        lvl, title, _ = self.calculate_status()
        print(f"📖 [记忆] 读取成功: {username} (Lv.{lvl} {title})")

    def get_user_state_obj(self):
        return UserState.from_dict(self.data.get("user_state", {}))

    def save_user_state(self, state_obj: UserState):
        self.data["user_state"] = state_obj.to_dict()
        self.save()

    def update_affection(self, delta):
        state = self.get_user_state_obj()
        state.affection += delta
        self.save_user_state(state)

    def save(self):
        if self.current_user and self.data:
            file_path = os.path.join(self.save_dir, f"{self.current_user}.json")
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=4)

    def add_history(self, role, content):
        if "chat_history" not in self.data: self.data["chat_history"] = []
        self.data["chat_history"].append({"role": role, "content": content})
        self.save()

    def get_recent_history(self, limit=60):
        # 获取最近记录，即使归档了，现在因为保留了尾部，所以能接上
        return self.data.get("chat_history", [])[-limit:]

    def calculate_status(self):
        state = self.get_user_state_obj()
        score = state.affection
        current_title = self._get_title_by_score(score)
        current_lvl = 1
        for i, (threshold, title) in enumerate(self.POSITIVE_LEVELS):
            if score >= threshold:
                current_lvl = i + 1
            else:
                break
        if score < 0: current_lvl = -1
        return current_lvl, current_title, 0

    def get_relationship_base_desc(self):
        state = self.get_user_state_obj()
        score = state.affection
        lvl, title, _ = self.calculate_status()
        username = self.current_user

        if score < -20:
            return f"Lv.{lvl} {title}", f"### ⚠️【强制态度：厌恶】\n你非常讨厌{username}。"
        elif score < 0:
            return f"Lv.{lvl} {title}", f"### 😠【强制态度：不满】\n{username}的言行让你感到不悦。"
        elif score < 100:
            return f"Lv.{lvl} {title}", f"### 😐【强制态度：礼貌】\n{username}是普通路人，保持礼貌距离。"
        elif score < 400:
            return f"Lv.{lvl} {title}", f"### ✨【强制态度：傲娇】\n{username}是熟人，可以适当傲娇。"
        elif score < 800:
            return f"Lv.{lvl} {title}", f"### 🤝【强制态度：挚友】\n{username}是好朋友，语气轻松。"
        else:
            return f"Lv.{lvl} {title}", f"### 💖【强制态度：深爱】\n{username}是你的灵魂伴侣，展现温柔粘人的一面。"

    async def compress_memory_if_needed(self, brain):
        # 实时对话中的小修剪，防止上下文过长炸内存
        # 🔥 修改：阈值调大，避免在归档前就把历史删光了
        history = self.data["chat_history"]
        if len(history) > 200:  # 只有超过 200 条才开始在运行时修剪
            print("🧹 [记忆] 实时对话过长，正在后台修剪...")
            chunk = history[:30]
            self.data["chat_history"] = history[30:]

            public_event = await asyncio.to_thread(brain.extract_public_event, chunk, self.current_user)
            if public_event: self.add_global_event(self.current_user, public_event)
            self.save()

    # ================= 🔥 核心修改：动态保留 + 记忆融合 🔥 =================
    def archive_session(self, brain):
        history = self.data.get("chat_history", [])
        if not history: return

        print("📚 [记忆] 正在进行散场归档与记忆融合...")
        current_summary = self.data.get("summary", "暂无记录")

        # 1. 动态计算保留条数 (50-200条)
        user_state = self.get_user_state_obj()
        aff = user_state.affection
        # 基础50条，每10点好感增加1.5条
        keep_count = 50 + int(max(0, aff) * 0.15)
        keep_count = min(keep_count, 200)  # 上限 200

        # 2. 提取公共事件 (存入个人专属 entries)
        try:
            public_event = brain.extract_public_event(history, self.current_user)
            if public_event:
                self.add_global_event(self.current_user, public_event)
                print(f"🗞️ [散场新闻] 已写入【{self.current_user}】的专属日记: {public_event}")
        except Exception as e:
            print(f"⚠️ 事件提取跳过: {e}")

        # 3. 记忆融合 (合并旧总结 + 新对话)
        try:
            # 整理本次对话文本
            dialogue_text = ""
            for msg in history:
                role = "芙宁娜" if msg['role'] == 'assistant' else "用户"
                dialogue_text += f"{role}: {msg['content']}\n"

            # 提示词：要求 AI 将新旧信息合并
            prompt = f"""
你正在更新芙宁娜对用户【{self.current_user}】的长期记忆。
请将【旧的记忆总结】与【新的对话经历】合并，生成一份更新后的、更全面的记忆总结。

【旧的记忆总结】：
{current_summary}

【新的对话经历】：
{dialogue_text}

**要求**：
1. 不要遗漏旧记忆中的关键信息（如用户身份、过去的重大事件）。
2. 将新对话中的关键进展（好感度变化、承诺、发生的事件、约定的事）补充进去。
3. 如果新旧信息有冲突，以【新对话】为准。
4. 字数控制在 500 字以内，采用第三人称叙述。
"""

            response = brain.client.chat.completions.create(
                model="deepseek-chat", messages=[{"role": "user", "content": prompt}],
                max_tokens=600, temperature=0.5
            )
            new_summary = response.choices[0].message.content

            # 更新数据
            self.data["summary"] = new_summary

            # 🔥 关键修改：保留尾部聊天记录，不完全清空
            if len(history) > keep_count:
                self.data["chat_history"] = history[-keep_count:]
                print(f"✂️ [记忆] 已修剪对话历史，保留最近 {keep_count} 条 (当前好感: {aff})")
            else:
                print(f"💾 [记忆] 对话较少，全部保留 ({len(history)}条)。")

            self.save()

            # 同步到世界名册
            lvl, title, _ = self.calculate_status()
            self.update_global_social_status(self.current_user, user_state.affection, title, new_summary)

            print(f"✅ [记忆] 记忆融合完毕！")

        except Exception as e:
            print(f"❌ 归档失败: {e}")