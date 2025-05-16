import camera
import network
import socket
import time
import sys
import machine
import _thread




from machine import UART
# 设置串口 1 的波特率为 115200，TX 引脚接 GPIO4，RX 引脚接 GPIO5
"""
    ESP32-CAM 串口连接示意图：
    |-----------------|
    |                 |
    | ESP32-CAM       |
    |                 |
    |  TX  ----> GPIO4|
    |  RX  <---- GPIO5|
    |                 |
    |-----------------|

    默认无奇偶校验位，数据位8，停止位1，波特率115200
"""
uart = UART(1, baudrate=115200, tx=4, rx=5)  # 按硬件实际定义




# WiFi配置
WIFI_SSID = "fff"
WIFI_PASS = "123456qaz789"
# WIFI_SSID = "她只是经过~"
# WIFI_PASS = "10203040"

# 全局状态
camera_initialized = False
control_running = True  # 控制服务器运行标志
led = machine.Pin(4, machine.Pin.OUT)  # GPIO4控制板载LED
led.off()
def setup_camera():
    """初始化摄像头"""
    global camera_initialized
    try:
        print("正在初始化摄像头_...")
        camera.init(0, format=camera.JPEG, framesize=camera.FRAME_VGA, fb_location=camera.PSRAM) # 初始化摄像头并指定使用PSRAM
        camera_initialized = True
        print("摄像头初始化成功")
    except Exception as e:
        print(f"摄像头初始化失败: {e}")
        cleanup_resources()
        raise

def cleanup_camera():
    """清理摄像头资源"""
    global camera_initialized
    if camera_initialized:
        try:
            print("正在反初始化摄像头...")
            camera.deinit()
            camera_initialized = False
            print("摄像头资源已释放")
        except Exception as e:
            print(f"摄像头反初始化异常: {e}")

def cleanup_resources():
    """清理所有资源"""
    global control_running
    control_running = False
    cleanup_camera()
    if 'wifi' in globals() and wifi:
        wifi.disconnect()
    if 'server_socket' in globals() and server_socket:
        server_socket.close()
    if 'control_socket' in globals() and control_socket:
        control_socket.close()

def connect_wifi():
    """连接WiFi"""
    wifi = network.WLAN(network.STA_IF)
    wifi.active(True)
    if not wifi.isconnected():
        print(f"正在连接WiFi: {WIFI_SSID}...")
        wifi.connect(WIFI_SSID, WIFI_PASS)
        
        for _ in range(20):  # 最多等待10秒
            if wifi.isconnected():
                break
            time.sleep(0.5)
        else:
            cleanup_resources()
            raise RuntimeError("WiFi连接超时")

    print(f"WiFi已连接，IP: {wifi.ifconfig()[0]}")
    return wifi


def take_photo():
    """拍照并保存到日期目录"""
    try:
        frame = camera.capture()
        if not frame:
            return "拍照失败: 无法获取帧"
        
        # 获取当前日期和时间
        current_time = time.localtime()
        date_dir = "/{:04d}_{:02d}_{:02d}".format(
            current_time[0],  # 年
            current_time[1],  # 月
            current_time[2]   # 日
        )
        
        # 创建日期目录（如果不存在）
        try:
            uos.mkdir(date_dir)
        except OSError as e:
            if e.args[0] != 17:  # 忽略目录已存在的错误
                raise
        
        # 生成带路径的文件名
        timestamp = "{:02d}_{:02d}_{:02d}".format(
            current_time[3],        # 时
            current_time[4],        # 分
            current_time[5]         # 秒
        )
        filename = "{}/photo_{}.jpg".format(date_dir, timestamp)
        
        # 保存照片
        with open(filename, "wb") as f:
            f.write(frame)
        
        return f"拍照成功: {filename}"
        
    except Exception as e:
        return f"拍照错误: {str(e)}"


def handle_control_client(conn, addr):
    """持续处理控制客户端连接（单字符模式）"""
    print(f"控制客户端连接: {addr}")
    try:
        # 设置非阻塞模式（MicroPython特有方式）
        conn.setblocking(False)
        
        while control_running:
            try:
                # 尝试接收1字节数据
                data = conn.recv(2) # 指定最大传输字节数 2 
                
                if data:  # 收到有效数据
                    cmd = data.decode()
                    print(f"收到控制命令: {cmd}")
                    
                    if cmd == 'L':
                        led.on()
                        conn.send(b"1")
                    elif cmd == 'l':
                        led.off()
                        conn.send(b"1")
                    elif cmd == 'P':
                        photo_result = take_photo()  # 这里可以打印结果或不打印
                        conn.send(b"1")




                    elif cmd in ('1','2','3','4','5'):
                        # 转发数字字符给STM32
                        uart.write(cmd.encode('ascii'))
                        print(f"转发给STM32: {cmd}")
                        conn.send(b"1")




                    else:
                        led.off()
                        conn.send(b"0")
                        print("无效命令")
                        
                elif data == b'':  # 客户端断开连接
                    print("客户端正常断开")
                    break
                    
            except OSError as e:
                if e.args[0] == 11:  # EAGAIN/EWOULDBLOCK
                    time.sleep_ms(100)  # 短暂等待避免CPU满载
                    continue
                elif e.args[0] == 128:  # ENOTCONN
                    print("客户端异常断开")
                    break
                raise
                
    except Exception as e:
        print(f"控制客户端处理异常: {e}")
    finally:
        print(f"控制客户端断开: {addr}")
        conn.close()
        
