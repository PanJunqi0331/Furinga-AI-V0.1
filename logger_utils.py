import sys
import os
import datetime


class DualLogger:
    def __init__(self, filename="runtime.log"):
        # 1. 确保 logs 文件夹存在
        self.log_dir = "logs"
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)

        # 2. 生成带日期的文件名 (例如: logs/2026-01-20.log)
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        self.filepath = os.path.join(self.log_dir, f"{today}.log")

        # 3.以此文件作为日志
        self.file = open(self.filepath, "a", encoding="utf-8")
        self.terminal = sys.stdout  # 记住原本的屏幕输出通道

    def write(self, message):
        # 屏幕显示一份
        self.terminal.write(message)
        # 文件里存一份
        self.file.write(message)
        self.file.flush()  # 强制立刻写入，防止程序崩了没存上

    def flush(self):
        # 必须实现这个方法，否则有些库会报错
        self.terminal.flush()
        self.file.flush()


def setup_logger():
    """开启日志记录"""
    # 将系统的标准输出 (print) 重定向到我们的 DualLogger
    sys.stdout = DualLogger()

    # 打印一条分隔线，标记这次启动的时间
    now_time = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"\n\n{'=' * 20} 启动记录: {now_time} {'=' * 20}\n")