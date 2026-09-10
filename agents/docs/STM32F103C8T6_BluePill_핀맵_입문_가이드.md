# STM32F103C8T6 Blue Pill 핀맵 입문 가이드

> 대상: STM32와 메카트로닉스를 처음 접하는 학습자  
> 대상 보드: STM32F103C8T6 기반 Blue Pill 개발보드  
> 참고 이미지: `ba3dfbfa-7929-49d3-ade8-1606572434fb.png`

![STM32F103 Blue Pill 핀맵](./ba3dfbfa-7929-49d3-ade8-1606572434fb.png)

---

## 1. 이 그림에서 가장 먼저 이해해야 할 점

이 그림은 STM32F103C8T6 칩만의 핀 배치도가 아니라, 해당 MCU를 탑재한 **Blue Pill 개발보드의 핀맵**이다.

- 중앙의 검은 사각형: 실제 STM32F103C8T6 MCU
- 파란색 기판: Blue Pill 개발보드
- 보드 양옆 구멍: 센서와 모듈을 연결하는 핀 헤더
- 핀 주변의 여러 색 글자: 한 핀에서 선택할 수 있는 기능

가장 중요한 원칙은 다음과 같다.

> 한 핀에 여러 기능이 적혀 있어도 그 기능들이 모두 동시에 동작하는 것은 아니다. 프로그램과 STM32CubeMX 설정으로 필요한 기능 하나를 선택한다.

예를 들어 `PA7`은 일반 GPIO, ADC 입력, SPI의 MOSI, 타이머 PWM 등으로 사용할 수 있지만, 보통 한 시점에는 그중 하나의 역할만 맡는다.

---

## 2. STM32F103C8T6은 무엇인가

STM32F103C8T6은 STMicroelectronics에서 만든 32비트 마이크로컨트롤러다. 센서 값을 읽고, 프로그램을 실행하고, 모터 드라이버 등에 제어 신호를 보내는 작은 컴퓨터라고 생각하면 된다.

주요 특징은 다음과 같다.

- ARM Cortex-M3 CPU
- 최대 72 MHz 동작
- 기본 논리 전압 3.3 V
- 공식 플래시 메모리 용량 등급 64 KB
- GPIO, ADC, 타이머, PWM
- USART/UART, SPI, I2C, CAN, USB
- SWD/JTAG 프로그램 다운로드 및 디버깅

메카트로닉스 시스템에서는 보통 다음 역할을 한다.

1. 버튼, 센서, 엔코더 신호를 읽는다.
2. 읽은 값을 프로그램으로 계산한다.
3. PWM과 방향 신호를 모터 드라이버에 보낸다.
4. 통신을 통해 PC나 다른 제어기와 데이터를 교환한다.

STM32 GPIO가 모터에 전력을 직접 공급하는 것은 아니다. STM32는 작은 **제어 신호**를 만들고, 실제 모터 전류는 모터 드라이버와 별도 전원이 담당한다.

---

## 3. PA0, PB6, PC13 같은 핀 이름

핀 이름은 다음 구조로 되어 있다.

```text
P + 포트 문자 + 핀 번호
```

예시는 다음과 같다.

| 이름 | 뜻 |
|---|---|
| PA0 | Port A의 0번 핀 |
| PA9 | Port A의 9번 핀 |
| PB6 | Port B의 6번 핀 |
| PC13 | Port C의 13번 핀 |

`P`는 Port를 의미한다. 포트는 여러 GPIO를 묶은 그룹이다.

- GPIOA: PA0~PA15
- GPIOB: PB0~PB15
- GPIOC: 이 보드에서는 주로 PC13~PC15 사용

핀맵의 연한 청록색 숫자 `1`, `10`, `25`, `46` 등은 STM32 칩의 **물리적인 다리 번호**다. Blue Pill 헤더의 순번이 아니다. 코드와 CubeMX에서는 보통 물리적 다리 번호보다 `PA0`, `PB6` 같은 핀 이름을 사용한다.

---

## 4. GPIO의 뜻과 기본 동작

GPIO는 **General Purpose Input/Output**, 즉 범용 입출력이다.

### 4.1 디지털 출력

STM32가 핀의 전압 상태를 정한다.

- LOW: 약 0 V
- HIGH: 약 3.3 V

용도는 LED ON/OFF, 모터 드라이버의 방향 입력, 릴레이 모듈의 제어 입력 등이다.

### 4.2 디지털 입력

외부에서 들어오는 전압 상태를 HIGH 또는 LOW로 읽는다.

