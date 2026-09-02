# 로봇 프로젝트 인수인계 문서

가제보(ROS2) 시뮬레이션으로 설계한 4족 바퀴/궤도 전환 로봇을, 실제 하드웨어(ESP32 + STM32 4개 + L298N + MG513/서보 모터)로 구현하는 프로젝트입니다.

---

## 1. 전체 구조 개요

```
노트북(파이썬 키보드 클라이언트)
   │  USB 시리얼 (또는 WiFi/TCP)
   ▼
ESP32 (WiFi AP + I2C 마스터)
   │  I2C 버스 (SDA=GPIO21, SCL=GPIO22)
   ▼
STM32 x4 (다리 1개당 1개, I2C 슬레이브, 주소 0x10~0x13)
   │  PWM + DIR 핀
   ▼
L298N 모터드라이버 (다리 1개당 2개)
   │
   ▼
모터 (다리 1개당 3개: MG513 x2, 5V DC x1)
```

**핵심 설계 원칙**: STM32 1개 = 다리(코너) 1개. 부팅 시 점퍼 핀을 읽어서 자기 코너 위치와 I2C 주소를 스스로 결정합니다.

---

## 2. 다리(코너) 1개당 하드웨어 — 유성기어 시스템

각 다리는 **유성기어(선기어-링기어-캐리어)** 로 궤도/바퀴 위치를 전환합니다. 모터는 3개입니다.

| 모터 | 종류 | 역할 |
|---|---|---|
| **바퀴축 모터** | MG513 (12V, 엔코더 있음) | 독립적으로 바퀴를 돌림 (일반 주행) |
| **선기어 모터** | MG513 (12V, 엔코더 있음) | 유성기어의 선기어를 돌림 (고정 상태에 따라 두 가지 역할) |
| **고정전환 모터** | 5V DC (엔코더 없음) | 링기어/캐리어 중 어느 쪽을 고정할지 전환 |

**선기어 모터의 이중 역할**:
- 링기어 고정 상태 → 선기어 회전 시 **캐리어가 회전** → 바퀴 지지축 위치 변경 (다리 접기/펴기)
- 캐리어 고정 상태 → 선기어 회전 시 **링기어가 회전** → 무한궤도 구동 (궤도 주행)

---

## 3. 핀 배정 (STM32F103C8T6, 다리 1개 기준)

### 3-1. I2C (ESP32와 통신)
| 용도 | 핀 |
|---|---|
| SCL | PB6 |
| SDA | PB7 |
| 코너 ID 점퍼 1 | PA0 (GND=0, 오픈=1) |
| 코너 ID 점퍼 2 | PA1 (GND=0, 오픈=1) |

코너 ID 점퍼표:

| PA0 | PA1 | 주소 | 위치 |
|---|---|---|---|
| GND | GND | 0x10 | 좌전 |
| 오픈 | GND | 0x11 | 우전 |
| GND | 오픈 | 0x12 | 좌후 |
| 오픈 | 오픈 | 0x13 | 우후 |

**I2C 풀업**: SDA, SCL 각각 4.7kΩ 저항을 3.3V로 (버스 전체에 1쌍만 필요, 보드마다 X). STM32(F103)는 오픈드레인 출력 핀에 내장 풀업을 못 쓰므로 외부 저항 필수. STM32가 1개일 때는 ESP32 내장 풀업만으로도 버텼지만, 2개 이상 물리면 반드시 외부 저항 필요.

### 3-2. 바퀴축 모터 (L298N #1, 채널 A)
| L298N 핀 | STM32 핀 | 역할 |
|---|---|---|
| ENA | PA6 (TIM3 CH1) | PWM |
| IN1 | PA7 | DIR1 |
| IN2 | PB0 | DIR2 |

엔코더: V+ → 3.3V / GND → 공통 / A상 → PA4 (EXTI4) / B상 → PA5

