# STM32 `Core/Src` 파일별 설명과 `main.c` 정밀 분석

## 1. 문서의 목적과 분석 기준

이 문서는 STM32를 처음 접하는 사람이 다음 내용을 이해할 수 있도록 작성한 입문자용 코드 해설이다.

- `stm32/mobility/Core/Src/`의 각 `.c` 파일이 무슨 역할을 하는가
- 전원을 켰을 때 어떤 순서로 코드가 실행되는가
- STM32CubeIDE가 만든 코드와 사용자가 작성한 코드를 어떻게 구분하는가
- 현재 `main.c`가 모터, 엔코더, I2C를 실제로 어떻게 다루는가
- 코드에 아직 구현되지 않은 기능과 안전상 주의점은 무엇인가

분석 기준은 다음과 같다.

| 항목 | 기준 |
|---|---|
| 저장소 | 현재 저장소의 `stm32/mobility/` 프로젝트 |
| 분석한 커밋 | `207cdd5` |
| 분석한 날짜 | 2026-09-08 KST |
| MCU | STM32F103C8T6, Cortex-M3, LQFP48 |
| HAL 패키지 | STM32Cube FW_F1 V1.8.7 |
| 공용 통신 규격 | `protocol/protocol.md`, 상태 `0.2.0-draft` |

이 문서는 **코드를 읽어서 설명한 결과**이다. 오실로스코프 측정이나 실제 기구 시험으로 새롭게 검증한 결과는 아니다. 특히 모터 방향, 엔코더 방향, 모터 드라이버의 정지 방식은 실제 배선과 드라이버 사양에 따라 달라질 수 있다.

---

## 2. 가장 먼저 알아둘 STM32 프로그램 구조

일반 PC 프로그램은 운영체제가 실행 파일을 불러서 `main()`을 호출한다. STM32에는 일반적인 PC 운영체제가 없으므로, 리셋 직후부터 마이크로컨트롤러가 직접 초기화 코드를 실행한다.

현재 프로젝트의 큰 실행 순서는 다음과 같다.

```text
전원 인가 또는 Reset
  ↓
startup_stm32f1xx.s의 Reset_Handler
  ↓
SystemInit()                         system_stm32f1xx.c
  ↓
C 런타임 초기화
  - 초기값이 있는 전역변수를 Flash에서 RAM으로 복사
  - 초기값이 없는 전역변수를 0으로 초기화
  ↓
main()                               main.c
  ↓
HAL_Init()
  - HAL 기본 초기화
  - 1 ms SysTick 준비
  - HAL_MspInit() 호출               stm32f1xx_hal_msp.c
  ↓
72 MHz 시스템 클록 설정
  ↓
GPIO, I2C, PWM 타이머 초기화
  ↓
I2C 주소 결정, 모터 정지, PWM과 I2C 인터럽트 시작
  ↓
while (1) 무한 반복

동시에 하드웨어 사건이 발생하면:
  인터럽트 벡터
    → stm32f1xx_it.c의 IRQHandler
    → HAL 공통 처리
    → main.c의 사용자 Callback
```

`while (1)`이 끝나지 않는 것은 정상이다. 임베디드 프로그램은 종료하는 대신 전원이 꺼질 때까지 제어 루프와 인터럽트를 계속 실행한다.

---

## 3. `Core/Src`의 6개 파일 한눈에 보기

| 파일 | 쉬운 비유 | 현재 프로젝트에서 하는 일 | 보통 직접 수정하는가 |
|---|---|---|---|
| `main.c` | 현장 작업자와 작업 순서표 | 모터 명령, I2C 송수신, 엔코더 계수, 주변장치 설정, 무한 루프 | 예. 주 사용자 코드 파일 |
| `stm32f1xx_hal_msp.c` | 전기실 배선 담당자 | 주변장치 클록, GPIO 대체 기능, NVIC 인터럽트 활성화 | 핀/주변장치 자원을 바꿀 때만 신중히 수정 |
| `stm32f1xx_it.c` | 긴급전화 교환원 | CPU 예외와 I2C·엔코더 인터럽트를 HAL 처리기로 전달 | 새 인터럽트를 추가할 때 수정 |
| `syscalls.c` | C 표준 라이브러리 통역기 | `printf`, `scanf`, 파일 함수가 요구하는 저수준 함수의 최소 틀 제공 | UART 로그 등을 연결할 때 일부 수정 |
| `sysmem.c` | RAM 공간 임대 관리자 | `malloc()`이 사용할 heap 공간을 늘리는 `_sbrk()` 제공 | 일반적으로 수정하지 않음 |
| `system_stm32f1xx.c` | 부팅 직후 기반 시설 | `SystemInit()`, `SystemCoreClock`, 클록값 계산 함수 제공 | ST/CMSIS 공급 파일이므로 보통 수정하지 않음 |

핵심은 `main.c` 혼자 모든 일을 하지 않는다는 점이다. 예를 들어 `main.c`에서 `HAL_TIM_PWM_Init()`를 호출하면 HAL 내부에서 `stm32f1xx_hal_msp.c`의 함수를 찾아 타이머 클록과 PWM 핀을 설정한다. 엔코더 신호가 들어오면 먼저 `stm32f1xx_it.c`를 통과한 뒤 `main.c`의 콜백으로 도착한다.

---

## 4. CubeMX/CubeIDE가 만드는 코드 형식

### 4.1 `USER CODE BEGIN/END`의 의미

`main.c`, `stm32f1xx_hal_msp.c`, `stm32f1xx_it.c`에는 다음과 같은 구역이 반복된다.

```c
/* USER CODE BEGIN 0 */
사용자가 작성한 코드
/* USER CODE END 0 */
```

`mobility.ioc`를 열어 CubeMX 코드 생성을 다시 실행하면 생성기가 주변 코드를 새로 만들 수 있다. `USER CODE` 구역 안의 코드는 보존 대상으로 취급된다. 따라서 직접 작성할 코드는 가능한 한 알맞은 `USER CODE` 구역 안에 둔다.

단, 이것이 절대적인 백업 장치는 아니다. 구역 이름이나 주석을 손상시키거나, 생성 설정을 크게 바꾸면 충돌할 수 있으므로 재생성 전에는 Git 변경 상태를 확인해야 한다.

### 4.2 `Private`와 `static`

Cube가 만든 제목에 `Private variables`, `Private function prototypes` 같은 표현이 있다. C에는 C++의 `private` 키워드가 없으므로, 여기서 private는 “주로 이 파일 안에서만 쓸 항목”이라는 조직상의 의미다.

```c
static void MX_GPIO_Init(void);
```

함수 앞의 `static`은 이 함수 이름을 현재 `.c` 파일 밖에서 직접 호출할 수 없게 한다. 반대로 `SystemClock_Config()`나 사용자 함수들은 현재 `static`이 아니므로 링크 단계에서 외부에도 보이는 전역 심볼이다. 실제로 다른 파일에서 호출할 필요가 없다면 사용자 보조 함수도 `static`으로 제한하는 편이 구조상 더 명확하다.

### 4.3 함수 선언과 함수 정의

파일 앞부분의 다음 코드는 함수의 존재와 입력·출력 형식만 먼저 알리는 **함수 원형 선언**이다.

```c
void ApplyCommand(char cmd);
```

뒤에 나오는 중괄호 포함 코드는 실제 동작을 작성한 **함수 정의**다.

```c
void ApplyCommand(char cmd)
{
  /* 실제 동작 */
}
```

C 컴파일러는 위에서 아래로 코드를 읽기 때문에, `main()`보다 아래에 정의된 함수를 `main()`에서 사용하려면 위쪽에 원형 선언이 필요하다.

### 4.4 자주 나오는 자료형

