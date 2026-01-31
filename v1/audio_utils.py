import asyncio
import os
import requests
import pygame
import re
import time
import random
from config import SOVITS_API_URL, EMOTION_MAP, DEFAULT_REF, ACTIONS

# 🔥🔥🔥 核心修复：设置 HF 镜像，解决国内无法下载模型的问题 🔥🔥🔥
# 必须在导入 sentence_transformers 之前设置
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

# ================= 📝 预设标准动作库 =================
TAG_ALIASES = {
    "安心": "释怀", "放松": "释怀", "叹气": "释怀", "原谅": "释怀",
    "喜欢": "真诚", "感动": "真诚", "温柔": "真诚", "表白": "真诚",
    "想要": "撒娇", "求你": "撒娇", "拜托": "撒娇", "饿": "撒娇", "馋": "撒娇",
    "好奇": "期待", "想听": "期待", "愉快": "期待", "听故事": "期待",
    "想念": "信任", "怀念": "信任", "回忆": "信任",
    "热": "吐槽", "无语": "吐槽",  "晒": "吐槽",
    "表演": "中二", "赐福": "中二", "神明": "中二", "威严": "中二", "审判": "中二",
    "犹豫": "纠结", "为难": "纠结", "矛盾": "纠结",
    "奇怪": "疑惑", "不解": "疑惑", "后悔": "疑惑",
    "推荐": "自信", "厉害": "自信", "强": "自信", "天赋": "自信",
    "剧院": "营业", "经典": "营业",
    "吓": "恐惧", "发抖": "恐惧", "阴影": "恐惧",
    "做梦": "噩梦",
    "自我介绍": "介绍", "大明星": "介绍",
    "独白": "孤独", "心事": "孤独",
    "秘密": "交易", "点心": "交易",
    "开心": "开心", "大笑": "开心", "喜悦": "开心", "嘿嘿": "开心", "可爱": "开心", "好": "开心",
    "兴奋": "激动", "星星眼": "激动",
    "愤怒": "生气", "暴怒": "生气", "不爽": "生气", "哼": "生气", "怒": "生气",
    "难过": "低落", "伤心": "低落", "大哭": "哭", "委屈": "低落", "遗憾": "营业",
    "震惊": "吃惊", "惊讶": "吃惊", "呆": "吃惊", "后退": "吃惊", "愣": "吃惊",
    "想": "思考", "沉思": "思考", "等等": "思考", "托腮": "托脸",
    "疑惑": "疑问", "不懂": "疑问", "诶": "疑问",
    "累": "困", "睡觉": "困", "哈欠": "困",
    "羞涩": "害羞", "脸红": "害羞",
    "尴尬": "汗", "擦汗": "汗",
    "怕": "害怕", "抖": "害怕",
    "晕倒": "晕", "晕": "晕",
    "变身": "变芒", "切换": "变荒",
    "思考": "托脸",
    "眨眼": "卖萌",
    "慌张": "急",
    "不耐烦": "生气",  # 👈 你的核心需求：不耐烦 -> 生气 (表现为皱眉/不爽，而不是睡觉)
    "无聊": "托脸",    # 无聊 -> 托腮思考 (比“困”更符合无聊发呆的状态)
    "嫌弃": "傲娇",    # 嫌弃 -> 傲娇/白眼
    "嘲笑": "得意",    # 嘲笑 -> 得意/叉腰
}

# ================= 🧠 本地语义模型加载 =================
try:
    from sentence_transformers import SentenceTransformer, util
    import torch

    print("🧠 [本地模型] 正在加载语义匹配模型 (paraphrase-multilingual-MiniLM-L12-v2)...")
    # 第一次运行会自动从镜像站下载约 470MB 的模型文件
    LOCAL_MODEL = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
    # 预计算标准库的向量
    VALID_EMOTIONS = list(ACTIONS.keys())
    EMOTION_EMBEDDINGS = LOCAL_MODEL.encode(VALID_EMOTIONS, convert_to_tensor=True)
    print("✅ [本地模型] 加载完毕！")
except ImportError:
    print("⚠️ [本地模型] 未检测到 sentence-transformers 库，将使用关键词兜底模式。")
    print("👉 建议运行: pip install sentence-transformers")
    LOCAL_MODEL = None
except Exception as e:
    print(f"⚠️ [本地模型] 加载失败: {e}")
    print("💡 提示：如果是网络问题，请检查是否已配置 HF_ENDPOINT 镜像。")
    LOCAL_MODEL = None


