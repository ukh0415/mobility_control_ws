# STM32 설정 최신본 (3모터 독립 제어 버전)

다리 1개(STM32 1개)를 기준으로, 바퀴축/선기어/고정전환 세 모터를 각각 독립적으로 정/역 회전시키는 최신 버전입니다.

---

## 1. 핀 배정 전체표

| 핀 | 기능 | 용도 |
|---|---|---|
| PA8 | TIM1_CH1 (PWM) | 선기어 모터 속도 |
| PB1 | GPIO_Output | 선기어 모터 DIR1 |
| PB10 | GPIO_Output | 선기어 모터 DIR2 |
| PA2 | TIM2_CH3 (PWM) | 고정전환 모터 속도 |
| PB8 | GPIO_Output | 고정전환 모터 DIR1 |
| PB9 | GPIO_Output | 고정전환 모터 DIR2 |
| PA6 | TIM3_CH1 (PWM) | 바퀴축 모터 속도 |
| PA7 | GPIO_Output | 바퀴축 모터 DIR1 |
| PB0 | GPIO_Output | 바퀴축 모터 DIR2 |
| PA4 | GPIO_EXTI4 | 바퀴축 모터 엔코더 A상 (인터럽트) |
| PA5 | GPIO_Input | 바퀴축 모터 엔코더 B상 |
| PB3 | GPIO_EXTI3 (선택) | 선기어 모터 엔코더 A상 — 코드 미구현, 필요시 설정 |
| PB5 | GPIO_Input (선택) | 선기어 모터 엔코더 B상 — 코드 미구현, 필요시 설정 |
| PB6 | I2C1_SCL | ESP32와 통신 |
| PB7 | I2C1_SDA | ESP32와 통신 |
| PA0 | GPIO_Input (Pull-up) | 코너 ID 점퍼 1 |
| PA1 | GPIO_Input (Pull-up) | 코너 ID 점퍼 2 |
| PC13 | GPIO_Output | 보드 LED (동작 확인용) |
| PA13 | SWDIO | ST-Link (SYS=Serial Wire 설정 시 자동 예약) |
| PA14 | SWCLK | ST-Link (SYS=Serial Wire 설정 시 자동 예약) |

코너 ID 점퍼표 (다리 여러 개 연결 시):

| PA0 | PA1 | I2C 주소 | 위치 |
|---|---|---|---|
| GND | GND | 0x10 | 좌전 |
| 오픈 | GND | 0x11 | 우전 |
| GND | 오픈 | 0x12 | 좌후 |
| 오픈 | 오픈 | 0x13 | 우후 |

---

## 2. CubeMX 설정 순서

1. **SYS**: Debug = Serial Wire
2. **RCC**: HSE = Crystal/Ceramic Resonator (보드 불량 시 3절 HSI 우회 참고)
3. **Clock Configuration**: HCLK = 72 (Enter 치면 PLL x9, APB1 /2, APB2 /1 자동 계산)
4. **I2C1**: Mode=I2C, Speed Mode=Standard, Speed=100000. NVIC에서 I2C1 event/error interrupt 둘 다 체크
5. **TIM1**: Channel1=PWM Generation CH1 (PA8), Prescaler=71, Period=999
6. **TIM2**: Channel3=PWM Generation CH3 (PA2), 같은 Prescaler/Period
7. **TIM3**: Channel1=PWM Generation CH1 (PA6), 같은 Prescaler/Period
8. **GPIO_Output 설정**: PA7, PB0, PB1, PB10, PB8, PB9, PC13
9. **GPIO_Input 설정**: PA0, PA1 (Pull-up), PA5, (선택)PB5
10. **EXTI 설정**: PA4 = GPIO_EXTI4 (Rising edge), (선택)PB3 = GPIO_EXTI3. NVIC에서 EXTI Line4(, Line3) interrupt 체크
11. Ctrl+S → Generate Code

핀 그림(Pinout view)에서 직접 클릭해서 기능 선택 → Categories에서 세부 파라미터(Prescaler, Pull-up 등) 조정, 순서는 반대로 해도 결과 동일함.

### 2-1. HSE 크리스탈 불량 보드용 우회 (필요시)

보드가 `Error_Handler()`의 `while(1)`에 갇히면 HSE 크리스탈 발진 실패. `SystemClock_Config()`를 아래로 교체:

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

