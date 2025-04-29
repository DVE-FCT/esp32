import json
import os

class CameraManager:
    """
    摄像头配置管理器
    
    功能：
    1. 管理多个摄像头配置（IP/端口）
    2. 将配置持久化到JSON文件
    3. 提供增删改查接口
    
    属性：
    cameras (dict): 存储所有摄像头配置，格式为 {name: {ip: str, port: str}}
    config_file (str): 配置文件路径
    
    使用示例：
    >>> manager = CameraManager()
    >>> manager.add_camera("客厅摄像头", "192.168.1.100", "8080")
    >>> manager.get_camera_list()
    ['客厅摄像头']
    """
    def __init__(self, config_file="cameras.json"):
        """
        初始化摄像头管理器
        
        参数：
        config_file (str): 配置文件路径，默认为当前目录的cameras.json
        """
        self.cameras = {}  # 摄像头配置字典
        self.config_file = config_file  # 配置文件路径
        self.load_cameras()  # 加载已有配置

    def load_cameras(self):
        """
        从配置文件加载摄像头配置
        
        说明：
        - 如果配置文件不存在，保持空配置
        - 文件格式应为UTF-8编码的JSON
        """
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    self.cameras = json.load(f)
            except json.JSONDecodeError:
                # 处理损坏的配置文件
                self.cameras = {}
                raise ValueError("配置文件格式错误，已重置为空配置")

    def save_cameras(self):
        """
        保存当前配置到文件
        
        说明：
        - 自动创建不存在的目录（如果是带路径的文件名）
        - 如果只是纯文件名，则保存到当前目录
        - 使用美观的格式化输出（indent=4）
        """
        # 获取目录路径（如果是纯文件名则返回None）
        dir_path = os.path.dirname(self.config_file)
        
        # 只有当路径包含目录时才创建
        if dir_path:  # 非空字符串时才创建目录
            os.makedirs(dir_path, exist_ok=True)
        
        # 保存文件
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(self.cameras, f, indent=4, ensure_ascii=False)


    def add_camera(self, name, ip, port):
        """
        添加新摄像头配置
        
        参数：
        name (str): 摄像头名称（唯一标识）
        ip (str): IP地址
        port (str/int): 端口号
        
        异常：
        ValueError: 当必要参数为空时抛出
        """
        if not all([name, ip, port]):
            raise ValueError("名称、IP和端口都不能为空")
            
        self.cameras[name] = {
            "ip": str(ip).strip(),
            "port": str(port).strip()
        }
        self.save_cameras()

    def remove_camera(self, name):
        """
        移除指定摄像头配置
        
        参数：
        name (str): 要移除的摄像头名称
        
        说明：
        - 如果名称不存在，静默忽略
        """
        if name in self.cameras:
            del self.cameras[name]
            self.save_cameras()

    def get_camera_list(self):
        """
        获取所有摄像头名称列表
        
        返回：
        list: 摄像头名称列表，按添加顺序排列
        """
        return list(self.cameras.keys())

    def get_camera_info(self, name):
        """
        获取指定摄像头的详细信息
        
        参数：
        name (str): 摄像头名称
        
        返回：
        dict/None: 包含ip和port的字典，如果不存在返回None
        """
        return self.cameras.get(name, None)

    def update_camera(self, name, new_name=None, ip=None, port=None):
        """
        更新摄像头配置
        
        参数：
        name (str): 原摄像头名称
        new_name (str): 新名称（可选）
        ip (str): 新IP地址（可选）
        port (str): 新端口号（可选）
        
        返回：
        bool: 是否更新成功
        """
        if name not in self.cameras:
            return False
            
        cam = self.cameras[name]
        if new_name and new_name != name:
            self.cameras[new_name] = self.cameras.pop(name)
            name = new_name
            
        if ip:
            self.cameras[name]["ip"] = str(ip).strip()
        if port:
            self.cameras[name]["port"] = str(port).strip()
            
        self.save_cameras()
        return True