# ================= 🎵 BGM 管理器 =================
class BGMManager:
    def __init__(self, bgm_folder="bgm"):
        self.bgm_folder = bgm_folder
        if not os.path.exists(self.bgm_folder):
            os.makedirs(self.bgm_folder)

        self.current_category = None
        self.categories = ["sleep", "sad", "happy", "jazz", "opera", "tension", "relax"]
        self.playlist = {cat: [] for cat in self.categories}
        self._scan_files()

    def _scan_files(self):
        count = 0
        for filename in os.listdir(self.bgm_folder):
            if not filename.endswith(".ogg"): continue
            assigned = False
            for cat in self.categories:
                if filename.startswith(cat):
                    self.playlist[cat].append(filename)
                    assigned = True
                    count += 1
                    break
            if not assigned:
                self.playlist["relax"].append(filename)
        print(f"🎵 [BGM库] 共加载 {count} 首音乐。")

    def update_state(self, mood, energy, activity_text=""):
        target = "relax"
        if energy < 20 or "睡" in activity_text:
            target = "sleep"
        elif "歌剧" in activity_text or "演出" in activity_text or "审判" in activity_text:
            target = "opera"
        elif "研究" in activity_text or "复杂" in activity_text or "思考" in activity_text or "代码" in activity_text:
            target = "tension"
        elif mood < 35:
            target = "sad"
        elif mood > 80:
            current_hour = time.localtime().tm_hour
            if current_hour >= 19 or current_hour <= 5:
                target = "jazz"
            else:
                target = "happy"
        else:
            target = "relax"
        self._play_random(target)

    def _play_random(self, category):
        if category == self.current_category and pygame.mixer.music.get_busy():
            return
        file_list = self.playlist.get(category)
        if not file_list:
            if category != "relax":
                self._play_random("relax")
            return
        chosen = random.choice(file_list)
        path = os.path.join(self.bgm_folder, chosen)
        # print(f"🎼 [BGM] 切换心情: {category.upper()} -> 正在播放: {chosen}") # 减少刷屏
        try:
            if pygame.mixer.music.get_busy():
                pygame.mixer.music.fadeout(1500)
                time.sleep(1.5)
            pygame.mixer.music.load(path)
            pygame.mixer.music.set_volume(0.35)
            pygame.mixer.music.play(-1, fade_ms=2000)
            self.current_category = category
        except Exception as e:
            print(f"❌ BGM播放失败: {e}")