72MHz→64MHz로 낮아지지만 모터 PWM에는 문제없음.

---

## 3. 키 매핑 (최신)

| 키 | 모터 | 동작 |
|---|---|---|
| `i` | 바퀴축 | 정회전 |
| `,` | 바퀴축 | 역회전 |
| `j` | 선기어 | 정회전 |
| `l` | 선기어 | 역회전 |
| `u` | 고정전환 | 정회전 |
| `o` | 고정전환 | 역회전 |
| `k` | 전체 | 정지 |

파이썬 클라이언트 쪽 설정:
```python
MOVE_KEYS = {"i", ",", "j", "l", "u", "o"}
TOGGLE_KEYS = set()
STOP_KEY = "k"
```

---

## 4. main.c 전체 코드

```c
/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.c
  * @brief          : Main program body
  ******************************************************************************
  * @attention
  *
  * Copyright (c) 2026 STMicroelectronics.
  * All rights reserved.
  *
  * This software is licensed under terms that can be found in the LICENSE file
  * in the root directory of this software component.
  * If no LICENSE file comes with this software, it is provided AS-IS.
  *
  ******************************************************************************
  */
/* USER CODE END Header */
/* Includes ------------------------------------------------------------------*/
#include "main.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */
#include <string.h>
#include <stdlib.h>
/* USER CODE END Includes */

/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN PTD */

/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */

/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/
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
/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
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

/* Private user code ---------------------------------------------------------*/
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
  switch (cmd) {
    // ---- 바퀴축 모터 (htim3, PA6/PA7/PB0) ----
    case 'i':  // 정회전
      SetMotor(&htim3, TIM_CHANNEL_1, GPIOA, GPIO_PIN_7, GPIOB, GPIO_PIN_0, 70);
      break;
    case ',':  // 역회전
      SetMotor(&htim3, TIM_CHANNEL_1, GPIOA, GPIO_PIN_7, GPIOB, GPIO_PIN_0, -70);
      break;

    // ---- 선기어 모터 (htim1, PA8/PB1/PB10) ----
    case 'j':  // 정회전
      SetMotor(&htim1, TIM_CHANNEL_1, GPIOB, GPIO_PIN_1, GPIOB, GPIO_PIN_10, 70);
      break;
    case 'l':  // 역회전
      SetMotor(&htim1, TIM_CHANNEL_1, GPIOB, GPIO_PIN_1, GPIOB, GPIO_PIN_10, -70);
      break;

    // ---- 고정전환 모터 (htim2, PA2/PB8/PB9) ----
    case 'u':  // 정회전
      SetMotor(&htim2, TIM_CHANNEL_3, GPIOB, GPIO_PIN_8, GPIOB, GPIO_PIN_9, 60);
      break;
    case 'o':  // 역회전
      SetMotor(&htim2, TIM_CHANNEL_3, GPIOB, GPIO_PIN_8, GPIOB, GPIO_PIN_9, -60);
      break;

    // ---- 전체 정지 ----
    case 'k':
      SetMotor(&htim3, TIM_CHANNEL_1, GPIOA, GPIO_PIN_7, GPIOB, GPIO_PIN_0, 0);
      SetMotor(&htim1, TIM_CHANNEL_1, GPIOB, GPIO_PIN_1, GPIOB, GPIO_PIN_10, 0);
      SetMotor(&htim2, TIM_CHANNEL_3, GPIOB, GPIO_PIN_8, GPIOB, GPIO_PIN_9, 0);
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

/* ---- HAL I2C 슬레이브 콜백들 ---- */

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

/* ---- 엔코더 A상(PA4) 인터럽트 (바퀴축 모터용) ---- */

void EXTI4_IRQHandler(void)
{
  HAL_GPIO_EXTI_IRQHandler(GPIO_PIN_4);
}

void HAL_GPIO_EXTI_Callback(uint16_t GPIO_Pin)
{
  if (GPIO_Pin == GPIO_PIN_4)
  {
    if (HAL_GPIO_ReadPin(GPIOA, GPIO_PIN_5) == GPIO_PIN_RESET)
    {
      encoderCount++;
    }
    else
    {
      encoderCount--;
    }
  }
}

/* USER CODE END 0 */

/**
  * @brief  The application entry point.
  * @retval int
  */
int main(void)
{

  /* USER CODE BEGIN 1 */

  /* USER CODE END 1 */

  HAL_Init();

  /* USER CODE BEGIN Init */

  /* USER CODE END Init */

  SystemClock_Config();

  /* USER CODE BEGIN SysInit */

  /* USER CODE END SysInit */

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

  HAL_TIM_PWM_Start(&htim1, TIM_CHANNEL_1);
  HAL_TIM_PWM_Start(&htim2, TIM_CHANNEL_3);
  HAL_TIM_PWM_Start(&htim3, TIM_CHANNEL_1);
  /* USER CODE END 2 */

  /* Infinite loop */
  /* USER CODE BEGIN WHILE */
  while (1)
  {
	  carrierAngleTenths = (int16_t)(encoderCount % 32000);

	  // 자가 복구: 완전히 멈춰있을 때(READY)만 다시 걸어준다.
	  if (hi2c1.State == HAL_I2C_STATE_READY)
	  {
	    HAL_I2C_EnableListen_IT(&hi2c1);
	  }

	  HAL_GPIO_TogglePin(GPIOC, GPIO_PIN_13);
	  HAL_Delay(10);
    /* USER CODE END WHILE */

    /* USER CODE BEGIN 3 */
  }
  /* USER CODE END 3 */
}

/**
  * @brief System Clock Configuration
  * @retval None
  */
void SystemClock_Config(void)
{
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSE;
  RCC_OscInitStruct.HSEState = RCC_HSE_ON;
  RCC_OscInitStruct.HSEPredivValue = RCC_HSE_PREDIV_DIV1;
  RCC_OscInitStruct.HSIState = RCC_HSI_ON;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
  RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSE;
  RCC_OscInitStruct.PLL.PLLMUL = RCC_PLL_MUL9;
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
  {
    Error_Handler();
  }

  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_SYSCLK
                              |RCC_CLOCKTYPE_PCLK1|RCC_CLOCKTYPE_PCLK2;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV2;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;

  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_2) != HAL_OK)
  {
    Error_Handler();
  }
}

/**
  * @brief I2C1 Initialization Function
  */
static void MX_I2C1_Init(void)
{
  hi2c1.Instance = I2C1;
  hi2c1.Init.ClockSpeed = 100000;
  hi2c1.Init.DutyCycle = I2C_DUTYCYCLE_2;
  hi2c1.Init.OwnAddress1 = 0;
  hi2c1.Init.AddressingMode = I2C_ADDRESSINGMODE_7BIT;
  hi2c1.Init.DualAddressMode = I2C_DUALADDRESS_DISABLE;
  hi2c1.Init.OwnAddress2 = 0;
  hi2c1.Init.GeneralCallMode = I2C_GENERALCALL_DISABLE;
  hi2c1.Init.NoStretchMode = I2C_NOSTRETCH_DISABLE;
  if (HAL_I2C_Init(&hi2c1) != HAL_OK)
  {
    Error_Handler();
  }
}

/**
  * @brief TIM1 Initialization Function
  */
static void MX_TIM1_Init(void)
{
  TIM_MasterConfigTypeDef sMasterConfig = {0};
  TIM_OC_InitTypeDef sConfigOC = {0};
  TIM_BreakDeadTimeConfigTypeDef sBreakDeadTimeConfig = {0};

  htim1.Instance = TIM1;
  htim1.Init.Prescaler = 71;
  htim1.Init.CounterMode = TIM_COUNTERMODE_UP;
  htim1.Init.Period = 999;
  htim1.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;
  htim1.Init.RepetitionCounter = 0;
  htim1.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;
  if (HAL_TIM_PWM_Init(&htim1) != HAL_OK)
  {
    Error_Handler();
  }
  sMasterConfig.MasterOutputTrigger = TIM_TRGO_RESET;
  sMasterConfig.MasterSlaveMode = TIM_MASTERSLAVEMODE_DISABLE;
  if (HAL_TIMEx_MasterConfigSynchronization(&htim1, &sMasterConfig) != HAL_OK)
  {
    Error_Handler();
  }
  sConfigOC.OCMode = TIM_OCMODE_PWM1;
  sConfigOC.Pulse = 0;
  sConfigOC.OCPolarity = TIM_OCPOLARITY_HIGH;
  sConfigOC.OCNPolarity = TIM_OCNPOLARITY_HIGH;
  sConfigOC.OCFastMode = TIM_OCFAST_DISABLE;
  sConfigOC.OCIdleState = TIM_OCIDLESTATE_RESET;
  sConfigOC.OCNIdleState = TIM_OCNIDLESTATE_RESET;
  if (HAL_TIM_PWM_ConfigChannel(&htim1, &sConfigOC, TIM_CHANNEL_1) != HAL_OK)
  {
    Error_Handler();
  }
  sBreakDeadTimeConfig.OffStateRunMode = TIM_OSSR_DISABLE;
  sBreakDeadTimeConfig.OffStateIDLEMode = TIM_OSSI_DISABLE;
  sBreakDeadTimeConfig.LockLevel = TIM_LOCKLEVEL_OFF;
  sBreakDeadTimeConfig.DeadTime = 0;
  sBreakDeadTimeConfig.BreakState = TIM_BREAK_DISABLE;
  sBreakDeadTimeConfig.BreakPolarity = TIM_BREAKPOLARITY_HIGH;
  sBreakDeadTimeConfig.AutomaticOutput = TIM_AUTOMATICOUTPUT_DISABLE;
  if (HAL_TIMEx_ConfigBreakDeadTime(&htim1, &sBreakDeadTimeConfig) != HAL_OK)
  {
    Error_Handler();
  }
  HAL_TIM_MspPostInit(&htim1);
}

/**
  * @brief TIM2 Initialization Function
  */
static void MX_TIM2_Init(void)
{
  TIM_MasterConfigTypeDef sMasterConfig = {0};
  TIM_OC_InitTypeDef sConfigOC = {0};

  htim2.Instance = TIM2;
  htim2.Init.Prescaler = 71;
  htim2.Init.CounterMode = TIM_COUNTERMODE_UP;
  htim2.Init.Period = 999;
  htim2.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;
  htim2.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;
  if (HAL_TIM_PWM_Init(&htim2) != HAL_OK)
  {
    Error_Handler();
  }
  sMasterConfig.MasterOutputTrigger = TIM_TRGO_RESET;
  sMasterConfig.MasterSlaveMode = TIM_MASTERSLAVEMODE_DISABLE;
  if (HAL_TIMEx_MasterConfigSynchronization(&htim2, &sMasterConfig) != HAL_OK)
  {
    Error_Handler();
  }
  sConfigOC.OCMode = TIM_OCMODE_PWM1;
  sConfigOC.Pulse = 0;
  sConfigOC.OCPolarity = TIM_OCPOLARITY_HIGH;
  sConfigOC.OCFastMode = TIM_OCFAST_DISABLE;
  if (HAL_TIM_PWM_ConfigChannel(&htim2, &sConfigOC, TIM_CHANNEL_3) != HAL_OK)
  {
    Error_Handler();
  }
  HAL_TIM_MspPostInit(&htim2);
}

/**
  * @brief TIM3 Initialization Function
  */
static void MX_TIM3_Init(void)
{
  TIM_MasterConfigTypeDef sMasterConfig = {0};
  TIM_OC_InitTypeDef sConfigOC = {0};

  htim3.Instance = TIM3;
  htim3.Init.Prescaler = 71;
  htim3.Init.CounterMode = TIM_COUNTERMODE_UP;
  htim3.Init.Period = 999;
  htim3.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;
  htim3.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;
  if (HAL_TIM_PWM_Init(&htim3) != HAL_OK)
  {
    Error_Handler();
  }
  sMasterConfig.MasterOutputTrigger = TIM_TRGO_RESET;
  sMasterConfig.MasterSlaveMode = TIM_MASTERSLAVEMODE_DISABLE;
  if (HAL_TIMEx_MasterConfigSynchronization(&htim3, &sMasterConfig) != HAL_OK)
  {
    Error_Handler();
  }
  sConfigOC.OCMode = TIM_OCMODE_PWM1;
  sConfigOC.Pulse = 0;
  sConfigOC.OCPolarity = TIM_OCPOLARITY_HIGH;
  sConfigOC.OCFastMode = TIM_OCFAST_DISABLE;
  if (HAL_TIM_PWM_ConfigChannel(&htim3, &sConfigOC, TIM_CHANNEL_1) != HAL_OK)
  {
    Error_Handler();
  }
  HAL_TIM_MspPostInit(&htim3);
}

/**
  * @brief GPIO Initialization Function
  */
static void MX_GPIO_Init(void)
{
  GPIO_InitTypeDef GPIO_InitStruct = {0};

  __HAL_RCC_GPIOD_CLK_ENABLE();
  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_GPIOB_CLK_ENABLE();

  HAL_GPIO_WritePin(GPIOA, GPIO_PIN_7, GPIO_PIN_RESET);
  HAL_GPIO_WritePin(GPIOB, GPIO_PIN_0|GPIO_PIN_1|GPIO_PIN_10|GPIO_PIN_8|GPIO_PIN_9, GPIO_PIN_RESET);

  GPIO_InitStruct.Pin = GPIO_PIN_0|GPIO_PIN_1;
  GPIO_InitStruct.Mode = GPIO_MODE_INPUT;
  GPIO_InitStruct.Pull = GPIO_PULLUP;
  HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);

  GPIO_InitStruct.Pin = GPIO_PIN_7;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);

  GPIO_InitStruct.Pin = GPIO_PIN_0|GPIO_PIN_1|GPIO_PIN_10|GPIO_PIN_8|GPIO_PIN_9;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(GPIOB, &GPIO_InitStruct);

  /* USER CODE BEGIN MX_GPIO_Init_2 */
  __HAL_RCC_GPIOC_CLK_ENABLE();
  GPIO_InitStruct.Pin = GPIO_PIN_13;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(GPIOC, &GPIO_InitStruct);

  GPIO_InitStruct.Pin = GPIO_PIN_4;
  GPIO_InitStruct.Mode = GPIO_MODE_IT_RISING;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);

  GPIO_InitStruct.Pin = GPIO_PIN_5;
  GPIO_InitStruct.Mode = GPIO_MODE_INPUT;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);

  HAL_NVIC_SetPriority(EXTI4_IRQn, 5, 0);
  HAL_NVIC_EnableIRQ(EXTI4_IRQn);
  /* USER CODE END MX_GPIO_Init_2 */
}

/**
  * @brief  This function is executed in case of error occurrence.
  */
void Error_Handler(void)
{
  __disable_irq();
  while (1)
  {
  }
}

#ifdef  USE_FULL_ASSERT
void assert_failed(uint8_t *file, uint32_t line)
{
}
#endif /* USE_FULL_ASSERT */
```

