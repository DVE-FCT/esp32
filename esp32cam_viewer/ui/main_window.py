from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                            QComboBox, QLineEdit, QPushButton, QLabel, 
                            QTextEdit, QFileDialog, QSizePolicy, QMessageBox)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer, pyqtSlot 
from PyQt5.QtGui import QImage, QPixmap

import numpy as np
import cv2, os, random, sys, json
from datetime import datetime

# 导入自定义模块
from core.video_thread import VideoStreamThread
from core.control_thread import ControlThread
from core.speed_thread import SpeedCalculationThread
from core.detection_thread import DetectionThread

from core.camera_manager import CameraManager
from core.camera_display import CameraDisplay 
from utils.logger import setup_logger 

class CameraApp(QMainWindow):
    """
    ESP32-CAM 视频监控系统主窗口
    """
    def __init__(self):
        super().__init__()
        
        # 初始化成员变量
        self.video_thread = None                # 视频流处理线程
        self.control_thread = None              # 控制线程实例
        
        self.light_state = False                # 灯光状态跟踪
        self.recording = False                  # 录制状态标志

        self.save_path = ""                     # 视频保存路径
        self.current_camera = None              # 当前连接的摄像头信息
        self.camera_manager = CameraManager()   # 摄像头管理器

        self.reconnect_timer = None             # 自动重连定时器
        self.frame_counter = 0                  # 帧计数器（用于性能监控）
        self.FPS = 6.0                          # 录制帧率，预估的帧率防止存储的视频过快

        self.speed_thread = None                # 速度标定线程
        self.calculated_roi_rect = None         # 存储计算出的ROI
        self.current_speed = 0.0                # 存储配准的速度
        self.speed_time_limit = 0.6             # 速度标定时间容差（秒）

        self.detection_thread = None            # 检测线程实例
        self.models = {}  # 存储模型名称和路径的字典

        
        # 创建data目录（如果不存在）
        self.data_dir = os.path.join(os.getcwd(), "data")
        os.makedirs(self.data_dir, exist_ok=True)
        # --- 为速度标定创建调试目录 ---
        self.speed_debug_dir = os.path.join(self.data_dir, 'speed_debug_output')
        os.makedirs(self.speed_debug_dir, exist_ok=True)
        # 创建存储检测结果的目录
        self.detection_result_dir = os.path.join(self.data_dir, 'detection_debug_output')
        os.makedirs(self.detection_result_dir, exist_ok=True)

        # 初始化UI界面
        self.setup_ui()
        
        # 设置信号槽连接
        self.setup_connections()
        
        # 初始化日志系统
        self.logger = setup_logger(self.log_display)
        self.logger.log("系统初始化完成", "INFO")
        
        # 初始化摄像头下拉框
        self.update_camera_selector()

        # 初始化模型选择框
        self.update_model_selector()

        # 初始化自动重连定时器
        self.init_reconnect_timer()

    def setup_ui(self):
        """初始化用户界面"""
        # 主窗口设置
        self.setWindowTitle("ESP32-CAM 视频监控系统")                     
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
        
        # 模型选择框
        self.model_selector = QComboBox()
        camera_layout.addWidget(QLabel("选择检测模型:"))
        camera_layout.addWidget(self.model_selector)

        # 摄像头下拉选择框
        self.cam_selector = QComboBox()
        camera_layout.addWidget(QLabel("选择摄像头:"))
        camera_layout.addWidget(self.cam_selector)
        
        # IP地址输入框
        self.ip_input = QLineEdit()
        self.ip_input.setPlaceholderText("192.168.1.100")
        camera_layout.addWidget(QLabel("局域网IP地址:"))
        camera_layout.addWidget(self.ip_input)
        
        # 端口输入框
        self.port_input = QLineEdit()
        self.port_input.setPlaceholderText("80")
        camera_layout.addWidget(QLabel("端口:"))
        camera_layout.addWidget(self.port_input)
        
        # 连接/断开按钮
        self.btn_connect = QPushButton("连接摄像头")
        self.btn_connect.setStyleSheet("color: black;")
        
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
        # self.btn_record.setStyleSheet("background-color: #f44336; color: black;")
        
        # 保存路径设置
        self.btn_save = QPushButton("设置保存路径")
        
        # 录制状态显示
        self.record_status = QLabel("录制状态: 未开始")
        self.record_status.setAlignment(Qt.AlignCenter)      # 设置文本居中
        
        record_layout.addWidget(self.btn_record)
        record_layout.addWidget(self.btn_save)
        record_layout.addWidget(self.record_status)
        
        # --- 灯光控制区域 ---
        light_group = QWidget()
        light_layout = QVBoxLayout(light_group)
        light_layout.setSpacing(8)
        
        self.btn_light = QPushButton("开灯")
        self.btn_light.setObjectName("btn_light")     
        self.btn_light.setStyleSheet("color: black;")
        light_layout.addWidget(self.btn_light)
        
        # --- 拍照控制区域 ---
        capture_group = QWidget()
        capture_layout = QVBoxLayout(capture_group)
        capture_layout.setSpacing(8)
        
        self.btn_capture = QPushButton("拍照")
        self.btn_capture.setObjectName("btn_capture")  
        self.btn_capture.setStyleSheet("color: black;")
        capture_layout.addWidget(self.btn_capture)

        # --- 日志显示区域 ---
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)                    # 只读模式
        self.log_display.setMinimumHeight(200)                # 设置最小高度
        
        # 将所有组件添加到控制面板
        control_layout.addWidget(camera_group)
        control_layout.addWidget(light_group)
        control_layout.addWidget(capture_group)
        control_layout.addWidget(record_group)
        control_layout.addWidget(QLabel("系统日志:"))
        control_layout.addWidget(self.log_display)
        
        # 将控制面板添加到主布局
        self.main_layout.addWidget(control_panel)

    def setup_video_display(self):
        """初始化视频显示区域 """
        # 视频显示容器
        video_container = QWidget()
        # 主垂直布局，用于容纳速度控制区、视频显示区和状态标签
        video_layout = QVBoxLayout(video_container)
        video_layout.setContentsMargins(0, 0, 0, 0)
        video_layout.setSpacing(5)  # 为各部分之间添加一点间距

        # 速度标定控制区
        speed_control_widget = QWidget() # 创建一个容器Widget
        speed_control_layout = QHBoxLayout(speed_control_widget) # 创建水平布局
        speed_control_layout.setContentsMargins(5, 2, 5, 2) # 设置内边距 (左,上,右,下)
        speed_control_layout.setSpacing(10) # 设置按钮和标签之间的间距

        # 速度配准按钮
        self.btn_register_speed = QPushButton("速度标定")
        self.btn_register_speed.setEnabled(False) # 初始禁用，连接后启用

        # 显示当前速度的标签
        self.label_current_speed = QLabel(f"当前速度: {self.current_speed:.2f} m/s")
        # 设置标签的对齐方式
        self.label_current_speed.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        # 将按钮和标签添加到水平布局中
        speed_control_layout.addWidget(self.btn_register_speed)
        speed_control_layout.addWidget(self.label_current_speed)
        speed_control_layout.addStretch(1) # 添加伸缩因子，将按钮和标签推到左侧

        # 检测按键
        self.btn_detection = QPushButton("开始检测")
        self.btn_detection.setEnabled(False) # 初始禁用，连接后启用
        # 匹配的圆形标签
        self.detection_label = QLabel()
        self.detection_label.setFixedSize(20, 20)
        self.detection_label.setStyleSheet("background-color: #81C784; border-radius: 10px;")
        speed_control_layout.addWidget(self.detection_label)
        speed_control_layout.addWidget(self.btn_detection)

        # --- 将新的速度控制布局添加到主垂直布局的顶部 ---
        video_layout.addWidget(speed_control_widget)

        # --- 原有的视频显示组件 ---
        # 使用自定义的CameraDisplay组件
        self.video_display = CameraDisplay()
        self.video_display.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Expanding
        )
        # 将视频显示组件添加到速度控制布局下方
        video_layout.addWidget(self.video_display)

        # --- 原有的状态信息标签 ---
        self.status_label = QLabel("准备连接摄像头...")
        self.status_label.setAlignment(Qt.AlignCenter)
        # 将状态标签添加到最下方
        video_layout.addWidget(self.status_label)

        # --- 将整个视频区域容器添加到主布局 ---
        self.main_layout.addWidget(video_container, stretch=1)

    def setup_connections(self):
        """设置所有信号槽连接"""
        # 按钮信号连接
        self.btn_connect.clicked.connect(self.connect_camera)     # 连接/断开摄像头按钮
        self.btn_record.clicked.connect(self.toggle_recording)    # 开始/停止录制按钮
        self.btn_save.clicked.connect(self.select_save_path)      # 设置保存路径按钮
        self.btn_add_camera.clicked.connect(self.add_camera)      # 添加摄像头按钮
        self.btn_remove_camera.clicked.connect(self.remove_camera)# 移除摄像头按钮

        self.btn_light.clicked.connect(self.LED_4_control)        # 开/关灯按钮
        self.btn_capture.clicked.connect(self.capture_image)      # 拍照按钮

        self.btn_register_speed.clicked.connect(self.start_speed_calibration) # 速度标定按钮
        self.btn_detection.clicked.connect(self.start_detection) # 检测按钮

        # 摄像头选择变化信号
        self.cam_selector.currentTextChanged.connect(self.switch_camera)

        # 模型选择变化信号
        self.model_selector.currentTextChanged.connect(self.switch_model)
        
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
        if self.video_thread and self.video_thread.isRunning():
            self.disconnect_camera()
            return
        
        ip = self.ip_input.text().strip()
        port = self.port_input.text().strip()
        use_local = not (ip and port)
        
        try:
            # 创建视频线程（网络或本地）
            self.video_thread = VideoStreamThread(device=0) if use_local else VideoStreamThread(ip, port)
            self.video_thread.frame_ready.connect(self.update_video_frame)
            self.video_thread.status_signal.connect(self.handle_thread_status)
            self.video_thread.start()
            self.logger.log("视频线程已启动", "DEBUG")

            # 创建控制线程（网络摄像头才需要）
            if not use_local:
                # 先断开现有连接
                if self.control_thread:
                    self.control_thread.stop()
                self.control_thread = ControlThread({"ip": ip, "port": port})
                # 控制线程信号连接
                self.control_thread.command_sent.connect(self.on_control_result)
                self.control_thread.connection_error.connect(self.on_control_error)
                self.control_thread.connection_status.connect(self.on_control_connection_changed)
                self.control_thread.light_state_changed.connect(self.on_light_state_changed)
                self.control_thread.start()
                self.logger.log("控制线程已启动", "DEBUG")
            
            # 更新UI状态
            connection_text = "本地摄像头" if use_local else f"{ip}:{port}"
            self.logger.log(f"摄像头连接中: {connection_text}", "INFO")
            
            # UI状态更新
            self.video_display.set_connected(True)
            self.btn_connect.setText("断开连接")
            self.btn_connect.setStyleSheet("background-color: #FF5722; color: black;")
            self.btn_record.setEnabled(True)
            # --- 启用速度标定按钮 ---
            self.btn_register_speed.setEnabled(True)
            # --- 启用检测按钮 ---
            self.btn_detection.setEnabled(True)
            self.status_label.setText(f"连接中: {connection_text}")
            
            # 保存当前摄像头信息
            self.current_camera = {
                "type": "local" if use_local else "network",
                "ip": None if use_local else ip,
                "port": None if use_local else port
            }
            
            # 停止自动重连
            if hasattr(self, 'reconnect_timer') and self.reconnect_timer.isActive():
                self.reconnect_timer.stop()
                self.logger.log("自动重连已停止", "DEBUG")
                
        except Exception as e:
            error_msg = f"连接失败: {str(e)}"
            self.logger.log(error_msg, "ERROR")
            
            # 失败状态处理
            self.video_display.set_connected(False)
            self.status_label.setText("连接失败")
            self.btn_connect.setText("连接摄像头")
            self.btn_connect.setStyleSheet("")
            self.btn_record.setEnabled(False)
            # --- 禁用速度标定按钮 ---
            self.btn_register_speed.setEnabled(False)
            
            # 启动自动重连（仅限网络摄像头）
            if not use_local and hasattr(self, 'reconnect_timer'):
                self.reconnect_timer.start()
                self.logger.log("将在5秒后尝试自动重连", "INFO")
            
            # 清理线程
            if hasattr(self, 'video_thread'):
                self.video_thread.stop()
                self.video_thread = None

    def disconnect_camera(self):
        """断开摄像头连接"""

        # --- 先停止速度标定线程（如果正在运行）---
        if self.speed_thread and self.speed_thread.isRunning():
            self.logger.log("断开连接：正在停止速度标定线程...", "INFO")
            self.speed_thread.stop()

        if self.video_thread:
            # 停止录制（如果正在录制）
            if self.recording:
                self.toggle_recording()
            
            # 停止视频线程
            self.video_thread.stop()
            self.video_thread = None

        # 停止控制线程（如果存在）
        if self.control_thread:
            self.control_thread.stop()
            self.control_thread = None
            
        # 更新UI状态
        self.video_display.set_connected(False)
        self.btn_connect.setText("连接摄像头")
        self.btn_connect.setStyleSheet("background-color: #4CAF50; color: black;")
        self.btn_record.setEnabled(False)
        self.btn_detection.setEnabled(False)
        # --- 禁用速度标定按钮 ---
        self.btn_register_speed.setEnabled(False)
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
            self.video_thread.start_recording(self.save_path, self.FPS)
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

    def LED_4_control(self):
        """灯光控制（分开实现）"""
        if not self.control_thread or not self.control_thread.is_connected:
            self.logger.log("未连接到可控制的摄像头", "ERROR")
            return
        if self.light_state == False:
            success = self.control_thread.turn_light_on()
            self.light_state = True
            self.btn_light.setText("关灯")
            self.btn_light.setStyleSheet("background-color: #FF5722; color: black;")
        else:
            success = self.control_thread.turn_light_off()
            self.light_state = False
            self.btn_light.setText("开灯")
            self.btn_light.setStyleSheet("background-color: #4CAF50; color: black;")
        
        if success:
            self.status_label.setText("灯光指令已发送")

    def capture_image(self):
        """拍照控制"""
        if not self.control_thread or not self.control_thread.is_connected:
            self.logger.log("未连接到可控制的摄像头", "ERROR")
            return
        success = self.control_thread.capture_photo()
        if success:
            self.status_label.setText("拍照指令已发送")

    def on_control_result(self, cmd, success):
        """指令结果处理"""
        action_map = {
            'L': ("开灯", "关灯失败"),
            'l': ("关灯", "开灯失败"), 
            'P': ("拍照成功", "拍照失败")
        }
        
        if cmd in action_map:
            msg = action_map[cmd][0] if success else action_map[cmd][1]
            self.status_label.setText(msg)
            self.logger.log(f"指令 {cmd} 执行{'成功' if success else '失败'}")

    def on_light_state_changed(self, status):
        self.status_label.setText(f"连接状态: {status}")

    def on_control_error(self, error_msg):
        """控制错误处理"""
        self.logger.log(f"控制错误: {error_msg}", "ERROR")
        self.status_label.setText("控制错误")

    def on_control_connection_changed(self, connected):
        """连接状态变化处理"""
        if connected:
            self.logger.log("控制连接已建立", "INFO")
        else:
            self.logger.log("控制连接已断开", "WARNING")

    def select_save_path(self):
        """自动生成唯一保存路径"""
        # self.save_path = self.generate_unique_filename()
        # self.logger.log(f"自动生成保存路径: {self.save_path}")
        
        # 如果需要用户确认，可以改用：
        suggested_path = self.generate_unique_filename()
        path, _ = QFileDialog.getSaveFileName(
            self, "保存视频", suggested_path, "MP4 Files (*.mp4)"
        )
        if path:
            self.save_path = path
            self.logger.log(f"用户选择保存路径: {self.save_path}")
        

    def generate_unique_filename(self):
        """生成绝对不会重复的文件名"""
        base_name = datetime.now().strftime("vid_%Y%m%d_%H_%M_%S_%f")[:-3]  # 精确到毫秒
        ext = ".mp4"
        filename = f"{base_name}{ext}"
        full_path = os.path.join(self.data_dir, 'vids',filename)
        
        # 极端情况处理：如果文件已存在（几乎不可能），追加序号
        counter = 1
        while os.path.exists(full_path):
            filename = f"{base_name}_{counter}{ext}"
            full_path = os.path.join(self.data_dir, 'vids',  filename)
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
            self.speed_thread.stop() # 停止标定线程
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


    def start_speed_calibration(self):
        """处理“速度标定”按钮点击事件"""
        # 1. 检查状态
        if not self.video_thread or not self.video_thread.isRunning():
            QMessageBox.warning(self, "警告", "请先连接摄像头。")
            return
        if self.speed_thread and self.speed_thread.isRunning():
            # 可选：允许用户停止当前的标定
            reply = QMessageBox.question(self, '确认', '速度标定已在进行中，要停止吗？',
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.speed_thread.stop() # 停止旧的，等待 finished 信号清理
                self.cleanup_speed_calibration()
                self.btn_register_speed.setText("速度标定")
                self.btn_register_speed.setStyleSheet("background-color: #81C784; color: black;")
                self.logger.log("等待旧标定线程结束...", "DEBUG")
            else:
                return # 用户选择不重新开始

        # 2. 获取当前帧以确定ROI
        current_frame = self.get_latest_frame_for_speed_thread()
        if current_frame is None:
            QMessageBox.warning(self, "警告", "无法获取当前视频帧，请稍候再试。")
            return

        frame_h, frame_w = current_frame.shape[:2]
        if frame_w <= 0 or frame_h <= 0:
            QMessageBox.warning(self, "警告", "获取到的视频帧尺寸无效。")
            return

        # 3. 计算ROI 
        roi_h = frame_h // 5
        roi_y = (frame_h - roi_h) // 2
        roi_x = frame_w // 8
        roi_w = frame_w - roi_x * 2
        self.calculated_roi_rect = (roi_x, roi_y, roi_w, roi_h)

        # 4. 通知 CameraDisplay 绘制 ROI 和参考线
        self.video_display.set_roi(self.calculated_roi_rect)

        # 5. 准备并启动 SpeedCalculationThread
        try:
            self.speed_thread = SpeedCalculationThread(
                frame_source_callable=self.get_latest_frame_for_speed_thread,
                roi_rect=self.calculated_roi_rect,
                save_path=self.speed_debug_dir, # 传递调试图像保存路径
                time_limit=self.speed_time_limit, # 传递时间限制
            )

            # --- 连接信号 ---
            self.speed_thread.calculation_complete.connect(self.on_speed_calculation_complete)
            self.speed_thread.calculation_error.connect(self.on_speed_calculation_error)
            self.speed_thread.status_update.connect(self.on_speed_status_update)

            # --- 启动线程 ---
            self.speed_thread.start()
            self.logger.log("速度标定线程已启动...", "INFO")
            self.status_label.setText("速度标定进行中...")
            self.btn_register_speed.setText("停止标定") # 可选：改变按钮文本
            self.btn_register_speed.setStyleSheet("background-color: #FF5722; color: black;")

        except Exception as e:
            error_msg = f"启动速度标定失败: {e}"
            self.logger.log(error_msg, "ERROR")
            QMessageBox.critical(self, "错误", error_msg)
            self.cleanup_speed_calibration() # 出错时清理

    # --- 新增：处理速度计算完成信号 ---
    @pyqtSlot(float)
    def on_speed_calculation_complete(self, speed):
        """处理来自速度线程的计算结果"""
        self.current_speed = speed
        self.update_speed_label()
        # 日志记录可以减少频率或使用 DEBUG 级别
        if self.logger: self.logger.log(f"速度更新: {speed:.3f} m/s", "DEBUG")
        self.cleanup_speed_calibration() 

    # --- 新增：处理速度计算错误信号 ---
    @pyqtSlot(str)
    def on_speed_calculation_error(self, error_message):
        """处理来自速度线程的错误"""
        if self.logger: self.logger.log(f"速度标定错误: {error_message}", "ERROR")
        self.status_label.setText(f"标定错误: {error_message}")
        QMessageBox.critical(self, "速度标定错误", error_message)
        self.cleanup_speed_calibration() # 出错时清理


    # --- 新增：处理速度线程状态更新信号 ---
    @pyqtSlot(str)
    def on_speed_status_update(self, status_message):
        """更新主状态标签以显示速度线程的状态"""
        self.status_label.setText(status_message)
        self.logger.log(f"速度标定状态更新: {status_message}", "DEBUG")

    # --- 新增：速度标定清理辅助函数 ---
    def cleanup_speed_calibration(self):
        """清理速度标定相关的状态和UI"""
        self.speed_thread = None # 清除线程引用
        if self.video_display:
            self.video_display.set_roi(None) # 停止绘制ROI
        self.calculated_roi_rect = None # 清除ROI记录
        self.btn_register_speed.setText("速度标定") # 恢复按钮文本
        self.btn_register_speed.setStyleSheet("background-color: #81C784; color: black;")
        self.status_label.setText("已停止速度标定") 

    # --- 需要添加更新速度标签的方法 ---
    def update_speed_label(self):
        """更新显示速度的标签文本"""
        self.label_current_speed.setText(f"当前速度: {self.current_speed:.2f} m/s")

    # --- 获取帧的方法，供速度线程调用 ---
    def get_latest_frame_for_speed_thread(self):
        """返回当前显示的最新原始帧"""
        if self.video_display:
            return self.video_display.get_current_frame()
        return None


    # 初始化模型选择下拉框
    def update_model_selector(self):
        """初始化模型选择下拉框"""
        # 清空下拉框
        self.model_selector.clear()
        self.model_selector.addItem("待选择...")  # 默认选项

        # 加载 models.json 文件
        try:
            with open("./models.json", "r") as f:
                self.models = json.load(f)
        except FileNotFoundError:
            print("models.json 文件未找到")
            return
        except json.JSONDecodeError:
            print("models.json 文件格式错误")
            return

        # 将模型名称添加到下拉框中
        for model_name in self.models.keys():
            self.model_selector.addItem(model_name)

    # 处理下拉框选择模型路径的函数
    def switch_model(self, model_name):
        """切换选中的模型:param model_name: 模型名称"""
        self.logger.log(f"已选择模型: {model_name}")


    # 处理检测按键的线程函数
    def start_detection(self):
        """处理“检测”按钮点击事件"""
        # 1. 检查状态
        if not self.video_thread or not self.video_thread.isRunning():
            QMessageBox.warning(self, "警告", "请先连接摄像头。")
            return    
        if self.detection_thread and self.detection_thread.isRunning():
            # 可选：允许用户停止当前的检测
            reply = QMessageBox.question(self, '确认', '检测已在进行中，要停止吗？',
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.detection_thread.stop() # 停止旧的，等待 finished 信号清理
                self.cleanup_detection()
                self.logger.log("等待旧检测线程结束...", "DEBUG")
            else:
                return # 用户选择不重新开始
            
        # 2. 获取当前帧以确定ROI
        current_frame = self.get_latest_frame_for_speed_thread()
        if current_frame is None:
            QMessageBox.warning(self, "警告", "无法获取当前视频帧，请稍候再试。")
            return

        frame_h, frame_w = current_frame.shape[:2]
        if frame_w <= 0 or frame_h <= 0:
            QMessageBox.warning(self, "警告", "获取到的视频帧尺寸无效。")
            return

        # 3. 计算ROI 
        roi_h = frame_h // 8
        roi_y = frame_h - roi_h
        roi_x = frame_w // 8
        roi_w = frame_w - roi_x * 2
        self.calculated_roi_rect = (roi_x, roi_y+10, roi_w, roi_h-10)

        # 4. 通知 CameraDisplay 绘制 ROI 和参考线
        self.video_display.set_roi(self.calculated_roi_rect)

        # 5. 准备并启动 DetectionThread
        try:
            self.detection_thread = DetectionThread(frame_source_callable=self.get_latest_frame_for_speed_thread, roi=self.calculated_roi_rect,
                                                     model_path=self.models[self.model_selector.currentText()], save_path=self.detection_result_dir)

            # --- 连接信号 ---
            self.detection_thread.detection_result.connect(self.on_detection_complete)
            self.detection_thread.error_occurred.connect(self.on_detection_error)
            self.detection_thread.status_updated.connect(self.on_detection_status_update)

            # --- 启动线程 ---
            self.detection_thread.start()
            self.logger.log("检测线程已启动...", "INFO")
            self.status_label.setText("检测进行中...")
            self.btn_detection.setText("停止检测") # 可选：改变按钮文本
            self.btn_detection.setStyleSheet("background-color: #FF5722; color: black;")
            self.detection_label.setStyleSheet("background-color: #FF5722; border-radius: 10px;")

        except Exception as e:
            error_msg = f"启动检测失败: {e}"
            self.logger.log(error_msg, "ERROR")
            self.cleanup_detection()

    # --- 新增：处理检测完成信号 ---
    @pyqtSlot(int, bool)
    def on_detection_complete(self, id, seed_tf):
        """处理来自检测线程的检测结果"""
        self.logger.log(f"检测结果: {id, seed_tf}", "DEBUG")
        if seed_tf and  self.control_thread and self.control_thread.is_connected:
            self.control_thread.time_control(str(3))
        else:
            self.logger.log("检测线程反馈_绑定端口失败", "ERROR")
        self.cleanup_detection()

    # --- 新增：处理检测错误信号 ---
    @pyqtSlot(str)
    def on_detection_error(self, error_message):
        """处理来自检测线程的错误"""
        if self.logger: self.logger.log(f"检测错误: {error_message}", "ERROR")
        self.status_label.setText(f"检测错误: {error_message}")
        self.cleanup_detection()

    # --- 新增：处理检测线程状态更新信号 ---
    @pyqtSlot(str)
    def on_detection_status_update(self, status_message):
        """更新主状态标签以显示检测线程的状态"""
        self.status_label.setText(status_message)
        self.logger.log(f"检测状态更新: {status_message}", "DEBUG")
        if status_message == "检测线程停止":
            self.cleanup_detection()

    # --- 新增：检测线程清理辅助函数 ---
    def cleanup_detection(self):
        """清理检测相关的状态和UI"""
        self.detection_thread = None # 清除线程引用
        if self.video_display:
            self.video_display.set_roi(None) # 停止绘制ROI
        self.calculated_roi_rect = None # 清除ROI记录
        self.btn_detection.setText("开始检测") # 恢复按钮文本
        self.btn_detection.setStyleSheet("background-color: #81C784; color: black;")
        self.status_label.setText("已停止检测") 
        self.detection_label.setStyleSheet("background-color: #81C784; border-radius: 10px;")


    def on_close(self, event):
        """窗口关闭事件处理"""
        if self.speed_thread and self.speed_thread.isRunning():
            self.speed_thread.stop() # 停止标定线程
            self.logger.log("关闭窗口：正在停止速度标定线程...")
        
        if self.video_thread and self.video_thread.isRunning():
            self.disconnect_camera()
            self.logger.log("关闭窗口：正在断开摄像头连接...")
        event.accept()
