#include "esp_camera.h"
#include <WiFi.h>
#include <WebServer.h>
#include <WiFiClient.h>

// WiFi配置
const char* ssid = "她只是经过~";
const char* password = "10203040";

// ESP32-CAM默认引脚配置（AI-Thinker模组）
// 使用预定义的引脚配置，因为摄像头是直接连接到ESP32-CAM板上的
#define CAMERA_MODEL_AI_THINKER
#include "camera_pins.h"

// LED灯控制引脚（ESP32-CAM板载LED）
#define FLASH_LED_PIN 4

// 图像参数设置
#define FRAME_SIZE FRAMESIZE_VGA  // 默认分辨率 640x480
#define JPEG_QUALITY 10           // 10-63，数字越小质量越高
#define BRIGHTNESS 0       // -2到2
#define CONTRAST 0         // -2到2
#define SATURATION 0       // -2到2

WebServer server(80);
bool isClientConnected = false; // 跟踪客户端连接状态
unsigned long connectedClients = 0; // 连接过的客户端计数

// 视频流处理函数
void handleStream() {
  isClientConnected = true;
  connectedClients++;
  WiFiClient client = server.client();
  
  // 设置MJPEG流头
  client.println("HTTP/1.1 200 OK");
  client.println("Content-Type: multipart/x-mixed-replace; boundary=frame");
  client.println("Access-Control-Allow-Origin: *"); // 允许跨域请求
  client.println();
  
  Serial.println("新客户端连接到视频流");
  
  while (client.connected()) {
    camera_fb_t *fb = esp_camera_fb_get();
    if (!fb) {
      Serial.println("帧获取失败");
      delay(100);
      continue;
    }

    // 发送帧数据
    client.println("--frame");
    client.println("Content-Type: image/jpeg");
    client.print("Content-Length: ");
    client.println(fb->len);
    client.println();
    client.write(fb->buf, fb->len);
    client.println();
    
    esp_camera_fb_return(fb);
    
    // 短暂延迟以控制帧率
    delay(30); // ~33fps
  }
  
  isClientConnected = false;
  Serial.println("客户端断开连接");
}

// 获取相机状态
void handleStatus() {
  String json = "{";
  json += "\"running\": true,";
  json += "\"uptime\": " + String(millis() / 1000) + ",";
  json += "\"heap\": " + String(esp_get_free_heap_size() / 1024) + ",";
  json += "\"clients\": " + String(connectedClients) + ",";
  json += "\"active\": " + String(isClientConnected);
  json += "}";
  
  server.send(200, "application/json", json);
}

// 设置相机参数
void handleSettings() {
  bool updated = false;
  sensor_t *s = esp_camera_sensor_get();
  
  if (server.hasArg("framesize")) {
    int fs = server.arg("framesize").toInt();
    if (fs >= 0 && fs <= 12) {
      s->set_framesize(s, (framesize_t)fs);
      updated = true;
    }
  }
  
  if (server.hasArg("quality")) {
    int quality = server.arg("quality").toInt();
    if (quality >= 10 && quality <= 63) {
      s->set_quality(s, quality);
      updated = true;
    }
  }
  
  if (server.hasArg("brightness")) {
    int brightness = server.arg("brightness").toInt();
    if (brightness >= -2 && brightness <= 2) {
      s->set_brightness(s, brightness);
      updated = true;
    }
  }
  
  if (server.hasArg("flash") && server.arg("flash") == "1") {
    digitalWrite(FLASH_LED_PIN, HIGH);
    updated = true;
  } else if (server.hasArg("flash") && server.arg("flash") == "0") {
    digitalWrite(FLASH_LED_PIN, LOW);
    updated = true;
  }
  
  if (updated) {
    server.send(200, "text/plain", "设置已更新");
  } else {
    server.send(200, "text/plain", "无变更");
  }
}

void startCameraServer() {
  // 设置路由
  server.on("/stream", HTTP_GET, handleStream);
  server.on("/status", HTTP_GET, handleStatus);
  server.on("/settings", HTTP_GET, handleSettings);
  
  // 主页
  server.on("/", HTTP_GET, [](){
    String html = "<!DOCTYPE html>";
    html += "<html><head>";
    html += "<meta name='viewport' content='width=device-width, initial-scale=1'>";
    html += "<title>ESP32-CAM 监控系统</title>";
    html += "<style>";
    html += "body { font-family: Arial; text-align: center; margin: 0; padding: 20px; }";
    html += "h1 { color: #0F3376; }";
    html += ".video-container { margin: 0 auto; margin-bottom: 20px; max-width: 800px; }";
    html += "img { width: 100%; max-width: 800px; height: auto; }";
    html += ".controls { margin: 0 auto; max-width: 800px; }";
    html += "button { background-color: #0F3376; color: white; padding: 10px 20px; ";
    html += "border: none; cursor: pointer; margin: 5px; border-radius: 4px; }";
    html += "button:hover { background-color: #0D2B5A; }";
    html += "</style>";
    html += "</head><body>";
    html += "<h1>ESP32-CAM 实时监控</h1>";
    html += "<div class='video-container'>";
    html += "<img src='/stream' id='stream'>";
    html += "</div>";
    html += "<div class='controls'>";
    html += "<button onclick='toggleFlash()'>开关闪光灯</button>";
    html += "<button onclick='refreshStream()'>刷新视频流</button>";
    html += "</div>";
    html += "<script>";
    html += "function toggleFlash() {";
    html += "  fetch('/settings?flash=' + (Math.random() > 0.5 ? '1' : '0'))";
    html += "    .then(response => console.log('闪光灯状态已切换'))";
    html += "}";
    html += "function refreshStream() {";
    html += "  const img = document.getElementById('stream');";
    html += "  img.src = '/stream?' + new Date().getTime();";
    html += "}";
    html += "</script>";
    html += "</body></html>";
    server.send(200, "text/html", html);
  });
  
  server.begin();
  Serial.println("HTTP服务器已启动");
}

