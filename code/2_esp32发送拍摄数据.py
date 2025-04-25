import socket
import network
import camera
import time


# 连接WiFi并添加错误处理
print("开始连接wifi")
# 初始化wifi网络接口对象
wlan = network.WLAN(network.STA_IF)
# 使能接口
wlan.active(True)
try:
    if not wlan.isconnected():
        print('connecting to network...')
        wlan.connect('她只是经过~', '10203040')

        # 循环等待连接成功
        while not wlan.isconnected():
            pass
    print('网络配置:', wlan.ifconfig())
except Exception as e:
    print("WiFi连接失败: ", e)

# 摄像头初始化并添加错误处理
try:
    print("初始化摄像头")
    camera.init(0, format=camera.JPEG)
except Exception as e:
    print("摄像头初始化失败，尝试重新初始化: ", e)
    try:
        # 释放摄像头资源 并 尝试重新初始化摄像头
        camera.deinit()
        camera.init(0, format=camera.JPEG)
    except Exception as e:
        print("摄像头重新初始化失败: ", e)

# 其他摄像头设置，添加错误处理
try:
    print("设置摄像头参数")
    # 上翻下翻
    camera.flip(1)
    # 左右翻转
    camera.mirror(1)
    # 设置分辨率——HVGA(480x320)
    camera.framesize(camera.FRAME_HVGA)
    # 特效——无效果
    camera.speffect(camera.EFFECT_NONE)
    # 设置白平衡
    # camera.whitebalance(camera.WB_HOME)  # 可根据需要打开
    # 设置饱和度——0
    camera.saturation(0)
    # 设置亮度——0
    camera.brightness(0)
    # 设置对比度——0
    camera.contrast(0)
    # 设置质量——10
    camera.quality(10)
except Exception as e:
    print("摄像头设置失败: ", e)

# 创建UDP socket并添加错误处理
try:
    print("创建UDP Socket")

    # AF_INET 表示使用 IPv4 协议，SOCK_DGRAM 表示使用 UDP 协议
    # 0 表示匹配前面的协议——自动选择与 SOCK_DGRAM 类型配套的协议（即 UDP）
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, 0)
except Exception as e:
    print("UDP Socket创建失败: ", e)

# 主循环，捕获和发送图像数据
try:
    while True:
        try:
            print("捕获图像并发送")
            buf = camera.capture()  # 获取图像数据
            s.sendto(buf, ("192.168.1.106", 9090))  # 向服务器发送图像数据
            time.sleep(0.1)
        except Exception as e:
            print("图像捕获或发送失败: ", e)
            break
except Exception as e:
    print("主循环运行出错: ", e)
finally:
    try:
        print("释放摄像头资源")
        camera.deinit()
    except Exception as e:
        print("释放摄像头资源时出错: ", e)