# 공용 제어 프로토콜

상태: `0.2.0-draft`

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

## 현재 진단용 상태 패킷

각 STM32는 엔코더 배선과 통신을 검증하기 위해 다음 5바이트 상태를
ESP32에 전송한다. 두 엔코더 값의 단위는 0.1도이다.

```text
byte 0      : mode
byte 1..2   : motor1_angle_tenths (int16, little-endian)
byte 3..4   : motor2_angle_tenths (int16, little-endian)
```

각도 값의 범위는 `0..3599`이며 `1234`는 `123.4도`를 의미한다. 모터1과 모터2 모두 1회전당 795카운트를 사용하고 반시계 방향을 양수로 정의한다.

ESP32의 TCP 상태 형식은 활성 다리마다 `mode,angle1_tenths,angle2_tenths`를 반복한다.

```text
STATUS,mode1,angle1_tenths,angle2_tenths,...\n
```

ESP32의 USB Serial 진단 출력은 사람이 바로 읽을 수 있도록 도 단위로 표시한다.

```text
leg[0] addr=0x10 ok=true mode=0 angle1=123.4deg angle2=278.6deg
```

이 형식은 기존 3바이트 진단 상태와 호환되지 않으므로 STM32와 ESP32
펌웨어를 함께 갱신해야 한다.

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