### 3-3. 선기어 모터 (L298N #1, 채널 B)
| L298N 핀 | STM32 핀 | 역할 |
|---|---|---|
| ENB | PA8 (TIM1 CH1) | PWM |
| IN3 | PB1 | DIR1 |
| IN4 | PB10 | DIR2 |

엔코더: V+ → 3.3V / GND → 공통 / A상 → PB3 (EXTI3) / B상 → PB5

### 3-4. 고정전환 모터 (L298N #2, 채널 A)
| L298N 핀 | STM32 핀 | 역할 |
|---|---|---|
| ENA | PA2 (TIM2 CH3) | PWM |
| IN1 | PB8 | DIR1 |
| IN2 | PB9 | DIR2 |

엔코더 없음.

### 3-5. 기타
| 용도 | 핀 |
|---|---|
| 보드 LED (동작 확인용) | PC13 |
| ST-Link SWDIO | PA13 |
| ST-Link SWCLK | PA14 |

---

## 4. 전원 배선

**절대 원칙: 모터 전원(12V/5V)과 로직 전원(STM32/ESP32용 5V, 3.3V)은 분리한다.** 모터 기동 전류가 로직 전원까지 흔들면 MCU가 리셋되어 통신이 끊긴다 (실제로 이 문제로 여러 번 애먹었음, 아래 8절 참고).

| 레일 | 공급 대상 | 비고 |
|---|---|---|
| 12V (배터리) | L298N #1의 모터전원 단자 (바퀴축+선기어 MG513 2개) | 5V 인에이블 점퍼 **제거 필수** |
| 5V (모터용, 로직과 분리된 별도 공급원) | L298N #2의 모터전원 단자 (고정전환 5V 모터) | 점퍼는 유지 가능하지만 **로직 레일과 절대 공유 금지** — 별도 5V 공급원 사용 |
| 5V (로직 전용, 벅컨버터 등) | ESP32, STM32 x4 | 모터 전원과 물리적으로 분리 |
| GND | 전부 공통 | 스타 그라운드 권장 |

엔코더 전원은 **3.3V만** (GPIO가 5V 입력을 못 견딤).

---

## 5. STM32CubeIDE / CubeMX 설정 (다리 1개 기준)

1. **새 프로젝트**: STM32F103C8Tx 선택, 초기화 없이 시작
2. **SYS**: Debug = Serial Wire (JTAG 안 씀, SWD만)
3. **RCC**: HSE = Crystal/Ceramic Resonator (단, HSE가 발진 안 하는 불량 보드가 있었음 — 이 경우 5-1절 HSI 우회 참고)
4. **Clock Configuration**: HCLK 72MHz로 (HSE 기준 PLL x9)
5. **I2C1**: Mode=I2C, Speed=Standard(100kHz), GPIO Settings에서 PB6/PB7 Pull-up 시도 가능하나 F103은 AF 출력에 내장 풀업 불가 (회색 비활성화, 정상)
6. **TIM1**: Channel1 = **PWM Generation CH1** (Output Compare 아님! 이거 잘못 설정해서 한참 헤맸음), Prescaler=71, Period=999
7. **TIM2**: Channel3 = PWM Generation CH3, 같은 Prescaler/Period. PB8, PB9는 GPIO_Output
8. **TIM3**: Channel1 = PWM Generation CH1, 같은 설정
9. **GPIO**: PA0/PA1 = Input Pull-up (ID 점퍼), 나머지 DIR 핀들 = GPIO_Output
10. NVIC에서 I2C1 event/error interrupt 활성화
11. Generate Code

### 5-1. HSE 크리스탈이 불량인 보드용 우회책

`SystemClock_Config()`에서 `Error_Handler()`로 빠지면(즉 `while(1)`에 갇히면) HSE 크리스탈 불량 의심. 아래처럼 HSI(내장 8MHz)로 대체:

```c
void SystemClock_Config(void)
{
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSI;
  RCC_OscInitStruct.HSIState = RCC_HSI_ON;
  RCC_OscInitStruct.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
  RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSI_DIV2;
  RCC_OscInitStruct.PLL.PLLMUL = RCC_PLL_MUL16;
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK) { Error_Handler(); }

  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_SYSCLK
                              |RCC_CLOCKTYPE_PCLK1|RCC_CLOCKTYPE_PCLK2;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV2;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;
  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_2) != HAL_OK) { Error_Handler(); }
}
```

64MHz로 살짝 낮아지지만 모터 PWM에는 전혀 문제없음.

---

## 6. STM32 main.c 최신 코드 (선기어 모터 명령은 아직 미완성 — 7절 TODO 참고)

```c
/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.c
  * @brief          : Main program body
  ******************************************************************************
  */
/* USER CODE END Header */
#include "main.h"

/* USER CODE BEGIN Includes */
#include <string.h>
#include <stdlib.h>
/* USER CODE END Includes */

I2C_HandleTypeDef hi2c1;
TIM_HandleTypeDef htim1;
TIM_HandleTypeDef htim2;
TIM_HandleTypeDef htim3;

/* USER CODE BEGIN PV */
typedef enum { CORNER_LF = 0, CORNER_RF = 1, CORNER_LR = 2, CORNER_RR = 3 } CornerId;
CornerId cornerId;
uint8_t myAddress;
uint8_t isLeftSide;

uint8_t i2c_rx_buf[1];
uint8_t i2c_tx_buf[3];
volatile char lastCommand = 'k';

uint8_t currentMode = 0;
int16_t carrierAngleTenths = 0;

// 엔코더 (바퀴축 모터, PA4/PA5)
volatile int32_t encoderCount = 0;

// 모드 전환 모터(5V, 논블로킹 타이밍)
volatile uint8_t modeSwitchActive = 0;
volatile uint32_t modeSwitchStartTick = 0;
const uint32_t MODE_SWITCH_DURATION_MS = 1000;
/* USER CODE END PV */

void SystemClock_Config(void);
static void MX_GPIO_Init(void);
static void MX_I2C1_Init(void);
static void MX_TIM1_Init(void);
static void MX_TIM2_Init(void);
static void MX_TIM3_Init(void);

/* USER CODE BEGIN PFP */
void ReadCornerId(void);
void ApplyCommand(char cmd);
void SetMotor(TIM_HandleTypeDef *htim, uint32_t channel,
              GPIO_TypeDef *dir1Port, uint16_t dir1Pin,
              GPIO_TypeDef *dir2Port, uint16_t dir2Pin,
              int16_t speedPercent);
void PrepareStatusBuffer(void);
/* USER CODE END PFP */

/* USER CODE BEGIN 0 */
void ReadCornerId(void)
{
  uint8_t bitA = (HAL_GPIO_ReadPin(GPIOA, GPIO_PIN_0) == GPIO_PIN_RESET) ? 0 : 1;
  uint8_t bitB = (HAL_GPIO_ReadPin(GPIOA, GPIO_PIN_1) == GPIO_PIN_RESET) ? 0 : 1;
  cornerId = (CornerId)((bitB << 1) | bitA);
  myAddress = 0x10 + cornerId;
  isLeftSide = (cornerId == CORNER_LF || cornerId == CORNER_LR) ? 1 : 0;
}

void SetMotor(TIM_HandleTypeDef *htim, uint32_t channel,
              GPIO_TypeDef *dir1Port, uint16_t dir1Pin,
              GPIO_TypeDef *dir2Port, uint16_t dir2Pin,
              int16_t speedPercent)
{
  if (speedPercent > 100) speedPercent = 100;
  if (speedPercent < -100) speedPercent = -100;

  if (speedPercent > 0) {
    HAL_GPIO_WritePin(dir1Port, dir1Pin, GPIO_PIN_SET);
    HAL_GPIO_WritePin(dir2Port, dir2Pin, GPIO_PIN_RESET);
  } else if (speedPercent < 0) {
    HAL_GPIO_WritePin(dir1Port, dir1Pin, GPIO_PIN_RESET);
    HAL_GPIO_WritePin(dir2Port, dir2Pin, GPIO_PIN_SET);
  } else {
    HAL_GPIO_WritePin(dir1Port, dir1Pin, GPIO_PIN_RESET);
    HAL_GPIO_WritePin(dir2Port, dir2Pin, GPIO_PIN_RESET);
  }

  uint32_t period = htim->Init.Period;
  uint32_t duty = (uint32_t)((abs(speedPercent) * (int32_t)period) / 100);
  __HAL_TIM_SET_COMPARE(htim, channel, duty);
}

void ApplyCommand(char cmd)
{
  int sign = isLeftSide ? 1 : -1;

  switch (cmd) {
    case 'f':  // 모드 전환 - 5V 고정전환 모터, 논블로킹
      currentMode = (currentMode == 0) ? 2 : 0;
      if (currentMode == 2) {
        SetMotor(&htim2, TIM_CHANNEL_3, GPIOB, GPIO_PIN_8, GPIOB, GPIO_PIN_9, 60);
      } else {
        SetMotor(&htim2, TIM_CHANNEL_3, GPIOB, GPIO_PIN_8, GPIOB, GPIO_PIN_9, -60);
      }
      modeSwitchStartTick = HAL_GetTick();
      modeSwitchActive = 1;
      break;

    case 'i':  // 전진 (바퀴축 모터)
      SetMotor(&htim3, TIM_CHANNEL_1, GPIOA, GPIO_PIN_7, GPIOB, GPIO_PIN_0, (int16_t)(70 * sign));
      break;
    case ',':  // 후진
      SetMotor(&htim3, TIM_CHANNEL_1, GPIOA, GPIO_PIN_7, GPIOB, GPIO_PIN_0, (int16_t)(-70 * sign));
      break;
    case 'j':  // 좌회전
      SetMotor(&htim3, TIM_CHANNEL_1, GPIOA, GPIO_PIN_7, GPIOB, GPIO_PIN_0, isLeftSide ? -40 : 70);
      break;
    case 'l':  // 우회전
      SetMotor(&htim3, TIM_CHANNEL_1, GPIOA, GPIO_PIN_7, GPIOB, GPIO_PIN_0, isLeftSide ? 70 : -40);
      break;

    case 'k':  // 정지 - 모드전환+바퀴축 모터
      SetMotor(&htim2, TIM_CHANNEL_3, GPIOB, GPIO_PIN_8, GPIOB, GPIO_PIN_9, 0);
      SetMotor(&htim3, TIM_CHANNEL_1, GPIOA, GPIO_PIN_7, GPIOB, GPIO_PIN_0, 0);
      // TODO: 선기어 모터(htim1) 정지도 추가 필요
      modeSwitchActive = 0;
      break;

    case '1':
      currentMode = 1;
      break;
    case '2':
      currentMode = 2;
      break;
    default:
      break;
  }
}

void PrepareStatusBuffer(void)
{
  i2c_tx_buf[0] = currentMode;
  i2c_tx_buf[1] = (uint8_t)(carrierAngleTenths & 0xFF);
  i2c_tx_buf[2] = (uint8_t)((carrierAngleTenths >> 8) & 0xFF);
}

void HAL_I2C_AddrCallback(I2C_HandleTypeDef *hi2c, uint8_t TransferDirection, uint16_t AddrMatchCode)
{
  if (TransferDirection == I2C_DIRECTION_TRANSMIT) {
    HAL_I2C_Slave_Sequential_Receive_IT(hi2c, i2c_rx_buf, 1, I2C_FIRST_AND_LAST_FRAME);
  } else {
    PrepareStatusBuffer();
    HAL_I2C_Slave_Sequential_Transmit_IT(hi2c, i2c_tx_buf, 3, I2C_FIRST_AND_LAST_FRAME);
  }
}

void HAL_I2C_SlaveRxCpltCallback(I2C_HandleTypeDef *hi2c)
{
  lastCommand = (char)i2c_rx_buf[0];
  ApplyCommand(lastCommand);
  HAL_I2C_EnableListen_IT(hi2c);
}

void HAL_I2C_SlaveTxCpltCallback(I2C_HandleTypeDef *hi2c)
{
  HAL_I2C_EnableListen_IT(hi2c);
}

void HAL_I2C_ErrorCallback(I2C_HandleTypeDef *hi2c)
{
  HAL_I2C_DeInit(hi2c);
  HAL_I2C_Init(hi2c);
  HAL_I2C_EnableListen_IT(hi2c);
}

void EXTI4_IRQHandler(void)
{
  HAL_GPIO_EXTI_IRQHandler(GPIO_PIN_4);
}

void HAL_GPIO_EXTI_Callback(uint16_t GPIO_Pin)
{
  if (GPIO_Pin == GPIO_PIN_4)
  {
    if (HAL_GPIO_ReadPin(GPIOA, GPIO_PIN_5) == GPIO_PIN_RESET)
      encoderCount++;
    else
      encoderCount--;
  }
}
/* USER CODE END 0 */

int main(void)
{
  HAL_Init();
  SystemClock_Config();

  MX_GPIO_Init();
  MX_I2C1_Init();
  MX_TIM1_Init();
  MX_TIM2_Init();
  MX_TIM3_Init();

  /* USER CODE BEGIN 2 */
  ReadCornerId();
  hi2c1.Init.OwnAddress1 = myAddress << 1;
  HAL_I2C_Init(&hi2c1);

  ApplyCommand('k');
  HAL_I2C_EnableListen_IT(&hi2c1);

  HAL_TIM_PWM_Start(&htim1, TIM_CHANNEL_1);   // 이거 빠뜨려서 한참 헤맸음. Config만 하고
  HAL_TIM_PWM_Start(&htim2, TIM_CHANNEL_3);   // Start를 안 부르면 PWM이 절대 안 나감.
  HAL_TIM_PWM_Start(&htim3, TIM_CHANNEL_1);
  /* USER CODE END 2 */

  while (1)
  {
    carrierAngleTenths = (int16_t)(encoderCount % 32000);

    // 모드 전환 모터: 1초 지나면 논블로킹으로 정지
    if (modeSwitchActive && (HAL_GetTick() - modeSwitchStartTick >= MODE_SWITCH_DURATION_MS))
    {
      SetMotor(&htim2, TIM_CHANNEL_3, GPIOB, GPIO_PIN_8, GPIOB, GPIO_PIN_9, 0);
      modeSwitchActive = 0;
    }

    // 자가 복구: 완전히 멈춰있을 때(READY)만 다시 걸어준다.
    // (BUSY 상태일 때 건드리면 진행 중인 통신을 방해하게 됨)
    if (hi2c1.State == HAL_I2C_STATE_READY)
    {
      HAL_I2C_EnableListen_IT(&hi2c1);
    }

    HAL_GPIO_TogglePin(GPIOC, GPIO_PIN_13);
    HAL_Delay(10);
  }
}

// SystemClock_Config, MX_I2C1_Init, MX_TIM1_Init, MX_TIM2_Init, MX_TIM3_Init,
// MX_GPIO_Init, Error_Handler는 CubeMX가 생성한 표준 형태 + 아래 커스텀 부분만 추가:
//
// MX_GPIO_Init()의 USER CODE BEGIN MX_GPIO_Init_2 안에 추가:
//   - PC13을 GPIO_Output으로 (CubeMX Pinout에서 설정 안 했으므로 직접)
//   - PA4를 GPIO_MODE_IT_RISING (엔코더 A상 인터럽트)
//   - PA5를 GPIO_MODE_INPUT (엔코더 B상)
//   - HAL_NVIC_SetPriority(EXTI4_IRQn, 5, 0); HAL_NVIC_EnableIRQ(EXTI4_IRQn);
```