**주의**: 이 파일은 코드에서 CubeMX가 자동 생성하는 `MX_GPIO_Init()` 안의 PC13/PA4/PA5 설정을 `USER CODE BEGIN MX_GPIO_Init_2` 구간에 수동으로 넣은 형태입니다. 만약 CubeMX에서 이 핀들(PC13, PA4, PA5)을 직접 지정하고 코드 재생성했다면, CubeMX가 자동으로 생성한 부분과 중복될 수 있습니다 — 실제 생성된 `main.c`를 열어서 이 핀들이 `USER CODE` 밖(자동 생성 영역)에 이미 들어가 있다면, `USER CODE BEGIN MX_GPIO_Init_2` 안의 해당 줄은 지우고 CubeMX가 만든 버전만 남기면 됩니다.

---

## 5. 이전 버전과의 차이 (변경 이력)

- `f`(고정전환 자동 1초 구동), `1`/`2`(모드값만 변경) 키 삭제
- `j`/`l`: 바퀴축 차동조향 → **선기어 모터 정/역회전**으로 재배정
- `u`/`o`: 고정전환 모터 정/역회전 **신규 추가**
- `sign`/`isLeftSide` 좌우 부호 로직 제거 (STM32 1개 단독 테스트용으로 단순화 — 4다리 전부 연결 시 복원 필요)
- `modeSwitchActive` 관련 논블로킹 타이머 로직 전부 제거 (자동 정지 방식 → 수동 정/역 방식 전환)
- `k`에서 세 모터(바퀴축/선기어/고정전환) 전부 정지하도록 보강

---

## 6. 다음에 할 일

1. 선기어 모터 엔코더(PB3/PB5) 필요해지면 CubeMX에서 추가 설정 + 코드 구현
2. 4다리 전부 연결 시 좌/우 부호 로직 복원
3. 캐리어 각도 안전 한계값 구현 (엔코더 PPR 확인 후)
4. STM32 #2~4 동일 방식으로 배선·검증 (점퍼만 다르게: PA0/PA1 조합)