| 형식 | 뜻 | 대표 범위/특징 | 현재 사용 예 |
|---|---|---|---|
| `uint8_t` | 부호 없는 8비트 정수 | 0~255 | I2C 바이트, 주소, 모드 |
| `int16_t` | 부호 있는 16비트 정수 | -32768~32767 | 속도 퍼센트, 기존 angle 필드 |
| `uint16_t` | 부호 없는 16비트 정수 | 0~65535 | GPIO 핀 마스크 |
| `int32_t` | 부호 있는 32비트 정수 | 약 -21억~+21억 | 엔코더 누적값 |
| `uint32_t` | 부호 없는 32비트 정수 | 0~약 42억 | 타이머 채널, 비트 분해용 값 |
| `char` | 문자 또는 작은 정수 1개 | `'i'`, `'k'` 등 | 1문자 명령 |
| `void` | 반환값 또는 인자가 없음 | `void f(void)` | 초기화·콜백 함수 |

고정 폭 정수형을 쓰면 MCU나 컴파일러가 달라져도 바이트 수를 명확히 알 수 있다. 통신 패킷에는 특히 중요하다.

### 4.5 포인터 `*`와 구조체 멤버 `->`

다음 함수는 타이머 구조체 자체를 복사하지 않고 그 주소를 받는다.

```c
void SetMotor(TIM_HandleTypeDef *htim, ...)
```

호출할 때 `&htim3`의 `&`는 `htim3`가 있는 메모리 주소를 뜻한다.

```c
SetMotor(&htim3, TIM_CHANNEL_1, ...);
```

함수 안의 `htim->Init.Period`는 “`htim`이 가리키는 구조체의 `Init` 안에 있는 `Period`”를 뜻한다. 포인터가 아니라 구조체 변수 자체라면 점 표기 `htim3.Init.Period`를 쓴다.

### 4.6 `volatile`이 필요한 이유

```c
volatile int32_t encoderCount = 0;
```

`encoderCount`는 `while (1)`의 일반 흐름이 아니라 엔코더 인터럽트에서도 갑자기 바뀐다. `volatile`은 컴파일러에 “이 값은 코드만 보고 예상할 수 없는 시점에 변하므로, 필요할 때 실제 메모리에서 다시 읽어라”라고 알린다.

`volatile`은 동시 접근 전체를 안전하게 만드는 잠금장치가 아니며, 범위 초과를 막아 주지도 않는다. 현재 Cortex-M3에서 정렬된 32비트 읽기·쓰기는 한 번의 접근으로 처리될 수 있지만, 여러 변수의 일관된 동시 스냅샷이나 복합 연산의 원자성은 별도 설계가 필요하다.

### 4.7 HAL, 매크로와 핸들

`HAL_GPIO_WritePin()`, `HAL_I2C_Init()` 같은 함수는 ST가 제공하는 Hardware Abstraction Layer이다. 레지스터 비트를 매번 직접 다루는 대신 공통 API를 사용하게 한다.

```c
TIM_HandleTypeDef htim1;
```

핸들은 해당 주변장치의 설정, 상태와 레지스터 주소를 모아 둔 관리 구조체다.

```c
__HAL_TIM_SET_COMPARE(htim, channel, value);
```

이름이 함수처럼 보이지만 `__HAL_...` 계열 중 다수는 전처리기 매크로다. 여기서는 PWM 듀티를 정하는 비교 레지스터 값을 바꾼다.

### 4.8 콜백 함수

`HAL_I2C_AddrCallback()`과 `HAL_GPIO_EXTI_Callback()`는 `main()`이 직접 호출하지 않는다. HAL이 특정 사건을 처리하다가 약한 기본 구현 대신 사용자가 정의한 같은 이름의 함수를 호출한다.

```text
하드웨어 사건 → IRQHandler → HAL IRQ 처리 함수 → 사용자 HAL_*Callback
```

콜백은 인터럽트 문맥에서 실행되므로 오래 걸리는 대기, 큰 연산, 무한 반복을 넣으면 다른 인터럽트와 메인 루프를 방해할 수 있다.

---

## 5. 현재 하드웨어와 핀 배정

### 5.1 MCU와 클록

`mobility.ioc` 기준 MCU는 STM32F103C8T6이다. 외부 8 MHz HSE를 PLL에서 9배 하여 시스템 클록 72 MHz를 만든다.

```text
HSE 8 MHz × PLL 9 = SYSCLK 72 MHz
AHB = 72 MHz
APB1 = 36 MHz, APB1 타이머 클록 = 72 MHz
APB2 = 72 MHz, APB2 타이머 클록 = 72 MHz
```

APB1 분주기가 2일 때 STM32F1의 타이머 클록은 APB1 클록의 2배가 되므로 TIM2와 TIM3도 72 MHz를 받는다. TIM1은 APB2 계열에서 72 MHz를 받는다.

### 5.2 핀 표

| 핀 | 현재 역할 | 설정 위치 |
|---|---|---|
| PD0 / PD1 | 8 MHz 외부 오실레이터 입력/출력 | `SystemClock_Config()`, `.ioc` |
| PA0 / PA1 | 코너 ID 비트 A/B, 내부 pull-up 입력 | `MX_GPIO_Init()`, `ReadCornerId()` |
| PB6 / PB7 | I2C1 SCL/SDA, 100 kHz, open-drain 대체 기능 | `stm32f1xx_hal_msp.c` |
| PA6 | 모터1 PWM, TIM3_CH1 | TIM3 초기화와 MSP PostInit |
| PA7 / PB0 | 모터1 방향 DIR1/DIR2 | `SetMotor()` 호출, GPIO 초기화 |
| PA8 | 모터2 PWM, TIM1_CH1 | TIM1 초기화와 MSP PostInit |
| PB1 / PB10 | 모터2 방향 DIR1/DIR2 | `SetMotor()` 호출, GPIO 초기화 |
| PA2 | 모터3 PWM, TIM2_CH3 | TIM2 초기화와 MSP PostInit |
| PB8 / PB9 | 모터3 방향 DIR1/DIR2 | `SetMotor()` 호출, GPIO 초기화 |
| PA4 / PA5 | 모터1(휠) 엔코더 A/B | EXTI4와 GPIO 입력 |
| PB3 / PB5 | 모터2 엔코더 A/B | USER CODE의 EXTI3와 GPIO 입력 |
| PA13 / PA14 | SWD 디버깅 SWDIO/SWCLK | 시스템 설정 |

주의할 점은 **모터 번호와 타이머 번호가 일치하지 않는다는 것**이다.

| 기구상 이름 | PWM 타이머 | PWM 핀 |
|---|---|---|
| 모터1: 휠 구동 | TIM3_CH1 | PA6 |
| 모터2: 선기어 구동 | TIM1_CH1 | PA8 |
| 모터3: 클러치 전환 | TIM2_CH3 | PA2 |

PB3는 원래 JTAG 핀과 겹친다. `HAL_MspInit()`에서 JTAG-DP를 끄고 SWD는 유지하여 PB3를 엔코더 입력으로 사용할 수 있게 한다. 따라서 PA13/PA14의 SWD 디버깅은 계속 사용할 수 있지만, 전체 JTAG 기능은 사용할 수 없다.

I2C의 PB6/PB7은 open-drain이다. 현재 코드가 내부 pull-up을 명시적으로 설정하지 않으므로 버스에는 전압과 속도에 맞는 **외부 pull-up 저항**이 필요하다.

---

## 6. `main.c` 파일 형식

현재 `main.c`는 다음 순서로 구성된다.

