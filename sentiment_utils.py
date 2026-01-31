import time
import json
import os
import random
import datetime
import asyncio
from dataclasses import dataclass
from config import (
    MOOD_DECAY_RATE, ENERGY_RECOVER_RATE, ENERGY_COST_PER_CHAT,
    ENERGY_LOW_THRESHOLD, SAVES_DIR, SCENE_MAP,
    FURINA_ACTIVITIES, STATUS_CHANGE_INTERVAL,
    ITEM_CONSTRAINTS
)


class GlobalStateManager:
    def __init__(self):
        self.filepath = os.path.join(SAVES_DIR, "global_state.json")
        self._load()

    # 🔥🔥🔥 [新方法] 核心逻辑提取：根据当前时间推荐活动 🔥🔥🔥
    def predict_activity_by_time(self):
        """
        根据当前真实时间，从库里筛选合适的活动，并推断地点。
        返回: (new_activity, new_location)
        """
        current_hour = datetime.datetime.now().hour
        candidate_activities = []
        keywords = []

        # 1.根据时间段筛选关键词
        if 23 <= current_hour or current_hour < 7:
            # 深夜
            keywords = ["睡", "梦", "星星", "夜宵", "浴缸", "被窝", "抱枕"]
        elif 7 <= current_hour < 10:
            # 早晨
            keywords = ["睡醒", "整理", "镜子", "视频"]
        elif 10 <= current_hour < 14:
            # 中午
            keywords = ["煮", "厨房", "剧本", "专访", "排练"]
        elif 14 <= current_hour < 18:
            # 下午
            keywords = ["下午茶", "甜点", "蛋糕", "逛", "鸽子", "海边", "露天"]
        else:
            # 晚上
            keywords = ["歌剧", "审判", "直播", "魔术", "雨", "流浪猫", "谢贝蕾妲"]

        # 2. 筛选活动
        for act in FURINA_ACTIVITIES:
            if any(k in act for k in keywords):
                candidate_activities.append(act)

        # 兜底
        if not candidate_activities:
            candidate_activities = FURINA_ACTIVITIES

        # 3. 随机选择
        new_act = random.choice(candidate_activities)

        # 4. 推断地点
        new_loc = "家里"
        if "歌剧" in new_act or "演" in new_act or "排练" in new_act or "审判" in new_act:
            new_loc = "歌剧院"
        elif "街" in new_act or "店" in new_act or "外" in new_act or "购买" in new_act:
            new_loc = "枫丹街道"
        elif "海" in new_act or "鸽子" in new_act:
            new_loc = "海边"
        elif "厨" in new_act or "煮" in new_act:
            new_loc = "厨房"
        elif "睡" in new_act or "被窝" in new_act or "床" in new_act:
            new_loc = "卧室"
        elif "浴" in new_act or "洗" in new_act:
            new_loc = "浴室"
        elif "吃" in new_act or "茶" in new_act or "咖啡" in new_act:
            new_loc = "露景泉"
        elif "直播" in new_act or "视频" in new_act or "书" in new_act:
            new_loc = "书房"

        return new_act, new_loc

    def _load(self):
        if not os.path.exists(self.filepath):
            # 初始化：直接调用复用的逻辑
            initial_act, initial_loc = self.predict_activity_by_time()

            self.data = {
                "mood": 50.0,
                "energy": 80.0,
                "current_activity": initial_act,
                "current_location": initial_loc,
                "current_item": "无",
                "travel_target": None,
                "travel_start_time": 0,
                "last_active_timestamp": time.time(),
                "last_update_time": time.time(),
                "last_switch_time": time.time(),
                "dialogue_count": 0
            }
            self._save()
        else:
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
                    if "last_switch_time" not in self.data: self.data["last_switch_time"] = time.time()
                    if "dialogue_count" not in self.data: self.data["dialogue_count"] = 0

                # 🔥🔥🔥 [离线重置] 检测是否离开太久 🔥🔥🔥
                last_active = self.data.get("last_active_timestamp", 0)
                now = time.time()
                # 计算小时差
                hours_passed = (now - last_active) / 3600.0

                # 如果离线超过 2 小时，强制刷新到当前时间段的状态！
                if hours_passed > 2:
                    print(f"🕰️ [系统] 检测到离线 {hours_passed:.1f} 小时，正在推演芙宁娜的新生活...")

                    # ✅ 复用逻辑！
                    new_act, new_loc = self.predict_activity_by_time()

                    self.data["current_activity"] = new_act
                    self.data["current_location"] = new_loc
                    self.data["last_switch_time"] = now
                    self.data["dialogue_count"] = 0  # 重置对话计数
                    self._save()

            except Exception as e:
                print(f"⚠️ 存档加载异常: {e}")
                new_act, new_loc = self.predict_activity_by_time()
                self.data = {
                    "mood": 50.0, "energy": 80.0,
                    "current_activity": new_act,
                    "current_location": new_loc,
                    "current_item": "无", "travel_target": None,
                    "last_switch_time": time.time()
                }

    def _save(self):
        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=4, ensure_ascii=False)

    def get_state(self):
        self._update_time_based_changes()
        return self.data

    def update(self, mood_delta=0, energy_delta=0):
        self._update_time_based_changes()
        self.data["mood"] = max(0, min(100, self.data["mood"] + mood_delta))
        self.data["energy"] = max(0, min(100, self.data["energy"] + energy_delta))
        self._save()
        return self.data

    def _update_time_based_changes(self):
        now = time.time()
        last_time = self.data.get("last_update_time", now)
        minutes_passed = (now - last_time) / 60.0

        if minutes_passed > 0:
            current_act = self.data.get("current_activity", "")
            is_sleeping = "睡" in current_act or "梦" in current_act

            current_mood = self.data["mood"]
            if is_sleeping:
                if current_mood < 60: self.data["mood"] = min(60, current_mood + 0.5 * minutes_passed)
            else:
                if current_mood > 50:
                    self.data["mood"] = max(50, current_mood - MOOD_DECAY_RATE * minutes_passed)
                elif current_mood < 50:
                    self.data["mood"] = min(50, current_mood + MOOD_DECAY_RATE * minutes_passed)

            recover_mult = 6.0 if is_sleeping else 1.0
            self.data["energy"] = min(100, self.data["energy"] + ENERGY_RECOVER_RATE * minutes_passed * recover_mult)

            self.data["last_update_time"] = now
            self._save()