void setup() {
  Serial.begin(115200);
  Serial.setDebugOutput(true);
  Serial.println("\n初始化ESP32-CAM...");

  // 设置闪光灯引脚为输出模式
  pinMode(FLASH_LED_PIN, OUTPUT);
  digitalWrite(FLASH_LED_PIN, LOW); // 默认关闭闪光灯
  
  // 摄像头配置
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sscb_sda = SIOD_GPIO_NUM;
  config.pin_sscb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;

  // 根据PSRAM可用情况配置帧大小、质量和缓冲区数量
  if(psramFound()){
    config.frame_size = FRAME_SIZE;
    config.jpeg_quality = JPEG_QUALITY;
    config.fb_count = 2;  // 使用双缓冲提高性能
    Serial.println("PSRAM已检测到，启用高分辨率");
  } else {
    config.frame_size = FRAMESIZE_SVGA;
    config.jpeg_quality = 12;
    config.fb_count = 1;
    Serial.println("PSRAM未检测到，使用低分辨率");
  }

  // 初始化摄像头
  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("摄像头初始化失败! 错误代码: 0x%x\n", err);
    if(err == ESP_ERR_CAMERA_NOT_DETECTED){
      Serial.println("摄像头未连接或OV2640初始化失败!");
    }
    delay(1000);
    ESP.restart();  // 尝试重启恢复
    return;
  }
  
  Serial.println("摄像头初始化成功!");

  // 获取传感器对象进行参数调整
  sensor_t *s = esp_camera_sensor_get();
  
  // 基本图像参数设置
  s->set_brightness(s, BRIGHTNESS);
  s->set_contrast(s, CONTRAST);
  s->set_saturation(s, SATURATION);
  s->set_special_effect(s, 0); // 无特效
  
  // 自动白平衡设置
  s->set_whitebal(s, 1);      // 启用自动白平衡
  s->set_awb_gain(s, 1);      // 启用自动白平衡增益
  s->set_wb_mode(s, 0);       // 自动模式
  
  // 自动曝光设置
  s->set_exposure_ctrl(s, 1); // 启用自动曝光
  s->set_aec2(s, 0);          // AEC DSP
  s->set_ae_level(s, 0);      // 曝光补偿 -2 到 2
  s->set_aec_value(s, 300);   // 自动曝光值
  
  // 增益控制
  s->set_gain_ctrl(s, 1);     // 启用自动增益控制
  s->set_agc_gain(s, 0);      // 0 到 30
  s->set_gainceiling(s, (gainceiling_t)0); // 增益上限
  
  // 图像校正
  s->set_bpc(s, 0);           // 坏点校正
  s->set_wpc(s, 1);           // 白点校正
  s->set_raw_gma(s, 1);       // 伽马校正
  s->set_lenc(s, 1);          // 镜头校正
  
  // 图像方向
  s->set_hmirror(s, 0);       // 水平镜像
  s->set_vflip(s, 0);         // 垂直翻转
  
  // 其他设置
  s->set_dcw(s, 1);           // 下采样
  s->set_colorbar(s, 0);      // 彩条测试模式

  // 连接WiFi
  WiFi.begin(ssid, password);
  WiFi.setSleep(false);  // 禁用WiFi睡眠模式，提高响应速度

  Serial.print("正在连接到WiFi");
  int wifiRetry = 0;
  while (WiFi.status() != WL_CONNECTED && wifiRetry < 20) {
    delay(500);
    Serial.print(".");
    wifiRetry++;
  }

  if(WiFi.status() != WL_CONNECTED){
    Serial.println("\nWiFi连接失败! 重启设备...");
    delay(3000);
    ESP.restart();
    return;
  }

  Serial.println("\nWiFi已连接");
  Serial.print("IP地址: ");
  Serial.println(WiFi.localIP());

  // 启动摄像头服务器
  startCameraServer();
  
  // 闪烁LED指示启动成功
  for (int i = 0; i < 3; i++) {
    digitalWrite(FLASH_LED_PIN, HIGH);
    delay(100);
    digitalWrite(FLASH_LED_PIN, LOW);
    delay(100);
  }
}

void loop() {
  static unsigned long lastStatusTime = 0;
  static unsigned long lastWifiCheckTime = 0;
  
  // 处理客户端请求
  server.handleClient();
  
  // 每10秒输出一次状态信息
  if (millis() - lastStatusTime > 10000) {
    lastStatusTime = millis();
    Serial.printf("运行状态: 已运行 %lu 秒 | 空闲内存: %d KB | 客户端状态: %s | 总连接数: %lu\n", 
                 lastStatusTime/1000, 
                 esp_get_free_heap_size()/1024,
                 isClientConnected ? "已连接" : "未连接",
                 connectedClients);
  }
  
  // 检查WiFi连接状态，如果断开则重连
  if (millis() - lastWifiCheckTime > 30000) {  // 每30秒检查一次
    lastWifiCheckTime = millis();
    if (WiFi.status() != WL_CONNECTED) {
      Serial.println("WiFi连接丢失，尝试重连...");
      WiFi.reconnect();
    }
  }
  
  // 短暂延迟确保ESP32不会过载
  delay(2);
}



// #define CAMERA_FLASH 4

// void setup()
// {
//     pinMode(CAMERA_FLASH, OUTPUT);
// }

// void loop()
// {
//     digitalWrite(CAMERA_FLASH, HIGH);
//     delay(1000);
//     digitalWrite(CAMERA_FLASH, LOW);
//     delay(2000);
// }
