import sys
import os
import datetime
class DualLogger:
    def __init__(self, filename="runtime.log"):
        self.log_dir = "logs"
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        self.filepath = os.path.join(self.log_dir, f"{today}.log")
        self.file = open(self.filepath, "a", encoding="utf-8")
        self.terminal = sys.stdout
    def write(self, message):
        if self.terminal:
            self.terminal.write(message)
        self.file.write(message)
        self.file.flush()
    def flush(self):
        if self.terminal:
            self.terminal.flush()
        self.file.flush()
    def isatty(self):
        if hasattr(self.terminal, 'isatty'):
            return self.terminal.isatty()
        return True

    def fileno(self):
        if hasattr(self.terminal, 'fileno'):
            return self.terminal.fileno()
        return 1
def setup_logger():
    sys.stdout = DualLogger()
    now_time = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"\n\n{'=' * 20} 启动记录: {now_time} {'=' * 20}\n")