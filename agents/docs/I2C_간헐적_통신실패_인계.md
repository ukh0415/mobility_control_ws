# leg[0] I2C 간헐적 통신 실패 인계

## 1. 현재 테스트 환경

- 노트북 → ESP32: USB 시리얼, `COM5`, `115200bps`
- ESP32 → STM32: I2C
- 현재는 다리 한 쪽만 테스트하므로 STM32 주소 `0x10`(`leg[0]`)만 연결되어 있음
- `leg[1]`~`leg[3]`의 `ok=false`는 현재 테스트에서는 정상이며 문제 대상이 아님
- 노트북 실행 파일: `pc/robot_control_client_serial.py`

## 2. 발생 증상

프로그램 실행 시 `leg[0]` 응답이 아래처럼 성공과 실패를 반복함.

```text
[] writeErr=0 bytesReceived=3
leg[0] addr=0x10 ok=true mode=0 angle=0.0

[] writeErr=0 bytesReceived=0
leg[0] addr=0x10 ok=false
```

키를 눌러도 모터 조작이 안정적으로 되지 않음. 같은 하드웨어가 다른 팀원 노트북에서는 작동한 적이 있음.

## 3. 로그 해석

```text
writeErr=0
```

ESP32가 STM32 주소 `0x10`으로 명령을 쓰는 단계에서는 ACK를 받았다는 의미다.

```text
bytesReceived=3
```

STM32 상태 데이터 3바이트 읽기에 성공했다는 의미다.

```text
bytesReceived=0
```

쓰기 직후 수행한 상태 읽기에서 STM32가 응답하지 않았다는 의미다. 배선이 완전히 끊긴 상황보다는 STM32가 쓰기 처리를 완료하고 다시 I2C 리슨/송신 준비 상태로 전환되기 전에 ESP32가 읽기를 요청했을 가능성이 높다.

## 4. 가장 먼저 확인할 사항

팀원 노트북에서 정상 동작했던 아래 파일을 확보해서 현재 사용 중인 버전과 비교한다.

- `esp32_i2c_master.ino`
- STM32 프로젝트의 `main.c`
- 팀원이 사용한 `robot_control_client_serial.py`

특히 ESP32 코드에서 다음 함수 및 키워드를 검색한다.

```cpp
Wire.beginTransmission(...)
Wire.endTransmission()
delayMicroseconds(...)
delay(...)
Wire.requestFrom(...)
```

## 5. ESP32에서 우선 적용할 수정

ESP32가 STM32에 명령을 쓴 다음 상태를 읽기 전까지의 간격을 확인한다. 현재 값이 `200us` 정도이거나 딜레이가 없다면 우선 `10ms`로 변경한다.

변경 전 예상 형태:

```cpp
Wire.beginTransmission(addr);
Wire.write(command);
int writeErr = Wire.endTransmission();

delayMicroseconds(200);

int bytesReceived = Wire.requestFrom(addr, 3);
```

변경 권장 형태:

```cpp
Wire.beginTransmission(addr);
Wire.write(command);
int writeErr = Wire.endTransmission();

// STM32가 수신 완료 콜백을 처리하고 다시 listen 상태가 될 시간을 준다.
delay(10);

int bytesReceived = Wire.requestFrom(addr, 3);
```

`10ms`에서 안정화되면 필요할 때 `5ms`, `3ms` 순서로 줄여 최소 안정값을 찾는다. 우선은 속도보다 통신 안정성을 확인하는 것이 목적이다.

여러 주소를 반복 조회하는 루프가 있다면 각 다리 처리 사이에도 짧은 간격을 둔다.

```cpp
for (int i = 0; i < 4; i++) {
    // 해당 주소에 명령 쓰기 및 상태 읽기
    delay(2);
}
```

현재는 `0x10`만 연결되어 있으므로 가능하면 테스트 동안 주소 `0x10`만 조회하도록 설정한다. 연결되지 않은 `0x11`~`0x13`의 반복 조회와 디버그 출력을 제거하면 문제를 더 명확히 관찰할 수 있다.

## 6. STM32 코드 확인 사항

STM32의 I2C 주소 콜백은 단발성 프레임에 맞게 아래 옵션을 사용해야 한다.

```c
HAL_I2C_Slave_Sequential_Receive_IT(
    hi2c, i2c_rx_buf, 1, I2C_FIRST_AND_LAST_FRAME);

HAL_I2C_Slave_Sequential_Transmit_IT(
    hi2c, i2c_tx_buf, 3, I2C_FIRST_AND_LAST_FRAME);
```

`I2C_NEXT_FRAME`을 사용하고 있다면 `I2C_FIRST_AND_LAST_FRAME`으로 변경한다.

