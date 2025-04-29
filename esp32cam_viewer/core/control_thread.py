import socket
from PyQt5.QtCore import QThread, pyqtSignal

class ControlThread(QThread):
    """
    ESP32-CAM控制线程(简化版)
    实现通过单个字符指令进行控制：L - 开灯, l - 关灯, P - 拍照
    """
    command_sent = pyqtSignal(str, bool)   # 指令发送完成信号
    connection_error = pyqtSignal(str)     # 连接错误信号
    connection_status = pyqtSignal(bool)   # 连接状态信号
    light_state_changed = pyqtSignal(bool) # 灯光状态变化信号

    def __init__(self, camera_config):
        super().__init__()
        self.camera_config = camera_config
        self._connected = False
        self._socket = None
        self._light_on = False

    def run(self):
        """线程主循环, 定期检查并处理指令队列"""
        pass  # 没有队列管理，直接按需发送指令

    def _establish_connection(self):
        """建立TCP连接"""
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.settimeout(5)
            self._socket.connect((self.ip_address, self.control_port))
            self._connected = True
            print ("\n---------------------------------------------------------------")
            print(f"控制端口连接成功: {self.ip_address}:{self.control_port}")
            print ("---------------------------------------------------------------\n")
            self.connection_status.emit(True)
            return True
        except Exception as e:
            self._cleanup_socket()
            self.connection_error.emit(f"连接失败: {str(e)}")
            return False

    def _process_command(self, command_char):
        """处理单个字符指令"""
        if not self._connected and not self._establish_connection():
            self.command_sent.emit(command_char, False)
            return

        try:
            self._socket.sendall(command_char.encode('ascii'))
            response = self._socket.recv(1)
            
            # 验证响应是否正常
            success = (response == b'\x31')  # 检查响应是否为ASCII '1'的二进制
            
            # 处理灯光状态变化
            if command_char == 'L':  # 开灯
                self._light_on = True
                self.light_state_changed.emit(True)
            elif command_char == 'l':  # 关灯
                self._light_on = False
                self.light_state_changed.emit(False)

            self.command_sent.emit(command_char, success)
            
        except Exception as e:
            self._cleanup_socket()
            error_msg = f"{command_char}指令错误: {str(e)}"
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
            self.connection_status.emit(False)

    def send_command(self, command_char):
        """直接发送单个字符指令"""
        if command_char not in ('L', 'l', 'P'):
            self.connection_error.emit("无效指令")
            return False
        
        self._process_command(command_char)
        return True

    def turn_light_on(self):
        """开灯"""
        return self.send_command('L')

    def turn_light_off(self):
        """关灯"""
        return self.send_command('l')

    def capture_photo(self):
        """拍照"""
        return self.send_command('P')

    def stop(self):
        """安全停止线程"""
        self._cleanup_socket()

    @property
    def control_port(self):
        return int(self.camera_config.get("port", 80)) + 1  # 控制端口为原端口+1

    @property
    def ip_address(self):
        return self.camera_config.get("ip", "")

    @property
    def is_light_on(self):
        return self._light_on

    @property
    def is_connected(self):
        return self._connected
