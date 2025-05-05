# core/speed_thread.py

import cv2
import numpy as np
import time
import os
from PyQt5.QtCore import QThread, pyqtSignal, QObject
from datetime import datetime

# --- 常量定义 ---
MARKER_DISTANCE_M = 0.04  # 标记间的实际距离 (4cm = 0.04米)
NUM_WHITE_MARKERS = 11     # 白色标记的数量
TOTAL_MARKERS = 1 + NUM_WHITE_MARKERS # 总标记数 (1黑 + 11白)

class SpeedCalculationThread(QThread):
    """
    通过分析视频帧中标记穿越中心参考线来计算传送带速度的线程。
    记录每个标记（1黑 + 9白）穿越ROI中心线的时间戳。
    使用连续标记的时间差和固定距离计算速度。
    持续更新计算出的速度值。
    简化了检测逻辑，假设标记按序清晰通过。
    """
    # --- 信号定义 ---
    calculation_complete = pyqtSignal(float)                # 信号：发送最新计算出的速度值 (m/s)
    calculation_error = pyqtSignal(str)                     # 信号：发送错误信息
    status_update = pyqtSignal(str)                         # 信号：发送状态更新文本
    # marker_detected_signal = pyqtSignal(object, float, str) # 信号：发送已检测到的标记信息 (marker_index, timestamp, marker_type)

    def __init__(self, frame_source_callable: callable, roi_rect: tuple, save_path: str, time_limit: float, parent: QObject = None):
        """
        初始化速度计算线程。
        :param frame_source_callable: 获取帧的回调函数。
        :param roi_rect: ROI区域 (x, y, w, h)。
        :param save_path: 保存调试图像的基础路径。
        :param parent: Qt父对象。
        """
        super().__init__(parent)
        self.frame_source = frame_source_callable
        self.roi_x, self.roi_y, self.roi_w, self.roi_h = roi_rect
        self.save_path_base = save_path
        self.time_limit = time_limit
        self._running = False

        # --- 线程状态变量 ---
        self.crossing_timestamps = []   # 存储每个标记穿越参考线的时间戳列表
        self.expected_marker_index = 0  # 期望检测到的下一个标记的索引 (0=黑, 1=白1, ..., 11=白11)
        self.reference_line_y = self.roi_h // 2 # ROI内部的中心水平参考线 y坐标 (相对于ROI上边界)
        self.crossing_tolerance = 5     # 标记中心点靠近参考线的容差范围 (像素)   ！！！

        # --- 图像处理参数 ---
        self.threshold_value = 200  # 二值化阈值
        self.min_contour_area = 1000  # 最小轮廓面积 (像素) ！！！

        # --- 调试设置 ---
        self.debug_save_path = os.path.join(self.save_path_base, "speed_debug_refline")
        try:
            os.makedirs(self.debug_save_path, exist_ok=True)
        except OSError as e:
            print(f"[SpeedThreadRef] 创建调试目录失败: {e}")
            self.debug_save_path = None # 标记为不可用

    def run(self):
        """线程执行的主体函数"""
        if not self.debug_save_path:
             self.calculation_error.emit(f"错误：调试图像保存路径不可用")
             return

        self._running = True
        self.crossing_timestamps = [] # 重置时间戳列表
        self.expected_marker_index = 0 # 从黑色标记开始期待
        self.status_update.emit(f"速度标定(参考线法)：等待黑色标记穿越中心线...")
        start_time = time.time()
        timeout_seconds = 45 # 稍微增加超时时间，因为需要检测更多标记，单位是秒

        while self._running and self.expected_marker_index < TOTAL_MARKERS:
            current_time = time.time()
            # 检查超时
            if current_time - start_time > timeout_seconds:
                if not self.crossing_timestamps: # 如果一个标记都没检测到
                     error_msg = f"错误：{timeout_seconds}秒内未检测到任何标记穿越"
                else: # 检测到部分标记
                     error_msg = f"错误：{timeout_seconds}秒超时，仅检测到 {len(self.crossing_timestamps)}/{TOTAL_MARKERS} 个标记"
                self.calculation_error.emit(error_msg)
                self._running = False
                break

            # 1. 获取帧并执行基本检查
            frame = self.frame_source()
            if frame is None:
                time.sleep(0.05)
                continue

            # 2. 裁剪ROI并检查有效性 (同前)
            frame_h, frame_w = frame.shape[:2]
            actual_roi_x = max(0, self.roi_x)
            actual_roi_y = max(0, self.roi_y)
            actual_roi_w = min(self.roi_w, frame_w - actual_roi_x)
            actual_roi_h = min(self.roi_h, frame_h - actual_roi_y)
            if actual_roi_w <= 0 or actual_roi_h <= 0:
                 # 避免频繁发送警告，可能只在第一次或变化时发送
                 time.sleep(0.1)
                 continue
            roi = frame[actual_roi_y : actual_roi_y + actual_roi_h, actual_roi_x : actual_roi_x + actual_roi_w]
            if roi.size == 0:
                time.sleep(0.1)
                continue

            # 3. 图像处理 (灰度化，二值化)
            gray_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            # 大于阈值的像素设置为白色，小于等于阈值的像素设置为黑色
            _, thresh_roi = cv2.threshold(gray_roi, self.threshold_value, 255, cv2.THRESH_BINARY)

            # 4. 查找轮廓
            contours, _ = cv2.findContours(thresh_roi, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            # 5. 检测是否有轮廓穿越参考线
            for contour in contours:
                if cv2.contourArea(contour) < self.min_contour_area:
                    continue

                # 计算轮廓中心点 (质心) 在ROI内的坐标
                M = cv2.moments(contour)
                if M["m00"] == 0: continue
                #cx = int(M["m10"] / M["m00"])
                cy = int(M["m01"] / M["m00"]) 

                # --- 检查是否穿越或接近参考线 ---
                # 如果轮廓中心点非常接近我们定义的中心参考线
                if abs(cy - self.reference_line_y) <= self.crossing_tolerance:
                    # 假设这个穿越的轮廓就是我们正在等待的那个标记
                    crossing_time = time.time()

                    # 记录时间戳
                    self.crossing_timestamps.append(crossing_time)

                    # 确定标记类型 (用于状态更新和调试)
                    marker_type = 'black' if self.expected_marker_index == 0 else f'white{self.expected_marker_index}'

                    self.status_update.emit(f"速度标定：检测到 '{marker_type}' 穿越中心线")

                    # --- 计算速度 ---
                    # 当我们有至少两个时间戳时，就可以计算速度
                    if len(self.crossing_timestamps) >= 2:
                        time_diff = self.crossing_timestamps[-1] - self.crossing_timestamps[-2]
                        if time_diff > self.time_limit: # 避免除零或无效时间差
                            current_speed = MARKER_DISTANCE_M / time_diff
                            # 发送最新计算的速度值
                            self.calculation_complete.emit(current_speed)
                            # 更新状态，显示最新速度（可选，可能太频繁）
                            # self.status_update.emit(f"实时速度: {current_speed:.3f} m/s")
                            # 保存调试图像 (显示参考线和检测到的轮廓)
                            self.save_debug_image(frame, thresh_roi, contour, marker_type, crossing_time)
                        else:
                            print(f"[SpeedThreadRef] 警告: 标记 '{marker_type}' 与前一个标记时间差过小 ({time_diff:.4f}s)")
                            # 删除最后一个时间戳，因为它可能是无效的
                            self.crossing_timestamps.pop()
                            self.expected_marker_index -= 1 # 回退期待的标记索引

                    # 准备期待下一个标记
                    self.expected_marker_index += 1

                    # 更新下一个期待的状态
                    if self.expected_marker_index < TOTAL_MARKERS:
                         next_marker_type = 'black' if self.expected_marker_index == 0 else f'white{self.expected_marker_index}'
                         self.status_update.emit(f"速度标定：等待 '{next_marker_type}' 穿越中心线...{self.expected_marker_index/TOTAL_MARKERS:.1%}")
                    else:
                         self.status_update.emit(f"速度标定：所有 {TOTAL_MARKERS} 个标记已检测完毕。")
                         self._running = False # 所有标记检测完成，结束线程

                    # 优化：一旦找到一个符合条件的穿越轮廓，就处理并跳出本帧的轮廓查找
                    # 假设同一帧内不会有多个标记同时精确穿越中心线
                    break # 跳出 for contour 循环

            # 检查是否因为检测完所有标记而停止
            if not self._running:
                break # 跳出 while _running 循环

            # 短暂暂停
            time.sleep(0.01) # 可以适当调小延时，提高检测精度

        # 线程结束时的最终处理
        if self._running and self.expected_marker_index < TOTAL_MARKERS : # 如果是因为外部stop()调用而结束
             self.status_update.emit("速度标定(参考线法)已手动停止")
        elif self.expected_marker_index == TOTAL_MARKERS and len(self.crossing_timestamps) >= 2:
             # 如果正常完成，可以额外发一个最终状态或平均速度（如果需要）
             final_speed = MARKER_DISTANCE_M / (self.crossing_timestamps[-1] - self.crossing_timestamps[-2])
             self.status_update.emit(f"速度标定(参考线法)完成。最终速度段: {final_speed:.3f} m/s")
             # 若要计算平均速度：
             if len(self.crossing_timestamps) == TOTAL_MARKERS :
                speeds = [MARKER_DISTANCE_M / (self.crossing_timestamps[i] - self.crossing_timestamps[i-1])
                          for i in range(1, len(self.crossing_timestamps))
                          if (self.crossing_timestamps[i] - self.crossing_timestamps[i-1]) > 0.001]
                if speeds:
                    avg_speed = sum(speeds) / len(speeds)
                    self.calculation_complete.emit(avg_speed) # 发送平均速度
                    self.status_update.emit(f"标定完成。平均速度: {avg_speed:.3f} m/s")
        elif not self.crossing_timestamps:
             # 如果是因为超时且未检测到任何标记而结束 (错误信息已在循环内发送)
             pass

        self._running = False # 确保最终状态为停止


    def save_debug_image(self, original_frame, processed_roi, contour, marker_type, timestamp):
        """保存用于调试分析的图像，并绘制参考线。"""
        if not self.debug_save_path: return # 如果路径无效则不保存

        try:
            # 1. 在原始帧副本上绘制ROI边界 (红色实线)
            frame_copy = original_frame.copy()
            # ROI 边界
            cv2.rectangle(frame_copy, (self.roi_x, self.roi_y),
                          (self.roi_x + self.roi_w, self.roi_y + self.roi_h),
                          (0, 0, 255), 2) # 红色
            # 参考线 (在ROI内部，相对于原始帧坐标)
            ref_line_abs_y = self.roi_y + self.reference_line_y
            cv2.line(frame_copy, (self.roi_x, ref_line_abs_y),
                     (self.roi_x + self.roi_w, ref_line_abs_y),
                     (255, 0, 0), 1) # 蓝色细线

            # 2. 在处理后的ROI副本上绘制参考线和检测到的轮廓
            processed_roi_color = cv2.cvtColor(processed_roi, cv2.COLOR_GRAY2BGR)
            # 参考线 (相对于ROI)
            cv2.line(processed_roi_color, (0, self.reference_line_y),
                     (self.roi_w, self.reference_line_y),
                     (255, 0, 0), 1) # 蓝色细线
            # 检测到的轮廓
            cv2.drawContours(processed_roi_color, [contour], -1, (0, 255, 0), 2) # 绿色
            # 轮廓中心点
            M = cv2.moments(contour)
            if M["m00"] != 0:
                 center_point = (int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"]))
                 cv2.circle(processed_roi_color, center_point, 3, (0, 255, 0), -1)

            # 3. 生成文件名
            ts_str = datetime.fromtimestamp(timestamp).strftime("%Y%m%d_%H%M%S_%f")[:-3]
            filename_orig = os.path.join(self.debug_save_path, f"{ts_str}_{marker_type}_1.jpg")
            filename_proc = os.path.join(self.debug_save_path, f"{ts_str}_{marker_type}_2.jpg")

            # 4. 保存图像
            rgb_frame_copy = cv2.cvtColor(frame_copy, cv2.COLOR_BGR2RGB)
            rgb_processed_roi_color = cv2.cvtColor(processed_roi_color, cv2.COLOR_BGR2RGB)
            cv2.imwrite(filename_orig, rgb_frame_copy)
            cv2.imwrite(filename_proc, rgb_processed_roi_color)

        except Exception as e:
             print(f"[SpeedThreadRef] 保存调试图像时发生错误: {e}")

    def stop(self):
        """外部调用的方法，用于请求线程停止"""
        if self._running:
            self.status_update.emit("速度标定(参考线法)：正在停止...")
            self._running = False