| 구역 | 현재 내용 |
|---|---|
| Header / Includes | `main.h`, 사용자 구역의 `stdlib.h` |
| Private typedef | Cube 구역은 비어 있고, 실제 `CornerId` enum은 사용자 변수 구역에 있음 |
| Private define / macro | 현재 비어 있음 |
| Private variables | I2C 핸들 1개, 타이머 핸들 3개, 주소·통신·상태·엔코더 변수 |
| Function prototypes | Cube 초기화 함수와 사용자 보조 함수의 원형 |
| USER CODE 0 | 주소 판독, 모터 출력, 명령 처리, 상태 패킷, I2C/EXTI 콜백 |
| `main()` | 부팅 초기화와 무한 루프 |
| Peripheral init functions | 클록, I2C1, TIM1/2/3, GPIO 설정 |
| Error handling | `Error_Handler()`, 선택적 assert 처리 |

`#include <stdlib.h>`는 현재 `SetMotor()`에서 `abs()`를 사용하기 위해 포함되어 있다.

---

## 7. `main.c` 전역변수 분석

### 7.1 HAL 핸들

```c
I2C_HandleTypeDef hi2c1;
TIM_HandleTypeDef htim1;
TIM_HandleTypeDef htim2;
TIM_HandleTypeDef htim3;
```

각 핸들은 주변장치 하나를 나타낸다. `hi2c1.Instance = I2C1`, `htim1.Instance = TIM1`처럼 실제 하드웨어와 연결된다. 인터럽트 파일에서도 I2C 핸들이 필요하므로 `stm32f1xx_it.c`는 `extern I2C_HandleTypeDef hi2c1;`로 같은 변수를 참조한다.

### 7.2 코너 ID와 I2C 주소

```c
typedef enum {
  CORNER_LF = 0,
  CORNER_RF = 1,
  CORNER_LR = 2,
  CORNER_RR = 3
} CornerId;

CornerId cornerId;
uint8_t myAddress;
```

`enum`은 숫자에 읽기 쉬운 이름을 붙인다. LF/RF/LR/RR은 각각 Left Front, Right Front, Left Rear, Right Rear로 해석되는 이름이다.

두 입력의 조합과 주소는 다음과 같다.

| PA1 `bitB` | PA0 `bitA` | 계산값 `(B << 1) \| A` | `cornerId` | 7비트 I2C 주소 |
|---:|---:|---:|---|---:|
| 0 | 0 | 0 | `CORNER_LF` | `0x10` |
| 0 | 1 | 1 | `CORNER_RF` | `0x11` |
| 1 | 0 | 2 | `CORNER_LR` | `0x12` |
| 1 | 1 | 3 | `CORNER_RR` | `0x13` |

PA0/PA1에는 내부 pull-up이 걸려 있으므로 외부에서 핀을 연결하지 않으면 일반적으로 High로 읽혀 `0x13`이 된다. 주소 선택 회로가 핀을 GND로 당기면 해당 비트가 0이 된다. 실제 보드의 스위치·점퍼 회로는 별도 확인이 필요하다.

### 7.3 I2C 버퍼와 마지막 명령

```c
uint8_t i2c_rx_buf[1];
uint8_t i2c_tx_buf[8];
volatile char lastCommand = 'k';
```

- 수신 버퍼는 현재 명령이 정확히 1바이트이기 때문에 길이가 1이다.
- 송신 버퍼는 현재 진단 상태 응답이 8바이트이기 때문에 길이가 8이다.
- `lastCommand`의 초기값 `'k'`는 정지 문자를 뜻한다.
- 현재 `lastCommand`는 수신 기록용으로만 저장되며, 상태 패킷에는 포함되지 않고 메인 루프에서 재실행되지 않는다.

### 7.4 상태와 엔코더 변수

```c
uint8_t currentMode = 0;
int16_t carrierAngleTenths = 0;
volatile int32_t encoderCount = 0;
volatile int32_t motor2_encoder_count = 0;
```

| 변수 | 실제 현재 의미 | 중요한 주의점 |
|---|---|---|
| `currentMode` | 상태 패킷 byte 0에 넣는 값 | 어디에서도 변경하지 않으므로 항상 0 |
| `carrierAngleTenths` | `encoderCount % 32000` 결과 | 이름과 달리 보정된 0.1도 값이 아님 |
| `encoderCount` | PA4 상승 에지를 PA5 방향으로 판정한 모터1 원시 누적 카운트 | signed overflow 방지 없음 |
| `motor2_encoder_count` | PB3 상승 에지를 PB5 방향으로 판정한 모터2 원시 누적 카운트 | int32 경계에서 명시적으로 순환 |

두 엔코더 모두 전원을 켜면 0부터 시작한다. 현재는 원점 센서, 영점 복귀, 운전 중 0점 재설정, Flash 저장이 없다.

---

## 8. 사용자 함수 정밀 분석

### 8.1 `ReadCornerId()`

```c
uint8_t bitA = (HAL_GPIO_ReadPin(GPIOA, GPIO_PIN_0) == GPIO_PIN_RESET) ? 0U : 1U;
uint8_t bitB = (HAL_GPIO_ReadPin(GPIOA, GPIO_PIN_1) == GPIO_PIN_RESET) ? 0U : 1U;
cornerId = (CornerId)((bitB << 1) | bitA);
myAddress = (uint8_t)(0x10U + (uint8_t)cornerId);
```

삼항 연산자 `조건 ? 참일 때 값 : 거짓일 때 값`으로 각 핀을 0 또는 1로 바꾼다. `bitB << 1`은 B 비트를 한 칸 왼쪽으로 밀어 값 0 또는 2를 만들고, `| bitA`로 하위 비트를 합친다.

이 함수는 부팅 때 한 번만 호출된다. 실행 중 점퍼를 바꾸어도 주소는 바뀌지 않으며, 변경을 적용하려면 리셋해야 한다.

### 8.2 `SetMotor()`

이 함수 하나를 세 모터에 공통으로 사용한다.

```c
void SetMotor(
  TIM_HandleTypeDef *htim,
  uint32_t channel,
  GPIO_TypeDef *dir1Port, uint16_t dir1Pin,
  GPIO_TypeDef *dir2Port, uint16_t dir2Pin,
  int16_t speedPercent)
```

입력은 “어느 타이머 채널을 쓸지”, “방향 핀 두 개가 어디인지”, “몇 퍼센트와 어느 방향으로 돌릴지”이다.

#### 1단계: 입력 범위 제한

```c
if (speedPercent > 100) speedPercent = 100;
if (speedPercent < -100) speedPercent = -100;
```

호출자가 실수로 150을 주어도 100으로, -200을 주어도 -100으로 제한한다.

#### 2단계: 방향 핀 설정

| `speedPercent` | DIR1 | DIR2 | 코드상 의미 |
|---:|---|---|---|
| 양수 | High | Low | 정방향 |
| 음수 | Low | High | 역방향 |
| 0 | Low | Low | 출력 정지 요청 |

Low/Low가 모터를 관성 정지시키는지, 전기적으로 제동하는지는 연결된 모터 드라이버의 진리표에 달려 있다. 소스 코드만으로는 실제 제동 방식을 확정할 수 없다.

#### 3단계: PWM 비교값 설정

```c
compare = abs(speedPercent) * Period / 100;
```

현재 모든 타이머의 `Period`가 999이다. 정수 나눗셈이므로 예시는 다음과 같다.

| 요청 | 계산된 compare | 대략적인 출력 비율 |
|---:|---:|---:|
| 0% | 0 | 0% |
| 60% | 599 | 약 59.9% |
| 70% | 699 | 약 69.9% |
| 100% | 999 | 약 99.9%에 해당하는 카운트 설정 |

PWM1의 정확한 파형 경계는 타이머 카운트와 비교 조건에 따라 해석해야 한다. 여기서는 “요청 퍼센트에 거의 비례하는 compare 값”으로 이해하면 된다.

