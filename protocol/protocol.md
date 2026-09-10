# 공용 제어 프로토콜

상태: `0.4.0-draft`

## 현재 구현: 누적 20도 캐리어 시험 (버전 4)

이 절이 아래 버전 3 시험 규격보다 우선한다. 상태 응답 byte3은 4이다.

- `p`: 현재 목표 홈 번호를 +1하여 기준에서 `+20° × 목표 홈 번호`로 이동한다.
- `n`: 현재 목표 홈 번호를 -1하여 기준에서 `+20° × 목표 홈 번호`로 이동한다.
- `r`: 목표 홈 번호를 0으로 만들고 기준 홈으로 이동한다.
- `h`: 새 동작 없는 heartbeat. 진행 중 목표를 유지한다.
- `z`: 기준 저장과 함께 목표 홈 번호를 0으로 설정한다.
- 한계는 기준에서 ±18칸(±360°)이다. 초과 명령은 fault 및 정지한다.
- 각 목표는 `round(목표 홈 번호 × 6010/9)`로 기준에서 직접 계산하므로
  한 칸을 정수 668로 계속 더할 때 생기는 반올림 누적 오차를 피한다.
- PC는 키 입력을 약 300ms 반복한 뒤 `h`를 heartbeat로 전송한다.
  `p/n/r`은 READY(1) 또는 DONE(3)에서만 PC가 허용한다.
- 이동 중 `k`로 취소하면 기준을 무효화한다. 실제 홈을 다시 맞춘 후 `z`가 필요하다.
- TCP 상태 문자열은 `STATUS_A4`이다. PC/ESP32/STM32를 함께 갱신한다.

## 현재 구현: 클러치 a 수동 고정 위치 시험 (버전 3)

이 절이 아래 버전 2 진단 규격보다 우선한다. PC/ESP32/STM32를 함께 갱신한다.
단일 모듈 0x10, 사용자가 링기어를 a로 고정한 상태에서만 사용한다.
모터1/3 및 기존 i/,/j/l/u/o 구동은 이 시험 펌웨어에서 금지한다.

| 문자 명령 | 동작 |
|---|---|
| z | 정지 안정 300ms 후 현재 모터2 count를 캐리어 0°로 저장. 사용자의 a 고정 확인을 의미하며 센서 확인이 아님 |
| p | 저장한 기준에서 +20° (카운트 증가 방향)로 이동 |
| n | 저장한 기준에서 -20° (카운트 감소 방향)로 이동 |
| r | 저장한 기준 0°로 복귀 |
| k | 전체 정지. 진행 중 동작 취소 |

모든 명령은 같은 문자를 주기적으로 재전송한다. 연속 동일 명령은 다시 실행하지 않는다.
p/n은 누적 한 칸 명령이 아니라 절대 +20/-20° 목표다. 재시도/재보정은 k 후 새 명령.
PC 100ms 재전송, ESP32 500ms 입력 단절 시 k, STM32 500ms 유효 명령 단절 시 fault.
알 수 없는 명령, I2C 오류, 이동 중 다른 위치 명령은 정지 및 fault.
fault는 기준을 무효화하며 k 후 정지 상태에서 z로 재보정한다.

상태는 8바이트 little-endian을 유지하되 byte3=3:
- byte0: 0=UNREFERENCED, 1=READY, 2=MOVING, 3=DONE, 4=FAULT.
- byte1..2: int16 캐리어 상대각, 0.1°. 미보정은 0 (byte0로 구분).
- byte4..7: int32 motor2 raw count.
USB 로그 state/carrier_deg/motor2_count 출력. TCP 줄은 STATUS_A3,state,angle,...로 변경.
환산은 모터2 2404/3 count/rev, 입력축→캐리어 15:1. 20°는 6010/9 count.
부팅/업로드 후 반드시 z 재실행. 과거 -6은 저장 상수가 아니다.

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
