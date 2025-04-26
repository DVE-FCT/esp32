import sys
from PyQt5.QtWidgets import QApplication # type: ignore
from ui.main_window import CameraApp

def main():
    app = QApplication(sys.argv)
    
    # 加载样式表 - 使用UTF-8编码
    try:
        with open('./ui/styles.qss', 'r', encoding='utf-8') as f:
            app.setStyleSheet(f.read())
    except FileNotFoundError:
        print("警告: 未找到样式表文件")
    
    window = CameraApp()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