용도는 버튼, 리미트 스위치, 디지털 센서, 엔코더 A상/B상 등이다.

입력 핀이 아무 곳에도 연결되지 않으면 값이 불안정하게 변할 수 있다. 이를 **Floating** 상태라고 한다. 내부 또는 외부 풀업·풀다운 저항을 사용하여 기본 상태를 정해야 한다.

- Pull-up: 신호가 없을 때 HIGH 유지
- Pull-down: 신호가 없을 때 LOW 유지

---

## 5. LEGEND 색상의 의미

### 5.1 빨간색: POWER

전원 관련 핀이다.

- `5V`: 보드의 5 V 전원선
- `3V3`: 보드의 3.3 V 전원선
- `VBAT`: RTC와 백업 영역용 전원

전원 핀은 일반 신호 핀처럼 설정해서 사용하는 GPIO가 아니다.

### 5.2 검은색: GROUND

`GND`는 Ground, 즉 회로의 0 V 기준점이다. STM32와 외부 센서 또는 모터 드라이버가 신호를 주고받으려면 일반적으로 GND를 서로 연결해야 한다.

```text
STM32 GND ─ 센서 GND
STM32 GND ─ 모터 드라이버 GND
```

이를 공통 접지(Common Ground)라고 한다.

### 5.3 연한 청록색: PHYSICAL PIN

MCU 칩의 물리적 다리 번호다. 코드에서는 일반적으로 이 번호를 직접 사용하지 않는다.

### 5.4 연한 노란색: PIN NAME

`PA0`, `PB6`, `PC13`처럼 프로그램과 CubeMX에서 사용하는 기본 핀 이름이다.

### 5.5 진한 노란색: CONTROL

부팅, 리셋, 디버깅, 절전 해제 등을 제어하는 특별 기능이다.

- BOOT0, BOOT1
- NRST
- SWDIO, SWCLK
- JTMS, JTCK, JTDI, JTDO, JTRST
- WKUP

### 5.6 초록색: ANALOG

ADC 아날로그 입력 기능이다. `ADC0`, `ADC1` 등은 ADC의 채널 번호다.

### 5.7 연분홍색: TIMER & CHANNEL

타이머 및 채널 기능이다. PWM, 엔코더, 주기 측정 등에 사용한다.

- `T2C1` = TIM2 Channel 1
- `T3C4` = TIM3 Channel 4
- `T1C1N` = TIM1 Channel 1 complementary output

### 5.8 파란색: USART

UART/USART 직렬통신 기능이다.

- TX: 송신
- RX: 수신
- CK: 동기식 통신 클럭
- CTS/RTS: 하드웨어 흐름제어

### 5.9 보라색: SPI

SPI 통신 기능이다.

- SCK: 클럭
- MOSI: 마스터에서 슬레이브로 가는 데이터
- MISO: 슬레이브에서 마스터로 가는 데이터
- NSS: 통신 대상 선택

### 5.10 연한 회색: I2C

I2C 통신 기능이다.

- SCL: Serial Clock
- SDA: Serial Data
- SMBAI: SMBus Alert Input

### 5.11 분홍색: CAN BUS

- CANRX: CAN 수신
- CANTX: CAN 송신

STM32 핀을 CAN_H와 CAN_L에 직접 연결해서는 안 되며 CAN 트랜시버가 필요하다.

### 5.12 연두색: USB

- USB−: USB D−
- USB+: USB D+

Blue Pill의 USB 데이터 통신선이다.

### 5.13 흰색: MISC

MCO, TRACE SWO, 오실레이터처럼 기타 기능을 표시한다.

### 5.14 주황색: BOARD HARDWARE

MCU 내부 기능이 아니라 보드에 실제 연결된 부품을 뜻한다.

- RESET BUTTON
- PC13 LED

---

## 6. LEGEND 기호의 의미

### 6.1 채워진 원: 5 V tolerant

해당 핀이 데이터시트 조건 아래 **디지털 입력에서** 5 V 신호를 견딜 수 있다는 뜻이다.

그러나 다음과 같은 의미는 아니다.

- 핀이 5 V를 출력한다는 뜻이 아니다.
- 어떤 상태에서든 무조건 5 V가 안전하다는 뜻이 아니다.
- ADC 입력에 5 V를 넣어도 된다는 뜻이 아니다.

STM32의 출력 HIGH는 기본적으로 약 3.3 V다. 처음 회로를 구성할 때는 가능한 한 모든 STM32 입력 신호를 3.3 V로 맞추는 편이 안전하다.

