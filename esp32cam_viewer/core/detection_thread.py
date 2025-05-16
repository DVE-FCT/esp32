import cv2, os, time
from datetime import datetime
from ultralytics import YOLO
from PyQt5.QtCore import QThread, pyqtSignal, QObject
from queue import Queue, Full
import os
os.environ["YOLO_VERBOSE"] = "False"

class DetectionThread(QThread):
    detection_result = pyqtSignal(int, bool)  # (格子ID, 有无种子)
    error_occurred = pyqtSignal(str)
    status_updated = pyqtSignal(str)

    def __init__(self, frame_source_callable: callable, roi: tuple, model_path: str, save_path: str = None, parent: QObject = None):
        super().__init__(parent)
        self.frame_source = frame_source_callable
        self.roi = roi
        self.model_path = model_path
        self.save_path_base = save_path
        self.running = False
        self.count = 2  # 总格子数，可以按需调整
        self.max_area = 100
        self.crossing_tolerance = 10

        # --- 新增状态变量 ---
        self.detection_active = False       # 初始不启用YOLO检测
        self.last_black_line_state = False
        self.current_grid_id = 0            # 当前格子ID，从0计数，检测到第1条黑线时+1变成1
        self.grid_seed_detected = False     # 当前格子内是否检测到过种子
        self.seed_detected_this_frame = False  # 当前帧是否检测到种子
        self.last_black_line_time = time.time()  # 最后检测到黑线时间

        self.frame_queue = Queue(maxsize=12)

        # 调试保存目录
        self.debug_save_path = None
        if self.save_path_base:
            try:
                self.debug_save_path = os.path.join(self.save_path_base, "detection_results")
                os.makedirs(self.debug_save_path, exist_ok=True)
            except Exception as e:
                self.debug_save_path = None
                print(f"[SeedDetector] 创建调试目录失败: {e}")

        self.model = YOLO(self.model_path)

    def run(self):
        self.running = True
        self.status_updated.emit("检测线程启动")

        while self.running:
            frame = self.frame_source()
            if frame is None:
                time.sleep(0.01)
                continue

            x, y, width, height = self.roi
            frame_h, frame_w = frame.shape[:2]
            roi_x = max(0, x)
            roi_y = max(0, y)
            roi_w = min(width, frame_w - roi_x)
            roi_h = min(height, frame_h - roi_y)

            if roi_w <=0 or roi_h <=0:
                self.error_occurred.emit("ROI区域无效")
                time.sleep(0.1)
                continue

            roi = frame[roi_y:roi_y+roi_h, roi_x:roi_x+roi_w]
            frame_copy = frame.copy()
            cv2.rectangle(frame_copy, (x,y),(x+width,y+height),(255,0,0),2)

            # 检测黑线状态
            current_black_line_state, binary_image = self.detect_black_line(roi)

            if current_black_line_state != self.last_black_line_state:
                self.last_black_line_time = time.time()

                if current_black_line_state:  # 黑线到达
                    if not self.detection_active:
                        # 第一次检测到黑线，开启检测，同时当前格子ID+1，从1开始
                        self.detection_active = True
                        self.current_grid_id = 1
                        self.grid_seed_detected = False
                        self.status_updated.emit("首次检测到黑线，启动YOLO检测，开始第1格子统计")
                    else:
                        # 后续每检测到黑线，意味着前面的格子检测结束，发送结果并进入新格子统计
                        self.detection_result.emit(self.current_grid_id, self.grid_seed_detected)
                        self.current_grid_id += 1
                        self.grid_seed_detected = False
                        self.status_updated.emit(f"检测到黑线，格子{self.current_grid_id}开始")
                    self.save_event_image(binary_image, frame_copy, f"black_in{self.current_grid_id}")

                else:  # 黑线离开
                    self.status_updated.emit("黑线离开")
                    self.save_event_image(binary_image, frame_copy, f"black_out{self.current_grid_id}")

                self.last_black_line_state = current_black_line_state

            # 超过5秒未检测到黑线，自动停止检测，并发送最后格子结果
            if self.detection_active and (time.time() - self.last_black_line_time) > 5:
                self.status_updated.emit("超过5秒未检测到黑线，停止检测线程")
                # 最后一个格子结果发送
                self.detection_result.emit(self.current_grid_id, self.grid_seed_detected)
                self.stop()
                break

            # YOLO检测，仅激活时进行
            self.seed_detected_this_frame = False
            if self.detection_active:
                try:
                    results = self.model(roi, conf=0.5, verbose=False)
                except Exception as e:
                    self.error_occurred.emit(f"YOLO异常: {e}")
                    results = []

                for result in results:
                    if len(results) > 0:
                        self.seed_detected_this_frame = True
                        for box in result.boxes:
                            x1,y1,x2,y2 = map(int, box.xyxy[0].tolist())
                            conf = float(box.conf)
                            cv2.rectangle(roi,(x1,y1),(x2,y2),(0,255,0),2)
                            cv2.putText(roi,f"{result.names[0]}:{conf:.2f}",(x1,y1-5),cv2.FONT_HERSHEY_SIMPLEX,0.5,(0,255,0),1)

                # 累积格子内是否检测到过种子
                if self.seed_detected_this_frame:
                    self.grid_seed_detected = True

                # 只有检测到种子时保存调试图片，文件名带格子ID
                if self.seed_detected_this_frame and self.debug_save_path:
                    self.save_debug_image(frame_copy, roi, self.current_grid_id)

            time.sleep(0.01)

        self.status_updated.emit("检测线程停止")

    def detect_black_line(self, roi):
        frame_gay = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        _, frame_gay = cv2.threshold(frame_gay, 100, 255, cv2.THRESH_BINARY_INV)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5,5))
        frame_gay = cv2.morphologyEx(frame_gay, cv2.MORPH_CLOSE, kernel)
        frame_bgr = cv2.cvtColor(frame_gay, cv2.COLOR_GRAY2BGR)
        contours, _ = cv2.findContours(frame_gay, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if contours:
            largest_contour = max(contours, key=cv2.contourArea)
            area = cv2.contourArea(largest_contour)
            if area > self.max_area:
                cv2.drawContours(frame_bgr, [largest_contour], -1, (0,255,0), 2)
                M = cv2.moments(largest_contour)
                if M["m00"] > 100:
                    cx = int(M["m10"]/M["m00"])
                    cy = int(M["m01"]/M["m00"])
                    cv2.circle(frame_bgr,(cx,cy),5,(0,255,0),-1)
                    return cy >= roi.shape[0] - self.crossing_tolerance, frame_bgr
        return False, frame_bgr

    def save_debug_image(self, frame, roi, grid_id):
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
            filename = os.path.join(self.debug_save_path, f"grid{grid_id}_seed_{timestamp}_result.jpg")
            filename_roi = os.path.join(self.debug_save_path, f"grid{grid_id}_seed_{timestamp}_roi.jpg")
            cv2.imwrite(filename_roi, cv2.cvtColor(roi, cv2.COLOR_BGR2RGB))
            cv2.imwrite(filename, cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        except Exception as e:
            print(f"[SeedDetector] 保存调试图片失败: {e}")

    def save_event_image(self, roi, frame, event_name):
        if not self.debug_save_path:
            return
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
            full_path = os.path.join(self.debug_save_path, f"{event_name}_{timestamp}_full.jpg")
            roi_path = os.path.join(self.debug_save_path, f"{event_name}_{timestamp}_roi.jpg")
            cv2.imwrite(full_path, cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            cv2.imwrite(roi_path, cv2.cvtColor(roi, cv2.COLOR_BGR2RGB))
        except Exception as e:
            print(f"[SeedDetector] 保存事件图像失败: {e}")

    def stop(self):
        self.running = False
        self.status_updated.emit("检测线程停止")
