import cv2, os, time
from datetime import datetime
from ultralytics import YOLO
from PyQt5.QtCore import QThread, pyqtSignal, QObject
from queue import Queue, Full
import os
os.environ["YOLO_VERBOSE"] = "False"


class DetectionThread(QThread):
    # 信号定义
    detection_result = pyqtSignal(int, bool)  # (格子数, 有无种子)
    error_occurred = pyqtSignal(str)  # 错误信息
    status_updated = pyqtSignal(str)  # 状态信息

    def __init__(self, frame_source_callable: callable, roi: tuple, model_path: str, save_path: str = None, parent: QObject = None):
        """
        初始化检测器
        :param frame_source_callable: callable, 用于获取帧的函数，函数签名为 () -> np.ndarray
        :param roi: tuple, 格式为 (x, y, width, height)，表示ROI区域
        :param model_path: str, YOLOv8 模型路径
        :param save_path: str, 调试图像保存路径（可选）
        :param parent: 父对象
        """
        super().__init__(parent)
        self.frame_source = frame_source_callable  # 用于获取帧的函数
        self.roi = roi  # 存储传入的ROI区域
        self.model_path = model_path  # YOLOv8 模型路径
        self.save_path_base = save_path  # 调试图像保存路径
        self.running = False  # 线程运行标志
        self.count = 2  # 要求的总格子数
        self.max_area = 100  # 最大检测面积

        # --- 检测状态变量 ---
        self.total_count = 0  # 已检测完的总格子计数
        self.detection_active = False  # 检测状态标志
        self.last_black_line_state = False  # 上一次黑线检测状态
        self.seed_detected = False  # 种子检测状态
        self.x = False  # 末尾黑线检测标志

        # --- 队列设置 ---
        self.frame_queue = Queue(maxsize=12)  # 最多缓存帧数

        # --- 调试设置 ---
        self.debug_save_path = os.path.join(self.save_path_base, "detection_results") if self.save_path_base else None
        if self.debug_save_path:
            try:
                os.makedirs(self.debug_save_path, exist_ok=True)
            except OSError as e:
                print(f"[SeedDetector] 创建调试目录失败: {e}")
                self.debug_save_path = None

        # --- 加载 YOLO 模型 ---
        self.model = YOLO(model=self.model_path)

    def detect_black_line(self, roi):
        """
        检测黑线是否经过ROI下边界
        返回：是否检测到黑线，处理后的二值化图像
        """
        frame_gay = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        _, frame_gay = cv2.threshold(frame_gay, 25, 255, cv2.THRESH_BINARY_INV)  # 黑白反转
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        frame_gay = cv2.morphologyEx(frame_gay, cv2.MORPH_CLOSE, kernel)
        frame_bgr = cv2.cvtColor(frame_gay, cv2.COLOR_GRAY2BGR)
        # 计算黑线中心点
        contours, _ = cv2.findContours(frame_gay, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if contours:
            largest_contour = max(contours, key=cv2.contourArea)
            area = cv2.contourArea(largest_contour)
            if area > self.max_area:   # 判断最大轮廓面积是否大于阈值
                cv2.drawContours(frame_bgr, [largest_contour], -1, (0, 255, 0), 2)
                M = cv2.moments(largest_contour)
                if M["m00"] > 100:
                    cx = int(M["m10"] / M["m00"])
                    cy = int(M["m01"] / M["m00"])
                    cv2.circle(frame_bgr, (cx, cy), 5, (0, 255, 0), -1)
                    return cy >= roi.shape[0] - 5, frame_bgr  # 是否接近下边界，以及处理后的二值化图像
        return False, frame_bgr


    def process_roi(self, roi, frame_copy):
        """
        处理传入的ROI区域，并返回绘制了ID、置信度和检测框的result_roi
        """
        try:
            current_black_line_state, binary_image = self.detect_black_line(roi)

            # 黑线状态变化检测
            print(f"黑线状态变化: {current_black_line_state} -> {self.last_black_line_state}")
            if current_black_line_state != self.last_black_line_state:
                if current_black_line_state:
                    # 黑线到达
                    self.status_updated.emit("黑线到达")
                    self.save_event_image(binary_image, frame_copy, "black_line_arrival")
                    # 黑线到达，开始新格子检测
                    self.detection_active = True
                    self.total_count += 1  # 增加格子计数
                else:
                    # 黑线离开
                    self.status_updated.emit("黑线离开")
                    self.save_event_image(binary_image, frame_copy, "black_line_departure")

                self.last_black_line_state = current_black_line_state
            self.status_updated.emit(f"已检测完{self.total_count}/{self.count}格子")

            self.seed_detected = False

            if self.detection_active and self.x == False:
                # 使用 YOLOv8 检测种子
                results = self.model(roi, conf=0.5, verbose=False)  # 关闭日志输出
                for result in results:
                    if len(results) > 0:
                        self.seed_detected = True
                        for box in result.boxes:
                            x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                            conf = float(box.conf)
                            cv2.rectangle(roi, (x1, y1), (x2, y2), (0, 255, 0), 2)
                            # 绘制种子ID和置信度
                            cv2.putText(roi, f"{result.names[0]}:{conf:.2f}", (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

            return roi, self.seed_detected

        except Exception as e:
            self.error_occurred.emit(str(e))
            self.stop()
            return roi, False  # 避免 None 出错

    def run(self):
        """
        线程运行方法
        """
        self.running = True
        self.status_updated.emit("检测线程启动")

        while self.running:
            # 检查是否完成所有格子的检测
            if self.total_count >= self.count:
                # 停止线程前，确保处理黑线离开的状态
                if self.last_black_line_state:
                    self.x = True
                    frame = self.frame_source()
                    cv2.rectangle(frame, (x, y), (x + width, y + height), (255, 0, 0), 2)  # 红色框标注ROI
                    roi = frame[actual_roi_y:actual_roi_y + actual_roi_h, actual_roi_x:actual_roi_x + actual_roi_w]
                    result_roi, _ = self.process_roi(roi, frame)
                self.stop()
                break

            # 1. 获取帧并加入队列
            try:
                frame = self.frame_source()
                if frame is not None:
                    self.frame_queue.put(frame, block=False)  # 非阻塞加入队列
            except Full:
                pass  # 队列已满，跳过当前帧

            # 2. 从队列中获取帧并处理
            if not self.frame_queue.empty():
                frame = self.frame_queue.get()

                # 提取并绘制 ROI 区域
                x, y, width, height = self.roi
                frame_h, frame_w = frame.shape[:2]
                actual_roi_x = max(0, x)
                actual_roi_y = max(0, y)
                actual_roi_w = min(width, frame_w - actual_roi_x)
                actual_roi_h = min(height, frame_h - actual_roi_y)

                if actual_roi_w <= 0 or actual_roi_h <= 0:
                    self.error_occurred.emit("ROI区域无效")
                    time.sleep(0.1)
                    continue
                roi = frame[actual_roi_y:actual_roi_y + actual_roi_h, actual_roi_x:actual_roi_x + actual_roi_w]
                frame_copy = frame.copy()
                cv2.rectangle(frame_copy, (x, y), (x + width, y + height), (255, 0, 0), 2)  # 红色框标注ROI
                # 3. 处理 ROI 区域并获取结果
                result_roi, self.seed_detected = self.process_roi(roi, frame_copy)
                if result_roi is not None:
                    # 将处理后的 ROI 绘制回原帧
                    frame_copy[actual_roi_y:actual_roi_y + actual_roi_h, actual_roi_x:actual_roi_x + actual_roi_w] = result_roi
                    # 4. 保存调试图像（可选）
                    if self.debug_save_path and self.seed_detected == True:
                        self.save_debug_image(frame_copy, roi)
                        self.seed_detected = False  # 种子检测完成后，不再重复保存

            # 5. 短暂暂停
            time.sleep(0.01)

        self.status_updated.emit("检测线程停止")


    def save_debug_image(self, frame, roi):
        """
        保存调试图像
        """
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
            filename = os.path.join(self.debug_save_path, f"debug_{timestamp}_result.jpg")
            filename_roi = os.path.join(self.debug_save_path, f"debug_{timestamp}_roi.jpg")
            cv2.imwrite(filename_roi, cv2.cvtColor(roi, cv2.COLOR_RGB2BGR))
            cv2.imwrite(filename, cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
        except Exception as e:
            print(f"[SeedDetector] 保存调试图像失败: {e}")

    def save_event_image(self, roi, frame, event_name):
        """
        保存黑线到达或离开时的图像
        """
        if self.debug_save_path:
            try:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
                filename = os.path.join(self.debug_save_path, f"{event_name}_{timestamp}_1.jpg")
                filename_roi = os.path.join(self.debug_save_path, f"{event_name}_{timestamp}_2.jpg")
                image_rgb = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                roi_rgb = cv2.cvtColor(roi, cv2.COLOR_BGR2RGB)
                cv2.imwrite(filename, image_rgb)
                cv2.imwrite(filename_roi, roi_rgb)
                print("*" * 30 + f"\n[SeedDetector] 保存事件图像:{filename}" + "\n" + "*" * 30)
            except Exception as e:
                print(f"[SeedDetector] 保存事件图像失败: {e}")

    def stop(self):
        """
        停止线程
        """
        self.running = False
        self.status_updated.emit("检测线程停止")