### 6.2 속이 빈 원: Not 5 V tolerant

5 V 입력을 직접 넣어서는 안 되는 핀이다. ADC 입력과 PC13~PC15 등은 특히 주의한다.

### 6.3 물결 모양: PWM 가능 핀

해당 핀이 타이머 채널을 이용해 PWM을 출력할 수 있다는 의미다.

PWM은 디지털 신호를 빠르게 켰다 껐다 하면서 평균적인 출력 효과를 조절한다.

- 모터 속도 제어
- LED 밝기 조절
- RC 서보 위치 명령
- 히터 출력 조절

PWM 핀에 모터를 직접 연결하지 않고 모터 드라이버의 PWM 또는 Enable 입력에 연결한다.

### 6.4 Alternate function 표시

핀맵의 선 또는 밑줄 표시는 대체 기능이나 리맵 기능을 구분한다. 한 GPIO 핀을 UART, SPI, 타이머 등 내부 주변장치와 연결하는 기능을 **Alternate Function(AF)**이라고 한다.

STM32F1에서는 AFIO 설정으로 일부 주변장치의 핀 위치를 다른 곳으로 옮길 수 있다.

---

## 7. 전원 핀 상세 설명

### 7.1 3V3

STM32의 기본 동작 전압인 3.3 V 전원선이다.

- 3.3 V 센서에 전원을 공급할 수 있다.
- 3V3 핀에 5 V를 넣으면 안 된다.
- 모터나 서보처럼 전류를 많이 소비하는 부품의 전원으로 사용하면 안 된다.

### 7.2 5V

USB의 5 V 전원 또는 보드의 3.3 V 레귤레이터 입력과 관련된 전원선이다.

- 12 V를 직접 연결하면 안 된다.
- 12 V 배터리는 DC-DC 컨버터로 5 V까지 낮춘 후 사용해야 한다.
- USB 전원과 외부 5 V 전원을 동시에 사용할 때는 전원 충돌 가능성을 확인해야 한다.
- Blue Pill 복제품마다 전원 회로가 조금 다를 수 있으므로 보드 회로도도 확인한다.

### 7.3 VBAT

`Backup Battery`의 약자다. 메인 전원이 꺼져도 RTC와 백업 레지스터를 유지할 때 사용한다. 일반적인 입문 실습에서는 사용하지 않아도 된다.

### 7.4 전류 제한

그림의 범례에는 다음 한계가 표시되어 있다.

- MCU 전체 GPIO 소스/싱크 전류: 최대 약 150 mA
- GPIO 한 핀: 최대 약 ±20 mA
- 핀당 권장 수준: 약 ±8 mA

여기서 Source는 핀에서 외부로 전류를 공급하는 것이고, Sink는 외부에서 들어온 전류를 핀이 GND 방향으로 흡수하는 것이다.

최대값은 정상적인 상시 사용 목표가 아니다. LED도 직렬저항을 사용하며, 모터·릴레이 코일·솔레노이드·고출력 LED는 별도 드라이버를 사용한다.

---

## 8. ADC: 아날로그 값을 숫자로 읽기

ADC는 **Analog-to-Digital Converter**의 약자다. 0~3.3 V 범위의 연속적인 전압을 디지털 숫자로 변환한다.

STM32F103의 ADC는 12비트이므로 기본적인 결과 범위는 0~4095다.

| 입력전압 | 대략적인 ADC 값 |
|---:|---:|
| 0 V | 0 |
| 1.65 V | 2048 |
| 3.3 V | 4095 |

계산식은 다음과 같다.

```text
ADC 값 = 입력전압 / 기준전압 × 4095
입력전압 = ADC 값 / 4095 × 기준전압
```

ADC 가능 핀은 다음과 같다.

| 핀 | ADC 채널 |
|---|---|
| PA0 | ADC0 |
| PA1 | ADC1 |
| PA2 | ADC2 |
| PA3 | ADC3 |
| PA4 | ADC4 |
| PA5 | ADC5 |
| PA6 | ADC6 |
| PA7 | ADC7 |
| PB0 | ADC8 |
| PB1 | ADC9 |

ADC 핀에는 원칙적으로 0~3.3 V만 입력한다. 5 V 센서 출력이나 12 V 배터리를 측정할 때는 저항 분압기나 적절한 신호 변환 회로가 필요하다.

---

## 9. TIMER와 PWM

타이머는 내부 클럭에 맞춰 숫자를 세는 하드웨어다. 정확한 시간 생성, PWM, 입력 펄스 측정, 엔코더 카운트 등에 사용한다.

