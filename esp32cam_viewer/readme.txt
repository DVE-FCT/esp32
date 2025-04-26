
1. 目录结构：

esp32cam_viewer/
├── main.py                   # 程序入口
├── ui/
│   ├── __init__.py
│   ├── main_window.py        # 主界面类
│   └── styles.qss            # 样式表
├── core/
│   ├── __init__.py
│   ├── camera_display.py     # 图像显示类
│   ├── video_thread.py       # 视频流处理线程
│   └── camera_manager.py     # 摄像头管理
├── utils/
│   ├── __init__.py
│   └── logger.py             # 日志系统
└── esp32_cam_arduino 
    └── esp32_cam_arduino.ino # arduino程序

2. 运行方式：

    1. 打开终端，进入esp32cam_viewer目录
    2. 运行命令：python main.py
    3. 程序运行后，点击“开始”按钮，打开摄像头，显示图像
    4. 点击“录制”按钮，打开录制功能，按下“R”键开始录制，按下“S”键停止录制，按下“Q”键退出录制
    5. 点击“退出”按钮，关闭摄像头，退出程序

3. 注意事项：

    1. 程序运行前，请确保已经正确安装了pyqt5、pyqtgraph、opencv-python、pyserial、pyqt5-tools等依赖库
    2. 程序运行前，请确保已经正确连接了esp32开发板、esp32开发板上的串口、esp32开发板上的摄像头
    3. 程序运行前，请确保esp32_cam_arduino.ino程序烧录成功，并在串口助手中查看是否有打印输出