이 함수는 엔코더 값을 전혀 읽지 않는다. 즉, 현재 모터 제어는 목표 각도나 목표 RPM을 맞추는 폐루프 제어가 아니라 일정 PWM을 바로 내보내는 **개방 루프 제어**다.

### 8.3 `ApplyCommand()`

`switch` 문은 수신 문자에 따라 실행할 분기를 고른다.

| 명령 | 대상 | PWM/방향 핀 | 출력 요청 | 현재 효과 |
|---|---|---|---:|---|
| `'i'` | 모터1 휠 | TIM3_CH1 / PA7·PB0 | +70% | 모터1 정방향 |
| `','` | 모터1 휠 | TIM3_CH1 / PA7·PB0 | -70% | 모터1 역방향 |
| `'j'` | 모터2 선기어 | TIM1_CH1 / PB1·PB10 | +70% | 모터2 정방향 |
| `'l'` | 모터2 선기어 | TIM1_CH1 / PB1·PB10 | -70% | 모터2 역방향 |
| `'u'` | 모터3 클러치 | TIM2_CH3 / PB8·PB9 | +60% | 모터3 정방향 |
| `'o'` | 모터3 클러치 | TIM2_CH3 / PB8·PB9 | -60% | 모터3 역방향 |
| `'k'` | 모든 모터 | 세 채널 전체 | 0% | 세 모터 정지 요청 |
| 그 외 | 없음 | 없음 | 변경 없음 | 기존 출력이 그대로 유지됨 |

여기서 중요한 점은 다음과 같다.

1. 명령 한 번으로 출력이 설정되면 다음 명령 전까지 그 PWM이 계속 유지된다.
2. 잘못된 문자는 `default`에서 아무 것도 하지 않으므로 기존 모터를 멈추지 않는다.
3. 다른 모터를 구동하는 명령이 와도 기존에 돌던 모터를 자동으로 정지하지 않는다. 예를 들어 `'i'` 다음 `'j'`를 보내면 모터1을 끄는 코드가 없으므로 모터1과 모터2가 함께 돌 수 있다.
4. 현재 코드에는 명령 수신 시간 제한, heartbeat, 통신 두절 시 로컬 정지, 상호 인터록이 없다.
5. 따라서 공용 안전 규칙의 “모터3 동작 중 모터1·2 정지”, “선행 모터 정지 확인 후 다음 동작”을 이 함수가 보장하지 않는다.

### 8.4 `PrepareStatusBuffer()`

ESP32가 STM32 상태를 읽으려 할 때 8바이트 응답을 만든다.

| byte | 내용 | 자료형/바이트 순서 |
|---:|---|---|
| 0 | `currentMode` | `uint8_t` |
| 1 | `carrierAngleTenths` 하위 바이트 | `int16`, little-endian |
| 2 | `carrierAngleTenths` 상위 바이트 | `int16`, little-endian |
| 3 | 진단 패킷 버전 `2` | `uint8_t` |
| 4 | `motor2_encoder_count` bit 0~7 | `int32`, little-endian |
| 5 | `motor2_encoder_count` bit 8~15 | `int32`, little-endian |
| 6 | `motor2_encoder_count` bit 16~23 | `int32`, little-endian |
| 7 | `motor2_encoder_count` bit 24~31 | `int32`, little-endian |

`motor2_encoder_count`는 먼저 `motor2_snapshot`에 한 번 복사한다. 그 다음 네 바이트를 만들기 때문에 바이트를 하나씩 만드는 도중 엔코더 인터럽트가 값을 바꾸더라도 서로 다른 카운트의 바이트가 섞이는 위험을 줄인다.

현재 `carrierAngleTenths`는 이름상 0.1도 단위의 캐리어 각도처럼 보이지만 실제 계산은 다음 한 줄뿐이다.

```c
carrierAngleTenths = (int16_t)(encoderCount % 32000);
```

엔코더 CPR/PPR, 감속비, 기구비를 사용하지 않으므로 실제 각도가 아니다. 또한 입력은 모터2 카운터가 아니라 PA4/PA5의 모터1 카운터다. 예를 들어 값 123이 전송되어도 그것만으로 12.3도라고 해석해서는 안 된다.

### 8.5 I2C 주소 일치 콜백

```c
void HAL_I2C_AddrCallback(..., uint8_t TransferDirection, ...)
```

ESP32 I2C master가 이 STM32의 주소를 부르면 실행된다.

```text
master가 STM32에 씀
  → TransferDirection == I2C_DIRECTION_TRANSMIT
  → STM32는 1바이트 Receive 인터럽트를 시작

master가 STM32에서 읽음
  → 반대 방향
  → 상태 버퍼를 만들고 8바이트 Transmit 인터럽트를 시작
```

이름이 헷갈릴 수 있는데 `TransferDirection`은 master 관점의 I2C 방향으로 이해해야 한다. master transmit이면 slave인 STM32는 receive한다.

`I2C_FIRST_AND_LAST_FRAME`은 현재 전송이 한 프레임 안에서 처음이자 마지막이라는 뜻이다. 명령 1바이트와 상태 8바이트를 각각 하나의 완결된 전송으로 처리한다.

### 8.6 I2C 수신·송신 완료 콜백

수신 완료 시:

```c
lastCommand = (char)i2c_rx_buf[0];
ApplyCommand(lastCommand);
HAL_I2C_EnableListen_IT(hi2c);
```

받은 명령을 저장하고 즉시 모터 출력에 적용한 다음, 다음 주소 호출을 듣도록 listen 모드를 다시 활성화한다. `ApplyCommand()`는 I2C 인터럽트 처리 흐름 안에서 실행된다.

송신 완료 시에는 데이터 변경 없이 listen 모드만 다시 활성화한다.

### 8.7 I2C 오류 콜백

```c
HAL_I2C_DeInit(hi2c);
HAL_I2C_Init(hi2c);
HAL_I2C_EnableListen_IT(hi2c);
```

I2C 오류가 나면 주변장치를 해제하고 같은 핸들 설정으로 다시 초기화한 뒤 수신 대기를 재개한다.

현재 한계는 다음과 같다.

- 오류 종류와 횟수를 기록하지 않는다.
- 각 HAL 함수의 반환값을 확인하지 않는다.
- I2C 오류가 발생해도 모터를 정지하지 않는다.
- 마지막 유효 명령 이후 얼마나 시간이 지났는지 감시하지 않는다.

따라서 통신이 끊기기 직전에 모터 구동 명령을 받았다면 PWM 출력이 계속 남을 수 있다. ESP32에 통신 failsafe가 있더라도 STM32 자체의 로컬 timeout이 필요하다는 프로젝트 안전 원칙을 현재 코드는 충족하지 않는다.

### 8.8 엔코더 EXTI 콜백

두 엔코더 모두 quadrature A/B 신호의 A상 **상승 에지 하나만** 센다. A상 상승 순간에 B상을 읽어서 방향을 판단하는 x1 계수다.

#### 모터2: PB3/PB5

```text
PB3 A상 상승
  → EXTI3_IRQHandler()
  → HAL_GPIO_EXTI_IRQHandler(MOTOR2_ENC_A_Pin)
  → HAL_GPIO_EXTI_Callback(MOTOR2_ENC_A_Pin)
  → PB5가 Low이면 +1, High이면 -1
```

최댓값에서 +1 하거나 최솟값에서 -1 할 때는 반대 경계로 명시적으로 순환한다.

```text
INT32_MAX에서 +1 요청 → INT32_MIN
INT32_MIN에서 -1 요청 → INT32_MAX
```

#### 모터1: PA4/PA5

```text
PA4 A상 상승
  → EXTI4_IRQHandler()
  → HAL_GPIO_EXTI_IRQHandler(WHEEL_ENC_A_Pin)
  → HAL_GPIO_EXTI_Callback(GPIO_PIN_4)
  → PA5가 Low이면 +1, High이면 -1
```