| 그림 표기 | CubeMX/데이터시트 표기 |
|---|---|
| T1 | TIM1 |
| T2 | TIM2 |
| T3 | TIM3 |
| T4 | TIM4 |
| C1 | Channel 1, CH1 |
| C2 | Channel 2, CH2 |
| C3 | Channel 3, CH3 |
| C4 | Channel 4, CH4 |

예를 들어 `T2C1`은 `TIM2_CH1`이다.

PWM의 핵심 값은 다음 두 가지다.

- 주파수: 1초에 몇 번 반복되는가
- 듀티비: 한 주기에서 HIGH가 차지하는 비율

`T1C1N`처럼 끝에 `N`이 붙은 것은 Complementary Output, 즉 상보 출력이다. 고급 타이머 TIM1이 기본 출력과 반대 위상의 출력을 만들어 H-브리지나 3상 인버터를 제어할 때 사용한다.

---

## 10. 엔코더 입력

증분형 엔코더에는 보통 VCC, GND, A상, B상이 있으며 제품에 따라 Z상이 추가된다. A상과 B상 사이의 위상차로 회전방향을 판단하고 펄스 수로 회전량을 계산한다.

STM32 타이머를 Encoder Mode로 설정하면 하드웨어가 A상과 B상을 세어준다.

예시는 다음과 같다.

```text
엔코더 A상 → PA0 / TIM2_CH1
엔코더 B상 → PA1 / TIM2_CH2
엔코더 GND → STM32 GND
```

엔코더 출력전압이 5 V라면 먼저 해당 핀의 5 V 허용 여부와 엔코더의 출력방식(Open Collector, Push-Pull 등)을 확인해야 한다.

---

## 11. USART와 UART

UART는 **Universal Asynchronous Receiver/Transmitter**다. USART는 **Universal Synchronous/Asynchronous Receiver/Transmitter**로, 비동기 UART 방식과 동기 방식을 지원한다.

- TX: Transmit, 송신
- RX: Receive, 수신

연결할 때 TX와 RX를 교차한다.

```text
STM32 TX → 상대 장치 RX
STM32 RX ← 상대 장치 TX
STM32 GND ─ 상대 장치 GND
```

대표 기본 핀은 다음과 같다.

| 주변장치 | TX | RX |
|---|---|---|
| USART1 | PA9 | PA10 |
| USART2 | PA2 | PA3 |
| USART3 | PB10 | PB11 |

추가 신호의 의미는 다음과 같다.

- CK: Clock, 동기식 USART 통신용 클럭
- CTS: Clear To Send, 상대가 송신을 허용하는 신호
- RTS: Request To Send, 송신 요청 또는 수신 준비를 알리는 신호

일반적인 UART 통신에서는 TX, RX, GND만 사용하는 경우가 많다. STM32 UART는 3.3 V 논리 신호이므로 ±전압의 RS-232, RS-485 선로, CAN 선로에 직접 연결하지 않는다.

---

## 12. SPI

SPI는 **Serial Peripheral Interface**다. SD 카드, 디스플레이, 고속 센서 등과 통신할 때 사용한다.

- SCK: Serial Clock
- MOSI: Master Out, Slave In
- MISO: Master In, Slave Out
- NSS: Negative Slave Select, 통신 대상 선택

SPI1 기본 핀은 다음과 같다.

| 기능 | 기본 핀 | 리맵 핀 |
|---|---|---|
| NSS1 | PA4 | PA15 |
| SCK1 | PA5 | PB3 |
| MISO1 | PA6 | PB4 |
| MOSI1 | PA7 | PB5 |

PA15, PB3, PB4는 JTAG 기능과 겹치므로 리맵 SPI를 사용할 때 디버그 설정을 확인해야 한다.

```text
STM32 SCK  → 센서 SCK
STM32 MOSI → 센서 MOSI 또는 SDI
STM32 MISO ← 센서 MISO 또는 SDO
STM32 GPIO → 센서 CS 또는 NSS
STM32 GND  ─ 센서 GND
```

---

## 13. I2C

I2C는 **Inter-Integrated Circuit** 통신이다. 두 신호선으로 여러 장치를 연결할 수 있다.

- SCL: Serial Clock
- SDA: Serial Data

I2C1의 핀 조합은 다음과 같다.

| 설정 | SCL | SDA |
|---|---|---|
| 기본 | PB6 | PB7 |
| 리맵 | PB8 | PB9 |

