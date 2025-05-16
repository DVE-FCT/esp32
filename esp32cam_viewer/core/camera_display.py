# (假设文件名是 ui/camera_display.py 或类似)

from PyQt5.QtWidgets import QLabel, QSizePolicy
from PyQt5.QtGui import QPixmap, QPainter, QImage, QFont, QColor, QPen, QFontMetrics
from PyQt5.QtCore import Qt, QSize, QRect
import numpy as np
import cv2 # 需要导入 cv2 用于颜色转换

class CameraDisplay(QLabel):
    """
    增强型视频显示组件，支持显示视频帧、未连接状态，并能绘制ROI和参考线。

    :param parent: 父组件对象 (可选)
    :type parent: QWidget

    属性说明：
    _connected: 当前连接状态 (bool)
    _mosaic_cache: 缓存的马赛克背景 (QImage)
    current_frame: 当前存储的原始视频帧 (np.ndarray, BGR格式)
    current_pixmap: 当前用于显示的缩放后的QPixmap
    roi_rect: 当前设置的ROI区域 (x, y, w, h) 或 None，坐标基于原始帧
    """
    def __init__(self, parent=None):
        """
        初始化视频显示组件
        """
        super().__init__(parent)
        # 基础设置
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(640, 480)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # 状态变量初始化
        self._connected = False
        self._mosaic_cache = None
        self.current_frame = None     # 存储原始 BGR 帧
        self.current_pixmap = None    # 存储准备显示的 QPixmap
        self.roi_rect = None          # 存储 ROI 矩形 (x, y, w, h)

        # 不再需要 self.update_display()，paintEvent 会处理初始状态
        self.update() # 触发初始绘制

    def set_connected(self, connected):
        """
        设置连接状态，并触发界面更新。
        """
        if self._connected != connected:
            self._connected = connected
            if not connected:
                # 断开连接时，清除帧和pixmap信息
                self.current_frame = None
                self.current_pixmap = None
                self.roi_rect = None # 也清除ROI
            # else: 连接成功时不需要立即做什么，等待 update_frame 或 paintEvent
            self.update() # 请求重新绘制

    def update_frame(self, frame: np.ndarray):
        """
        更新视频帧显示。接收 RGB 格式的 numpy 数组。
        """
        # 存储原始 RGB 帧
        self.current_frame = frame

        if self._connected and self.current_frame is not None:
            try:
                h, w, ch = self.current_frame.shape
                if ch == 3: # 确保是彩色图像
                    bytes_per_line = 3 * w
                    qt_image = QImage(frame.data, w, h, bytes_per_line, QImage.Format_RGB888)

                    # 将 QImage 转换为 QPixmap 并缩放以适应 QLabel 的当前大小，保持纵横比
                    # 将缩放后的结果存储在 self.current_pixmap 中，供 paintEvent 使用
                    self.current_pixmap = QPixmap.fromImage(qt_image).scaled(
                        self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
                    )
                else: # 如果不是3通道图像，则清空 pixmap
                    self.current_pixmap = None

            except Exception as e:
                print(f"[CameraDisplay] 转换帧时出错: {e}")
                self.current_pixmap = None # 出错时清除

            # 请求重新绘制控件，让 paintEvent 来显示图像和可能的叠加层
            self.update()
        # 如果未连接或帧为空，则不处理，paintEvent 会绘制相应状态

    # +++ 新增方法 +++
    def get_current_frame(self):
        """返回当前存储的原始 OpenCV 视频帧 (BGR格式)。"""
        return self.current_frame

    # +++ 新增方法 +++
    def set_roi(self, roi_rect: tuple):
        """
        设置要在视频帧上绘制的ROI矩形区域。
        :param roi_rect: 元组 (x, y, w, h) 或 None (不绘制)。坐标是相对于原始帧尺寸的。
        """
        if self.roi_rect != roi_rect:
            self.roi_rect = roi_rect
            self.update() # 请求重新绘制以显示或隐藏ROI

    # --- 需要重写 paintEvent ---
    def paintEvent(self, event):
        """
        重写绘制事件，用于绘制背景、视频帧、水平ROI边界和水平参考线。
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing) # 抗锯齿

        # 绘制背景（无论连接与否，提供一个基础）
        painter.fillRect(self.rect(), QColor(30, 30, 30)) # 深灰色背景

        if not self._connected:
            # --- 绘制未连接状态 ---
            if self._mosaic_cache is None or self._mosaic_cache.size() != self.size():
                 if self.size().width() > 0 and self.size().height() > 0:
                     self._mosaic_cache = self.create_mosaic_background()
                 else:
                     self._mosaic_cache = None

            if self._mosaic_cache:
                 painter.drawImage(0, 0, self._mosaic_cache)

            self.draw_connection_text(painter, self.size())

        else:
            # --- 绘制已连接状态 ---
            if self.current_pixmap:
                # 计算绘制Pixmap的位置，使其在QLabel中居中显示
                px = (self.width() - self.current_pixmap.width()) // 2
                py = (self.height() - self.current_pixmap.height()) // 2
                painter.drawPixmap(px, py, self.current_pixmap)

                # --- 如果设置了ROI，则绘制水平ROI边界和水平参考线 ---
                if self.roi_rect and self.current_frame is not None:
                    frame_h, frame_w = self.current_frame.shape[:2]
                    if frame_w > 0 and frame_h > 0:
                        # 计算缩放比例
                        scale_w = self.current_pixmap.width() / frame_w
                        scale_h = self.current_pixmap.height() / frame_h

                        # 计算缩放和平移后的ROI坐标 (基于原始帧ROI)
                        scaled_roi_x = int(px + self.roi_rect[0] * scale_w)
                        scaled_roi_y = int(py + self.roi_rect[1] * scale_h)
                        scaled_roi_w = int(self.roi_rect[2] * scale_w)
                        scaled_roi_h = int(self.roi_rect[3] * scale_h)

                        # --- 修改：绘制ROI的两条水平边界线 (红色虚线) ---
                        pen_roi = QPen(QColor(255, 0, 0)) # 红色
                        pen_roi.setStyle(Qt.DashLine)     # 虚线
                        pen_roi.setWidth(2)               # 线宽
                        painter.setPen(pen_roi)
                        # Top boundary
                        painter.drawLine(scaled_roi_x, scaled_roi_y, scaled_roi_x + scaled_roi_w, scaled_roi_y)
                        # Bottom boundary
                        painter.drawLine(scaled_roi_x, scaled_roi_y + scaled_roi_h, scaled_roi_x + scaled_roi_w, scaled_roi_y + scaled_roi_h)

                        # --- 修改：绘制中心水平参考线 (蓝色实线) ---
                        # 参考线在ROI内部的垂直中心，其 y 坐标相对于 ROI 顶部是 roi_h / 2
                        # 换算成相对于原始帧的 y 坐标是 roi_y + roi_h / 2
                        ref_line_orig_y = self.roi_rect[1] + self.roi_rect[3] // 2
                        # 将原始帧中的 y 坐标映射到显示的 pixmap 坐标
                        scaled_ref_line_y = int(py + ref_line_orig_y * scale_h)

                        pen_refline = QPen(QColor(0, 0, 255)) # 蓝色
                        pen_refline.setStyle(Qt.SolidLine)   # 实线
                        pen_refline.setWidth(1)             # 细线
                        painter.setPen(pen_refline)
                        # 从ROI左边界绘制到右边界 (使用 scaled_roi_x 和 scaled_roi_w)
                        painter.drawLine(scaled_roi_x, scaled_ref_line_y, scaled_roi_x + scaled_roi_w, scaled_ref_line_y)
            else:
                # 如果已连接但还没有帧数据，可以显示 "加载中..."
                font = QFont("Microsoft YaHei", 18)
                painter.setFont(font)
                painter.setPen(QColor(200, 200, 200)) # 浅灰色
                painter.drawText(self.rect(), Qt.AlignCenter, "视频加载中...")

    # --- 以下方法保持不变 ---
    def create_mosaic_background(self):
        """创建马赛克纹理背景"""
        size = self.size()
        block_size = 20
        # 使用 uint8 确保与 QImage 兼容
        img = np.zeros((size.height(), size.width(), 3), dtype=np.uint8)

        for y in range(0, size.height(), block_size):
            for x in range(0, size.width(), block_size):
                # 生成稍暗的灰色，避免太亮
                gray_val = np.random.randint(40, 80)
                color = (gray_val, gray_val, gray_val)
                img[y:y+block_size, x:x+block_size] = color

        height, width, channel = img.shape
        # BGR -> RGB (虽然这里是灰度，但保持通道顺序一致性)
        # QImage 需要 RGB 格式
        # img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB) # 对于灰度其实BGR/RGB一样，但明确指定格式更好
        # return QImage(img_rgb.data, width, height, width * 3, QImage.Format_RGB888).copy()
        # 或者直接使用 Format_RGB888 因为我们的numpy数组就是 H x W x 3 (RGB顺序)
        return QImage(img.data, width, height, width * 3, QImage.Format_RGB888).copy()


    def draw_connection_text(self, painter, size):
        """绘制连接状态文字"""
        font = QFont("Microsoft YaHei", 24, QFont.Bold)
        painter.setFont(font)
        text = "摄像头未连接"

        metrics = QFontMetrics(font)
        # 使用 boundingRect 获取更准确的尺寸
        text_rect = metrics.boundingRect(QRect(0, 0, size.width(), size.height()), Qt.AlignCenter, text) # type: ignore
        # x = (size.width() - text_rect.width()) // 2
        # y = (size.height() + metrics.ascent() - metrics.descent()) // 2 # 更精确的垂直居中
        # 或者直接使用 QRect 来绘制居中文本
        text_rect_centered = QRect(0, 0, size.width(), size.height()) # type: ignore


        # 绘制阴影
        painter.setPen(QColor(0, 0, 0, 150))
        # painter.drawText(x + 2, y + 2, text)
        painter.drawText(text_rect_centered.translated(2, 2), Qt.AlignCenter, text) # 绘制阴影

        # 绘制主文字
        painter.setPen(QColor(255, 255, 255))
        # painter.drawText(x, y, text)
        painter.drawText(text_rect_centered, Qt.AlignCenter, text) # 绘制文字


    # --- 移除不再需要的方法 ---
    # def update_display(self): ...
    # def show_disconnected_state(self): ...