모터1 카운터에는 모터2와 같은 경계 처리가 없다. `encoderCount++`가 `INT32_MAX`를 넘거나 `encoderCount--`가 `INT32_MIN`을 넘으면 부호 있는 정수 overflow가 되어 C 언어 수준에서 동작이 보장되지 않는다. `% 32000`은 송신용 값만 줄이며 원본 `encoderCount`의 overflow를 막지 않는다.

두 엔코더 입력 모두 `GPIO_NOPULL`이고 소프트웨어 디바운스나 입력 필터가 없다. 센서 출력 방식, 외부 pull-up/down, 전압 레벨, 최대 펄스 속도를 실제 하드웨어에서 확인해야 한다. 펄스 속도가 너무 빠르면 각 에지마다 CPU 인터럽트를 처리하는 현재 방식에서 누락 가능성이 생기므로 타이머 Encoder Mode도 후속 대안이 될 수 있다.

---

## 9. `main()` 실행 순서 정밀 분석

### 9.1 `HAL_Init()`

```c
HAL_Init();
```

HAL 내부 상태, Flash prefetch 관련 기본 설정, NVIC 우선순위 그룹, 1 ms 시간 기준인 SysTick 등을 준비한다. 이 과정에서 `HAL_MspInit()`가 호출되어 AFIO와 PWR 클록을 켜고 JTAG를 비활성화하되 SWD는 유지한다.

### 9.2 `SystemClock_Config()`

```c
SystemClock_Config();
```

외부 8 MHz HSE와 PLL ×9를 이용해 CPU를 72 MHz로 설정한다. APB1은 36 MHz, APB2는 72 MHz가 된다. Flash latency는 2 wait state로 설정한다.

HSE 발진 실패나 HAL 설정 실패가 나면 `Error_Handler()`로 들어간다.

### 9.3 주변장치 초기화

```c
MX_GPIO_Init();
MX_I2C1_Init();
MX_TIM1_Init();
MX_TIM3_Init();
MX_TIM2_Init();
```

- GPIO를 먼저 준비하여 주소 선택 입력, 방향 출력, 엔코더 인터럽트를 설정한다.
- I2C1을 100 kHz slave용 설정으로 초기화한다. 이 첫 초기화 시 `OwnAddress1`은 0이다.
- 세 타이머를 PWM 모드로 설정하며 초기 compare 값은 0이다.

엔코더 EXTI는 `MX_GPIO_Init()` 단계에서 활성화되므로 이후 신호가 들어오면 PWM 시작 전이라도 카운터가 갱신될 수 있다.

### 9.4 주소를 읽고 I2C 재초기화

```c
ReadCornerId();
hi2c1.Init.OwnAddress1 = (uint32_t)myAddress << 1;
HAL_I2C_Init(&hi2c1);
```

PA0/PA1을 읽어 7비트 주소 `0x10`~`0x13`을 결정한다. STM32F1 HAL 설정 필드에는 주소를 한 비트 왼쪽으로 이동한 형태를 넣는다. 예를 들어 7비트 주소 `0x10`은 `OwnAddress1`에 `0x20`으로 들어간다. 버스에서 말하는 STM32 주소는 계속 `0x10`이다.

첫 번째 `MX_I2C1_Init()`은 주소 0으로 초기화하고, 사용자 구역에서 실제 주소를 넣어 다시 `HAL_I2C_Init()`한다. 기능상 동적 주소를 적용하기 위한 구조지만, 코드를 처음 읽을 때 “왜 I2C 초기화를 두 번 하나”라고 느끼기 쉬운 부분이다.

### 9.5 안전한 시작 출력과 기능 시작

```c
ApplyCommand('k');
HAL_TIM_PWM_Start(...);
HAL_I2C_EnableListen_IT(&hi2c1);
```

먼저 세 방향 핀을 Low로 만들고 compare를 0으로 설정한 뒤 PWM 출력을 시작한다. 마지막으로 I2C 주소 listen 인터럽트를 활성화한다. 각 시작 함수가 실패하면 `Error_Handler()`로 간다.

### 9.6 무한 루프

```c
while (1)
{
  carrierAngleTenths = (int16_t)(encoderCount % 32000);

  if (hi2c1.State == HAL_I2C_STATE_READY)
  {
    HAL_I2C_EnableListen_IT(&hi2c1);
  }
}
```

메인 루프가 반복해서 하는 일은 두 가지뿐이다.

1. 모터1 원시 카운트의 나머지를 `carrierAngleTenths`에 복사한다.
2. I2C 상태가 READY이면 listen 모드를 다시 활성화한다.

모터 명령 처리와 엔코더 계수는 주로 인터럽트에서 실행된다. 이 루프에는 주기 제어용 delay가 없어 가능한 한 빠르게 반복한다. 현재 연산량은 작지만 CPU 시간을 계속 사용하며, 주기적으로 해야 할 제어·안전 감시의 명시적인 시간 기준도 없다.

---

## 10. 주변장치 초기화 함수 분석

### 10.1 `SystemClock_Config()`

| 항목 | 설정 |
|---|---|
| 발진원 | HSE ON, HSI도 ON |
| PLL 입력 | HSE |
| HSE predivider | ÷1 |
| PLL multiplier | ×9 |
| SYSCLK | PLL clock = 72 MHz |
| AHB | SYSCLK ÷1 = 72 MHz |
| APB1 | HCLK ÷2 = 36 MHz |
| APB2 | HCLK ÷1 = 72 MHz |
| Flash latency | 2 |

HSI도 켜져 있지만 정상 설정에서 시스템 클록원은 HSE 기반 PLL이다.

### 10.2 `MX_I2C1_Init()`

| 항목 | 설정 |
|---|---|
| 속도 | 100,000 Hz |
| 주소 방식 | 7-bit |
| duty cycle | 2 |
| dual address | 사용 안 함 |
| general call | 사용 안 함 |
| clock stretching | 허용 (`NOSTRETCH_DISABLE`) |
| 최초 own address | 0, 이후 `main()`에서 동적 주소로 재설정 |

I2C1 핀과 인터럽트는 이 함수 자체가 아니라 `HAL_I2C_Init()`이 호출하는 MSP 함수에서 준비된다.

### 10.3 `MX_TIM1_Init()`, `MX_TIM2_Init()`, `MX_TIM3_Init()`

세 타이머의 핵심 설정은 거의 같다.

| 항목 | TIM1 | TIM2 | TIM3 |
|---|---:|---:|---:|
| 입력 타이머 클록 | 72 MHz | 72 MHz | 72 MHz |
| Prescaler | 71 | 71 | 71 |
| Counter tick | 1 MHz | 1 MHz | 1 MHz |
| Period/ARR | 999 | 999 | 999 |
| PWM 주파수 | 1 kHz | 1 kHz | 1 kHz |
| 채널 | CH1 | CH3 | CH1 |
| 초기 Pulse | 0 | 0 | 0 |

계산식은 다음과 같다.

```text
counter clock = 72,000,000 / (71 + 1) = 1,000,000 Hz
PWM frequency = 1,000,000 / (999 + 1) = 1,000 Hz
```

TIM1은 advanced-control timer라 break/dead-time 설정 구조가 추가로 보이지만 현재 break 입력, dead time, automatic output 기능은 사용하지 않는다. 모터 H-bridge 방향 전환의 dead time을 TIM1이 자동으로 관리하는 구조도 아니다.

### 10.4 `MX_GPIO_Init()`

초기화 순서는 다음과 같다.