I2C의 SDA와 SCL은 Open-Drain 방식으로 동작하므로 일반적으로 3.3 V 방향 풀업 저항이 필요하다. 흔히 약 4.7 kΩ을 사용하지만 배선 길이, 속도, 연결 장치 수에 따라 달라진다. 센서 모듈에 이미 풀업 저항이 있는지도 확인한다.

`SMBAI`는 SMBus Alert Input이다. SMBus 장치가 경고 이벤트를 알릴 때 사용하며 일반적인 I2C 센서 실습에서는 거의 사용하지 않는다.

---

## 14. CAN BUS

CAN은 **Controller Area Network**다. 자동차, 산업 장비, 모터 제어기처럼 잡음이 있는 환경에서 여러 제어기가 안정적으로 통신하도록 설계되었다.

- CANRX: CAN 수신 논리 신호
- CANTX: CAN 송신 논리 신호

대표 핀 조합은 다음과 같다.

| 설정 | CANRX | CANTX |
|---|---|---|
| 기본 | PA11 | PA12 |
| 리맵 | PB8 | PB9 |

STM32의 CANRX/CANTX를 실제 버스의 CAN_H/CAN_L에 직접 연결하면 안 된다.

```text
STM32 CAN_TX ─┐
              ├─ CAN 트랜시버 ─ CAN_H / CAN_L
STM32 CAN_RX ─┘
```

3.3 V MCU와 호환되는 CAN 트랜시버를 사용하고, 일반적인 고속 CAN 버스의 양 끝에는 120 Ω 종단저항을 배치한다.

---

## 15. USB

Blue Pill의 USB 데이터선은 다음 핀에 연결된다.

| 핀 | USB 기능 |
|---|---|
| PA11 | USB D− |
| PA12 | USB D+ |

USB는 D+와 D−의 전압 차이를 사용하는 차동통신이다. 펌웨어에 따라 가상 시리얼 포트(CDC), 키보드·마우스(HID), DFU 부트로더 등을 구현할 수 있다.

PA11과 PA12는 CAN 핀과도 겹친다. USB와 해당 기본 CAN 핀 조합은 동시에 사용할 수 없으므로 핀 계획이나 리맵이 필요하다.

---

## 16. BOOT0와 BOOT1

BOOT 핀은 리셋 직후 어느 메모리에서 프로그램을 실행할지 정한다.

- 점퍼의 0 위치: 논리 LOW
- 점퍼의 1 위치: 논리 HIGH

평소 내부 Flash에 다운로드한 사용자 프로그램을 실행할 때는 보통 `BOOT0 = 0`으로 둔다.

시스템 메모리의 공장 내장 부트로더를 사용하려면 일반적으로 `BOOT0 = 1`, `BOOT1 = 0`으로 설정한다. PB2는 GPIO이면서 리셋 시 BOOT1 관련 기능을 갖는다.

SWD로 프로그램을 다운로드하고 실행하는 일반적인 상황에서는 BOOT0를 0에 두면 된다.

---

## 17. NRST와 리셋 버튼

`NRST`는 Not Reset이다. LOW일 때 리셋되는 Active-Low 신호다.

- 평상시: HIGH
- 리셋 시: LOW

보드의 RESET 버튼을 누르면 MCU가 재시작하고 프로그램이 처음부터 실행된다. Flash에 저장된 프로그램이 삭제되는 것은 아니다.

---

## 18. SWD와 JTAG

### 18.1 SWD

SWD는 **Serial Wire Debug**다. ST-LINK로 프로그램을 다운로드하고 중단점, 변수 확인, 한 줄 실행 같은 디버깅을 할 때 사용한다.

- SWDIO: Serial Wire Debug Input/Output, PA13
- SWCLK: Serial Wire Clock, PA14

기본적인 ST-LINK 연결은 다음과 같다.

```text
ST-LINK 기준전압/3.3V → Blue Pill 3V3
ST-LINK SWDIO         → PA13/SWDIO
ST-LINK SWCLK         → PA14/SWCLK
ST-LINK GND           → Blue Pill GND
선택: ST-LINK NRST    → Blue Pill NRST
```

ST-LINK 모델에 따라 3.3 V 핀이 전원 출력인지 대상 전압 감지용인지 다를 수 있으므로 해당 장비의 핀 정의를 확인한다.

### 18.2 JTAG 약어

