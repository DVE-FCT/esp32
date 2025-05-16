# 导入必要的库
import sys  # 系统相关，用于退出程序
import cv2  # OpenCV库，用于图像处理
import numpy as np  # NumPy库，用于高效处理数组（图像）
from PyQt5.QtWidgets import (  # PyQt5 GUI组件
    QApplication, QWidget, QLabel, QPushButton, QSlider, QFileDialog,
    QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox
)
from PyQt5.QtGui import QImage, QPixmap  # PyQt5图像处理相关
from PyQt5.QtCore import Qt, pyqtSignal, QTimer # PyQt5核心功能，如信号、定时器、对齐等

# --- 辅助函数：将OpenCV图像 (numpy array) 转换为 PyQt 可显示的 QPixmap ---
def convert_cv_qt(cv_img, width=None, height=None):
    """
    将OpenCV格式的图像转换为QPixmap。
    :param cv_img: 输入的OpenCV图像 (numpy.ndarray)。
    :param width: 期望的显示宽度（可选，会保持纵横比缩放）。
    :param height: 期望的显示高度（可选，会保持纵横比缩放）。
    :return: QPixmap 对象，如果输入无效则返回空 QPixmap。
    """
    if cv_img is None:
        return QPixmap() # 如果图像为空，返回空Pixmap

    # 检查图像维度并进行颜色空间转换
    if len(cv_img.shape) == 3: # 彩色图像 (通常是 BGR)
        # OpenCV 默认 BGR，Qt 需要 RGB
        rgb_image = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_image.shape  # 获取高度、宽度、通道数
        bytes_per_line = ch * w     # 每行的字节数
        # 创建 QImage 对象
        convert_to_Qt_format = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format_RGB888)
    elif len(cv_img.shape) == 2: # 灰度图像 (例如掩码)
        h, w = cv_img.shape         # 获取高度、宽度
        bytes_per_line = w          # 每行的字节数
        # 创建 QImage 对象 (灰度)
        convert_to_Qt_format = QImage(cv_img.data, w, h, bytes_per_line, QImage.Format_Grayscale8)
        # 注意：如果想显示应用掩码后的彩色结果，应先用cv2.bitwise_and处理，然后转换那个结果（它会是BGR格式）
    else:
        print("不支持的图像格式") # 控制台输出错误信息
        return QPixmap() # 不支持的格式，返回空Pixmap

    # 如果提供了目标尺寸，则进行缩放
    if width and height:
        # 按指定宽高缩放，保持纵横比，平滑变换
        p = convert_to_Qt_format.scaled(width, height, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    elif width:
        # 按指定宽度缩放，保持纵横比，平滑变换
         p = convert_to_Qt_format.scaledToWidth(width, Qt.SmoothTransformation)
    elif height:
        # 按指定高度缩放，保持纵横比，平滑变换
        p = convert_to_Qt_format.scaledToHeight(height, Qt.SmoothTransformation)
    else:
        # 不进行缩放
        p = convert_to_Qt_format

    # 从 QImage 创建 QPixmap 并返回
    return QPixmap.fromImage(p)

# --- 主应用窗口类 ---
class ImageProcessorApp(QWidget):
    # 定义一个自定义信号，用于在滑块值改变后稍作延迟触发更新
    updateNeeded = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.original_frame = None # 存储原始加载的 BGR 图像
        self.hsv_frame = None      # 存储转换后的 HSV 图像
        self.current_mask = None   # 存储当前计算出的 HSV 掩码 (黑白图)
        self.masked_result = None  # 存储应用掩码后的原始彩色图像区域
        self.is_hsv_mode = False   # 标记当前是否处于 HSV 处理模式
        self.display_width = 400   # 图像显示区域的最大宽度 (像素)

        # --- HSV 阈值默认值 ---
        # (这些值大致对应你之前代码计算得出的范围，注意OpenCV的H范围是0-179)
        self.h_min_val = 27
        self.h_max_val = 75  # 约 27.1 + 48.2 = 75.3
        self.s_min_val = 36  # 约 54.8 - 18.6 = 36.2
        self.s_max_val = 73  # 约 54.8 + 18.6 = 73.4
        self.v_min_val = 152 # 约 162.1 - 9.8 = 152.3
        self.v_max_val = 171 # 约 162.1 + 9.8 = 171.9

        # 初始化用户界面
        self.initUI()
        # 连接自定义信号到更新槽函数
        self.updateNeeded.connect(self.apply_hsv_filter_and_update_display)
        # 用于缓冲滑块更新的定时器
        self.update_timer = None

    # --- 初始化用户界面 ---
    def initUI(self):
        self.setWindowTitle('PyQt5 OpenCV 图像处理器') # 设置窗口标题
        self.setGeometry(100, 100, 900, 600) # 设置窗口位置和大小 (x, y, width, height)

        # --- 主布局 (垂直布局) ---
        main_layout = QVBoxLayout()

        # --- 顶部区域: 控制按钮 ---
        button_layout = QHBoxLayout() # 水平布局放按钮
        self.btn_load = QPushButton('加载图片') # 创建按钮
        self.btn_load.clicked.connect(self.load_image) # 连接点击信号到槽函数
        self.btn_hsv_mode = QPushButton('启用 HSV 模式') # 创建按钮
        self.btn_hsv_mode.setCheckable(True) # 设置为可切换状态的按钮
        self.btn_hsv_mode.toggled.connect(self.toggle_hsv_mode) # 连接状态切换信号到槽函数
        self.btn_hsv_mode.setEnabled(False) # 初始时禁用，直到加载图片
        self.btn_reset = QPushButton('复位') # 创建按钮
        self.btn_reset.clicked.connect(self.reset_all) # 连接点击信号到槽函数
        self.btn_reset.setEnabled(False) # 初始时禁用，直到加载图片

        # 将按钮添加到按钮布局中
        button_layout.addWidget(self.btn_load)
        button_layout.addWidget(self.btn_hsv_mode)
        button_layout.addWidget(self.btn_reset)
        button_layout.addStretch(1) # 添加伸缩因子，将按钮推到左侧
        main_layout.addLayout(button_layout) # 将按钮布局添加到主布局

        # --- 中部区域: 图像显示 ---
        image_layout = QHBoxLayout() # 水平布局放两个图像标签
        # 左侧：原始图像显示标签
        self.original_display_label = QLabel('请先加载一张图片') # 创建标签
        self.original_display_label.setAlignment(Qt.AlignCenter) # 文本居中
        self.original_display_label.setMinimumSize(200, 150) # 设置最小尺寸
        self.original_display_label.setStyleSheet("border: 1px solid gray;") # 添加灰色边框
        # 右侧：处理后图像显示标签
        self.processed_display_label = QLabel('处理后的图像将显示在此处') # 创建标签
        self.processed_display_label.setAlignment(Qt.AlignCenter) # 文本居中
        self.processed_display_label.setMinimumSize(200, 150) # 设置最小尺寸
        self.processed_display_label.setStyleSheet("border: 1px solid gray;") # 添加灰色边框

        # 将图像标签添加到图像布局中，设置伸缩因子为1，使其平分空间
        image_layout.addWidget(self.original_display_label, 1)
        image_layout.addWidget(self.processed_display_label, 1)
        main_layout.addLayout(image_layout, 1) # 将图像布局添加到主布局，设置伸缩因子为1

        # --- 底部区域: HSV 控制滑块 ---
        # 使用 QGroupBox 将 HSV 控制器组织起来
        self.hsv_groupbox = QGroupBox("HSV 阈值") # 创建分组框
        hsv_layout = QGridLayout() # 使用网格布局放置滑块和标签

        # 定义滑块参数 (显示名称, 最小值, 最大值, 初始值)
        # 注意：内部标识符仍用英文，方便代码处理
        slider_params = [
            ("H 最小", "H Min", 0, 179, self.h_min_val), ("H 最大", "H Max", 0, 179, self.h_max_val),
            ("S 最小", "S Min", 0, 255, self.s_min_val), ("S 最大", "S Max", 0, 255, self.s_max_val),
            ("V 最小", "V Min", 0, 255, self.v_min_val), ("V 最大", "V Max", 0, 255, self.v_max_val),
        ]

        self.sliders = {} # 字典存储滑块控件
        self.slider_labels = {} # 字典存储滑块对应的标签控件

        row = 0 # 网格布局的行计数器
        for display_name, internal_name, min_val, max_val, initial_val in slider_params:
            # 创建显示标签，包含初始值
            label = QLabel(f"{display_name}: {initial_val}")
            # 创建水平滑块
            slider = QSlider(Qt.Horizontal)
            slider.setRange(min_val, max_val) # 设置范围
            slider.setValue(initial_val) # 设置初始值
            slider.setObjectName(internal_name) # 设置对象名称，用于后续识别是哪个滑块
            # 连接滑块值变化信号到槽函数，使用 lambda 捕获当前滑块和标签对象
            slider.valueChanged.connect(lambda value, s=slider, l=label, dn=display_name: self.slider_value_changed(s, l, value, dn))

            # 存储滑块和标签
            self.sliders[internal_name] = slider
            self.slider_labels[internal_name] = label

            # 将标签和滑块添加到网格布局
            hsv_layout.addWidget(self.slider_labels[internal_name], row, 0) # 第 row 行，第 0 列
            hsv_layout.addWidget(self.sliders[internal_name], row, 1) # 第 row 行，第 1 列
            row += 1 # 移动到下一行

        self.hsv_groupbox.setLayout(hsv_layout) # 设置分组框的布局
        self.hsv_groupbox.setEnabled(False) # 初始时禁用 HSV 控制区域
        main_layout.addWidget(self.hsv_groupbox) # 将分组框添加到主布局

        # --- 设置窗口的主布局 ---
        self.setLayout(main_layout)

    # --- 加载图片文件 ---
    def load_image(self):
        options = QFileDialog.Options()
        # options |= QFileDialog.DontUseNativeDialog # 如果需要非原生对话框，取消注释
        # 打开文件选择对话框
        file_path, _ = QFileDialog.getOpenFileName(self, "选择图片文件", "",
                                                   "图片文件 (*.png *.xpm *.jpg *.bmp *.jpeg *.gif)", options=options)
        if file_path: # 如果用户选择了文件
            # 使用 OpenCV 读取图片 (BGR格式)
            self.original_frame = cv2.imread(file_path)
            if self.original_frame is not None: # 检查是否成功加载
                print(f"图片已加载: {file_path}, 尺寸: {self.original_frame.shape}") # 控制台输出中文信息
                # 将 BGR 图像转换为 HSV 图像，只转换一次，存储起来
                self.hsv_frame = cv2.cvtColor(self.original_frame, cv2.COLOR_BGR2HSV)
                self.reset_all() # 加载新图后，重置UI状态（但不清除图像）
                self.apply_hsv_filter_and_update_display() # 更新界面显示加载的图片
                # 启用 HSV 模式按钮和复位按钮
                self.btn_hsv_mode.setEnabled(True)
                self.btn_reset.setEnabled(True)
            else:
                # 加载失败
                print(f"加载图片错误: {file_path}") # 控制台输出中文错误信息
                self.original_display_label.setText("加载图片错误") # 在标签上显示错误
                self.original_frame = None
                self.hsv_frame = None
                # 禁用相关按钮
                self.btn_hsv_mode.setEnabled(False)
                self.btn_hsv_mode.setChecked(False) # 确保按钮状态也复位
                self.btn_reset.setEnabled(False)

    # --- 切换 HSV 模式 ---
    def toggle_hsv_mode(self, checked):
        """当 HSV 模式按钮状态改变时调用"""
        self.is_hsv_mode = checked # 更新模式标志
        self.hsv_groupbox.setEnabled(checked) # 启用/禁用 HSV 滑块组

        if checked: # 如果进入 HSV 模式
            self.btn_hsv_mode.setText("禁用 HSV 模式") # 更新按钮文本
            # 立即应用一次当前的 HSV 阈值进行处理
            self.apply_hsv_filter_and_update_display()
        else: # 如果退出 HSV 模式
            self.btn_hsv_mode.setText("启用 HSV 模式") # 更新按钮文本
            # 清除处理后的图像显示区域
            self.processed_display_label.clear()
            self.processed_display_label.setText('处理后的图像将显示在此处')
            # 清空掩码和结果图像变量
            self.current_mask = None
            self.masked_result = None
        # 无论如何，都更新一下显示（主要是为了清除右侧图像）
        # self.update_display() # 这句现在由 apply_hsv_filter_and_update_display 或退出模式时处理

    # --- 滑块值变化处理 ---
    def slider_value_changed(self, slider, label, value, display_name):
        """当滑块值改变时调用"""
        # 更新标签显示当前值 (使用传入的中文显示名称)
        label.setText(f"{display_name}: {value}")

        internal_name = slider.objectName() # 获取滑块的内部标识符 (H Min, H Max etc.)

        # --- 基本的阈值校验：确保 Min <= Max ---
        # 这部分逻辑可以根据需要做得更复杂
        if "Min" in internal_name:
            max_slider_name = internal_name.replace("Min", "Max")
            max_slider = self.sliders.get(max_slider_name)
            # 如果最小值大于最大值，强制将最小值设为最大值
            if max_slider and value > max_slider.value():
                slider.setValue(max_slider.value())
                value = slider.value() # 获取修正后的值
                label.setText(f"{display_name}: {value}") # 再次更新标签
        elif "Max" in internal_name:
            min_slider_name = internal_name.replace("Max", "Min")
            min_slider = self.sliders.get(min_slider_name)
            # 如果最大值小于最小值，强制将最大值设为最小值
            if min_slider and value < min_slider.value():
                slider.setValue(min_slider.value())
                value = slider.value() # 获取修正后的值
                label.setText(f"{display_name}: {value}") # 再次更新标签

        # 注意：这里不再直接调用 apply_hsv_filter，而是启动定时器
        # --- 使用定时器进行防抖 (Debounce) 处理 ---
        # 如果定时器已存在并且正在运行，则停止并重新启动它
        if self.update_timer:
            self.update_timer.stop()
        else:
            # 如果定时器不存在，创建一个一次性定时器
            self.update_timer = QTimer()
            self.update_timer.setSingleShot(True) # 只触发一次
            # 定时器超时后，连接到触发更新的槽函数
            self.update_timer.timeout.connect(self.trigger_update)

        # 启动/重启定时器，延迟 50 毫秒
        # 这意味着只有在滑块停止移动 50ms 后，才会真正执行图像处理
        self.update_timer.start(50)

    # --- 定时器触发的更新 ---
    def trigger_update(self):
        """定时器超时后调用的槽函数，实际执行图像处理和显示更新"""
        if self.is_hsv_mode: # 仅在 HSV 模式下处理
            self.apply_hsv_filter_and_update_display()
        self.update_timer = None # 处理完毕，重置定时器标志

    # --- 应用 HSV 滤波并更新显示 (合并原 apply_hsv_filter 和 update_display 的部分逻辑) ---
    def apply_hsv_filter_and_update_display(self):
        """计算 HSV 掩码、应用掩码，并更新两个图像显示区域"""
        if self.original_frame is None: # 必须有原始图像
             # 更新原始图像显示（显示提示信息）
            qt_original_pixmap = convert_cv_qt(self.original_frame, width=self.display_width)
            self.original_display_label.setPixmap(qt_original_pixmap) # 会显示空
            self.original_display_label.setText("请先加载一张图片")
             # 清理处理后的图像显示
            self.processed_display_label.clear()
            self.processed_display_label.setText('处理后的图像将显示在此处')
            return

        # 总是更新原始图像的显示
        qt_original_pixmap = convert_cv_qt(self.original_frame, width=self.display_width)
        self.original_display_label.setPixmap(qt_original_pixmap)

        # --- 如果处于 HSV 模式，则进行处理并更新右侧显示 ---
        if self.is_hsv_mode and self.hsv_frame is not None:
            # 从滑块获取当前的 HSV 阈值
            h_min = self.sliders["H Min"].value()
            h_max = self.sliders["H Max"].value()
            s_min = self.sliders["S Min"].value()
            s_max = self.sliders["S Max"].value()
            v_min = self.sliders["V Min"].value()
            v_max = self.sliders["V Max"].value()

            # 创建 NumPy 数组表示颜色范围下界和上界
            lower_bound = np.array([h_min, s_min, v_min])
            upper_bound = np.array([h_max, s_max, v_max])

            # 使用 cv2.inRange 创建二值掩码
            # 在 hsv_frame 中，像素值在 [lower_bound, upper_bound] 区间内的为白色(255)，否则为黑色(0)
            self.current_mask = cv2.inRange(self.hsv_frame, lower_bound, upper_bound)

            # 使用掩码和按位与操作，从原始 BGR 图像中提取颜色在范围内的区域
            # 掩码为白色的地方，保留原始图像像素；掩码为黑色的地方，结果为黑色
            self.masked_result = cv2.bitwise_and(self.original_frame, self.original_frame, mask=self.current_mask)
            # print("HSV 滤波器已应用") # 用于调试的输出

            # 转换处理后的图像为 QPixmap 并显示
            qt_processed_pixmap = convert_cv_qt(self.masked_result, width=self.display_width)
            self.processed_display_label.setPixmap(qt_processed_pixmap)

        # --- 如果不处于 HSV 模式，则清除右侧显示 ---
        elif not self.is_hsv_mode:
            self.processed_display_label.clear()
            self.processed_display_label.setText('处理后的图像将显示在此处')

    # --- 重置滑块到默认值 ---
    def reset_sliders(self):
        """将所有滑块的值重置为初始设定的默认值"""
        # 使用初始值重设滑块
        self.sliders["H Min"].setValue(self.h_min_val)
        self.sliders["H Max"].setValue(self.h_max_val)
        self.sliders["S Min"].setValue(self.s_min_val)
        self.sliders["S Max"].setValue(self.s_max_val)
        self.sliders["V Min"].setValue(self.v_min_val)
        self.sliders["V Max"].setValue(self.v_max_val)
        # 同时更新滑块旁边的标签显示
        # 需要重新获取 display_name，这里简化处理，直接用内部名
        # 更准确的做法是迭代 slider_params 或维护一个映射
        for internal_name, slider in self.sliders.items():
            # 尝试从标签的当前文本中提取中文名称部分
            current_text = self.slider_labels[internal_name].text()
            display_name_part = current_text.split(':')[0] # 取冒号前的部分
            # 更新标签文本
            self.slider_labels[internal_name].setText(f"{display_name_part}: {slider.value()}")


    # --- 复位所有状态 ---
    def reset_all(self):
        """点击复位按钮时调用，恢复到初始状态（除了已加载的图像）"""
        # 如果当前在 HSV 模式，先切换回非 HSV 模式
        if self.btn_hsv_mode.isChecked():
            self.btn_hsv_mode.setChecked(False) # 这会自动调用 toggle_hsv_mode
        else:
            # 如果本来就不在 HSV 模式，手动确保控件状态正确
            self.is_hsv_mode = False
            self.hsv_groupbox.setEnabled(False)
            self.btn_hsv_mode.setText("启用 HSV 模式")
            # 清理处理后的图像显示
            self.processed_display_label.clear()
            self.processed_display_label.setText('处理后的图像将显示在此处')

        # 清空处理结果变量
        self.current_mask = None
        self.masked_result = None
        # 重置滑块的值和标签
        self.reset_sliders()
        # 更新显示（确保原始图像显示，右侧清空）
        self.apply_hsv_filter_and_update_display() # 调用这个函数能同时处理显示逻辑

# --- 程序入口点 ---
if __name__ == '__main__':
    app = QApplication(sys.argv) # 创建 PyQt 应用实例
    ex = ImageProcessorApp()      # 创建主窗口实例
    ex.show()                     # 显示窗口
    sys.exit(app.exec_())         # 进入 Qt 事件循环，等待用户操作，直到退出