1. GPIOD, GPIOA, GPIOB 주변장치 클록 활성화
2. 모든 모터 방향 출력 핀을 먼저 Low로 기록
3. PA0/PA1을 pull-up 입력으로 설정
4. 모터1 엔코더 PA4를 상승 에지 EXTI, PA5를 입력으로 설정
5. 방향 핀들을 push-pull 출력으로 설정
6. EXTI4 우선순위를 5로 설정하고 활성화
7. USER CODE에서 PB5 입력, PB3 상승 에지 EXTI 설정
8. EXTI3 우선순위를 5로 설정하고 활성화

출력 모드를 설정하기 전에 출력 데이터 값을 Low로 써 두는 것은 핀 전환 순간 원치 않는 High glitch 가능성을 줄이는 일반적인 초기화 패턴이다.

PB3의 A상 설정 직전에 `GPIO_InitStruct.Pull`을 다시 대입하지 않지만, 바로 앞 PB5 설정에서 넣은 `GPIO_NOPULL` 값이 구조체에 남아 있으므로 PB3도 현재 NOPULL로 초기화된다. 동작은 맞지만 각 핀 블록에 필요한 필드를 명시하면 향후 코드 변경 때 더 읽기 쉽고 안전하다.

---

## 11. 인터럽트 우선순위와 실제 호출 경로

STM32에서 숫자가 작을수록 높은 선점 우선순위다.

| 인터럽트 | 우선순위 | 역할 |
|---|---:|---|
| I2C1 event | 0 | 주소 일치, 송수신 이벤트 |
| I2C1 error | 0 | 버스 오류 |
| EXTI3 | 5 | 모터2 엔코더 A상 |
| EXTI4 | 5 | 모터1 엔코더 A상 |
| SysTick | 15 | HAL의 1 ms tick |

따라서 I2C 인터럽트가 엔코더 EXTI보다 높고, 두 엔코더는 같은 우선순위다. 우선순위가 높은 인터럽트가 낮은 인터럽트 처리를 잠시 중단하고 먼저 실행할 수 있다.

호출 관계를 파일별로 보면 다음과 같다.

```text
I2C 주소/데이터/오류
  → stm32f1xx_it.c
       I2C1_EV_IRQHandler() 또는 I2C1_ER_IRQHandler()
  → HAL I2C driver
  → main.c
       HAL_I2C_AddrCallback()
       HAL_I2C_SlaveRxCpltCallback()
       HAL_I2C_SlaveTxCpltCallback()
       HAL_I2C_ErrorCallback()

PA4 엔코더 상승
  → stm32f1xx_it.c의 EXTI4_IRQHandler()
  → HAL_GPIO_EXTI_IRQHandler()
  → main.c의 HAL_GPIO_EXTI_Callback()

PB3 엔코더 상승
  → stm32f1xx_it.c USER CODE의 EXTI3_IRQHandler()
  → HAL_GPIO_EXTI_IRQHandler()
  → main.c의 HAL_GPIO_EXTI_Callback()
```

---

## 12. `stm32f1xx_hal_msp.c` 상세 설명

MSP는 MCU Support Package의 약자다. HAL의 논리 설정과 실제 MCU 자원을 연결하는 파일로 이해하면 된다.

### 12.1 `HAL_MspInit()`

- AFIO 클록을 켠다.
- PWR 클록을 켠다.
- JTAG-DP를 끄고 SW-DP는 유지한다.
- 결과적으로 JTAG가 점유하던 PB3를 GPIO/EXTI로 사용할 수 있게 한다.

### 12.2 `HAL_I2C_MspInit()`

I2C1일 때만 다음 작업을 수행한다.

- GPIOB 클록 활성화
- PB6=SCL, PB7=SDA를 alternate-function open-drain으로 설정
- I2C1 주변장치 클록 활성화
- I2C1 event/error IRQ를 우선순위 0으로 활성화

`HAL_I2C_MspDeInit()`은 반대로 I2C1 클록, 핀 설정과 IRQ를 해제한다. `main.c`의 I2C 오류 콜백이 DeInit을 호출하므로 오류 복구 때 실제로 이 함수가 실행된다.

### 12.3 `HAL_TIM_PWM_MspInit()`

TIM1, TIM2, TIM3 중 어떤 핸들이 들어왔는지 확인하여 해당 타이머 클록을 켠다. 아직 PWM 핀은 설정하지 않는다.

### 12.4 `HAL_TIM_MspPostInit()`

타이머 채널 설정이 끝난 후 PWM 출력 핀을 alternate-function push-pull로 만든다.

- TIM1_CH1 → PA8
- TIM2_CH3 → PA2
- TIM3_CH1 → PA6

### 12.5 DeInit 함수

`HAL_TIM_PWM_MspDeInit()`은 해당 타이머 클록을 끈다. 현재 정상 실행 흐름에서는 호출하지 않는다.

이 파일은 `.ioc` 설정을 바탕으로 재생성될 가능성이 높다. 직접 수정할 때는 USER CODE 구역을 사용하고, 가능하면 먼저 CubeMX 핀/주변장치 설정을 고치는 것이 좋다.

---

## 13. `stm32f1xx_it.c` 상세 설명

이 파일에는 두 종류의 인터럽트 처리기가 있다.

### 13.1 Cortex-M3 예외 처리기

| 함수 | 의미 | 현재 동작 |
|---|---|---|
| `NMI_Handler()` | 마스킹할 수 없는 매우 중요한 인터럽트 | 무한 루프 |
| `HardFault_Handler()` | 잘못된 주소/상태 등 심각한 fault | 무한 루프 |
| `MemManage_Handler()` | 메모리 관리 fault | 무한 루프 |
| `BusFault_Handler()` | 버스 접근 fault | 무한 루프 |
| `UsageFault_Handler()` | 잘못된 명령어/상태 | 무한 루프 |
| `SVC_Handler()` | OS 등이 쓰는 supervisor call | 비어 있음 |
| `DebugMon_Handler()` | 디버그 모니터 | 비어 있음 |
| `PendSV_Handler()` | RTOS 문맥 전환 등에 사용 | 비어 있음 |
| `SysTick_Handler()` | 주기 tick | `HAL_IncTick()` 호출 |

현재 RTOS를 사용하지 않으므로 SVC와 PendSV에는 사용자 동작이 없다. fault 처리기는 오류 기록이나 모터 정지 없이 무한 루프에 머문다.

### 13.2 주변장치 IRQ 처리기

- `EXTI4_IRQHandler()`는 모터1 엔코더 PA4 사건을 HAL로 넘긴다.
- `EXTI3_IRQHandler()`는 USER CODE 구역에 있으며 모터2 엔코더 PB3 사건을 HAL로 넘긴다.
- `I2C1_EV_IRQHandler()`는 I2C event를 HAL에 넘긴다.
- `I2C1_ER_IRQHandler()`는 I2C error를 HAL에 넘긴다.

IRQHandler 안에서 엔코더 증감이나 명령 처리를 직접 하지 않고 HAL에 넘기는 이유는 HAL이 pending flag 정리와 내부 상태 머신을 처리한 다음 공통 callback을 불러 주기 때문이다.

---

## 14. `syscalls.c` 상세 설명

STM32에는 기본적으로 화면, 키보드, 파일 시스템, 프로세스가 없다. 그러나 GCC가 사용하는 newlib C 라이브러리의 `printf()`, `scanf()`, `malloc()` 같은 함수는 운영체제와 비슷한 저수준 함수를 기대한다. `syscalls.c`는 링크가 가능하도록 최소 구현을 제공한다.

### 14.1 입출력 연결점

```c
extern int __io_putchar(int ch) __attribute__((weak));
extern int __io_getchar(void) __attribute__((weak));
```

`_write()`는 각 문자를 `__io_putchar()`로, `_read()`는 `__io_getchar()`로 넘긴다. `weak`는 다른 파일에 같은 이름의 실제 구현이 있으면 그것을 우선 사용하도록 한다.