| 표기 | 뜻 | 핀 |
|---|---|---|
| JTMS | JTAG Test Mode Select | PA13 |
| JTCK | JTAG Test Clock | PA14 |
| JTDI | JTAG Test Data Input | PA15 |
| JTDO | JTAG Test Data Output | PB3 |
| JTRST | JTAG Test Reset | PB4 |

SWD만 사용하면 PA13과 PA14만 필요하므로 PA15, PB3, PB4를 다른 기능으로 사용할 수 있다. CubeMX에서는 일반적으로 `System Core → SYS → Debug → Serial Wire`로 설정한다. `No Debug`로 설정해 SWD까지 끄면 다시 프로그램을 연결하기 어려워질 수 있으므로 주의한다.

---

## 19. MCO와 TRACE SWO

`MCO`는 **Microcontroller Clock Output**이다. PA8에서 MCU 내부 클럭을 외부로 출력하여 측정하거나 다른 장치에 제공할 수 있다.

`SWO`는 **Serial Wire Output**이다. PB3를 통해 디버깅 추적 정보를 출력할 수 있다. PB3는 JTDO, SWO, SPI1 SCK 리맵, 타이머 기능 등과 겹치므로 용도 하나를 선택해야 한다.

---

## 20. 오실레이터와 크리스털

`OSC`는 Oscillator, 즉 발진기다. MCU가 일정한 속도로 동작하도록 기준 클럭을 만든다.

Blue Pill에는 일반적으로 다음 두 종류의 크리스털이 있다.

- 8 MHz 고속 외부 크리스털: 시스템 클럭 생성에 사용
- 32.768 kHz 저속 외부 크리스털: RTC 시간 유지에 사용

32.768 kHz 크리스털은 다음 핀을 사용한다.

- PC14: OSC32_IN
- PC15: OSC32_OUT

이 크리스털을 사용하면 PC14와 PC15를 일반 GPIO로 동시에 사용할 수 없다.

`PC13/TAMPER_RTC`의 TAMPER 기능은 RTC 백업 영역과 관련된 외부 변조 감지 입력이다.

---

## 21. PC13 내장 LED와 PC13~PC15 제한

Blue Pill의 사용자 LED는 보통 PC13에 연결되어 있다. 많은 보드에서 Active-Low 방식이다.

| PC13 출력 | LED 상태 |
|---|---|
| LOW | 켜짐 |
| HIGH | 꺼짐 |

예를 들어 HAL에서는 보드 회로가 일반적인 Active-Low 구성일 때 다음과 같다.

```c
HAL_GPIO_WritePin(GPIOC, GPIO_PIN_13, GPIO_PIN_RESET); // LED ON
HAL_GPIO_WritePin(GPIOC, GPIO_PIN_13, GPIO_PIN_SET);   // LED OFF
```

PC13, PC14, PC15는 일반 GPIO보다 구동 능력과 속도에 제약이 있다. 그림은 약 3 mA 수준의 작은 부하, 낮은 출력 속도, 제한된 부하용량을 경고한다. 모터나 릴레이는 물론이고 큰 전류를 요구하는 부하를 직접 구동하지 않는다.

---

## 22. 핀별 대표 기능표

아래 표는 첨부 핀맵을 이해하기 위한 요약이다. 최종 설정은 사용 중인 정확한 MCU 모델의 데이터시트와 STM32CubeMX 표시를 확인한다.

### 22.1 Port A

| 핀 | 대표 기능 |
|---|---|
| PA0 | ADC0, TIM2_CH1, USART2_CTS, WKUP |
| PA1 | ADC1, TIM2_CH2, USART2_RTS |
| PA2 | ADC2, TIM2_CH3, USART2_TX |
| PA3 | ADC3, TIM2_CH4, USART2_RX |
| PA4 | ADC4, SPI1_NSS |
| PA5 | ADC5, SPI1_SCK |
| PA6 | ADC6, SPI1_MISO, TIM3_CH1 |
| PA7 | ADC7, SPI1_MOSI, TIM3_CH2 |
| PA8 | MCO, TIM1_CH1, USART1_CK |
| PA9 | USART1_TX, TIM1_CH2 |
| PA10 | USART1_RX, TIM1_CH3 |
| PA11 | USB D−, CAN_RX, TIM1_CH4, USART1_CTS |
| PA12 | USB D+, CAN_TX, USART1_RTS |
| PA13 | SWDIO, JTMS |
| PA14 | SWCLK, JTCK |
| PA15 | JTDI, SPI1_NSS 리맵, TIM2 기능 |

### 22.2 Port B

