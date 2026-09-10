/*
  ESP32 I2C 마스터 + WiFi 서버

  역할:
    1. WiFi AP + TCP 서버 (노트북 키보드 클라이언트와 통신) - 이전과 동일
    2. I2C 마스터로 4개의 STM32(슬레이브, 주소 0x10~0x13)에 대해
       매 사이클마다 "명령 쓰기 -> 상태 읽기"를 반복
    3. 읽어온 4개 다리의 상태를 TCP로 노트북에 그대로 릴레이

  배선:
    ESP32 GPIO21 (SDA) -> 4개 STM32 SDA 핀 전부 병렬 연결 (버스에 4.7kΩ 풀업 1개)
    ESP32 GPIO22 (SCL) -> 4개 STM32 SCL 핀 전부 병렬 연결 (버스에 4.7kΩ 풀업 1개)
    GND 공통

  상태 패킷 포맷 (STM32 1개당 8바이트, protocol/protocol.md):
    byte3: version=4, byte4..7: motor2 count (int32 little-endian)
    byte0        : state (0=UNREFERENCED,1=READY,2=MOVING,3=DONE,4=FAULT)
    byte1,byte2  : leg_angle   (int16, little-endian, 0.1도 단위 → 실제각도 = 값/10.0)

  노트북으로 보내는 상태 라인 포맷 (텍스트, 사람이 보기 쉽게):
    STATUS_A4,state1,angle1,...\n
*/

#include <WiFi.h>
#include <Wire.h>

// ---- WiFi/TCP 설정 ----
const char* AP_SSID     = "ROBOT_AP";
const char* AP_PASSWORD = "robot1234";
const uint16_t TCP_PORT = 8888;
const unsigned long FAILSAFE_MS = 500;

WiFiServer server(TCP_PORT);
WiFiClient client;
unsigned long lastCommandTime = 0;
char currentCmd = 'k';

// ---- I2C 설정 ----
const uint8_t LEG_ADDR[4] = {0x10, 0x11, 0x12, 0x13};  // 좌전,우전,좌후,우후
const uint8_t ACTIVE_LEG_COUNT = 1;  // 현재는 leg[0](0x10) 한 다리만 테스트
const unsigned long POLL_INTERVAL_MS = 100;  // 한 다리 진단 중에는 10Hz로 여유 확보
unsigned long lastPollTime = 0;

struct LegStatus {
  uint8_t mode;
  int16_t angle_tenths;  // 0.1도 단위
  int32_t motor2_encoder_count;
  bool ok;                // 이번 사이클에 정상 응답했는지
};
LegStatus legs[4];

uint8_t sendCommandToLeg(uint8_t addr, char cmd) {
  Wire.beginTransmission(addr);
  Wire.write((uint8_t)cmd);
  return Wire.endTransmission();  // 0=성공, 1~4=에러 코드
}

bool readStatusFromLeg(uint8_t addr, LegStatus &out, uint8_t &bytesReceived) {
  bytesReceived = Wire.requestFrom((int)addr, 8);
  if (bytesReceived != 8) {
    while (Wire.available()) Wire.read();
    return false;
  }
  out.mode = Wire.read();
  uint8_t lo = Wire.read();
  uint8_t hi = Wire.read();
  out.angle_tenths = (int16_t)((hi << 8) | lo);
  uint8_t version = Wire.read();
  uint32_t rawCount = 0;
  for (uint8_t i = 0; i < 4; ++i) {
    rawCount |= (uint32_t)(uint8_t)Wire.read() << (8U * i);
  }
  if (version != 4) return false;
  out.motor2_encoder_count = (rawCount <= INT32_MAX)
      ? (int32_t)rawCount : -1 - (int32_t)(UINT32_MAX - rawCount);
  return true;
}

void pollAllLegs(char cmd) {
  for (int i = 0; i < ACTIVE_LEG_COUNT; i++) {
    uint8_t writeErr = sendCommandToLeg(LEG_ADDR[i], cmd);
    delay(20);  // STM32가 수신 처리 후 송신 준비 상태로 돌아갈 시간 확보
    uint8_t bytesReceived = 0;
    legs[i].ok = readStatusFromLeg(LEG_ADDR[i], legs[i], bytesReceived) && writeErr == 0;
    if (!legs[i].ok) {
      currentCmd = 'k';
      sendCommandToLeg(LEG_ADDR[i], 'k');
    }

    // 진단용: 주소 0x10(leg[0])만 상세 로그 출력
    if (i == 0) {
      Serial.print("[진단] cmd=");
      Serial.print(cmd);
      Serial.print(" writeErr=");
      Serial.print(writeErr);
      Serial.print(" bytesReceived=");
      Serial.println(bytesReceived);
    }
  }
}

void sendStatusToClient() {
  if (!(client && client.connected())) return;
  String line = "STATUS_A4";
  for (int i = 0; i < ACTIVE_LEG_COUNT; i++) {
    line += ",";
    line += legs[i].ok ? String(legs[i].mode) : "NA";
    line += ",";
    line += legs[i].ok ? String(legs[i].angle_tenths / 10.0, 1) : "NA";
  }
  line += "\n";
  client.print(line);
}

void printStatusToSerial() {
  for (int i = 0; i < ACTIVE_LEG_COUNT; i++) {
    Serial.print("leg[");
    Serial.print(i);
    Serial.print("] addr=0x");
    Serial.print(LEG_ADDR[i], HEX);
    Serial.print(" ok=");
    Serial.print(legs[i].ok ? "true" : "false");
    if (legs[i].ok) {
      Serial.print(" state=");
      Serial.print(legs[i].mode);
      Serial.print(" carrier_deg=");
      Serial.print(legs[i].angle_tenths / 10.0, 1);
      Serial.print(" motor2_count=");
      Serial.print(legs[i].motor2_encoder_count);
    }
    Serial.print("  |  ");
  }
  Serial.println();
}

void setup() {
  Serial.begin(115200);

  pinMode(21, INPUT_PULLUP);  // SDA
  pinMode(22, INPUT_PULLUP);  // SCL

  Wire.begin(21, 22);        // SDA=21, SCL=22 (ESP32 기본 I2C 핀)
  Wire.setClock(100000);     // 100kHz 표준모드

  WiFi.softAP(AP_SSID, AP_PASSWORD);
  Serial.print("AP 시작됨. IP: ");
  Serial.println(WiFi.softAPIP());

  server.begin();
  lastCommandTime = millis();
  lastPollTime = millis();
}

void loop() {
  // 클라이언트 연결 확인
  if (!client || !client.connected()) {
    WiFiClient newClient = server.available();
    if (newClient) {
      client = newClient;
      Serial.println("클라이언트 연결됨");
    }
  }

  // Bench control is USB-only. TCP clients may observe status.
  if (client && client.connected() && client.available()) {
    while (client.available()) {
      client.read();
    }
  }

  // USB 시리얼로도 명령 수신 (WiFi 없이 유선 테스트용)
  if (Serial.available()) {
    while (Serial.available()) {
      char c = Serial.read();
      if (c == '\n' || c == '\r') continue;
      currentCmd = c;
      lastCommandTime = millis();
    }
  }

  // 안전장치: 명령 끊기면 정지
  if (millis() - lastCommandTime > FAILSAFE_MS) {
    currentCmd = 'k';
  }

  // 주기적으로 I2C 폴링 (명령 쓰기 + 상태 읽기) + 상태 릴레이
  if (millis() - lastPollTime >= POLL_INTERVAL_MS) {
    lastPollTime = millis();
    pollAllLegs(currentCmd);
    sendStatusToClient();
    printStatusToSerial();
  }
}
