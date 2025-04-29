import sys
import socket
import threading
from PyQt5.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, 
                            QWidget, QPushButton, QLabel, QTextEdit, QHBoxLayout)
from PyQt5.QtCore import Qt, pyqtSignal, QThread, QTimer
from PyQt5.QtGui import QColor, QPalette

class ControlThread(QThread):
    """
    ESP32-CAM控制线程(长连接实现)
    支持连接/断开管理和自动重连
    """
    command_sent = pyqtSignal(str, bool)
    connection_error = pyqtSignal(str)
    connection_changed = pyqtSignal(bool)  # 连接状态变化信号
    
    def __init__(self, camera_config):
        super().__init__()
        self.camera_config = camera_config
        self._mutex = threading.Lock()
        self._command_queue = []
        self._active = True
        self._connected = False
        self._socket = None
        self.light_state = False
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 3

    def run(self):
        """主线程循环"""
        while self._active:
            if self._command_queue:
                cmd = self._command_queue.pop(0)
                self._process_command(cmd)
            else:
                self.msleep(50)

    def connect_camera(self):
        """主动连接摄像头"""
        with self._mutex:
            if not self._connected:
                return self._establish_connection()
        return True

    def disconnect_camera(self):
        """主动断开连接"""
        with self._mutex:
            self._cleanup_socket()
        return True

    def _establish_connection(self):
        """建立TCP连接"""
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.settimeout(5)
            self._socket.connect((self.ip_address, self.control_port))
            self._connected = True
            self.reconnect_attempts = 0
            self.connection_changed.emit(True)
            return True
        except Exception as e:
            self._cleanup_socket()
            self.connection_error.emit(f"连接失败: {str(e)}")
            return False

    def _process_command(self, command_char):
        """处理指令"""
        if not self._connected and not self._establish_connection():
            self.command_sent.emit(command_char, False)
            return

        try:
            self._socket.sendall(command_char.encode('ascii'))
            response = self._socket.recv(1).decode('ascii')
            success = (response == '1')
            
            if command_char in ('L', 'l'):
                self.light_state = (command_char == 'L')
            
            self.command_sent.emit(command_char, success)
        except Exception as e:
            self._cleanup_socket()
            error_msg = f"指令{command_char}错误: {str(e)}"
            self.connection_error.emit(error_msg)
            self.command_sent.emit(command_char, False)

    def _cleanup_socket(self):
        """清理socket资源"""
        if self._socket:
            try:
                self._socket.close()
            except:
                pass
        self._socket = None
        if self._connected:
            self._connected = False
            self.connection_changed.emit(False)

    def send_command(self, command_char):
        """线程安全的指令发送"""
        if not self._active:
            return False

        command_char = str(command_char).strip()
        if len(command_char) != 1:
            self.connection_error.emit("指令必须为单字符")
            return False

        with self._mutex:
            self._command_queue.append(command_char)
        return True

    def stop(self):
        """安全停止线程"""
        self._active = False
        self._cleanup_socket()
        self.wait()

    @property
    def control_port(self):
        return self.camera_config.get("port", 80) + 1

    @property
    def ip_address(self):
        return self.camera_config.get("ip", "")

    def toggle_light(self):
        cmd = 'l' if self.light_state else 'L'
        return self.send_command(cmd)

    def capture_photo(self):
        return self.send_command('P')

class TestWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.camera_config = {
            "ip": "192.168.1.105",
            "port": 80
        }
        self.setup_ui()
        self.setup_control_thread()

    def setup_ui(self):
        self.setWindowTitle("ESP32-CAM控制器")
        self.setGeometry(300, 300, 450, 400)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        layout = QVBoxLayout()
        
        # 连接控制区域
        connection_box = QHBoxLayout()
        
        self.btn_connect = QPushButton("连接")
        self.btn_connect.setStyleSheet("background-color: #4CAF50; color: white;")
        self.btn_connect.clicked.connect(self.toggle_connection)
        connection_box.addWidget(self.btn_connect)
        
        self.connection_status = QLabel("未连接")
        self.connection_status.setAlignment(Qt.AlignCenter)
        palette = self.connection_status.palette()
        palette.setColor(QPalette.WindowText, QColor(255, 0, 0))
        self.connection_status.setPalette(palette)
        connection_box.addWidget(self.connection_status)
        
        layout.addLayout(connection_box)
        
        # 控制按钮区域
        control_box = QHBoxLayout()
        
        self.btn_light = QPushButton("开灯")
        self.btn_light.setEnabled(False)
        self.btn_light.clicked.connect(self.toggle_light)
        control_box.addWidget(self.btn_light)
        
        self.btn_capture = QPushButton("拍照")
        self.btn_capture.setEnabled(False)
        self.btn_capture.clicked.connect(self.capture_photo)
        control_box.addWidget(self.btn_capture)
        
        layout.addLayout(control_box)
        
        # 状态显示
        self.status_label = QLabel("准备就绪")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)
        
        # 日志显示
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        layout.addWidget(self.log_display)
        
        central_widget.setLayout(layout)

    def setup_control_thread(self):
        self.control_thread = ControlThread(self.camera_config)
        self.control_thread.command_sent.connect(self.on_command_result)
        self.control_thread.connection_error.connect(self.on_control_error)
        self.control_thread.connection_changed.connect(self.on_connection_changed)
        self.control_thread.start()
        
    def toggle_connection(self):
        """切换连接状态"""
        if self.btn_connect.text() == "连接":
            self.log("尝试连接摄像头...")
            self.btn_connect.setEnabled(False)
            self.status_label.setText("连接中...")
            QTimer.singleShot(100, lambda: self.control_thread.connect_camera())
        else:
            self.log("主动断开连接")
            self.control_thread.disconnect_camera()

    def on_connection_changed(self, connected):
        """处理连接状态变化"""
        if connected:
            self.btn_connect.setText("断开")
            self.btn_connect.setStyleSheet("background-color: #f44336; color: white;")
            self.connection_status.setText("已连接")
            self.connection_status.setStyleSheet("color: green;")
            self.btn_light.setEnabled(True)
            self.btn_capture.setEnabled(True)
            self.log("控制连接已建立")
            self.status_label.setText("连接成功")
        else:
            self.btn_connect.setText("连接")
            self.btn_connect.setStyleSheet("background-color: #4CAF50; color: white;")
            self.connection_status.setText("未连接")
            self.connection_status.setStyleSheet("color: red;")
            self.btn_light.setEnabled(False)
            self.btn_capture.setEnabled(False)
            self.status_label.setText("已断开")
        self.btn_connect.setEnabled(True)

    def toggle_light(self):
        if self.control_thread.toggle_light():
            new_text = "关灯" if self.btn_light.text() == "开灯" else "开灯"
            self.btn_light.setText(new_text)

    def capture_photo(self):
        if self.control_thread.capture_photo():
            self.status_label.setText("拍照指令已发送")
            QTimer.singleShot(2000, lambda: self.status_label.setText("准备就绪"))

    def on_command_result(self, cmd, success):
        status = "成功" if success else "失败"
        self.log(f"指令 {cmd} 执行{status}")
        if cmd == 'P' and success:
            self.status_label.setText("拍照完成")

    def on_control_error(self, error_msg):
        self.log(error_msg, "ERROR")
        self.status_label.setText("通信错误")

    def log(self, message, level="INFO"):
        """日志记录"""
        self.log_display.append(f"[{level}] {message}")
        # 自动滚动到底部
        cursor = self.log_display.textCursor()
        cursor.movePosition(cursor.End)
        self.log_display.setTextCursor(cursor)

    def closeEvent(self, event):
        if hasattr(self, 'control_thread'):
            self.control_thread.stop()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = TestWindow()
    window.show()
    sys.exit(app.exec_())
