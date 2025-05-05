import cv2
import os

class VideoSplitter:
    def __init__(self, video_path, start_time=0, end_time=None, save_path='output_frames', return_frames=False):
        """
        初始化 VideoSplitter 类
        :param video_path: 视频文件路径
        :param start_time: 从视频的哪一秒开始提取帧（默认从 0 秒开始）
        :param end_time: 到视频的哪一秒结束提取帧（默认提取到视频结束）
        :param save_path: 保存拆分帧图像的文件夹路径（默认保存到当前目录下的 'output_frames' 文件夹）
        :param return_frames: 是否返回每一帧的图像数据（默认不返回）
        """
        self.video_path = video_path
        self.start_time = start_time
        self.end_time = end_time
        self.save_path = save_path
        self.return_frames = return_frames
        
        if not os.path.exists(save_path):
            os.makedirs(save_path)

    def split_video(self):
        cap = cv2.VideoCapture(self.video_path) # VideoCapture 是 OpenCV 中的一个类，用于从视频文件或摄像头中读取视频流
        if not cap.isOpened():
            print(f"错误：无法打开视频文件 {self.video_path}")
            return None
        
        fps = cap.get(cv2.CAP_PROP_FPS)                        # 捕获视频的帧率
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))  # 捕获视频的总帧数
        video_duration = total_frames / max(1.0, fps)
        
        print(f"视频信息: {fps}FPS, 总帧数: {total_frames}, 时长: {video_duration:.2f}秒")
        
        start_frame = int(self.start_time * fps)
        end_frame = int((self.end_time if self.end_time else video_duration) * fps)
        
        print(f"处理范围: 第 {start_frame}-{end_frame} 帧")
        
        cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)   # 设置起始帧
        
        for i in range(start_frame, end_frame):
            ret, frame = cap.read() # 调用一次，读取一帧
            if not ret:
                break
                
            filename = os.path.join(self.save_path, f"frame_{i:04d}.jpg")
            if not cv2.imwrite(filename, frame):
                print(f"警告: 无法保存 {filename}")
            else:
                print(f"已保存: {filename}")
        
        cap.release()


# 示例使用
video_path = r"C:\Users\lenovo\Desktop\esp32\esp32\esp32cam_viewer\data\vids\vid_20250430_12_16_33_339.mp4" 
save_path = r"C:\Users\lenovo\Desktop\esp32\esp32\esp32cam_viewer\data\vids\vid_20250430_12_16_33_339"
return_frames = True  # 是否返回帧
# 开始时间、结束时间设置为 None 则默认处理整个视频（必须要传入）
splitter = VideoSplitter(video_path, start_time=0, end_time=None, save_path=save_path, return_frames=return_frames)
frames = splitter.split_video()

# 转换为RGB格式
frames = [cv2.cvtColor(frame, cv2.COLOR_BGR2RGB) for frame in frames]