def control_server():
    """改进的控制服务器"""
    global control_socket
    control_socket = socket.socket()
    control_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    control_socket.bind(('0.0.0.0', 81))
    control_socket.listen(5)  # 增加等待队列
    print(f"\n控制服务器已启动 (持续连接模式): port 81")

    while control_running:
        try:
            conn, addr = control_socket.accept()
            print(f"新的控制连接: {addr}")
            # 为每个客户端创建独立线程
            _thread.start_new_thread(handle_control_client, (conn, addr))
        except Exception as e:
            if control_running:
                print(f"控制服务器接受连接错误: {e}")

def handle_client(conn, addr):
    """处理视频客户端连接"""
    print(f"视频客户端连接: {addr}")
    try:
        # 读取请求头
        request = conn.recv(1024)
        if b"GET /" not in request:
            print("非HTTP GET请求")
            return False

        # 发送标准MJPG流头
        response_headers = (
            # 标准HTTP响应行，表示请求成功
            "HTTP/1.1 200 OK\r\n"   
            # 服务器将不断用新数据替换旧数据； 定义分隔符为"frame"，用于分隔每个JPEG帧
            "Content-Type: multipart/x-mixed-replace; boundary=frame\r\n"
            # 保持TCP连接不关闭，避免频繁建立新连接
            "Connection: keep-alive\r\n"
            # 禁止客户端缓存视频流数据，确保总是获取最新帧
            "Cache-Control: no-cache\r\n"
            # HTTP头的结束标记(空行)
            "Pragma: no-cache\r\n\r\n"
        ).encode()
        conn.send(response_headers)

        # 持续发送视频帧
        frame_count = 0
        last_frame_time = time.time()
        last_frame = None
        
        while True:
            try:
                # 获取帧
                frame = camera.capture()
                if not frame:
                    if last_frame:  # 使用上一帧避免中断
                        frame = last_frame
                    else:
                        print("获取到空帧，跳过")
                        continue
                else:
                    last_frame = frame
                
                # 发送帧
                frame_header = (
                    # 边界标记，与响应头中定义的boundary一致
                    "--frame\r\n"
                    # 声明当前部分的内容类型为JPEG图像
                    "Content-Type: image/jpeg\r\n"
                    # 指定当前JPEG帧的字节长度； 帧头的结束标记(空行)
                    f"Content-Length: {len(frame)}\r\n\r\n"
                ).encode()
                conn.sendall(frame_header + frame)
                frame_count += 1
                
                # 打印FPS
                current_time = time.time()
                if current_time - last_frame_time >= 5:
                    fps = frame_count / (current_time - last_frame_time)
                    print(f"正在推流 | FPS: {fps:.1f} | 客户端: {addr}")
                    frame_count = 0
                    last_frame_time = current_time
                
                # time.sleep(0.05)  # ~20 FPS 控制发送视频帧的间隔时间
                time.sleep(0.1)  # ~10 FPS 
                
            except OSError as e:
                print(f"客户端断开: {addr} | 错误: {e}")
                return True
                
    except Exception as e:
        print(f"处理客户端异常: {e}")
    finally:
        try:
            conn.close()
        except:
            pass
    return False

def main():
    """主程序"""
    global server_socket, control_socket
    
    try:
        setup_camera()
        wifi = connect_wifi()
        
        # 启动控制服务器线程(port 81)
        _thread.start_new_thread(control_server, ())
        
        # 创建HTTP视频服务器(port 80)
        server_socket = socket.socket()
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind(('0.0.0.0', 80))
        server_socket.listen(1)
        print(f"视频服务器已启动: http://{wifi.ifconfig()[0]}:80/")

        # 主服务循环
        while True:
            try:
                print("等待视频客户端连接...")
                conn, addr = server_socket.accept()
                handle_client(conn, addr)
            except KeyboardInterrupt:
                print("\n收到中断信号")
                break
            except Exception as e:
                print(f"服务器错误: {e}")
                time.sleep(1)  # 防止错误循环
                
    except Exception as e:
        print(f"程序异常: {e}")
    finally:
        print("正在清理资源...")
        cleanup_resources()
        print("程序正常退出")

if __name__ == "__main__":
    main()