**전체 파일이 필요하면 이전 대화 로그에서 마지막으로 전달된 완전한 main.c를 참고하세요.**

---

## 7. TODO (미완성/알려진 과제)

1. **선기어 모터 명령 미구현**: `ApplyCommand()`에 htim1(선기어) 조작 로직이 아직 없음. 지금은 바퀴축(htim3)만 i/,/j/l로 조작 가능. 원래 설계는 `m` 키로 대상(바퀴/링기어) 전환 후 방향키로 조작하는 방식(가제보 최종 버전과 동일)으로 갈 계획이었으나, 모터 배선 검증이 우선이라 미룸.
2. **엔코더 각도 변환 미완성**: `carrierAngleTenths`는 지금 엔코더 원시 펄스 카운트를 그대로 담고 있음. 실제 "도(degree)" 단위로 변환하려면 모터의 엔코더 PPR(회전당 펄스 수)을 확인해서 계수를 곱해야 함.
3. **캐리어 각도 안전 한계값 없음**: 가제보 시뮬레이션에는 다리가 일정 각도(±120도 등) 이상 안 접히게 하는 제한이 있었는데, 실물에는 아직 구현 안 됨. 모터를 오래 누르고 있으면 기구적으로 걸릴 수 있으니 짧게짧게 테스트할 것.
4. **`k`(정지)에서 선기어 모터 정지 누락**: 위 코드의 `case 'k'`에 htim1 정지 코드 추가 필요.
5. **STM32 #2~4 미완성**: 지금까지 검증된 건 STM32 #1(주소 0x10) 하나뿐. 나머지 3개는 같은 코드를 올리고 점퍼만 다르게 설정하면 되지만, 실제 연결/검증은 아직 안 함.
6. **모터 3개 → L298N 2개 필요**: 다리 1개당 모터가 3개라 L298N도 2개 필요함 (기존 계획은 다리당 1개였음). 전체 4다리 기준 L298N 8개 필요.