수신/송신 완료 후에는 다시 리슨 상태로 진입하는지 확인한다.

```c
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
```

에러 발생 후 I2C를 복구하는 콜백도 확인한다.

```c
void HAL_I2C_ErrorCallback(I2C_HandleTypeDef *hi2c)
{
    HAL_I2C_DeInit(hi2c);
    HAL_I2C_Init(hi2c);
    HAL_I2C_EnableListen_IT(hi2c);
}
```

주의: `ApplyCommand()`나 I2C 인터럽트 콜백 안에 `HAL_Delay()`를 넣으면 안 된다. 인터럽트 안의 블로킹 딜레이 때문에 다음 I2C 응답이 막힐 수 있다.

## 7. Python 클라이언트 확인 방법

현재 Python 클라이언트는 키 입력 시 다음 로그를 출력하도록 수정되어 있다.

```text
[키 입력] i (이동 명령 전송 시작)
[키 해제] i -> k (정지)
```

이 로그가 나오면 노트북의 키 입력 감지는 정상이다. 이 상태에서도 `leg[0]`이 `true/false`를 반복하면 키보드 인식보다 ESP32↔STM32 I2C 구간을 우선 점검한다.

Python의 아래 값은 키를 누르는 동안 명령을 반복 전송하는 간격이다.

```python
REPEAT_INTERVAL = 0.1
```

진단 목적으로 `0.2` 또는 `0.5`로 늘렸을 때 안정화되는지 볼 수는 있다. 그러나 이것은 임시 진단이며, 근본적으로 확인할 값은 ESP32의 `Wire.endTransmission()`과 `Wire.requestFrom()` 사이 딜레이다.

## 8. 권장 테스트 순서

1. 모터를 바닥에서 띄우거나 모터 전원을 분리해 안전을 확보한다.
2. 팀원 노트북에서 정상 동작했던 ESP32/STM32 소스 버전을 백업한다.
3. ESP32가 테스트 중 `0x10`만 조회하도록 한다.
4. ESP32의 write→read 딜레이를 `10ms`로 설정하고 업로드한다.
5. 시리얼 모니터를 닫는다. 같은 COM 포트는 Python과 시리얼 모니터가 동시에 열 수 없다.
6. 저장소 루트에서 `python .\pc\robot_control_client_serial.py`를 실행한다.
7. 키를 누르지 않은 상태에서 `leg[0] ok=true`가 연속으로 유지되는지 확인한다.
8. `i`, `j`, `l`, `,`, `k`를 각각 짧게 테스트한다.
9. 1분 이상 `bytesReceived=0`이 발생하지 않는지 확인한다.
10. 안정적이면 딜레이를 `5ms`, 필요하면 `3ms`까지 줄여 재시험한다.

## 9. 해결 판정 기준

아래 조건을 모두 만족하면 해결된 것으로 본다.

- `leg[0] addr=0x10 ok=true`가 지속됨
- `bytesReceived=3`이 지속되고 `bytesReceived=0`이 발생하지 않음
- 키 입력 로그가 출력됨
- 이동 키를 누르는 동안 모터가 동작함
- 이동 키를 놓거나 `k`를 누르면 즉시 정지함
- ESP32 또는 STM32가 재부팅되거나 멈추지 않음

## 10. 그래도 실패할 경우

딜레이를 `10ms`로 변경해도 `bytesReceived=0`이 계속 발생하면 다음 순서로 확인한다.

1. 정상 동작 팀원 노트북의 `esp32_i2c_master.ino`와 현재 소스의 정확한 차이 비교
2. SDA/SCL 각각 4.7kΩ 외부 풀업이 3.3V에 연결됐는지 확인
3. ESP32, STM32, 모터 드라이버의 GND 공통 연결 확인
4. I2C 속도를 `100kHz`로 설정했는지 확인
5. 모터 전원을 분리했을 때 통신이 안정되는지 확인
6. 다른 USB 케이블 및 USB 포트로 시험
7. 로직 전원 전압 강하 또는 ESP32/STM32 리셋 여부 확인

모터 전원을 분리하면 안정되고 연결하면 실패하는 경우에는 신호 딜레이뿐 아니라 모터 기동 전류에 의한 전압 강하와 노이즈도 함께 의심해야 한다.

## 11. 작업 후 공유 요청

수정 후 아래 자료를 공유하면 원인 확정 및 재발 방지에 도움이 된다.

- 수정한 `esp32_i2c_master.ino`
- 실제 적용한 write→read 딜레이 값
- 수정 전후 시리얼 로그
- 사용한 ESP32/STM32 펌웨어 버전 또는 파일 생성 시각
- 모터 전원 연결/분리 상태별 테스트 결과
