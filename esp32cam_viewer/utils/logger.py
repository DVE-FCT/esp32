from PyQt5.QtCore import pyqtSignal, QObject
from datetime import datetime

class QtLogger(QObject):
    """
    Qt日志记录器类，继承自QObject，用于在PyQt应用中实现线程安全的日志记录
    
    特性：
    - 支持多线程环境下的日志记录
    - 自动添加时间戳和日志级别
    - 通过信号槽机制实现与UI组件的安全通信
    
    信号：
    log_signal: 当有新日志时发射，携带格式化后的日志消息(str)
    """
    log_signal = pyqtSignal(str)  # 定义一个发射字符串的信号

    def log(self, message, level="INFO"):
        """
        记录日志消息
        
        参数：
        message (str): 要记录的日志消息内容
        level (str): 日志级别，默认为"INFO"
                    可选值："DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"
        
        处理流程：
        1. 获取当前时间戳
        2. 格式化日志消息
        3. 通过信号发射日志消息
        """
        # 生成当前时间的时间戳 (格式: YYYY-MM-DD HH:MM:SS)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # 格式化日志消息 [时间戳] 级别: 消息内容
        formatted = f"[{timestamp}] {level}: {message}"
        # 发射信号(线程安全)
        self.log_signal.emit(formatted)

def setup_logger(log_widget):
    """
    创建并配置QtLogger实例
    
    参数：
    log_widget (QTextEdit/QPlainTextEdit): 用于显示日志的Qt文本组件
    
    返回：
    QtLogger: 配置好的日志记录器实例
    
    典型用法：
    >>> log_display = QTextEdit()
    >>> logger = setup_logger(log_display)
    >>> logger.log("系统初始化完成")
    """
    # 创建日志记录器实例
    logger = QtLogger()
    # 将日志信号连接到UI组件的append方法
    logger.log_signal.connect(log_widget.append)
    return logger