---

## 8. 겪었던 문제와 해결 이력 (똑같은 삽질 방지용)

| 증상 | 원인 | 해결 |
|---|---|---|
| ST-Link 업로드 시 `DEV_TARGET_RESET_ERR` | 전원 부족 또는 배선 헐거움 | 자체 USB 전원 사용, SWD 배선 재확인, Reset Mode를 Hardware reset으로 |
| 업로드 중 `Error finishing flash operation` | 브레드보드 배선 불안정, SWD 클럭 너무 빠름 | Debug Configurations에서 Frequency를 480kHz로 낮춤 |
| I2C 스캐너에서 유령 주소 여러 개 잡힘 | 외부 풀업 저항 없음(ESP32 내장 풀업만으로는 부족) | SDA/SCL에 4.7kΩ 외부 저항 추가 |
| STM32가 한 번 응답하고 계속 먹통 | I2C 에러 발생 시 단순 재리슨만으로 복구 안 됨 | `HAL_I2C_ErrorCallback`에서 `HAL_I2C_DeInit`+`HAL_I2C_Init` 후 재리슨 |
| I2C 쓰기/읽기가 간헐적으로 실패 (`writeErr=4`) | 마스터가 명령 쓰고 바로 읽기 요청하는 간격이 너무 짧음(200us) | 간격을 3~10ms로 늘림. STM32의 `HAL_I2C_AddrCallback`에서 `I2C_NEXT_FRAME` 대신 `I2C_FIRST_AND_LAST_FRAME` 사용 (단발성 전송이므로) |
| STM32 LED가 계속 켜져있어서 "멈췄나?" 오해 | `HAL_Delay(10)`이라 50Hz로 너무 빨리 깜빡여서 눈에 안 보임 | `HAL_Delay(500)`으로 잠깐 바꿔서 확인 → 정상 작동 확인됨 |
| STM32가 `Error_Handler()`의 `while(1)`에 갇힘 | 외부 HSE 크리스탈 발진 실패 (보드 불량) | HSI(내장클럭) + PLL x16으로 우회 (5-1절 참고) |
| PWM 핀에서 신호가 전혀 안 나옴 | `HAL_TIM_PWM_ConfigChannel()`만 호출하고 `HAL_TIM_PWM_Start()`를 안 부름 | `main()`의 USER CODE 2에 `HAL_TIM_PWM_Start()` 3줄 추가 |
| TIM1이 PWM Generation이 아니라 Output Compare로 설정됨 | CubeMX에서 Channel1을 잘못 선택 (Output Compare CH1으로) | 'PWM Generation CH1'으로 재설정, `HAL_TIM_OC_Init`→`HAL_TIM_PWM_Init`, `TIM_OCMODE_TIMING`→`TIM_OCMODE_PWM1`로 코드도 수동 수정 |
| 모드 전환(5V 모터) 시마다 WiFi 연결이 끊김 | 모터 기동 전류가 로직 전원(5V 레일)과 공유되어 전압 강하 → ESP32/STM32 브라운아웃 | 모터 전원을 로직 레일과 분리 (별도 5V 공급원 사용) |
| `ApplyCommand()`에 `HAL_Delay(500)` 넣었더니 I2C 응답이 그동안 막힘 | I2C 콜백(인터럽트 컨텍스트) 안에서 블로킹 딜레이 사용 | `HAL_GetTick()` 기반 논블로킹 타이밍으로 재설계 (6절 코드 참고) |
| L298N OUT2에서 LED가 안 켜짐 | 처음엔 "정상(H-브릿지 특성)"으로 오판했으나, 실제로는 방향 반대일 때도 안 켜짐 → 단선 | 배선 재점검으로 단선 지점 찾아 수리 |
| STM32가 총 2개 이상 물릴 때 하나가 죽어있음 | 개별 STM32 보드의 하드웨어 불량(크리스탈 등) | 여유 보드로 교체 또는 HSI 우회 |
| 전체 시스템이 갑자기 다 멈춤(모든 모터 무반응) | 배선 작업 중 어딘가 헐거워지거나 쇼트 (진행 중, 미해결) | 진단 중: 열/냄새 없음, STM32 LED 정상, I2C도 `ok=true`로 정상 — L298N 전원/배선 재확인 필요 |