현재 프로젝트에는 두 함수의 실제 UART 구현이 없다. 따라서 `printf()` 로그가 UART나 USB로 자동 출력되는 상태가 아니다. 실제로 `printf()`를 사용하려면 UART 초기화와 `__io_putchar()` 구현 등을 추가해야 한다.

### 14.2 지원하지 않는 운영체제 기능

`_open`, `_close`, `_fork`, `_execve`, `_unlink` 등은 실패를 반환한다. MCU에 일반 운영체제나 파일 시스템이 없기 때문이다. `_getpid()`가 1을 반환하는 것도 실제 프로세스 관리가 있다는 뜻이 아니라 최소 호환용 값이다.

### 14.3 수정 시점

UART 디버그 출력, semihosting, 파일 시스템을 붙일 때만 주로 수정한다. 현재 모터/I2C 로직과 직접 연결된 파일은 아니다.

---

## 15. `sysmem.c` 상세 설명

`malloc()`처럼 실행 중 동적 메모리를 요청하는 함수는 heap을 늘리는 `_sbrk()`가 필요하다.

```text
RAM 낮은 주소
  .data → .bss → heap이 위로 증가 → 빈 공간 ← stack이 아래로 증가
RAM 높은 주소
```

`_sbrk()`는 linker script가 제공하는 심볼을 사용한다.

| 심볼 | 의미 |
|---|---|
| `_end` | 정적 데이터가 끝나고 heap이 시작할 위치 |
| `_estack` | RAM 위쪽의 초기 stack 위치 |
| `_Min_Stack_Size` | linker가 보장하려는 최소 stack 예약 크기 |

heap이 예약 stack 영역까지 침범하려 하면 `errno = ENOMEM`으로 실패한다. `.ioc`에는 heap `0x200` bytes, stack `0x400` bytes가 설정되어 있다.

현재 `main.c`는 `malloc()`을 사용하지 않는다. `abs()`는 표준 라이브러리 함수지만 동적 메모리를 요청하지 않는다. 작은 MCU의 실시간 제어에서는 메모리 단편화와 실패 시점의 불확실성 때문에 동적 할당을 최소화하는 편이 일반적이다.

---

## 16. `system_stm32f1xx.c` 상세 설명

이 파일은 ST가 제공하는 CMSIS 시스템 파일이다.

### 16.1 `SystemInit()`

startup assembly가 `main()` 전에 호출한다. 현재 빌드 설정에서는 외부 SRAM 초기화를 하지 않고, 사용자 vector table 재배치 매크로도 꺼져 있으므로 함수가 하는 일은 거의 없다.

실제 72 MHz 클록 설정은 이 파일이 아니라 `main.c`의 `SystemClock_Config()`가 수행한다. 파일 머리말은 여러 STM32F1 설정에 공통인 일반 설명이므로 현재 함수 본문과 구분해서 읽어야 한다.

### 16.2 `SystemCoreClock`

```c
uint32_t SystemCoreClock = 8000000;
```

리셋 기본값은 8 MHz이다. 이후 HAL이 클록을 72 MHz로 설정하면서 이 값을 갱신한다. 다른 라이브러리는 이 값을 보고 지연이나 주변장치 계산을 할 수 있다.

### 16.3 `SystemCoreClockUpdate()`

RCC 레지스터를 읽어서 현재 HSI/HSE/PLL 설정과 AHB prescaler를 계산한 뒤 `SystemCoreClock`을 갱신한다. 실행 중 레지스터를 직접 바꾸어 클록 구성을 변경했다면 호출해야 한다.

### 16.4 직접 수정 여부

이 파일은 공급사 코드이므로 특별한 이유가 없다면 직접 수정하지 않는다. 외부 크리스털 주파수가 기본 8 MHz와 다르다면 프로젝트 설정과 `HSE_VALUE`가 실제 하드웨어와 일치하는지 확인해야 한다.

---

## 17. 현재 코드가 실제로 할 수 있는 것

현재 구현된 기능은 다음과 같다.

- 두 주소 선택 핀으로 STM32 4대의 I2C 주소를 `0x10`~`0x13`으로 구분
- ESP32에서 1문자 I2C 명령 수신
- 세 DC 모터의 방향과 고정 PWM 출력 수동 설정
- `'k'` 명령으로 세 모터 출력 0 요청
- 모터1과 모터2 엔코더를 A상 상승 에지 x1 방식으로 계수
- 8바이트 진단 상태 응답으로 모터1 파생값과 모터2 원시 카운트 송신
- I2C 오류 발생 시 I2C 주변장치 재초기화 시도

---

## 18. 현재 코드가 아직 하지 못하는 것

다음 기능은 변수나 이름 때문에 이미 구현된 것처럼 보일 수 있지만, 실제로는 구현되어 있지 않다.

- 엔코더 기반 목표 RPM 제어
- 엔코더 기반 캐리어 목표 각도 제어
- PID 또는 다른 폐루프 제어
- 엔코더 count를 실제 각도나 RPM으로 환산
- 캐리어 원점 복귀와 절대 위치 복구
- 클러치 a/b 위치 센서 판독과 체결 완료 판정
- `currentMode` 상태 전이
- 휠/트랙 모드 상태 머신
- 모터 정지 상태의 엔코더 기반 확인
- 모터1·2·3 상호 인터록
- 명령 timeout과 STM32 자체 통신 failsafe
- 센서 단선, stuck, 방향 오류 검출
- 과전류, 과온, 드라이버 fault 입력 처리
- 오류 플래그와 오류 로그
- 잘못된 명령에 대한 NACK 또는 안전 정지
- 구조화 명령 패킷, checksum/CRC, sequence 처리

즉, 현재 코드는 **수동 단품 시험과 진단에 가까운 단계**이며, 공용 문서에 설계된 최종 모빌리티 상태 머신은 아직 들어 있지 않다.

---

## 19. 면밀한 분석에서 확인된 위험과 개선 우선순위

이 절은 코드 변경 내용이 아니라 현재 상태에 대한 검토 결과다.

### 19.1 최우선: 어떤 오류에서도 모터를 먼저 정지

현재 `Error_Handler()`는 다음과 같다.

```c
__disable_irq();
while (1) { }
```

CPU 인터럽트를 끄고 멈추지만 이미 동작 중인 PWM 타이머와 GPIO 출력이 자동으로 0이 된다고 보장할 수 없다. CPU가 무한 루프에 있어도 하드웨어 타이머는 계속 PWM을 출력할 수 있다. HardFault 등 `stm32f1xx_it.c`의 fault handler도 마찬가지로 정지 출력을 먼저 만들지 않는다.

따라서 실제 기구 운전 전에는 다음 원칙이 필요하다.

```text
오류 진입
  → 세 PWM compare를 0
  → 모든 방향/enable 출력을 안전 상태로 변경
  → 필요하면 드라이버 hardware enable 차단
  → 오류 상태와 원인을 기록
  → 복구 조건이 검증될 때까지 구동 금지
```

소프트웨어가 멈춰도 모터가 정지하도록 드라이버 enable, watchdog, break 입력 같은 하드웨어 차단 수단도 검토해야 한다.

### 19.2 최우선: STM32 로컬 명령 timeout

현재 마지막 명령 이후 시간이 지나도 모터는 계속 돈다. ESP32나 PC 통신 상태와 무관하게 STM32가 자체적으로 시간을 재고, 정해진 시간 안에 유효한 heartbeat/명령이 없으면 모든 모터를 정지해야 한다.

### 19.3 최우선: 모터 상호 인터록

각 문자 명령은 대상 모터만 바꾸므로 여러 모터를 동시에 켤 수 있다. 프로젝트 안전 규칙에 맞게 상태 머신 안에서 허용된 모터만 구동하고, 다음 단계 전에는 엔코더나 센서로 이전 모터의 실제 정지를 확인해야 한다.

