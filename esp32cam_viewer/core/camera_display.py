"""
摄像头视频显示组件 (CameraDisplay)

功能概述：
1. 双状态显示：已连接时显示实时视频流，未连接时显示美观的占位界面
2. 自适应布局：自动适应父容器尺寸变化
3. 性能优化：马赛克背景缓存机制减少CPU开销
4. 视觉增强：专业的文字渲染效果（带阴影）

典型使用场景：
- 网络摄像头监控系统
- 安防监控平台

类继承关系：
QLabel -> CameraDisplay
"""
from PyQt5.QtWidgets import QLabel, QSizePolicy
from PyQt5.QtGui import QPixmap, QPainter, QImage, QFont, QColor, QFontMetrics
from PyQt5.QtCore import Qt
import numpy as np

# 仅测试导入
import cv2

class CameraDisplay(QLabel):
    """
    增强型视频显示组件
    
    :param parent: 父组件对象 (可选)
    :type parent: QWidget
    
    属性说明：
    _connected: 当前连接状态 (bool)
    _mosaic_cache: 缓存的马赛克背景 (QImage)
    """
    def __init__(self, parent=None):
        """
        初始化视频显示组件
        
        参数说明：
        parent -- 父级组件 (默认None)
        """
        super().__init__(parent)
        # 基础设置
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(640, 480)  # 最小显示尺寸
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        # 状态变量初始化
        self._connected = False
        self._mosaic_cache = None
        
        # 初始显示状态
        self.update_display()

    def set_connected(self, connected):
        """
        设置连接状态
        
        参数说明：
        connected -- 是否连接成功 (bool)
                     True: 显示视频流
                     False: 显示未连接提示
        
        典型调用：
        >>> display.set_connected(True)  # 连接成功时调用
        >>> display.set_connected(False) # 断开连接时调用
        """
        if self._connected != connected:
            self._connected = connected
            self.update_display()

    def update_display(self):
        """
        根据当前状态更新显示内容
        
        内部逻辑：
        - 未连接时：显示马赛克背景+提示文字
        - 已连接时：清空显示等待视频帧
        """
        if not self._connected:
            self.show_disconnected_state()
        else:
            self.clear()  # 使用QLabel的clear方法

    def show_disconnected_state(self):
        """
        显示未连接状态UI
        
        实现细节：
        1. 生成/获取缓存的马赛克背景
        2. 在背景上绘制状态文字
        3. 设置最终显示的Pixmap
        """
        # 背景生成（带尺寸变化检测）
        if (self._mosaic_cache is None or 
            self._mosaic_cache.size() != self.size()):
            self._mosaic_cache = self.create_mosaic_background()
        
        # 创建带文字的Pixmap
        pixmap = QPixmap(self._mosaic_cache)
        painter = QPainter(pixmap)
        try:
            self.draw_connection_text(painter, pixmap.size())
        finally:
            painter.end()
        
        self.setPixmap(pixmap)

    def create_mosaic_background(self):
        """
        创建马赛克纹理背景
        
        返回说明：
        QImage -- 生成的背景图像
        
        算法说明：
        - 使用numpy创建三维数组模拟RGB图像
        - 20x20像素为基本马赛克块
        - 每个块随机生成灰度值(50-100)
        """
        size = self.size()
        block_size = 20
        img = np.zeros((size.height(), size.width(), 3), dtype=np.uint8)
        
        # 生成马赛克图案
        for y in range(0, size.height(), block_size):
            for x in range(0, size.width(), block_size):
                color = np.random.randint(50, 100, 3)  # 随机灰度
                img[y:y+block_size, x:x+block_size] = color
                
        # 转换为QImage (注意内存共享)
        height, width, _ = img.shape
        return QImage(img.data, width, height, 
                     width * 3, QImage.Format_RGB888).copy()  # 必须copy保证数据独立

    def draw_connection_text(self, painter, size):
        """
        绘制连接状态文字
        
        参数说明：
        painter -- QPainter对象
        size    -- 绘制区域大小 (QSize)
        
        视觉效果：
        - 微软雅黑24pt加粗字体
        - 白色文字+黑色阴影
        - 完全居中显示
        """
        font = QFont("Microsoft YaHei", 24, QFont.Bold)
        painter.setFont(font)
        text = "摄像头未连接"
        
        # 计算文字位置（精确居中）
        metrics = QFontMetrics(font)
        text_rect = metrics.boundingRect(text)
        x = (size.width() - text_rect.width()) // 2
        y = (size.height() - text_rect.height()) // 2
        
        # 绘制阴影（偏移2像素）
        painter.setPen(QColor(0, 0, 0, 150))  # 半透明黑色
        painter.drawText(x+2, y+2, text)
        
        # 绘制主文字
        painter.setPen(QColor(255, 255, 255))  # 纯白色
        painter.drawText(x, y, text)

    def update_frame(self, frame):
        """
        更新视频帧显示
        
        参数说明：
        frame -- 视频帧数据 (numpy.ndarray)
                要求格式：RGB三通道，形状(h,w,3)
        
        注意事项：
        - 仅当connected=True时有效
        - 自动保持宽高比缩放
        - 使用高质量平滑缩放
        """
        if self._connected and frame is not None:
            h, w, ch = frame.shape
            # 创建QImage（不复制数据）
            q_img = QImage(frame.data, w, h, 
                          w * ch, QImage.Format_RGB888)
            
            # 缩放并显示（保持宽高比）
            self.setPixmap(
                QPixmap.fromImage(q_img).scaled(
                    self.size(),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation  # 高质量缩放
                )
            )


# 使用示例
# if __name__ == "__main__":
#     from PyQt5.QtWidgets import QApplication, QVBoxLayout, QWidget, QPushButton
#     import sys
#     import numpy as np
    
#     def create_test_frame():
#         """生成测试视频帧"""
#         img = np.zeros((480, 640, 3), dtype=np.uint8)
#         cv2.putText(img, "模拟视频流", (50, 240), 
#                    cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 255, 0), 3)
#         return img
    
#     app = QApplication(sys.argv)
    
#     # 创建测试窗口
#     window = QWidget()
#     layout = QVBoxLayout(window)
    
#     # 创建显示组件
#     display = CameraDisplay()
#     layout.addWidget(display)
    
#     # 添加测试按钮
#     btn_connect = QPushButton("模拟连接")
#     btn_disconnect = QPushButton("模拟断开")
#     btn_update = QPushButton("更新帧")
    
#     def on_connect():
#         display.set_connected(True)
#         display.update_frame(create_test_frame())
    
#     btn_connect.clicked.connect(on_connect)
#     btn_disconnect.clicked.connect(lambda: display.set_connected(False))
#     btn_update.clicked.connect(lambda: display.update_frame(create_test_frame()))
    
#     layout.addWidget(btn_connect)
#     layout.addWidget(btn_disconnect)
#     layout.addWidget(btn_update)
    
#     window.show()
#     sys.exit(app.exec_())
