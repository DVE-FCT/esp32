import cv2
import numpy as np
import requests
import time
from datetime import datetime

ESP32_IP = "192.168.1.111"  # 替换为ESP32实际IP   工作室的网
# ESP32_IP = "192.168.43.107"  # 替换为ESP32实际IP     手机热点
PORT = 80  # 端口号
url = f"http://{ESP32_IP}:{PORT}/"

class VideoProcessor:
    def __init__(self):
        # 性能统计
        self.frame_count = 0
        self.start_time = time.time()
        self.fps = 0

    def calculate_fps(self):
        """计算并返回FPS"""
        self.frame_count += 1
        if self.frame_count % 5 == 0:  # 每5帧计算一次
            elapsed = time.time() - self.start_time
            self.fps = 5 / elapsed
            self.start_time = time.time()
        return self.fps

    def draw_status(self, frame):
        """在图像上绘制状态信息"""
        h, w = frame.shape[:2]
        
        # 白色文字设置
        text_color = (255, 255, 255)  # 白色
        font = cv2.FONT_HERSHEY_SIMPLEX
        
        # FPS显示在右上角
        fps_text = f"FPS: {self.fps:.1f}"
        fps_size = cv2.getTextSize(fps_text, font, 0.7, 2)[0]
        cv2.putText(frame, fps_text, (w - fps_size[0] - 10, 30), 
                   font, 0.7, text_color, 2)
        
        # 时间戳显示在左上角
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cv2.putText(frame, timestamp, (10, 30), 
                   font, 0.5, text_color, 1)

def process_mjpeg_stream():
    buffer = b""
    boundary = b"--frame"
    processor = VideoProcessor()
    reconnect_delay = 1  # 重连延迟(秒)
    
    while True:
        try:
            print(f"尝试连接到ESP32-CAM服务器: {url}")
            with requests.get(url, stream=True, timeout=10) as response:
                print("连接成功，开始接收视频流...")
                
                for chunk in response.iter_content(chunk_size=8192):  # 增大块大小提高性能
                    if not chunk:
                        print("收到空数据块，可能连接中断")
                        time.sleep(0.1)
                        continue
                        
                    buffer += chunk
                    
                    while True:
                        # 查找边界标记
                        boundary_pos = buffer.find(boundary)
                        if boundary_pos == -1:
                            break
                            
                        # 提取一个完整帧
                        frame_start = buffer.find(b"\r\n\r\n", boundary_pos)
                        if frame_start == -1:
                            break
                            
                        frame_start += 4  # 跳过\r\n\r\n
                        frame_end = buffer.find(boundary, frame_start)
                        
                        if frame_end == -1:  # 未找到下一帧边界
                            if len(buffer) > 2*1024*1024:  # 防止缓冲区过大(2MB)
                                buffer = buffer[frame_start:]
                            break
                            
                        # 提取JPEG数据
                        jpeg_data = buffer[frame_start:frame_end]
                        buffer = buffer[frame_end:]
                        
                        if len(jpeg_data) < 100:  # 过滤过小数据包
                            continue
                            
                        try:
                            # 解码图像
                            img = cv2.imdecode(np.frombuffer(jpeg_data, dtype=np.uint8), cv2.IMREAD_COLOR)
                            if img is None:
                                print("JPEG解码失败")
                                continue
                                
                            # 计算FPS
                            fps = processor.calculate_fps()
                            
                            # 绘制状态信息
                            processor.draw_status(img)
                            
                            # 显示原始图像
                            cv2.imshow("ESP32-CAM Stream", img)
                            
                        except Exception as e:
                            print(f"图像处理错误: {e}")
                            
                    # 检查退出键
                    if cv2.waitKey(1) == ord('q'):
                        raise KeyboardInterrupt
                        
        except requests.exceptions.RequestException as e:
            print(f"连接错误: {e}，尝试重新连接...")
            time.sleep(reconnect_delay)
            
        except KeyboardInterrupt:
            print("用户主动终止")
            break
            
        except Exception as e:
            print(f"未处理的异常: {e}")
            time.sleep(reconnect_delay)
            
    cv2.destroyAllWindows()
    print("客户端已关闭")

if __name__ == "__main__":
    print("启动MJPG流客户端...")
    process_mjpeg_stream()