---

## 9. 관련 소프트웨어 파일

| 파일 | 역할 |
|---|---|
| `main.c` | STM32 펌웨어 (STM32CubeIDE 프로젝트) |
| `esp32_i2c_master.ino` | ESP32 — WiFi AP + I2C 마스터 + USB 시리얼 명령 수신 |
| `robot_control_client.py` | 노트북 — WiFi(TCP)로 키보드 명령 전송 |
| `pc/robot_control_client_serial.py` | 노트북 — USB 시리얼로 키보드 명령 전송 (WiFi 인터넷 유지하며 테스트 가능) |
| `i2c_scanner.ino` | 진단용 — I2C 버스에 응답하는 장치 주소 스캔 |

### 키 매핑 (파이썬 클라이언트 공통)
```
i 전진 / , 후진 / j 좌회전 / l 우회전 / k 정지
f 모드 전환(고정전환 모터 1초 구동) / 1, 2 예약(미사용)
ESC 종료
```

---

## 10. 지금 당장 이어서 할 일 (인수 시 우선순위)

1. **9절 표의 마지막 행(전체 시스템 정지) 문제부터 해결** — L298N #1 전원(12V, GND) 배선을 처음부터 다시 확인, 특히 선기어 모터 연결하면서 흔들린 부분 없는지
2. 해결되면 선기어 모터(htim1) 명령을 `ApplyCommand()`에 추가
3. STM32 #2~4를 같은 방식으로 배선·검증 (점퍼만 다르게)
4. 캐리어 각도 안전 한계값 구현 (엔코더 PPR 확인 후)
5. `m` 키 기반 3모드 전환 방식으로 조작 체계 정리 (가제보 최종 버전과 일치시키기)
