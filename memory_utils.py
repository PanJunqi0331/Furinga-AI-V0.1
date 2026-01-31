import json
import os
import time
import datetime
import asyncio
from sentiment_utils import UserState
from sentence_transformers import SentenceTransformer, util
import torch


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

        print("🧠 [记忆] 正在初始化 RAG 检索神经...")
        try:
            self.rag_model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
            print("✅ [记忆] RAG 检索引擎就绪！")
        except:
            print("⚠️ [记忆] RAG 模型加载失败，主动回忆功能将不可用。")
            self.rag_model = None

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

    def _format_entry_content(self, content):
        """
        🛠️ 工具：将记忆内容标准化为字符串
        兼容旧版(str)和新版(dict)
        """
        if isinstance(content, dict):
            # 将结构化数据拼成一段话，方便阅读和检索
            items_str = ", ".join(content.get("items", []))
            loc = content.get("location", "未知地点")
            event = content.get("event", "")
            return f"在【{loc}】涉及物品【{items_str}】：{event}"
        return str(content)  # 旧版直接返回字符串

    def search_relevant_memories(self, query_text, threshold=0.35, top_k=3):
        """
        🔥 RAG 核心：根据用户说的话，去搜以前的日记
        :param query_text: 用户当前说的话
        :param threshold: 相似度阈值 (0~1)，低于这个就不提取，防止瞎联想
        """
        if not self.rag_model or not query_text: return ""

        try:
            # 1. 准备数据源：只搜【当前用户】的日记 entries
            # 因为 global_diary.json 才是存长期记忆的地方
            with open(self.global_diary_path, "r", encoding="utf-8") as f:
                diary_data = json.load(f)

            user_entries = []
            # 兼容性读取：读取当前用户的 entries
            rels = diary_data.get("relationships", {})
            if self.current_user in rels:
                user_entries = rels[self.current_user].get("entries", [])

            if not user_entries: return ""

            # 2. 提取文本内容列表
            # 格式: "2026-01-28: 和白竹去了海边..."
            corpus = [f"{e['date']}: {e['content']}" for e in user_entries]

            # 3. 向量计算 (语义搜索)
            # 编码用户的当前问题
            query_embedding = self.rag_model.encode(query_text, convert_to_tensor=True)
            # 编码所有日记 (为了速度，实际生产中这里应该预计算并缓存，但你日记少，实时算也很快)
            corpus_embeddings = self.rag_model.encode(corpus, convert_to_tensor=True)

            # 4. 计算相似度 (Cosine Similarity)
            cos_scores = util.cos_sim(query_embedding, corpus_embeddings)[0]

            # 5. 取出前 Top K
            # torch.topk 会返回分数和索引
            top_results = torch.topk(cos_scores, k=min(top_k, len(corpus)))

            found_memories = []
            for score, idx in zip(top_results.values, top_results.indices):
                if score > threshold:
                    found_memories.append(corpus[idx])
                    print(f"🔦 [RAG] 捞回记忆 (匹配度 {score:.2f}): {corpus[idx][:20]}...")

            if found_memories:
                return "\n".join(found_memories)
            return ""

        except Exception as e:
            print(f"⚠️ RAG 搜索出错: {e}")
            return ""

    def add_history(self, role, content):
        self.data["chat_history"].append({
            "role": role,
            "content": content,
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # 精确到秒
        })
        # 保持只存最近 50 条，防止无限膨胀
        if len(self.data["chat_history"]) > 50:
            self.data["chat_history"].pop(0)

    # 🔥 修改 2: 获取历史时，支持格式化输出给 LLM 看
    def get_formatted_history(self, limit=20):
        """
        🔥 返回带【时间戳】和【具体人名】的对话历史
        格式: [22:30] 白竹: 芙芙晚上好
        """
        history = self.data.get("chat_history", [])[-limit:]
        formatted_lines = []

        for h in history:
            # 1. 解析角色名
            if h["role"] == "assistant":
                role_name = "芙宁娜"
            else:
                # 如果是 user，直接显示当前用户的名字（如“白竹”）
                role_name = self.current_user if self.current_user else "用户"

            # 2. 解析时间 (兼容旧存档没有 timestamp 的情况)
            ts = h.get("timestamp", "未知时间")
            # 为了节省 Token，只显示时分 (22:30)，除非跨天了
            if len(ts) > 16:
                time_str = ts[11:16]  # 取 "HH:MM"
            else:
                time_str = ts

            # 3. 组合成清晰的剧本格式
            formatted_lines.append(f"[{time_str}] {role_name}: {h['content']}")

        return "\n".join(formatted_lines)

    def get_last_chat_info(self):
        """
        🔥 获取上次互动的具体情报 (时间 + 最后一句内容)
        """
        try:
            # 1. 获取时间
            user_state_dict = self.data.get("user_state", {})
            last_date = user_state_dict.get("last_active_date", "第一次见面")

            # 2. 获取上次聊天的最后一句
            history = self.data.get("chat_history", [])
            last_topic = "没有特别的内容"

            if len(history) > 0:
                # 取最后一条历史记录
                last_msg = history[-1]

                # ✅ 核心修复：把 "你" 改成 "芙宁娜"，把 "用户" 改成 "白竹"
                # 这样 DeepSeek 看到的就是 "芙宁娜说了:..."，绝对不会搞混是谁说的
                if last_msg['role'] == 'assistant':
                    role_name = "芙宁娜"
                else:
                    role_name = self.current_user if self.current_user else "用户"

                content = last_msg['content']
                if len(content) > 30: content = content[:30] + "..."
                last_topic = f"{role_name}说了: “{content}”"

            return f"【上次互动时间】: {last_date}\n【上次结束话题】: {last_topic}"

        except Exception as e:
            return "【上次互动】: 记忆模糊"

    def get_global_activity_log(self, limit=10):
        """
        🔥 获取世界线变动记录 (读取所有人的最近日记)
        返回格式: "2026-01-30 23:50 [白竹]: 聊了关于蛋糕的事..."
        """
        try:
            default = {"summary": "", "relationships": {}}
            data = self._load_json_or_reset(self.global_diary_path, default)

            all_entries = []

            # 1. 遍历所有人，把日记都挖出来
            if "relationships" in data:
                for username, info in data["relationships"].items():
                    entries = info.get("entries", [])
                    for entry in entries:
                        # 给每条日记打上用户名标签
                        entry_with_name = entry.copy()
                        entry_with_name["username"] = username
                        all_entries.append(entry_with_name)

            # 2. 按时间倒序排列 (最新的在前)
            # 假设 date 格式是 "YYYY-mm-dd HH:MM"
            all_entries.sort(key=lambda x: x.get("date", ""), reverse=True)

            # 3. 取最近的 N 条
            recent = all_entries[:limit]

            # 4. 格式化输出
            log_text = ""
            for e in recent:
                # 过滤掉内容为空的
                content = self._format_entry_content(e['content'])
                log_text += f"- {e['date']} 【{e['username']}】: {content}\n"

            return log_text if log_text else "(近期无其他访客)"

        except Exception as e:
            print(f"⚠️ 读取全局日志失败: {e}")
            return "(读取失败)"

    def get_person_brief(self, target_name):
        """
        🔥 联想检索：获取某个特定路人的简报
        """
        try:
            with open(self.global_diary_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                rels = data.get("relationships", {})

            if target_name in rels:
                info = rels[target_name]
                aff = info.get("affection", 0)
                title = info.get("title", "陌生人")
                # 如果有印象就读印象，没有就读最近的一条日记
                impression = info.get("impression", "")
                if not impression and info.get("entries"):
                    impression = info["entries"][-1]["content"]

                if not impression: impression = "没什么特别的印象。"

                return f"- 【{target_name}】 (好感:{int(aff)} | 身份:{title}): {impression}"
            return None
        except Exception as e:
            print(f"⚠️ 检索失败: {e}")
            return None

    def _init_global_diary(self):
        # 确保 relationships 存在
        default = {"summary": "", "relationships": {}, "social_graph": {}}
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

    # ================= 🔥 新增：社交八卦读写接口 🔥 =================

    def update_user_gender(self, username, gender):
        """
        🔥 更新用户的性别记录
        gender: "male", "female", "unknown"
        """
        try:
            default = {"summary": "", "relationships": {}, "social_graph": {}}
            data = self._load_json_or_reset(self.global_diary_path, default)

            if "relationships" not in data: data["relationships"] = {}
            if username not in data["relationships"]:
                data["relationships"][username] = {"entries": []}

            # 如果已经有性别且不是 unknown，通常不覆盖（除非显式更正），这里简单处理为直接覆盖
            old_gender = data["relationships"][username].get("gender", "unknown")
            if old_gender != gender and gender != "unknown":
                data["relationships"][username]["gender"] = gender
                with open(self.global_diary_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=4)
                print(f"⚧️ [性别识别] 更新了【{username}】的性别: {gender}")

        except Exception as e:
            print(f"⚠️ 性别更新失败: {e}")

    def get_user_gender(self, username):
        """获取用户性别，默认为 unknown"""
        try:
            with open(self.global_diary_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("relationships", {}).get(username, {}).get("gender", "unknown")
        except:
            return "unknown"

    def update_social_relation(self, source_user, target_user, relation_desc, gossip_content):
        """记录 A 对 B 的看法"""
        try:
            default = {"summary": "", "relationships": {}, "social_graph": {}}
            data = self._load_json_or_reset(self.global_diary_path, default)

            if "social_graph" not in data: data["social_graph"] = {}
            if source_user not in data["social_graph"]: data["social_graph"][source_user] = {}

            # 记录：白竹 -> 黑球 = 喜欢
            data["social_graph"][source_user][target_user] = {
                "relation": relation_desc,
                "content": gossip_content,
                "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            }

            with open(self.global_diary_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            print(f"🕸️ [社交网络] 已记录: 【{source_user}】->【{target_user}】 ({relation_desc})")

        except Exception as e:
            print(f"⚠️ 社交关系更新失败: {e}")

    def get_social_context(self, current_user):
        """获取关于当前用户的八卦 (别人怎么看他 + 他怎么看别人)"""
        try:
            default = {"summary": "", "relationships": {}, "social_graph": {}}
            data = self._load_json_or_reset(self.global_diary_path, default)
            graph = data.get("social_graph", {})

            gossip_text = ""

            # 1. 别人怎么看我 (Incoming)
            for src, targets in graph.items():
                if current_user in targets:
                    info = targets[current_user]
                    gossip_text += f"- 👂 【传闻】{src} 对你的态度是：{info['relation']} (\"{info['content']}\")\n"

            # 2. 我怎么看别人 (Outgoing)
            if current_user in graph:
                for target, info in graph[current_user].items():
                    gossip_text += f"- 💭 【记忆】你曾表示对 {target} 的态度是：{info['relation']}\n"

            return gossip_text if gossip_text else "暂无关于你的流言蜚语。"
        except:
            return "暂无情报"
    # 🔥🔥🔥 核心修改：写入个人专属 entries 🔥🔥🔥

    def get_user_affection(self, username):
        """
        🔥 快速查询芙宁娜对某个用户的真实好感度
        用于判断吃醋、护短等逻辑
        """
        try:
            # 直接读取目标的存档文件
            file_path = os.path.join(self.save_dir, f"{username}.json")
            if os.path.exists(file_path):
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("user_state", {}).get("affection", 0)
            return 0  # 如果没见过这个人，好感默认为 0
        except:
            return 0

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
                        readable_content = self._format_entry_content(latest['content'])
                        text += f"- 关于【{name}】: {readable_content} ({latest['date']})\n"
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
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        self.data["chat_history"].append({
            "role": role,
            "content": content,
            "timestamp": timestamp
        })
        if len(self.data["chat_history"]) > 100:
            self.data["chat_history"] = self.data["chat_history"][-100:]

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

    def archive_session(self, brain):
        history = self.data.get("chat_history", [])
        if not history: return

        print("📚 [记忆] 正在进行结构化归档与记忆融合...")
        current_summary = self.data.get("summary", "暂无记录")

        # ================= 🔥 1. 新增：生成结构化日记 (JSON格式) 🔥 =================
        try:
            # 计算时间范围
            try:
                start_ts = history[0].get("timestamp", datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
                start_time = start_ts[11:16] if len(start_ts) > 16 else "刚刚"
            except:
                start_time = "刚刚"
            end_time = datetime.datetime.now().strftime("%H:%M")

            # 🧠 调用新的结构化生成器 (返回字典)
            # 注意：请确保 brain_utils.py 里已经有了 generate_structured_diary 函数
            structured_entry = brain.generate_structured_diary(
                self.current_user, start_time, end_time, history
            )

            if structured_entry:
                # 🛠️ 使用工具函数把字典转成好读的字符串，打印出来看看
                readable_log = self._format_entry_content(structured_entry)
                print(f"📜 [新日记] {readable_log}")

                # 💾 存入 global_diary.json (现在存进去的是一个包含 people/event 等字段的字典)
                self.add_global_event(self.current_user, structured_entry)
        except AttributeError:
            print("⚠️ Brain 类缺少 generate_structured_diary 方法，跳过日记生成。")
        except Exception as e:
            print(f"⚠️ 日记生成跳过: {e}")

        # ================= 🔄 2. 原有逻辑：动态计算保留条数 (完全保留) =================
        user_state = self.get_user_state_obj()
        aff = user_state.affection
        keep_count = 50 + int(max(0, aff) * 0.15)
        keep_count = min(keep_count, 200)  # 上限 200

        # ================= 📰 3. 原有逻辑：提取公共事件 (完全保留) =================
        try:
            public_event = brain.extract_public_event(history, self.current_user)
            if public_event and "None" not in public_event:
                self.add_global_event(self.current_user, public_event)
                print(f"🗞️ [散场新闻] 已写入【{self.current_user}】的专属日记: {public_event}")
        except Exception as e:
            print(f"⚠️ 事件提取跳过: {e}")

        # ================= 🧠 4. 原有逻辑：LLM 记忆融合 (完全保留) =================
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

            # ================= ✂️ 5. 原有逻辑：动态保留尾部记录 (完全保留) =================
            if len(history) > keep_count:
                self.data["chat_history"] = history[-keep_count:]
                print(f"✂️ [记忆] 已修剪对话历史，保留最近 {keep_count} 条 (当前好感: {aff})")
            else:
                print(f"💾 [记忆] 对话较少，全部保留 ({len(history)}条)。")

            self.save()

            # 同步到世界名册
            lvl, title, _ = self.calculate_status()
            self.update_global_social_status(self.current_user, user_state.affection, title, new_summary)

            print(f"✅ [记忆] 结构化归档完毕！")

        except Exception as e:
            print(f"❌ 归档失败: {e}")

    def get_title_by_affection(self, affection):
        """
        🛠️ 工具：根据好感度数值，返回对应的称号
        """
        # 1. 负面等级
        if affection < 0:
            current_title = "普通陌生人"
            for threshold, title, _ in self.NEGATIVE_LEVELS:
                if affection <= threshold:
                    current_title = title
                else:
                    break  # 既然是排序的，找到第一个不满足的就可以停了
            return current_title

        # 2. 正面等级
        current_title = "路过的看客"
        for threshold, title in self.POSITIVE_LEVELS:
            if affection >= threshold:
                current_title = title
            else:
                break
        return current_title

    def get_known_users(self):
        """🔥 获取所有认识的用户列表 (用于八卦检索)"""
        try:
            with open(self.global_diary_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                # 安全获取 relationships 的 keys
                return list(data.get("relationships", {}).keys())
        except Exception as e:
            print(f"⚠️ 读取用户列表失败: {e}")
            return []