@dataclass
class UserState:
    affection: float = 0.0
    consecutive_gift_count: int = 0
    consecutive_provocation_count: int = 0
    last_active_date: str = ""

    def to_dict(self):
        return {
            "affection": self.affection,
            "consecutive_gift_count": self.consecutive_gift_count,
            "consecutive_provocation_count": self.consecutive_provocation_count,
            "last_active_date": self.last_active_date
        }

    @staticmethod
    def from_dict(data):
        obj = UserState()
        obj.affection = data.get("affection", 0.0)
        obj.consecutive_gift_count = data.get("consecutive_gift_count", 0)
        obj.consecutive_provocation_count = data.get("consecutive_provocation_count", 0)
        obj.last_active_date = data.get("last_active_date", "")
        return obj


class SentimentEngine:
    def __init__(self):
        self.global_state_mgr = GlobalStateManager()
        self.TIER_HATED = -20
        self.TIER_FRIEND = 400
        self.TIER_LOVER = 800

        self.model = None
        print("✅ [情感引擎] 轻量化模式启动 (依靠关键词+LLM)")

        self.keywords = {
            "gift_high": ["限量版", "特供", "绝版", "宝石", "剧本", "摩拉"],
            "gift_food": ["蛋糕", "甜点", "奶茶", "马卡龙", "红茶", "通心粉", "点心", "好吃的", "吃饭", "请你"],
            "comfort": ["辛苦", "累吗", "休息", "依靠", "别哭", "对不起", "抱歉", "别生气", "没事的", "我在"],
            "intimate": ["老婆", "亲亲", "结婚", "爱", "宝贝", "想你", "贴贴", "抱抱"],
            "neg": [
                "讨厌", "笨", "傻", "丑", "闭嘴", "垃圾", "滚", "骂", "坏", "去死", "恶心",
                "蠢", "没脑子", "弱智", "白痴", "有病", "神经", "智障", "废物", "烦", "别说话"
            ],
            "provoke": ["不喜欢你", "被骗", "不如我", "眼光差", "不要你", "被绿", "虚伪", "无聊"]
        }

    def get_global_state(self):
        return self.global_state_mgr.get_state()

    def _detect_intent(self, text):
        detected_intents = []
        if any(w in text for w in self.keywords["neg"]): detected_intents.append("hostile")
        if any(w in text for w in self.keywords["provoke"]): detected_intents.append("provoke")
        if any(w in text for w in self.keywords["intimate"] + ["喜欢"]): detected_intents.append("love")
        if any(w in text for w in ["晚安", "再见", "拜拜", "睡了", "走了"]): detected_intents.append("farewell")
        return detected_intents

    def attempt_auto_switch(self, last_interaction_ts):
        """
        🔥 尝试自动切换状态 (复用 GlobalStateManager 的逻辑)
        """
        g_state = self.global_state_mgr.data
        now = time.time()
        last_switch = g_state.get("last_switch_time", 0)
        current_count = g_state.get("dialogue_count", 0)

        # 1. 智能动态锁逻辑
        lock_duration = 120
        if current_count >= 5: lock_duration = 10
        if now - last_interaction_ts < lock_duration: return False, None, None

        # 2. 冷却检查
        if current_count < 5:
            if now - last_switch < STATUS_CHANGE_INTERVAL:
                return False, None, None

        # 3. 🔥 复用核心逻辑：获取新活动 🔥
        new_act, new_loc = self.global_state_mgr.predict_activity_by_time()
        current_act = g_state.get("current_activity", "")

        # 防止连续随到同一个
        retries = 0
        while new_act == current_act and retries < 5:
            new_act, new_loc = self.global_state_mgr.predict_activity_by_time()
            retries += 1

        # 4. 执行更新
        current_hour = datetime.datetime.now().hour
        print(f"🔄 [生活流] 芙宁娜决定换个事做({current_hour}点|已聊{current_count}轮): {current_act} -> {new_act}")
        self.global_state_mgr.data["current_activity"] = new_act
        self.global_state_mgr.data["current_location"] = new_loc
        self.global_state_mgr.data["last_switch_time"] = now
        self.global_state_mgr.data["dialogue_count"] = 0
        self.global_state_mgr.update(mood_delta=5)

        return True, new_act, new_loc

    def _calculate_impact(self, text, current_act, intents, current_affection=0):
        impact_aff = 0
        impact_mood = 0
        reaction_type = "normal"
        is_lover = current_affection >= self.TIER_LOVER

        if "hostile" in intents: return (-5 if is_lover else -10), -15, "hurt"
        if "provoke" in intents: return (-2 if is_lover else -5), -10, "offended"
        if any(w in text for w in self.keywords["gift_high"]): return 15, 15, "excited"
        if any(w in text for w in self.keywords["gift_food"]): return 5, 10, "happy"
        if "love" in intents: return 3, 5, "shy"
        if any(w in text for w in self.keywords["comfort"]): return 8, 10, "touched"
        if not intents and len(text) > 2: return 0.5, 0.5, "normal"
        return impact_aff, impact_mood, reaction_type

    def apply_decision_and_update(self, text, user_state, decision_data):
        g_state = self.global_state_mgr.get_state()
        current_act = g_state.get("current_activity", "")
        next_state = decision_data.get("next_state", {})
        next_loc = next_state.get("location", g_state["current_location"])
        next_act = next_state.get("activity", g_state["current_activity"])
        next_item = next_state.get("item", "无")

        # 防OOC校验
        valid_items = None
        for state_key, items in ITEM_CONSTRAINTS.items():
            if state_key in next_act or state_key in next_loc:
                valid_items = items
                break
        if valid_items is not None:
            if next_item not in valid_items and next_item != "无":
                if not any(x in text for x in ["送", "给"]):
                    print(f"🚫 [防OOC] 修正物品: {next_item} -> 无")
                    next_item = "无"

        # 计数器逻辑
        current_count = g_state.get("dialogue_count", 0)
        if next_act == current_act:
            self.global_state_mgr.data["dialogue_count"] = current_count + 1
        else:
            self.global_state_mgr.data["dialogue_count"] = 0

        self.global_state_mgr.data["current_location"] = next_loc
        self.global_state_mgr.data["current_activity"] = next_act
        self.global_state_mgr.data["current_item"] = next_item

        energy_cost = 2
        intents = self._detect_intent(text)
        aff_impact, mood_impact, _ = self._calculate_impact(text, next_act, intents, user_state.affection)

        # 挑衅处理
        is_provocation = "hostile" in intents
        if is_provocation:
            user_state.consecutive_provocation_count += 1
            aff_impact *= 1.5
        else:
            user_state.consecutive_provocation_count = 0
        user_state.affection += aff_impact
        self.global_state_mgr.update(mood_delta=mood_impact, energy_delta=-energy_cost)

        return user_state, next_act

    def check_blacklist_state(self, user_state: UserState):
        if user_state.affection > -100: return False, None, None
        return True, "[生气] 吵死了！离我远点！", None

    def get_interruption_reaction(self):
        self.global_state_mgr.update(mood_delta=-2)
        return -2, "💢", "[生气] 喂！听我把话说完！"


