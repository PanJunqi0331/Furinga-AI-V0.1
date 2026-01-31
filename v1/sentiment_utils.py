import time
import json
import os
import random
import re
import datetime
from dataclasses import dataclass, field
from config import (
    MOOD_DECAY_RATE, ENERGY_RECOVER_RATE, ENERGY_COST_PER_CHAT,
    ENERGY_LOW_THRESHOLD, SAVES_DIR,
    FURINA_ACTIVITIES, STATUS_CHANGE_INTERVAL
)

try:
    from sentence_transformers import SentenceTransformer, util
    import torch

    HAS_SEMANTIC_MODEL = True
except ImportError:
    print("⚠️ [情感引擎] 未检测到 sentence-transformers，将降级为关键词模式。")
    HAS_SEMANTIC_MODEL = False

TIME_ACTIVITIES = {
    "early_morning": ["还在被窝里赖床", "迷迷糊糊地揉眼睛", "抱着海豹抱枕呼呼大睡", "在床上翻来覆去不想起"],
    "morning": ["在阳台享用精致的早茶", "挑选今天要穿的礼服", "对着镜子练习优雅的微笑", "阅读最新的《蒸汽鸟报》"],
    "noon": ["正在享用通心粉午餐", "在庭院里散步消食", "趴在桌上午休小憩"],
    "afternoon": ["正在举办下午茶沙龙", "品尝限量的精致甜点", "在书房构思新的剧本", "练习歌剧的唱段"],
    "evening": ["正在享用丰盛的晚餐", "欣赏枫丹廷的日落", "在浴缸里泡澡放松", "整理一天的见闻"],
    "night": ["做睡前的护肤保养", "坐在窗边看星星", "写今天的日记", "有点饿了，在纠结要不要吃宵夜"],
    "late_night": ["早已进入梦乡", "正在做关于蛋糕的美梦", "睡得很熟，雷打不动", "发出轻微的呼噜声"]
}

LOCATION_MAP = {
    "被窝": "卧室", "床": "卧室", "梦": "卧室", "睡": "卧室",
    "阳台": "阳台", "茶": "下午茶沙龙", "甜点": "下午茶沙龙",
    "庭院": "庭院", "散步": "庭院",
    "书房": "书房", "剧本": "书房",
    "浴缸": "浴室", "澡": "浴室",
    "餐": "餐厅", "通心粉": "餐厅",
    "歌剧": "歌剧院", "唱段": "歌剧院",
    "日记": "书桌", "星星": "窗边",
    "妆": "梳妆台", "口红": "梳妆台", "礼服": "衣帽间"
}


def get_current_time_status():
    now = datetime.datetime.now()
    h = now.hour
    time_str = now.strftime("%H:%M")
    if 5 <= h < 8:
        return "early_morning", "清晨", time_str
    elif 8 <= h < 11:
        return "morning", "上午", time_str
    elif 11 <= h < 14:
        return "noon", "中午", time_str
    elif 14 <= h < 18:
        return "afternoon", "下午", time_str
    elif 18 <= h < 23:
        return "evening", "晚上", time_str
    elif 23 <= h < 24 or 0 <= h < 2:
        return "night", "深夜", time_str
    else:
        return "late_night", "凌晨", time_str