### 19.4 잘못된 명령과 I2C 오류의 fail-safe 처리

현재 알 수 없는 문자는 무시되고 I2C 오류는 통신만 재초기화한다. 둘 다 기존 PWM을 유지할 수 있다. 잘못된 길이·명령·상태 전이는 오류 상태와 정지로 연결하는 것이 안전하다.

### 19.5 물리 단위와 변수 의미 일치

`carrierAngleTenths`에는 실제 각도가 아닌 모터1 count 나머지가 들어간다. 후속 구현에서는 원시 count와 계산된 0.1도 값을 다른 이름·필드로 구분하고, 엔코더 CPR, 감속비, 유성기어 기구비, 원점 기준을 적용해야 한다.

### 19.6 모터1 카운터 overflow 통일

모터2와 달리 모터1은 signed overflow를 명시적으로 처리하지 않는다. 두 카운터의 정책을 통일하거나, 제한된 범위에서 안전하게 차이를 계산하는 계수 방식을 정의해야 한다.

### 19.7 EXTI 기반 엔코더의 속도 한계 검증

현재는 A상 상승마다 CPU 인터럽트를 일으킨다. 최대 모터 RPM, 엔코더 PPR, 감속비를 이용해 초당 인터럽트 수를 계산하고 누락 여부를 측정해야 한다. 필요하면 TIM Encoder Mode와 입력 digital filter로 이전한다.

### 19.8 모터 방향 반전 절차

정방향 명령 직후 역방향 명령이 오면 코드가 방향 핀과 PWM compare를 즉시 변경한다. 기구 관성이나 H-bridge 특성에 따라 큰 전류가 흐를 수 있으므로 PWM 0 → 정지 확인/짧은 dead time → 방향 변경 → ramp-up 절차가 필요할 수 있다.

---

## 20. 초보자가 디버거에서 보면 좋은 변수

STM32CubeIDE에서 breakpoint를 사용하거나 Expressions/Live Expressions로 다음 값을 보면 흐름을 이해하기 쉽다.

| 변수 | 관찰 포인트 |
|---|---|
| `cornerId` | PA0/PA1 조합이 0~3 중 무엇으로 읽히는가 |
| `myAddress` | 기대한 `0x10`~`0x13`인가 |
| `lastCommand` | ESP32가 보낸 문자가 도착하는가 |
| `htim1.Instance`, `htim2.Instance`, `htim3.Instance` | 핸들이 올바른 타이머를 가리키는가 |
| 각 TIM의 CCR | 명령에 따라 0, 599, 699 등으로 바뀌는가 |
| `encoderCount` | 모터1 회전 방향에 따라 증감하는가 |
| `motor2_encoder_count` | 모터2 회전 방향에 따라 증감하는가 |
| `i2c_tx_buf[0..7]` | 상태 패킷이 규격과 맞게 만들어지는가 |
| `hi2c1.State`, `hi2c1.ErrorCode` | I2C가 listen/ready/error 중 어디에 있는가 |

실제 모터가 연결된 상태에서 breakpoint로 CPU를 멈추면 PWM 하드웨어는 계속 동작할 수 있다. 먼저 모터 전원을 분리하거나 드라이버 enable을 안전하게 차단한 무부하 상태에서 디버깅해야 한다.

---

## 21. 코드를 읽는 추천 순서

처음부터 모든 HAL 내부 코드를 따라가면 양이 너무 많다. 다음 순서가 이해하기 쉽다.

1. `main.c`의 전역변수와 `ApplyCommand()`를 읽어 입력 문자와 모터 출력을 연결한다.
2. `SetMotor()`에서 방향 핀과 PWM compare가 어떻게 정해지는지 본다.
3. `main()`의 부팅 순서를 읽는다.
4. `MX_GPIO_Init()`과 세 타이머 초기화에서 실제 핀과 1 kHz PWM을 확인한다.
5. `stm32f1xx_hal_msp.c`에서 I2C/PWM 핀과 주변장치 클록을 확인한다.
6. `stm32f1xx_it.c`에서 인터럽트가 HAL로 들어가는 경로를 확인한다.
7. 다시 `main.c`의 HAL 콜백을 읽어 I2C와 엔코더 사건의 최종 처리를 확인한다.
8. 마지막으로 `syscalls.c`, `sysmem.c`, `system_stm32f1xx.c`를 런타임 기반 파일로 이해한다.

---

## 22. 용어 정리

| 용어 | 쉬운 설명 |
|---|---|
| MCU | CPU, RAM, Flash, GPIO, 타이머 등이 한 칩에 들어간 마이크로컨트롤러 |
| GPIO | 디지털 High/Low를 입력받거나 출력하는 핀 |
| Alternate Function | GPIO 핀을 타이머 PWM, I2C 같은 주변장치에 연결하는 모드 |
| RCC | 각 클록원을 선택하고 주변장치 클록을 켜는 블록 |
| HSE / HSI | 외부 고속 발진원 / 내부 고속 발진원 |
| PLL | 입력 클록을 배수하여 더 높은 주파수를 만드는 회로 |
| PWM | 빠른 ON/OFF의 시간 비율로 평균 출력을 조절하는 방식 |
| Prescaler | 타이머 입력 클록을 나누는 값 |
| Period/ARR | 타이머가 어디까지 센 뒤 0으로 돌아갈지 정하는 값 |
| CCR/compare | PWM에서 출력 전환 시점을 정하는 비교값 |
| I2C master | 클록과 통신 시작을 주도하는 장치. 현재 ESP32 |
| I2C slave | 주소 호출에 응답하는 장치. 현재 STM32 |
| EXTI | 외부 핀 에지로 CPU 인터럽트를 발생시키는 기능 |
| NVIC | 어떤 인터럽트를 허용하고 우선순위를 어떻게 둘지 관리하는 블록 |
| ISR/IRQHandler | 인터럽트 발생 시 CPU가 우선 실행하는 함수 |
| callback | HAL 처리가 끝난 특정 시점에 사용자 코드를 실행하도록 정한 함수 |
| open loop | 센서 결과로 오차를 보정하지 않고 정해진 출력만 내는 제어 |
| closed loop | 센서 측정값과 목표값의 오차를 이용해 출력을 계속 보정하는 제어 |
| little-endian | 여러 바이트 정수에서 가장 낮은 8비트를 먼저 보내는 순서 |
| heap | `malloc()` 등이 실행 중 할당하는 RAM 영역 |
| stack | 함수 호출, 지역변수, 복귀 주소 등에 쓰는 RAM 영역 |

---

## 23. 관련 파일과 문서

- STM32 애플리케이션: [`main.c`](../../stm32/mobility/Core/Src/main.c)
- 공통 핀 정의: [`main.h`](../../stm32/mobility/Core/Inc/main.h)
- CubeMX 설정 원본: [`mobility.ioc`](../../stm32/mobility/mobility.ioc)
- 공용 통신 규격: [`protocol.md`](../../protocol/protocol.md)
- 모터1·2 엔코더 비교: [`20260907_130217_모터1_모터2_엔코더_읽기_비교.md`](20260907_130217_모터1_모터2_엔코더_읽기_비교.md)
- 모터2 엔코더 추가 기록: [`20260907_122148_motor2_엔코더_추가.md`](20260907_122148_motor2_엔코더_추가.md)
- 휠·트랙 전환 목표 설계: [`휠_트랙_모드_전환_시퀀스.md`](휠_트랙_모드_전환_시퀀스.md)

이 문서를 기준으로 코드를 수정할 때는 `protocol/protocol.md`의 단위와 바이트 순서를 먼저 확인하고, 실제 모터 시험은 저속·저출력·무부하·단일 모듈부터 시작해야 한다.