async def handle_level_change(vts, audio_mgr, brain, memory_mgr, username, old_aff, new_aff):
    """
    🔥 核心：检测等级变化并触发感言
    """
    old_title = memory_mgr.get_title_by_affection(old_aff)
    new_title = memory_mgr.get_title_by_affection(new_aff)
    if old_title == new_title: return
    print(f"\n🆙 [系统] 检测到等级变动: {old_title} -> {new_title}")
    is_levelup = new_aff > old_aff
    if is_levelup:
        injection = f"""
        🎉【系统提示：好感度突破！】
        恭喜！你与用户的关系刚刚从【{old_title}】升职到了【{new_title}】！
        请立刻停下手中的事，发表一段“升级感言”。
        要求：
        1. 语气要傲娇但开心（毕竟升级了）。
        2. 点评一下这个新称号（比如“哼，终于有点长进了”）。
        3. 给他一点口头上的嘉奖或祝福。
        """
    else:
        injection = f"""
        ⚠️【系统提示：好感度下跌！】
        警告！因为刚才的不愉快，你与用户的关系从【{old_title}】跌落到了【{new_title}】。
        请立刻停下手中的事，发表一段“降级警告”。
        要求：
        1. 语气要失望、冷漠或生气。
        2. 警告他如果再这样下去，就要把他拉黑了。
        """
    try:
        decision = brain.unified_decision_maker(
            user_text="(系统触发等级变动事件)",
            current_state_dict={"energy": 50, "mood": 50},
            sentiment_injection=injection,
            history_str="",
            memory_long_term="",
            memory_global="",
            relationship_info=f"- 名字: {username}\n- 新等级: {new_title}",
            social_context="等级变动",
            last_chat_info=""
        )
        reply = decision["reply_text"]
        print(f"✨ 芙宁娜(等级感言): {reply}")
        memory_mgr.add_history("assistant", reply)
        memory_mgr.save()
        while audio_mgr.is_playing:  # 假设你有这个标记，如果没有，见下一步
            await asyncio.sleep(0.5)
        await audio_mgr.speak(reply, vts)
    except Exception as e:
        print(f"⚠️ 等级感言触发失败: {e}")