class GlobalStateManager:
    def __init__(self):
        self.filepath = os.path.join(SAVES_DIR, "global_state.json")
        self._load()

    def _load(self):
        key, _, _ = get_current_time_status()
        initial_activity = random.choice(TIME_ACTIVITIES[key])
        initial_loc = self._infer_location(initial_activity)

        if not os.path.exists(self.filepath):
            self.data = {
                "mood": 50.0, "energy": 100.0,
                "current_activity": initial_activity, "current_location": initial_loc,
                "travel_target": None, "travel_start_time": 0,
                "last_active_timestamp": time.time(), "last_update_time": time.time()
            }
            self._save()
        else:
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
                    if "current_activity" not in self.data: self.data["current_activity"] = initial_activity
                    if "current_location" not in self.data: self.data["current_location"] = self._infer_location(
                        self.data["current_activity"])
                    if "travel_target" not in self.data: self.data["travel_target"] = None
            except:
                self.data = {"mood": 50.0, "energy": 100.0, "current_activity": initial_activity,
                             "current_location": initial_loc, "travel_target": None}

    def _save(self):
        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=4, ensure_ascii=False)

    def get_state(self):
        self._update_time_based_changes()
        return self.data

    def _infer_location(self, activity_text):
        for k, v in LOCATION_MAP.items():
            if k in activity_text: return v
        return "家里"

    def start_travel(self, target_place, activity_desc):
        self.data["travel_target"] = {"location": target_place, "activity": activity_desc}
        self.data["travel_start_time"] = time.time()
        self.data["current_activity"] = f"正在前往{target_place}的路上"
        self.data["current_location"] = "路途之中"
        self._save()
        print(f"🚀 [出发] 目标: {target_place} (预计 10秒后到达)")

    def update(self, mood_delta=0, energy_delta=0, force_activity=None):
        self._update_time_based_changes()
        self.data["mood"] = max(0, min(100, self.data["mood"] + mood_delta))
        self.data["energy"] = max(0, min(100, self.data["energy"] + energy_delta))
        if force_activity:
            self.data["current_activity"] = force_activity
            self.data["current_location"] = self._infer_location(force_activity)
            self.data["last_activity_change"] = time.time()
            self.data["travel_target"] = None
            print(f"🚀 [场景跳转] 芙宁娜瞬移到了：{force_activity}")
        self._save()
        return self.data

    def _update_time_based_changes(self):
        now = time.time()
        last_time = self.data.get("last_update_time", now)
        minutes_passed = (now - last_time) / 60.0

        if minutes_passed > 0:
            is_sleeping = "睡" in self.data["current_activity"] or "梦" in self.data["current_activity"]

            # 心情恢复
            current_mood = self.data["mood"]
            if is_sleeping:
                if current_mood < 60: self.data["mood"] = min(60, current_mood + 0.5 * minutes_passed)
            else:
                if current_mood > 50:
                    self.data["mood"] = max(50, current_mood - MOOD_DECAY_RATE * minutes_passed)
                elif current_mood < 50:
                    self.data["mood"] = min(50, current_mood + MOOD_DECAY_RATE * minutes_passed)

            # 精力恢复
            recover_mult = 6.0 if is_sleeping else 1.0
            self.data["energy"] = min(100, self.data["energy"] + ENERGY_RECOVER_RATE * minutes_passed * recover_mult)

            # 旅行到达检测
            if self.data.get("travel_target") and (now - self.data.get("travel_start_time", 0) > 10):
                target = self.data["travel_target"]
                print(f"🏁 [抵达] 芙宁娜到达了: {target['location']}")
                self.data["current_location"] = target['location']
                self.data["current_activity"] = target['activity']
                self.data["travel_target"] = None

            # 1. 生理极限检测
            if self.data["energy"] < 15:
                is_traveling = self.data.get("travel_target") is not None
                is_home = self.data["current_location"] in ["家里", "卧室", "客厅", "浴室", "书房", "梳妆台"]

                if not is_sleeping and not is_traveling:
                    if not is_home:
                        if "回家" not in self.data["current_activity"]:
                            print(f"📉 [生理极限] 精力过低({int(self.data['energy'])})，她撑不住了，自动触发回家。")
                            self.start_travel("家里", "因为太累了，正在赶回家")
                            return
                    else:
                        if "睡" not in self.data["current_activity"]:
                            print(f"📉 [生理极限] 精力过低({int(self.data['energy'])})，她倒头就睡。")
                            self.data["current_activity"] = "在床上精疲力尽地昏睡过去"
                            self.data["current_location"] = "卧室"
                            self.data["last_activity_change"] = now
                            self._save()
                            return

            # 2. 自动生活流
            time_key, _, _ = get_current_time_status()
            last_change = self.data.get("last_activity_change", 0)

            if not self.data.get("travel_target") and (now - last_change > STATUS_CHANGE_INTERVAL):
                is_dating = (now - self.data.get("last_active_timestamp", 0) < 900)
                current_is_home = self.data["current_location"] in ["家里", "卧室", "客厅", "浴室"]

                if is_dating and not current_is_home:
                    print("💓 [生活流] 正在和用户外出，推迟自动回家。")
                else:
                    valid_activities = TIME_ACTIVITIES[time_key]
                    if self.data["energy"] < 20 and time_key not in ["late_night", "early_morning"]:
                        new_act = "在沙发上打盹补觉"
                    else:
                        new_act = random.choice(valid_activities)

                    if new_act != self.data["current_activity"]:
                        print(f"📅 [日程切换] ({time_key}) 芙宁娜现在开始：{new_act}")
                        self.data["current_activity"] = new_act
                        self.data["current_location"] = self._infer_location(new_act)
                        self.data["last_activity_change"] = now

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
        self.semantic_anchors = {}
        if HAS_SEMANTIC_MODEL:
            try:
                print("🧠 [情感引擎] 正在加载语义分析模型 (MiniLM)...")
                self.model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
                self.semantic_anchors = {
                    "hostile": self.model.encode(["讨厌你", "滚开", "去死", "恶心", "闭嘴", "垃圾", "废物"]),
                    "provoke": self.model.encode(["他不喜欢你", "你被骗了", "他有别人了", "你不如我", "眼光真差"]),
                    "love": self.model.encode(["喜欢你", "爱你", "想你", "最爱你了", "抱抱", "贴贴"]),
                    "sad": self.model.encode(["我好难过", "我想哭", "我不开心", "我很绝望"]),
                    "invite": self.model.encode(["带你出去玩", "我们去约会吧", "想不想去海边", "去公园走走"]),
                    "greeting": self.model.encode(["你好", "早安", "晚上好", "哈喽", "在吗"]),
                    "farewell": self.model.encode(["我走了", "再见", "晚安", "拜拜", "明天见", "休息吧", "去睡觉了"])
                }
                print("✅ [情感引擎] 语义感知已就绪！")
            except:
                pass

        self.keywords = {
            "gift_high": ["限量版", "特供", "绝版", "宝石", "剧本"],
            "gift_food": ["蛋糕", "甜点", "奶茶", "马卡龙", "红茶", "通心粉", "礼物", "点心", "好吃的"],
            "comfort": ["辛苦了", "累吗", "休息一下", "我在", "依靠我", "别哭", "对不起", "我的错", "抱歉", "别生气"],
            "intimate": ["老婆", "亲亲", "结婚", "爱", "宝贝", "想你"],
            "neg": ["讨厌", "笨", "傻", "丑", "闭嘴", "垃圾", "滚", "骂", "坏", "去死"],
            "give": ["请你", "给你", "送你", "带你", "买给你", "投喂"],
            "return": ["回家", "回去", "回宫", "到家", "结束", "累了", "散场"]
        }
        self.breakdown_phrases = ["[大哭] 够了！", "[哭] 为什么……", "[崩溃] 我讨厌你！"]
        self.sleep_phrases = ["[困] ……", "[困] Zzz……"]
        self.refuse_phrases = ["[冷漠] ……", "[烦躁] 别来烦我。", "[疲惫] 没力气说话。"]

    def get_global_state(self):
        return self.global_state_mgr.get_state()

    def _detect_intent(self, text):
        detected_intents = []
        if self.model:
            embedding = self.model.encode(text, convert_to_tensor=True)
            for label, anchors in self.semantic_anchors.items():
                scores = util.cos_sim(embedding, anchors)[0]
                local_max = torch.max(scores).item()
                threshold = 0.55 if label in ["provoke", "hostile"] else 0.45
                if local_max > threshold: detected_intents.append(label)

        if any(w in text for w in self.keywords["neg"]):
            if "hostile" not in detected_intents: detected_intents.append("hostile")

        if "greeting" in detected_intents or "晚上好" in text or "早上好" in text:
            if "farewell" in detected_intents:
                detected_intents.remove("farewell")
                print("☀️ [语义修正] 检测到问候语，移除离别判定。")

        if "farewell" in detected_intents:
            if "hostile" in detected_intents: detected_intents.remove("hostile")
            if "provoke" in detected_intents: detected_intents.remove("provoke")
            print("🌙 [语义分析] 检测到离别/晚安，清除敌意判定。")

        return detected_intents

    def _calculate_impact(self, text, current_act, intents, current_affection):
        impact_aff = 0;
        impact_mood = 0;
        reaction_type = "normal"

        is_lover = current_affection >= self.TIER_LOVER
        is_enemy = current_affection <= self.TIER_HATED

        if "hostile" in intents:
            if is_lover: return -2, -2, "confused"
            if is_enemy: return -20, -25, "hurt"
            return -10, -15, "hurt"

        if "provoke" in intents:
            if is_lover: return -5, -5, "pout"
            return -10, -10, "offended"

        if any(w in text for w in self.keywords["gift_high"]):
            base_score = 15 if is_lover else 10
            impact_aff += base_score;
            impact_mood += 15;
            reaction_type = "excited"

        elif any(w in text for w in self.keywords["gift_food"]):
            impact_aff += 5;
            impact_mood += 10;
            reaction_type = "happy"

        if "love" in intents or any(w in text for w in self.keywords["intimate"]):
            if is_enemy: return -5, -5, "offended"
            reaction_type = "shy"
            impact_aff += 3

        elif any(w in text for w in self.keywords["comfort"]):
            impact_aff += 8;
            impact_mood += 10;
            reaction_type = "touched"

        return impact_aff, impact_mood, reaction_type

    def _generate_dynamic_prompt(self, mood, energy, affection, activity, reaction_type):
        g_state = self.global_state_mgr.get_state()
        current_location = g_state.get("current_location", "沫芒宫")
        is_traveling = g_state.get("travel_target") is not None
        _, time_desc, time_str = get_current_time_status()

        mask_desc = "优雅、高傲" if affection < self.TIER_FRIEND else "傲娇、调皮、有些小任性"
        core_desc = "心情平稳"
        subtext = ""
        if mood < 5:
            core_desc = "【彻底崩溃】";
            subtext += "⚠️【情绪失控】哭泣、尖叫。"
        elif mood < 30:
            core_desc = "【心情低落】";
            subtext += "声音低沉。"

        loc_desc = "前往目的地的途中" if is_traveling else current_location

        prompt = f"""
[当前状态]
- 🕒 时间: {time_str} ({time_desc})
- 📍 地点: {loc_desc} {'(正在移动中)' if is_traveling else ''}
- 📅 活动: {activity}
- 🎭 面具: {mask_desc}
- ❤️ 内心: {core_desc}
- 🚀 状态: {'正在移动中...' if is_traveling else '驻留中'}

[指令]
1. 反应类型：<{reaction_type}>。
2. {subtext}
3. 如果处于【移动中】，表达期待或聊聊路上的风景。
4. 如果处于【驻留中】，结合地点描述你正在做的事情。
"""
        return prompt

    def analyze(self, text: str, user_state: UserState):
        g_state = self.global_state_mgr.get_state()
        curr_mood = g_state["mood"]
        curr_energy = g_state["energy"]
        curr_act = g_state["current_activity"]
        is_traveling = g_state.get("travel_target") is not None
        _, time_desc, _ = get_current_time_status()

        intents = self._detect_intent(text)

        has_food = any(w in text for w in self.keywords["gift_food"])
        has_comfort = any(w in text for w in self.keywords["comfort"])
        is_savior = has_food or has_comfort or "love" in intents

        is_provocation = "hostile" in intents or "provoke" in intents

        if is_provocation:
            user_state.consecutive_provocation_count += 1
            penalty_multiplier = 1.0 + (0.5 * (user_state.consecutive_provocation_count - 1))
            print(
                f"⚠️ [情感系统] 检测到连续挑衅！当前连击: {user_state.consecutive_provocation_count} (伤害倍率 x{penalty_multiplier})")
        else:
            if is_savior and user_state.consecutive_provocation_count > 0:
                print("✨ [情感系统] 用户道歉/示好，挑衅连击清零！触发心软回血！")
                user_state.affection += 10
                user_state.consecutive_provocation_count = 0
            elif "normal" in intents:
                pass

        if curr_mood < 5 and is_provocation and not is_savior:
            user_state.affection -= (20.0 * penalty_multiplier)
            self.global_state_mgr.update(mood_delta=-10.0)
            return user_state, "", "大哭", random.choice(self.breakdown_phrases)

        # 拒绝回答逻辑 (深夜强制睡觉)
        is_late_night = time_desc in ["深夜", "凌晨"]
        is_sleeping = "睡" in curr_act or "梦" in curr_act

        # 唤醒逻辑
        force_switch_act = None
        prompt_injection = ""
        action = None
        has_woken_up = False

        if is_sleeping and not is_provocation and "farewell" not in intents:
            print("⏰ [系统] 用户互动，芙宁娜从睡梦中醒来。")
            force_switch_act = "穿着睡衣坐在床上揉眼睛"
            prompt_injection += " (用户把你吵醒了，你迷迷糊糊地坐起来。注意：虽然醒了但还在床上。)"
            curr_energy = 50
            action = "吃惊"
            has_woken_up = True

        elif (curr_energy < 5 or curr_mood < 10) and not is_savior:
            self.global_state_mgr.update(energy_delta=0.5)
            if curr_energy < 5:
                if "睡" not in curr_act:
                    self.global_state_mgr.update(force_activity="在家里抱着巨大的海豹抱枕补觉")
                return user_state, "", "困", random.choice(self.sleep_phrases)
            elif curr_mood < 10:
                return user_state, "", "生气", random.choice(self.refuse_phrases)

        # 3. 正常逻辑
        aff_delta = 0;
        mood_delta = 0;
        energy_cost = 3

        today_date = datetime.datetime.now().strftime("%Y-%m-%d")
        if user_state.last_active_date != today_date:
            aff_delta += 10.0;
            mood_delta += 10.0;
            user_state.last_active_date = today_date

        if not is_provocation: aff_delta += 0.2

        is_invite = ("invite" in intents) or ("带你" in text) or (
                "去" in text and any(w in text for w in ["玩", "逛", "看"]))

        can_travel = not is_traveling and not has_woken_up and not is_sleeping

        # 🔥🔥🔥 核心修复：时空一致性锁 🔥🔥🔥
        # 1. 检测是否在问居家话题
        home_keywords = ["化妆", "口红", "换衣服", "洗澡", "泡澡", "睡衣", "找东西"]
        is_asking_home_task = any(w in text for w in home_keywords)

        # 2. 检测当前是否在外面
        home_locations = ["家里", "卧室", "浴室", "梳妆台", "书房", "客厅", "阳台", "衣帽间"]
        is_currently_outside = g_state["current_location"] not in home_locations

        # 3. 如果在外面却问居家话题，注入强提示
        if is_currently_outside and is_asking_home_task:
            prompt_injection += " (系统强制指令：你现在【已经在外面】了！用户问起化妆/衣服/找东西等居家琐事，请回复【出门前已经弄好了】。严禁描述现在回去找东西，严禁瞬移回家！)"
            action = "摊手"  # 配合无奈或得意的表情

        if is_invite and can_travel:
            if is_late_night:
                prompt_injection += " (深夜拒绝出门)"
                action = "困"
            elif user_state.affection >= self.TIER_FRIEND and curr_energy > 25:
                # 1. 提取地点
                loc_match = re.search(r"(?:去|到)(.+?)(?:玩|吃|看|转|走|吧|好不好|行不行|！|。|，|$)", text)
                target_place = loc_match.group(1).strip() if loc_match else "外面"

                # 2. 清理垃圾字符
                for junk in ["好不好", "行不行", "吧", "吗", "了", "啊"]:
                    target_place = target_place.replace(junk, "")

                # 3. 智能判断：是否已经在该地点？
                current_loc_fuzzy = g_state["current_location"]
                # 如果已经在外面，且目标也是模糊的“外面”，则视为原地活动
                is_already_there = (target_place == "外面" and current_loc_fuzzy not in ["家里", "卧室", "客厅", "浴室",
                                                                                         "书房"]) or (
                                               target_place in current_loc_fuzzy)

                if is_already_there:
                    # 已经在目的地了，不需要旅行，直接互动
                    prompt_injection += f" (用户想去【{target_place}】，但你们已经在外面/目的地了。吐槽一下他的记性，然后继续在当前地点玩。)"
                    action = "摊手"
                else:
                    # 真的需要移动
                    self.global_state_mgr.start_travel(target_place, f"在{target_place}游玩")
                    prompt_injection += f" (用户邀请你去【{target_place}】，你很高兴地答应了。注意：你们现在刚刚出发。)"
                    aff_delta += 10
                    mood_delta += 20
                    action = "激动"

            elif curr_energy <= 25:
                prompt_injection += " (太累拒绝出门)"
                action = "困"

        # 约定等待逻辑
        is_waiting = any(w in text for w in ["等你", "找我", "洗完", "化完妆"])
        if is_waiting and can_travel:
            self.global_state_mgr.start_travel("你的身边", "在你身边")
            prompt_injection += " (用户愿意等你。请让他稍等，表现出你很快就会收拾好去找他。)"
            action = "害羞"
            aff_delta += 5

        wants_return = any(w in text for w in self.keywords["return"])
        # 场景锁：如果在梳妆台（补妆）也算在家，不触发回家逻辑
        is_currently_out = "家" not in curr_act and "卧室" not in curr_act and "梳妆台" not in curr_act and not is_traveling

        if is_currently_out and wants_return:
            force_switch_act = "回到家里，瘫倒在沙发上休息"
            energy_cost = 25
            prompt_injection += " (终于到家了，累瘫了)"
            action = "困"

        if has_food:
            user_state.consecutive_gift_count += 1
            if user_state.consecutive_gift_count > 3:
                mood_delta -= 5
            else:
                aff_delta += 5;
                mood_delta += 15;
                action = "吃蛋糕";
                prompt_injection += " (用户送有好吃的！)"

        if has_comfort:
            aff_delta += 5;
            mood_delta += 20;
            action = "微笑";
            prompt_injection += " (用户道歉/安慰了你)"

        # 晚安逻辑
        is_farewell = "farewell" in intents
        farewell_keywords = ["晚安", "再见", "拜拜", "休息", "睡", "走了", "下线", "明天见", "安"]
        has_explicit_farewell = any(w in text for w in farewell_keywords)

        if is_farewell and has_explicit_farewell:
            now_hour = datetime.datetime.now().hour
            should_sleep = (21 <= now_hour or now_hour < 7) or (curr_energy < 20)

            if should_sleep:
                force_switch_act = "在床上呼呼大睡"
                if curr_energy < 20:
                    prompt_injection += " (用户说晚安了。你精力已经耗尽了，顺势倒在床上睡着吧，不用强撑了。)"
                else:
                    prompt_injection += " (用户说晚安了。时间也不早了，乖乖躺下睡觉。)"
                action = "困"
                energy_cost = -50
            else:
                prompt_injection += " (用户要暂时离开了，礼貌道别，期待下次见面。)"
                action = "挥手"

        aff_impact, mood_impact, reaction = self._calculate_impact(text, curr_act, intents, user_state.affection)

        if is_provocation:
            aff_impact = aff_impact * penalty_multiplier
            mood_impact = mood_impact * penalty_multiplier
            prompt_injection += f" (警告：你正在连续挑衅她！她越来越生气了！)"

        if not force_switch_act and not is_invite:
            aff_delta += aff_impact;
            mood_delta += mood_impact

        if force_switch_act and not action: reaction = "excited"

        user_state.affection += aff_delta
        new_g_state = self.global_state_mgr.update(mood_delta=mood_delta, energy_delta=-energy_cost,
                                                   force_activity=force_switch_act)
        final_act = force_switch_act if force_switch_act else new_g_state['current_activity']

        system_prompt = self._generate_dynamic_prompt(new_g_state['mood'], new_g_state['energy'], user_state.affection,
                                                      final_act, reaction)
        final_prompt = system_prompt + f"\n[系统备注] {prompt_injection}"

        action_map = {"excited": "激动", "happy": "吃蛋糕", "hurt": "哭", "offended": "生气", "shy": "害羞",
                      "touched": "微笑", "confused": "思考", "pout": "傲娇"}
        if not action: action = action_map.get(reaction, None)

        return user_state, final_prompt, action, None

    def check_blacklist_state(self, user_state: UserState):
        if user_state.affection > -100: return False, None, None
        return True, "[生气] 吵死了！离我远点！", None

    def get_interruption_reaction(self):
        self.global_state_mgr.update(mood_delta=-2)
        return -2, "💢", "[生气] 喂！听我把话说完！"