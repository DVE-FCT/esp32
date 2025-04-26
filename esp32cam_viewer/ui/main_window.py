from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                            QComboBox, QLineEdit, QPushButton, QLabel, 
                            QTextEdit, QFileDialog, QSizePolicy)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtGui import QImage, QPixmap

import numpy as np
import cv2, os, random
from datetime import datetime

# 导入自定义模块
from core.video_thread import VideoStreamThread
from core.camera_manager import CameraManager
from core.camera_display import CameraDisplay 
from utils.logger import setup_logger 

class CameraApp(QMainWindow):
    """
    ESP32-CAM 视频监控系统主窗口
    功能：
    1. 多摄像头管理（添加/删除/切换）
    2. 实时视频流显示
    3. 视频录制功能
    4. 系统日志记录
    5. 性能监控（帧率、CPU占用率）
    6. 自动重连功能（断线自动重连）
    """
    def __init__(self):
        super().__init__()
        
        # 初始化成员变量
        self.video_thread = None                # 视频流处理线程
        self.recording = False                  # 录制状态标志
        self.save_path = ""                     # 视频保存路径
        self.current_camera = None              # 当前连接的摄像头信息
        self.camera_manager = CameraManager()   # 摄像头管理器

        self.reconnect_timer = None             # 自动重连定时器
        self.frame_counter = 0                  # 帧计数器（用于性能监控）
        
        # 创建data目录（如果不存在）
        self.data_dir = os.path.join(os.getcwd(), "data")
        os.makedirs(self.data_dir, exist_ok=True)

        # 初始化UI界面
        self.setup_ui()
        
        # 设置信号槽连接
        self.setup_connections()
        
        # 初始化日志系统
        self.logger = setup_logger(self.log_display)
        self.logger.log("系统初始化完成", "INFO")
        
        # 初始化摄像头下拉框
        self.update_camera_selector()

        # 初始化自动重连定时器
        self.init_reconnect_timer()

    def setup_ui(self):
        """初始化用户界面"""
        # 主窗口设置
        self.setWindowTitle("ESP32-CAM Viewer")                     
        self.setGeometry(100, 100, 1200, 800)                   # 设置窗口位置和大小(x,y,width,height)
        
        # 中央部件
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)              # 设置中心部件
        
        # 主布局 (水平布局：左侧控制面板 + 右侧视频显示)
        self.main_layout = QHBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(10, 10, 10, 10)     # 设置边距(左,上,右,下)
        self.main_layout.setSpacing(10)                         # 设置组件间距   
        
        # 初始化控制面板（左）
        self.setup_control_panel()
        
        # 初始化视频显示区域（右）
        self.setup_video_display()

        # 设置左右两部分的比例为2:3 ，因为左边固定宽度，右边自适应，所以调整比例没有影响窗口拓展时的布局
        # self.main_layout.setStretch(0, 4)  # 左侧控制面板占比2
        # self.main_layout.setStretch(1, 6)  # 右侧视频显示占比3

    def setup_control_panel(self):
        """初始化左侧控制面板"""
        # 控制面板容器
        control_panel = QWidget()
        control_panel.setFixedWidth(400)                        # 固定宽度      
        control_layout = QVBoxLayout(control_panel)             
        control_layout.setSpacing(15)                           # 设置组件间距    
        
        # --- 摄像头选择区域 ---
        camera_group = QWidget()
        camera_layout = QVBoxLayout(camera_group)
        camera_layout.setSpacing(8)
        
        # 摄像头下拉选择框
        self.cam_selector = QComboBox()
        camera_layout.addWidget(QLabel("选择摄像头:"))
        camera_layout.addWidget(self.cam_selector)
        
        # IP地址输入框
        self.ip_input = QLineEdit()
        self.ip_input.setPlaceholderText("192.168.1.100")
        camera_layout.addWidget(QLabel("IP地址:"))
        camera_layout.addWidget(self.ip_input)
        
        # 端口输入框
        self.port_input = QLineEdit()
        self.port_input.setPlaceholderText("80")
        camera_layout.addWidget(QLabel("端口:"))
        camera_layout.addWidget(self.port_input)
        
        # 连接/断开按钮
        self.btn_connect = QPushButton("连接摄像头")
        self.btn_connect.setStyleSheet("background-color: #4CAF50; color: white;")
        
        # 摄像头管理按钮
        self.btn_add_camera = QPushButton("添加当前配置")
        self.btn_remove_camera = QPushButton("移除选中摄像头")
        
        camera_layout.addWidget(self.btn_connect)
        camera_layout.addWidget(self.btn_add_camera)
        camera_layout.addWidget(self.btn_remove_camera)
        
        # --- 录制控制区域 ---
        record_group = QWidget()
        record_layout = QVBoxLayout(record_group)
        record_layout.setSpacing(8)
        
        # 录制控制按钮
        self.btn_record = QPushButton("开始录制")
        self.btn_record.setEnabled(False)  # 初始禁用
        self.btn_record.setStyleSheet("background-color: #f44336; color: white;")
        
        # 保存路径设置
        self.btn_save = QPushButton("设置保存路径")
        
        # 录制状态显示
        self.record_status = QLabel("录制状态: 未开始")
        self.record_status.setAlignment(Qt.AlignCenter)      # 设置文本居中
        
        record_layout.addWidget(self.btn_record)
        record_layout.addWidget(self.btn_save)
        record_layout.addWidget(self.record_status)
        
        # --- 日志显示区域 ---
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)                    # 只读模式
        self.log_display.setMinimumHeight(200)                # 设置最小高度
        
        # 将所有组件添加到控制面板
        control_layout.addWidget(camera_group)
        control_layout.addWidget(record_group)
        control_layout.addWidget(QLabel("系统日志:"))
        control_layout.addWidget(self.log_display)
        
        # 将控制面板添加到主布局
        self.main_layout.addWidget(control_panel)

    def setup_video_display(self):
        """初始化视频显示区域"""
        # 视频显示容器
        video_container = QWidget()
        video_layout = QVBoxLayout(video_container)    # 在这个容器中添加的所有子组件都会按照从上到下的顺序排列
        video_layout.setContentsMargins(0, 0, 0, 0)
        
        # 使用自定义的CameraDisplay组件
        self.video_display = CameraDisplay()
        self.video_display.setSizePolicy(
            QSizePolicy.Expanding, 
            QSizePolicy.Expanding
        )
        
        # 状态信息标签
        self.status_label = QLabel("准备连接摄像头...")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("font-size: 16px; color: #666;")
        
        # 添加到布局
        video_layout.addWidget(self.video_display)
        video_layout.addWidget(self.status_label)
        
        # 将视频区域添加到主布局（使用stretch参数使其占据剩余空间）
        self.main_layout.addWidget(video_container, stretch=1)

    def setup_connections(self):
        """设置所有信号槽连接"""
        # 按钮信号连接
        self.btn_connect.clicked.connect(self.connect_camera)
        self.btn_record.clicked.connect(self.toggle_recording)
        self.btn_save.clicked.connect(self.select_save_path)
        self.btn_add_camera.clicked.connect(self.add_camera)
        self.btn_remove_camera.clicked.connect(self.remove_camera)
        
        # 摄像头选择变化信号
        self.cam_selector.currentTextChanged.connect(self.switch_camera)
        
        # 窗口关闭事件处理
        self.closeEvent = self.on_close

    def init_reconnect_timer(self):
        """初始化自动重连定时器"""
        # 定时器默认是不活动的，不会自动触发 timeout 信号
        self.reconnect_timer = QTimer()
        self.reconnect_timer.setInterval(2000)  # 2秒重试间隔
        self.reconnect_timer.timeout.connect(self.attempt_reconnect)
        
    def attempt_reconnect(self):
        """尝试自动重连"""
        if not self.video_thread and self.current_camera:
            ip = self.current_camera.get("ip", "")       # 使用了字典的 get 方法，并且设置了默认值为空字符串，以防 ip 或 port 键不存在时不会引发 KeyError
            port = self.current_camera.get("port", "")
            if ip and port:
                self.logger.log(f"尝试自动重连... {ip}:{port}", "INFO")
                self.ip_input.setText(ip)
                self.port_input.setText(port)
                self.connect_camera()

    def update_camera_selector(self):
        """更新摄像头下拉选择框"""
        self.cam_selector.clear()
        cameras = self.camera_manager.get_camera_list()
        
        if cameras:
            self.cam_selector.addItems(cameras)          # 添加摄像头名称
            self.cam_selector.setCurrentIndex(0)         # 默认选择第一个摄像头
        else:
            # 默认值
            self.ip_input.setText("192.168.1.100")
            self.port_input.setText("80")

    def connect_camera(self):
        """连接/断开摄像头"""
        if self.video_thread:
            # 如果已连接，则断开连接
            self.disconnect_camera()
            return
        
        # 获取输入参数
        ip = self.ip_input.text().strip()
        port = self.port_input.text().strip()
        
        # 验证输入
        if not ip or not port:
            self.logger.log("错误：请输入有效的IP和端口", "ERROR")
            return
            
        self.logger.log(f"正在连接 {ip}:{port}...", "INFO")
        
        try:
            # 创建并启动视频线程
            self.video_thread = VideoStreamThread(device=0)  # 改成本地摄像头
            #self.video_thread = VideoStreamThread(ip, port)
            self.video_thread.frame_ready.connect(self.update_video_frame)
            self.video_thread.status_signal.connect(self.handle_thread_status)
            self.video_thread.start()
            
            # 更新UI状态
            self.video_display.set_connected(True)
            self.btn_connect.setText("断开连接")
            self.btn_connect.setStyleSheet("background-color: #FF5722; color: white;")
            self.btn_record.setEnabled(True)
            self.status_label.setText(f"已连接: {ip}:{port}")
            self.current_camera = {"ip": ip, "port": port}
            
            # 停止自动重连定时器
            if self.reconnect_timer.isActive():             # 防止重复启动
                self.reconnect_timer.stop()
                self.logger.log("停止自动重连定时器，因为已连接摄像头", "INFO")

            self.logger.log("摄像头连接成功")
            
        except Exception as e:
            self.logger.log(f"连接失败: {str(e)}", "ERROR")
            self.video_display.set_connected(False)

            # 启动自动重连定时器
            self.reconnect_timer.start()
            self.logger.log("启动自动重连定时器", "INFO")

    def disconnect_camera(self):
        """断开摄像头连接"""
        if self.video_thread:
            # 停止录制（如果正在录制）
            if self.recording:
                self.toggle_recording()
            
            # 停止视频线程
            self.video_thread.stop()
            self.video_thread = None
            
            # 更新UI状态
            self.video_display.set_connected(False)
            self.btn_connect.setText("连接摄像头")
            self.btn_connect.setStyleSheet("background-color: #4CAF50; color: white;")
            self.btn_record.setEnabled(False)
            self.status_label.setText("已断开连接")
            self.record_status.setText("录制状态: 未开始")
            
            self.logger.log("已断开摄像头连接")

    def toggle_recording(self):
        """开始/停止录制"""
        if not self.video_thread:
            self.logger.log("警告：请先连接摄像头", "WARNING")
            return
            
        if not self.recording:
            # 开始录制
            self.start_recording()
        else:
            # 停止录制
            self.stop_recording()

    def start_recording(self):
        """开始录制（自动生成新文件名）"""
        # 每次开始录制都生成新文件名
        self.save_path = self.generate_unique_filename()
        
        try:
            self.video_thread.start_recording(self.save_path)
            self.recording = True
            self.btn_record.setText("停止录制")
            self.record_status.setText("录制状态: 进行中")
            self.status_label.setText(f"正在录制: {os.path.basename(self.save_path)}")
            self.logger.log(f"开始录制: {self.save_path}")
        except Exception as e:
            self.logger.log(f"录制失败: {str(e)}", "ERROR")

    def stop_recording(self):
        """停止视频录制"""
        if self.video_thread and self.recording:
            self.video_thread.stop_recording()
            self.recording = False
            self.btn_record.setText("开始录制")
            self.record_status.setText("录制状态: 已停止")
            self.status_label.setText(f"已保存: {self.save_path}")
            self.logger.log(f"视频已保存到: {self.save_path}")

    def select_save_path(self):
        """自动生成唯一保存路径"""
        self.save_path = self.generate_unique_filename()
        self.logger.log(f"自动生成保存路径: {self.save_path}")
        
        # 如果需要用户确认，可以改用：
        """
        suggested_path = self.generate_unique_filename()
        path, _ = QFileDialog.getSaveFileName(
            self, "保存视频", suggested_path, "MP4 Files (*.mp4)"
        )
        if path:
            self.save_path = path
        """

    def generate_unique_filename(self):
        """生成绝对不会重复的文件名"""
        base_name = datetime.now().strftime("视频_%Y%m%d_%H%M%S_%f")[:-3]  # 精确到毫秒
        ext = ".mp4"
        filename = f"{base_name}{ext}"
        full_path = os.path.join(self.data_dir, filename)
        
        # 极端情况处理：如果文件已存在（几乎不可能），追加序号
        counter = 1
        while os.path.exists(full_path):
            filename = f"{base_name}_{counter}{ext}"
            full_path = os.path.join(self.data_dir, filename)
            counter += 1
        
        return full_path


    def update_video_frame(self, frame):
        """
        更新视频帧显示
        :param frame: numpy.ndarray格式的视频帧
        """
        self.video_display.update_frame(frame)
        
        # 更新状态信息（如果正在录制）
        if self.recording:
            self.status_label.setText(f"正在录制: {self.save_path}")

    def handle_thread_status(self, status_type, message):
        """
        处理视频线程状态消息
        :param status_type: 消息类型（error/warning/info）
        :param message: 消息内容
        """
        if status_type == "error":
            self.logger.log(message, "ERROR")
            self.disconnect_camera()
        elif status_type == "warning":
            self.logger.log(message, "WARNING")
        else:
            self.logger.log(message)

    def add_camera(self):
        """添加当前配置到摄像头列表"""
        ip = self.ip_input.text().strip()
        port = self.port_input.text().strip()
        
        if not ip or not port:
            self.logger.log("错误：请输入有效的IP和端口", "ERROR")
            return
            
        # 生成摄像头名称
        name = f"Camera {len(self.camera_manager.cameras)+1}"
        
        # 添加到管理器
        self.camera_manager.add_camera(name, ip, port)
        self.update_camera_selector()
        
        self.logger.log(f"已添加摄像头: {name} ({ip}:{port})")

    def remove_camera(self):
        """移除选中的摄像头"""
        current = self.cam_selector.currentText()
        if not current:
            return
            
        self.camera_manager.remove_camera(current)
        self.update_camera_selector()
        
        self.logger.log(f"已移除摄像头: {current}")

    def switch_camera(self, name):
        """
        切换选中的摄像头
        :param name: 摄像头名称
        """
        if not name:
            return
            
        # 从管理器获取摄像头信息
        cam = self.camera_manager.get_camera_info(name)
        if cam:
            self.ip_input.setText(cam["ip"])
            self.port_input.setText(cam["port"])

    def on_close(self, event):
        """窗口关闭事件处理"""
        if self.video_thread:
            self.disconnect_camera()
        event.accept()

# # 主程序入口
# if __name__ == "__main__":
#     import sys
#     from PyQt5.QtWidgets import QApplication
    
#     app = QApplication(sys.argv)
    
#     # 设置全局样式
#     app.setStyleSheet("""
#         QMainWindow {
#             background-color: #F5F5F5;
#         }
#         QPushButton {
#             padding: 5px;
#             border-radius: 4px;
#             min-width: 80px;
#         }
#         QTextEdit {
#             font-family: Consolas;
#             font-size: 12px;
#         }
#     """)
    
#     window = CameraApp()
#     window.show()
#     sys.exit(app.exec_())
