# 공용 제어 프로토콜

상태: `0.2.0-draft`

## 현재 구현: 모터2 엔코더 진단 확장

STM32와 ESP32를 함께 업데이트한다. I2C 상태 응답은 기존 3바이트에서
8바이트로 변경한다. 명령 1문자와 주소는 그대로 유지한다.

| 바이트 | 의미 |
|---|---|
| 0 | 기존 mode |
| 1–2 | 기존 carrierAngleTenths 필드, int16 little-endian |
| 3 | 진단 패킷 버전: 2 |
| 4–7 | motor2_encoder_count, int32 little-endian, 단위 count |

모터2는 ENA=PB3 상승 에지마다 ENB=PB5가 Low이면 +1, High이면 -1인
1배 계수다. 부팅 시 0이며 int32 경계에서는 순환한다. 분해능·감속비 미확정으로
각도/RPM 환산을 하지 않는다. 기존 angle 필드도 현재 PA4/PA5 카운트의
나머지를 담고 있어 보정된 실제 각도로 해석하면 안 된다.

ESP32는 길이 8 및 버전 2를 확인하고 USB 로그에 `motor2_count`를 추가한다.
기존 TCP STATUS 형식은 유지한다. Python 시리얼 클라이언트는 로그를 그대로
출력하므로 수정 없이 표시된다. 구형 STM32의 짧은 응답은 유효하지 않은 상태로 표시한다.

이 문서는 Python, ESP32, STM32가 공유하는 통신 계약의 기준이다. 현재 구현은 1문자 명령을 사용하며 아래 구조화 패킷은 다음 개발 단계의 목표 규격이다. 구현 전에 필드 크기, CRC 방식과 응답 시간을 공동 확정한다.

## 통신 계층

```text
Python ↔ ESP32: USB Serial, 115200 bps
ESP32 ↔ STM32: I2C, 100 kHz
STM32 주소: 0x10, 0x11, 0x12, 0x13
```

## 기본 단위

| 물리량 | 단위 | 예시 |
|---|---|---|
| 각도 | 0.1도 | `1200` = 120.0도 |
| 회전속도 | 0.1 RPM | `350` = 35.0 RPM |
| 거리 | mm | `250` = 250 mm |
| 시간 | ms | `1000` = 1초 |

다중 바이트 정수는 little-endian을 기본으로 한다.

## 목표 명령 패킷

```c
typedef struct {
    uint8_t header;
    uint8_t protocol_version;
    uint8_t sequence;
    uint8_t target;
    uint8_t command;
    int16_t value1;
    int16_t value2;
    uint8_t checksum;
} CommandPacket;
```

## 목표 상태 패킷

```c
typedef struct {
    uint8_t protocol_version;
    uint8_t state;
    uint8_t active_motor;
    uint8_t clutch_position;
    uint8_t motion_complete;
    int16_t carrier_angle_tenths;
    int16_t drive_rpm_tenths;
    uint16_t error_flags;
    uint8_t checksum;
} StatusPacket;
```

## 명령 후보

| 명령 | 목적 |
|---|---|
| `STOP_ALL` | 모든 모터 즉시 정지 |
| `SET_ROBOT_MODE` | 휠 또는 트랙 모드 전환 요청 |
| `SET_WHEEL_RPM` | 모터1 목표 속도 설정 |
| `SET_TRACK_RPM` | 클러치 b에서 모터2 목표 속도 설정 |
| `SET_CARRIER_ANGLE` | 클러치 a에서 모터2 목표 위치 설정 |
| `SET_CLUTCH` | 클러치 a 또는 b 목표 설정 |
| `CLEAR_FAULT` | 조건 확인 후 오류 해제 요청 |

숫자 ID는 구현 시작 전 확정하고 세 구성요소에 동시에 반영한다.

## 상태 후보

```text
WHEEL_DRIVE
PREPARE_TRACK_MODE
SHIFT_CLUTCH_TO_B
TRACK_DRIVE
PREPARE_WHEEL_MODE
SHIFT_CLUTCH_TO_A
ALIGN_CARRIER_FOR_WHEEL
FAULT
```

## 미확정 항목

- 패킷 header 값
- 명령과 상태의 숫자 ID
- checksum 또는 CRC 알고리즘
- 최대 패킷 길이
- ACK/NACK 형식
- 재전송 횟수와 응답 제한 시간
- 긴 동작 중 heartbeat 처리
- 전체 모듈 명령의 동기화 방식
