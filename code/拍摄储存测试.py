import camera

# 初始化摄像头
camera.init(0, format=camera.JPEG, fb_location=camera.PSRAM)

# 拍摄一张图片
buf = camera.capture()  # 大小是640x480

# 保存图片到文件
with open("第一张图片.png", "wb") as f:
    f.write(buf)  # buf中的数据就是图片的数据，所以直接写入到文件就行了
    print("拍照已完成，点击Thonny左侧【MicroPython设备】右侧的三，\n然后看到‘刷新’，点击刷新会看到 图片，\n然后右击图片名称，选择下载到电脑的路径即可...")
