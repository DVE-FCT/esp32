import cv2
import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal, QDateTime
from PIL import ImageFont, ImageDraw, Image

class VideoStreamThread(QThread):
    """
    视频流处理线程类（继承自QThread）
    功能：从IP摄像头获取视频流，支持实时显示和录制功能
    信号：
    - frame_ready: 发送处理后的视频帧(numpy数组)
    - status_signal: 发送状态信息(状态类型, 消息内容)
    """
    frame_ready = pyqtSignal(np.ndarray)
    status_signal = pyqtSignal(str, str)  # (status_type, message)

    def __init__(self, ip=None, port=None, device=0):
        """
        初始化视频流线程
        :param ip: 摄像头IP地址
        :param port: 摄像头端口号
        :param device: (默认0) 本地摄像头设备号
        """
        super().__init__()
        # 视频流URL（MJPG格式）
        if ip and port:
            self.stream_url = f"http://{ip}:{port}/stream"  # 网络摄像头
        else:
            self.stream_url = device  # 本地摄像头编号

        # 线程控制标志
        self._is_running = True    # 控制线程运行
        self._recording = False    # 录制状态标志

        # 视频录制相关属性
        self.writer = None                  # 视频写入器对象
        self.recording_start_time = 0       # 录制开始时间戳(毫秒)
        self.indicator_radius = 12          # 红点半径
        self.radius_increasing = True       # 红点半径变化方向

        # 测试用属性（验证代码执行路径）
        self.test_frame_count = 0           # 测试：已处理帧数计数器
        self.test_last_status = ""          # 测试：最后发出的状态信息

    def run(self):
        """
        线程主运行方法（重写QThread方法）
        功能：持续获取视频帧并处理
        """
        self._emit_status("debug", "视频流线程启动")

        # 创建视频捕获对象
        cap = cv2.VideoCapture(self.stream_url)
        if not cap.isOpened():
            self._emit_status("error", f"无法打开视频流 {self.stream_url}")
            return

        # 主循环
        while self._is_running:
            self.test_frame_count += 1

            # 读取视频帧
            ret, frame = cap.read()
            if not ret:
                self._emit_status("warning", "视频帧获取失败")
                continue

            # 录制处理逻辑
            processed_frame = self._process_frame(frame)

            # 发送处理后的帧（BGR转RGB）
            self.frame_ready.emit(cv2.cvtColor(processed_frame, cv2.COLOR_BGR2RGB))

        # 资源释放
        cap.release()
        if self.writer:
            self.writer.release()

        self._emit_status("debug", "视频流线程停止")

    def _process_frame(self, frame):
        """
        帧处理函数（内部方法）
        :param frame: 原始视频帧
        :return: 处理后的视频帧
        """
        # 始终绘制时间戳
        frame = self._add_timestamp(frame)

        # 录制状态处理
        if self._recording:
            # 写入视频文件
            if self.writer:
                self.writer.write(frame)

            # 添加录制指示器
            frame = self._add_recording_indicator(frame)

        return frame
    
    def _add_timestamp(self, frame):
        """
        添加时间戳到每一帧
        :param frame: 原始视频帧
        :return: 添加时间戳后的视频帧
        """
        # 当前时间显示（左上角）
        now = QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm:ss")
        frame = self._draw_text_with_pil(
            frame,
            now,
            position=(30, 30),  # 左上角
            font_size=18,
            color=(255, 255, 255)
        )

        return frame

    def _add_recording_indicator(self, frame):
        """
        添加录制指示器（内部方法）
        :param frame: 原始视频帧
        :return: 添加指示器后的视频帧
        """
        # 计算已录制时长（秒）
        current_time = QDateTime.currentMSecsSinceEpoch()
        elapsed_seconds = int((current_time - self.recording_start_time) / 1000)

        # 红点闪烁逻辑：1秒开 1秒关（根据当前秒数的奇偶）
        if elapsed_seconds % 2 == 0:
            cv2.circle(frame, (frame.shape[1] - 50, 50), self.indicator_radius, (0, 0, 255), -1)

        # 中文 & 英文文字使用PIL绘制（录制时长 + 时间戳）
        frame = self._draw_text_with_pil(
            frame,
            f"已录制: {elapsed_seconds}s",
            position=(frame.shape[1] - 200, 30),  # 右上角
            font_size=24,
            color=(255, 255, 255)
        )

        return frame

    def _draw_text_with_pil(self, frame, text, position=(50, 50), font_size=24, color=(255, 255, 255)):
        """
        使用PIL绘制支持中文的文字
        :param frame: OpenCV图像帧 (BGR)
        :param text: 显示文字（支持中文）
        :param position: 显示位置(x, y)
        :param font_size: 字体大小
        :param color: 字体颜色 (B, G, R)
        """
        # OpenCV图像转PIL格式
        image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(image)

        draw = ImageDraw.Draw(pil_img)
        try:
            font = ImageFont.truetype("simhei.ttf", font_size)  # 中文黑体
        except:
            font = ImageFont.load_default()

        draw.text(position, text, font=font, fill=color[::-1])  # RGB顺序

        # PIL图像转回OpenCV格式
        frame = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
        return frame

    def _emit_status(self, status_type, message):
        """
        发送状态信息（封装方法）
        :param status_type: 状态类型（error/warning/info/debug）
        :param message: 状态消息内容
        """
        self.test_last_status = f"{status_type}:{message}"  # 测试记录
        self.status_signal.emit(status_type, message)

    # ---------- 公共控制接口 ----------
    def start_recording(self, filepath):
        """
        开始录制视频
        :param filepath: 视频保存路径（建议.avi格式）
        """
        # 初始化视频写入器（XVID编码，20fps，640x480分辨率） ！！！注意分辨率
        self.writer = cv2.VideoWriter(
            filepath,
            cv2.VideoWriter_fourcc(*'XVID'),
            20.0,
            (640, 480)
        )
        if not self.writer.isOpened():
            self._emit_status("error", "无法创建视频文件")
            return

        self._recording = True
        self.recording_start_time = QDateTime.currentMSecsSinceEpoch()
        self._emit_status("info", "视频录制已开始")

    def stop_recording(self):
        """停止视频录制"""
        self._recording = False
        if self.writer:
            self.writer.release()
            self.writer = None
            self._emit_status("info", "视频录制已停止")

    def stop(self):
        """停止线程运行"""
        self._is_running = False
        self.wait()  # 等待线程结束
        self._emit_status("debug", "线程已安全停止")

    # ---------- 测试辅助方法 ----------
    def get_test_info(self):
        """
        获取测试信息（用于单元测试）
        :return: (已处理帧数, 最后状态信息)
        """
        return (self.test_frame_count, self.test_last_status)