# ================= 🗣️ 语音管理器 (本地模型版) =================
class AudioManager:
    def __init__(self):
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=4096)
                pygame.mixer.set_num_channels(8)
        except Exception as e:
            print(f"⚠️ 混音器初始化警告: {e}")

        self.stop_event = asyncio.Event()
        self.session = requests.Session()
        self.last_hand_action_time = 0
        self.voice_channel = pygame.mixer.Channel(1)

    def stop(self):
        self.stop_event.set()
        if self.voice_channel.get_busy():
            self.voice_channel.stop()

    def _get_ref_audio_path(self, relative_path):
        abs_path = os.path.abspath(relative_path)
        if not os.path.exists(abs_path):
            filename = os.path.basename(relative_path)
            root_path = os.path.abspath(filename)
            if os.path.exists(root_path):
                abs_path = root_path
            else:
                return None
        return abs_path.replace("\\", "/")

    # 🔥🔥🔥 核心：本地语义匹配 🔥🔥🔥
    def _map_emotion_local(self, raw_tag):
        """
        使用本地模型计算 raw_tag 与 VALID_EMOTIONS 的余弦相似度
        """
        if LOCAL_MODEL is None:
            # 降级方案：关键词匹配
            if any(c in raw_tag for c in ["红", "羞", "低头", "躲", "捂"]): return "害羞"
            if any(c in raw_tag for c in ["气", "哼", "跺", "怒", "瞪"]): return "生气"
            if any(c in raw_tag for c in ["笑", "乐", "哈", "喜", "转圈"]): return "开心"
            if any(c in raw_tag for c in ["惊", "呆", "愣", "诶", "啊"]): return "吃惊"
            if any(c in raw_tag for c in ["哭", "泪", "悲", "呜"]): return "哭"
            if any(c in raw_tag for c in ["困", "睡", "欠", "累", "迷糊"]): return "困"
            return "正常"

        try:
            # 1. 计算输入标签的向量
            input_embedding = LOCAL_MODEL.encode(raw_tag, convert_to_tensor=True)

            # 2. 计算与所有标准动作的相似度
            cos_scores = util.cos_sim(input_embedding, EMOTION_EMBEDDINGS)[0]

            # 3. 找到得分最高的动作
            best_score_idx = torch.argmax(cos_scores).item()
            best_score = cos_scores[best_score_idx].item()
            best_emotion = VALID_EMOTIONS[best_score_idx]

            # 4. 阈值判定 (如果相似度太低，说明不沾边)
            if best_score > 0.4:  # 0.35 是经验值，比较宽松
                print(f"🧠 [语义匹配] '{raw_tag}' ≈ '{best_emotion}' (相似度: {best_score:.2f})")
                return best_emotion
            else:
                print(f"🧠 [语义匹配] '{raw_tag}' 语义不明 (最高匹配: {best_emotion}, {best_score:.2f}) -> 回退正常")
                return "正常"

        except Exception as e:
            print(f"⚠️ 匹配出错: {e}")
            return "正常"

    async def _tts_producer(self, sentences, audio_queue, emotion):
        print(f"🏭 [音频工厂] 开始处理 {len(sentences)} 句话 (情感: {emotion})...")
        speed = 1.0
        if emotion in ["生气", "急", "激动", "吃惊"]:
            speed = 1.2  # 语速加快
        elif emotion in ["困", "低落", "悲伤", "无聊"]:
            speed = 0.85  # 语速变慢
        elif emotion in ["傲娇", "得意"]:
            speed = 1.1  # 稍微轻快
        for i, text in enumerate(sentences):
            if self.stop_event.is_set(): break
            clean_text = re.sub(r"\[.*?\]|\(.*?\)|\（.*?\）|\【.*?\】", "", text).strip()
            if not clean_text: continue

            ref_data = EMOTION_MAP.get(emotion, DEFAULT_REF)
            ref_path = self._get_ref_audio_path(ref_data["file"])
            if not ref_path: continue

            payload = {
                "text": clean_text, "text_lang": "zh", "ref_audio_path": ref_path,
                "prompt_text": ref_data["text"], "prompt_lang": "zh",
                "text_split_method": "cut5", "batch_size": 1,
                "speed_factor": speed,  # 应用动态语速
            }
            try:
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(None,
                                                      lambda: self.session.post(f"{SOVITS_API_URL}/tts", json=payload))
                if response.status_code == 200 and len(response.content) > 1000:
                    filename = f"temp_{int(time.time())}_{i}.wav"
                    with open(filename, "wb") as f: f.write(response.content)
                    await audio_queue.put((filename, text))
            except Exception as e:
                print(f"❌ API异常: {e}")
        await audio_queue.put(None)

    async def _audio_player(self, audio_queue, vts, emotion):
        first_sentence = True
        while True:
            if self.stop_event.is_set():
                while not audio_queue.empty():
                    try:
                        audio_queue.get_nowait(); audio_queue.task_done()
                    except:
                        break
                break
            item = await audio_queue.get()
            if item is None: break
            filename, text = item
            if not os.path.exists(filename): continue

            print(f"▶️ 正在播放: {text[:15]}...")
            if vts and first_sentence:
                if emotion in ACTIONS: await vts.trigger_action(emotion)
                await vts.look_at_camera()
                first_sentence = False

            try:
                sound = pygame.mixer.Sound(filename)
                self.voice_channel.play(sound)
                while self.voice_channel.get_busy():
                    if self.stop_event.is_set(): self.voice_channel.stop(); return
                    await asyncio.sleep(0.1)
            except Exception as e:
                print(f"⚠️ 播放错误: {e}")
            finally:
                await asyncio.sleep(0.1)
                if os.path.exists(filename):
                    try:
                        os.remove(filename)
                    except:
                        pass
        if not self.stop_event.is_set() and vts:
            await vts.look_at_camera()

    async def speak(self, full_text, vts):
        if not full_text: return
        emotion = "正常"
        match = re.search(r"\[(.*?)\]", full_text)

        if match:
            raw_tag = match.group(1)
            # 1. 精准匹配
            if raw_tag in ACTIONS:
                emotion = raw_tag
            # 2. 同义词表匹配
            elif raw_tag in TAG_ALIASES:
                emotion = TAG_ALIASES[raw_tag]
                print(f"🔧 [自动修正] '{raw_tag}' -> '{emotion}'")
            # 3. 🔥 本地模型语义匹配
            else:
                emotion = self._map_emotion_local(raw_tag)

        clean_text = re.sub(r"\[.*?\]|\(.*?\)|\（.*?\）|\【.*?\】", "", full_text).strip()
        sentences = []
        for part in re.split(r'(。|！|？|\n|…)', clean_text):
            if part.strip(): sentences.append(part.strip())

        queue = asyncio.Queue()
        self.stop_event.clear()
        await asyncio.gather(self._tts_producer(sentences, queue, emotion), self._audio_player(queue, vts, emotion))