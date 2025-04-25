import socket
import cv2
import io
from PIL import Image
import numpy as np

# 创建一个UDP套接字
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, 0)

# 绑定套接字到本地地址和端口9090，使其可以接收来自任何 IP 地址的 UDP 数据包
"""
    0.0.0.0 表示“所有可用的网络接口”，即该程序可以接收来自任何网络接口的消息;
    无论数据包是从本地网络（LAN）、外部网络，还是其他任何地方发送来的，程序都能接收到。

    9090 是自定义的端口号，可以任意设置，但要和esp32程序中的发送数据的端口号一致。
"""
s.bind(("0.0.0.0", 9090))

# 无限循环，持续接收数据
while True:
    # 从套接字接收数据并储存在data中，最大缓冲区大小为100000字节
    # 同时获取发送数据的IP地址
    data, IP = s.recvfrom(100000)
    
    # 将接收到的字节数据放入字节流中
    bytes_stream = io.BytesIO(data)
    
    # 使用PIL库打开字节流中的图像（RGB）
    image = Image.open(bytes_stream)
    
    # 将PIL图像转换为numpy数组（opencv的数据格式）
    img = np.asarray(image)
    
    # 将图像的颜色格式从RGB转换为BGR，以匹配OpenCV的格式
    img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    
    # 使用OpenCV显示图像，并设置窗口标题为"ESP32 Capture Image"
    cv2.imshow("ESP32 Capture Image", img)
    
    # 检查是否按下'q'键，如果是则退出循环
    if cv2.waitKey(1) == ord("q"):
        break