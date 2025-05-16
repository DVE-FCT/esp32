import cv2
import time
import torch
from ultralytics import YOLO
from deep_sort_realtime.deepsort_tracker import DeepSort

# 检查 GPU 可用性
device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Using device: {device}")

# 初始化 YOLOv8
model = YOLO(model="C:/Users/lenovo/Desktop/esp32/esp32cam_viewer/models/yolov8.pt")

# 初始化 DeepSORT (使用 CLIP_RN50)
tracker = DeepSort(
    max_age=30,
    n_init=5,
    max_cosine_distance=0.2,
    embedder="clip_RN50",  # 使用 CLIP 特征提取
    half=True,             # 半精度加速（需 GPU）
    bgr=True,
    embedder_gpu=True,     # 使用 GPU 运行 CLIP
    embedder_model_name="RN50",  # 明确指定 CLIP 模型
    embedder_wts="C:/Users/lenovo/.cache/clip/RN50.pt"  # 预训练权重路径
)

# 打开视频
video_path = "C:/Users/lenovo/Desktop/esp32/esp32cam_viewer/data/vids/vid_20250430_12_16_33_339.mp4"
cap = cv2.VideoCapture(video_path)

# 获取视频信息
original_fps = cap.get(cv2.CAP_PROP_FPS)
width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
print(f"Video Info: {width}x{height}@{original_fps:.2f}fps")

# 设置目标帧率 (6 FPS)
target_fps = 6
frame_delay = 1.0 / target_fps  # 每帧间隔时间（秒）

# 性能统计
total_frames = 0
total_processing_time = 0

while cap.isOpened():
    # 读取下一帧
    ret, frame = cap.read()
    if not ret:
        break

    start_time = time.time()

    # YOLOv8 检测（降低分辨率加速）
    results = model(frame, imgsz=320, stream=True, half=True, conf=0.7)

    # 处理检测结果
    detections = []
    for r in results:
        boxes = r.boxes.xyxy.cpu().numpy()
        confs = r.boxes.conf.cpu().numpy()
        cls_ids = r.boxes.cls.cpu().numpy()
        detections.extend([([x1, y1, x2-x1, y2-y1], conf, int(cls)) 
                         for (x1, y1, x2, y2), conf, cls in zip(boxes, confs, cls_ids)])

    # 过滤低置信度检测（减少 CLIP 计算量）
    detections = [d for d in detections if d[1] > 0.5]

    # DeepSORT 跟踪（CLIP 特征提取在此步骤完成）
    tracked_objects = tracker.update_tracks(detections, frame=frame)

    # 绘制结果
    for obj in tracked_objects:
        if not obj.is_confirmed():
            continue
        track_id = obj.track_id
        x1, y1, x2, y2 = map(int, obj.to_tlbr())
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(frame, f"ID: {track_id}", (x1, y1-10), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

    # 计算处理时间
    process_time = time.time() - start_time
    total_processing_time += process_time
    total_frames += 1

    # 显示处理信息
    fps = 1.0 / process_time
    avg_fps = total_frames / total_processing_time
    info_text = f"Curr FPS: {fps:.1f} | Avg FPS: {avg_fps:.1f} | Processed: {total_frames}"
    cv2.putText(frame, info_text, (10, 30), 
               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

    # 显示结果
    cv2.imshow("YOLOv8 + DeepSORT (CLIP_RN50)", frame)

    # 控制帧率
    elapsed = time.time() - start_time
    if elapsed < frame_delay:
        time.sleep(frame_delay - elapsed)

    # 按 q 退出
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# 释放资源
cap.release()
cv2.destroyAllWindows()
print(f"Total frames processed: {total_frames}, Average FPS: {total_frames/total_processing_time:.2f}")
