import time
import asyncio
from collections import defaultdict


class TrafficController:
    def __init__(self, process_interval=3.0, max_queue_size=20):
        """
        :param process_interval: 芙宁娜处理弹幕的节奏 (每隔几秒看一次弹幕)
        :param max_queue_size: 弹幕池最大容量 (超过就丢弃低优先级的)
        """
        self.msg_queue = []  # 弹幕池
        self.process_interval = process_interval
        self.max_queue_size = max_queue_size
        self.is_processing = False

        # 用户碎片缓存 (用于合并同一个人的连续发言)
        # 格式: {username: {"text": ["哈", "哈"], "score": 100, "time": 12345}}
        self.fragment_buffer = defaultdict(lambda: {"text": [], "score": 0, "time": 0})

    def add_message(self, username, text, affection_score):
        """
        接收一条新弹幕 (非阻塞)
        """
        if not text.strip(): return

        # 1. 先存入碎片缓存 (防抖合并)
        user_buf = self.fragment_buffer[username]
        user_buf["text"].append(text)
        user_buf["score"] = affection_score
        user_buf["time"] = time.time()

        print(f"📨 [弹幕池] 收到 {username} (Lv.{affection_score}): {text}")

    async def get_best_message(self):
        """
        🔥 核心算法：挑一条最值得回的弹幕
        """
        # 1. 先把碎片拼成完整句子
        current_time = time.time()
        candidates = []

        # 遍历所有发过言的用户
        users_to_clear = []
        for username, data in self.fragment_buffer.items():
            # 只有当用户 "停嘴" 超过 0.5 秒，才认为这一句说完了
            if current_time - data["time"] > 0.5:
                full_text = "，".join(data["text"])
                candidates.append({
                    "username": username,
                    "text": full_text,
                    "score": data["score"],
                    "timestamp": data["time"]
                })
                users_to_clear.append(username)

        # 清理已处理的碎片
        for u in users_to_clear:
            del self.fragment_buffer[u]

        if not candidates:
            return None

        # 2. 排序 (优先级算法)
        # 规则：分数高的优先 > 字数多的优先(认为是更有内容的) > 新的优先
        candidates.sort(key=lambda x: (x["score"], len(x["text"]), x["timestamp"]), reverse=True)

        # 3. 选出第一名 (VIP)
        best_msg = candidates[0]

        # 4. 【残酷的现实】剩下的弹幕... 被无视了 (Log里记一下)
        ignored_count = len(candidates) - 1
        if ignored_count > 0:
            print(f"💨 [直播间] 芙芙无视了其他 {ignored_count} 条低优先级弹幕 (太忙了回不过来)")

        return best_msg