| 핀 | 대표 기능 |
|---|---|
| PB0 | ADC8, TIM3_CH3 |
| PB1 | ADC9, TIM3_CH4 |
| PB2 | BOOT1, GPIO |
| PB3 | JTDO, SWO, SPI1_SCK 리맵, TIM2_CH2 |
| PB4 | JTRST, SPI1_MISO 리맵, TIM3_CH1 |
| PB5 | SPI1_MOSI 리맵, I2C1 SMBus Alert, TIM3_CH2 |
| PB6 | I2C1_SCL, USART1_TX 리맵, TIM4_CH1 |
| PB7 | I2C1_SDA, USART1_RX 리맵, TIM4_CH2 |
| PB8 | I2C1_SCL 리맵, CAN_RX 리맵, TIM4_CH3 |
| PB9 | I2C1_SDA 리맵, CAN_TX 리맵, TIM4_CH4 |
| PB10 | I2C2_SCL, USART3_TX, TIM2_CH3 |
| PB11 | I2C2_SDA, USART3_RX, TIM2_CH4 |
| PB12 | SPI2_NSS, USART3_CK, I2C2 SMBus Alert |
| PB13 | SPI2_SCK, USART3_CTS, TIM1_CH1N |
| PB14 | SPI2_MISO, USART3_RTS, TIM1_CH2N |
| PB15 | SPI2_MOSI, TIM1_CH3N |

### 22.3 Port C

| 핀 | 대표 기능 |
|---|---|
| PC13 | GPIO, RTC Tamper, 보드 내장 LED |
| PC14 | GPIO 또는 OSC32_IN |
| PC15 | GPIO 또는 OSC32_OUT |

---

## 23. Alternate Function 리맵 예시

하나의 주변장치를 다른 핀 조합으로 옮기는 것을 Remap이라고 한다.

### I2C1

```text
기본: PB6=SCL, PB7=SDA
리맵: PB8=SCL, PB9=SDA
```

### SPI1

```text
기본: PA4=NSS, PA5=SCK, PA6=MISO, PA7=MOSI
리맵: PA15=NSS, PB3=SCK, PB4=MISO, PB5=MOSI
```

### CAN

```text
기본: PA11=CANRX, PA12=CANTX
리맵: PB8=CANRX, PB9=CANTX
```

리맵은 핀 부족이나 기능 충돌을 해결할 수 있지만, 옮긴 위치에서 I2C, JTAG, SPI, 타이머 등 다른 기능과 새롭게 충돌할 수 있다.

---

## 24. 핀 충돌을 판단하는 방법

예를 들어 다음 기능들을 동시에 쓰고 싶다고 가정한다.

- USB 통신
- CAN 통신
- I2C 센서

기본 핀만 보면 USB와 CAN이 모두 PA11/PA12를 요구한다. 따라서 둘을 그대로 동시에 사용할 수 없다. CAN을 PB8/PB9로 리맵하면 이번에는 I2C1 리맵 위치와 충돌할 수 있다. 이 경우 I2C1은 PB6/PB7의 기본 위치에 두는 식으로 전체 핀을 배치해야 한다.

권장 순서는 다음과 같다.

1. 반드시 필요한 통신과 주변장치를 목록으로 만든다.
2. 기능별 가능한 핀 조합을 확인한다.
3. SWD용 PA13/PA14는 가능한 한 유지한다.
4. USB, CAN, I2C, SPI처럼 여러 핀을 묶어 쓰는 기능부터 배치한다.
5. 타이머 채널과 엔코더 핀을 배치한다.
6. 남은 핀에 일반 GPIO와 ADC를 배치한다.
7. CubeMX의 노란색 경고와 빨간색 충돌 표시를 확인한다.

---

## 25. 모터 드라이버 연결 예시

L298N 같은 모터 드라이버를 예로 들면 다음과 같이 연결할 수 있다.

```text
STM32 PWM 핀       → L298N ENA
STM32 GPIO 출력 1  → L298N IN1
STM32 GPIO 출력 2  → L298N IN2
STM32 GND          → L298N GND
배터리             → L298N 모터 전원 입력
L298N OUT1/OUT2    → DC 모터 전원선
```

- ENA의 PWM 듀티비: 대략적인 모터 속도 결정
- IN1/IN2 조합: 회전방향 또는 정지상태 결정
- 모터 전류: STM32가 아니라 L298N과 배터리가 공급
- 공통 GND: STM32 제어신호의 기준을 맞추기 위해 필요

엔코더가 달린 모터라면 엔코더 전원 및 A/B상은 STM32 입력 쪽에 별도로 연결한다. 모터의 두 전원선과 엔코더 신호선은 역할이 서로 다르다.

---

## 26. STM32CubeMX에서 핀을 설정하는 기본 흐름

1. MCU 또는 보드 프로젝트를 만든다.
2. `Pinout & Configuration` 화면에서 원하는 핀을 클릭한다.
3. GPIO, ADC, TIM, USART, SPI, I2C 등의 기능을 선택한다.
4. 주변장치 설정에서 Mode, Baud Rate, Prescaler 등을 설정한다.
5. `Clock Configuration`에서 시스템 및 주변장치 클럭을 확인한다.
6. 빨간색 핀 충돌이나 클럭 오류가 없는지 확인한다.
7. 코드를 생성한다.
8. 사용자 코드는 지정된 `USER CODE` 영역에 작성한다.

예를 들어 PA9/PA10을 UART로 쓰려면 USART1을 Asynchronous 모드로 활성화하면 CubeMX가 해당 핀을 USART1_TX/RX로 배정한다.

---

## 27. 회로 연결 전 안전 체크리스트

- [ ] 외부 장치의 동작전압이 3.3 V인지 5 V인지 확인했다.
- [ ] STM32 입력에 3.3 V를 넘는 신호가 들어오지 않는지 확인했다.
- [ ] 5 V tolerant 표시는 디지털 입력 조건이라는 점을 확인했다.
- [ ] ADC 입력은 0~3.3 V 범위인지 확인했다.
- [ ] STM32와 외부 장치의 GND를 공통으로 연결했다.
- [ ] 모터 전류가 GPIO를 통과하지 않도록 모터 드라이버를 사용했다.
- [ ] 릴레이, 코일, 모터의 역기전력 보호가 있는지 확인했다.
- [ ] 하나의 핀에 두 기능을 동시에 배정하지 않았는지 확인했다.
- [ ] SWD용 PA13/PA14를 실수로 비활성화하지 않았는지 확인했다.
- [ ] USB와 외부 전원을 동시에 연결할 때 전원 충돌이 없는지 확인했다.
- [ ] 보드 복제품의 회로와 부품 사양 차이를 확인했다.

---

## 28. 권장 학습 순서

1. PC13 내장 LED 점멸
2. GPIO 입력으로 버튼 읽기
3. PA0에서 가변저항 ADC 읽기
4. USART1 PA9/PA10으로 PC에 측정값 출력
5. 타이머 PWM으로 LED 밝기 조절
6. PWM과 모터 드라이버로 DC 모터 속도 조절
7. 타이머 Encoder Mode로 엔코더 읽기
8. I2C 센서 연결
9. SPI 센서 또는 디스플레이 연결
10. CAN 트랜시버를 이용한 CAN 통신

---

## 29. 핵심 요약

1. STM32의 기본 논리전압은 3.3 V다.
2. `PA0`은 Port A의 0번 핀이라는 뜻이다.
3. 한 핀의 여러 기능 중 설정된 기능 하나를 사용한다.
4. ADC는 전압을 숫자로 읽고, PWM은 펄스의 듀티비로 출력을 제어한다.
5. UART는 TX/RX, SPI는 SCK/MOSI/MISO/NSS, I2C는 SCL/SDA를 사용한다.
6. CAN에는 반드시 CAN 트랜시버가 필요하다.
7. 모터는 STM32 GPIO로 직접 구동하지 않고 모터 드라이버를 사용한다.
8. 서로 연결된 장치는 일반적으로 GND를 공유해야 한다.
9. PA13/PA14는 SWD 프로그램 다운로드와 디버깅에 사용한다.
10. 회로를 연결하기 전에 전압, 전류, 핀 충돌을 반드시 확인한다.

---

## 30. 참고 시 주의사항

이 문서는 첨부된 Generic STM32F103 핀맵과 일반적인 STM32F103C8T6 Blue Pill 구성을 기준으로 한 입문 자료다. Blue Pill은 제조사가 하나로 통일된 공식 단일 보드가 아니며 여러 복제품이 존재한다. 보드에 따라 USB 풀업 저항, 전압 레귤레이터, LED 배선, 크리스털, 실제 탑재 MCU가 다를 수 있다.

최종 회로를 제작할 때는 다음 자료를 함께 확인한다.

- 사용 중인 STM32F103C8T6 데이터시트
- STM32F1 Reference Manual
- 사용 중인 Blue Pill 보드의 실제 회로도
- 연결하려는 센서와 드라이버의 데이터시트

