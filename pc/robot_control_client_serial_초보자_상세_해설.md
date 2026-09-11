# robot_control_client_serial.py 초보자 상세 해설

## 1. 이 문서의 목적

이 문서는 `pc/robot_control_client_serial.py`를 Python을 거의 처음 접하는 사람도 읽을 수 있도록 설명한 자료이다. 원본 코드의 줄 번호는 문서 작성 시점의 1~178줄을 기준으로 한다.

이 프로그램을 한 문장으로 요약하면 다음과 같다.

> Windows 키보드에서 한 글자 명령을 받아 USB 시리얼로 ESP32에 반복 전송하고, ESP32가 보내는 상태 로그를 화면에 표시하는 클러치 a 캐리어 벤치 시험용 프로그램이다.

이 프로그램은 로봇 전체 제어 프로그램이 아니다. 현재 공용 프로토콜의 “누적 20도 캐리어 시험(버전 4)”에 맞춘 시험용 클라이언트이며, 모터1과 모터3을 구동하지 않는 시험 펌웨어를 전제로 한다.

## 2. 가장 먼저 알아야 할 안전 사항

이 파일은 실제 모터 명령을 전송한다. 따라서 코드를 읽거나 실행할 때 다음 조건을 먼저 확인해야 한다.

- 링기어를 사용자가 클러치 a 위치에 확실히 고정한 시험 구성에서만 사용한다.
- 모터1과 모터3이 비활성화된 대응 ESP32/STM32 시험 펌웨어를 사용한다.
- 처음에는 저속·저출력·무부하·단일 모듈 조건으로 시험한다.
- 기준 홈이 실제로 맞지 않은 상태에서 `z`를 누르면 잘못된 위치를 0도로 저장할 수 있다.
- 이상 동작 시 `k`를 눌러 정지한다.
- 이동 중 `k`로 취소하면 기준이 무효화되므로 실제 홈을 다시 맞춘 뒤 `z`를 눌러야 한다.
- PC 프로그램의 명령 거부는 보조 안전장치일 뿐이다. 최종 정지, 제한 시간, 상태 전이와 인터록은 STM32에서도 독립적으로 보장되어야 한다.

## 3. 프로그램과 장치의 관계

~~~text
사용자 키보드
    │  z / p / n / r / k / Esc
    ▼
Python 프로그램
    │  USB Serial, 115200 bps
    │  한 글자 + 줄바꿈 전송
    ▼
ESP32
    │  I2C, 100 kHz
    ▼
STM32 모듈
    └─ 센서 판독, 위치 제어, 로컬 상태 머신, 비상 정지
~~~

Python은 각도나 엔코더 목표를 직접 계산하지 않는다. Python은 `p`, `n` 같은 문자만 ESP32로 보낸다. 누적 목표 홈 번호, 20도에 해당하는 엔코더 count, 실제 위치 제어와 fault 판정은 ESP32/STM32 쪽의 책임이다.

## 4. 키 명령과 상태 번호

### 4.1 키 명령

| 키 | 의미 | 프로그램이 하는 일 |
|---|---|---|
| `z` | 현재 위치를 기준 0도로 저장 | 약 0.3초 동안 `z`를 반복 전송한 후 `h`로 전환 |
| `p` | 현재 목표 홈 번호를 1 증가 | 결과적으로 기준에서 `+20° × 목표 홈 번호`로 이동 요청 |
| `n` | 현재 목표 홈 번호를 1 감소 | 결과적으로 기준에서 `+20° × 목표 홈 번호`로 이동 요청 |
| `r` | 기준 홈으로 복귀 | 목표 홈 번호를 0으로 만드는 명령 전송 |
| `h` | heartbeat | 새 목표를 만들지 않고 통신과 진행 중 목표를 유지 |
| `k` | 전체 정지 | 사용자가 다른 명령을 누를 때까지 계속 `k` 전송 |
| `Esc` | PC 프로그램 종료 | 백그라운드 반복을 끝내고 마지막으로 `k` 전송 |

중요한 차이는 “키를 0.3초 누르고 있는 것”과 “모터가 0.3초만 움직이는 것”이 같지 않다는 점이다. 프로그램은 키를 한 번 누르면 해당 명령 문자를 약 0.3초 동안 반복해서 보이고, 그 뒤에는 `h`를 보낸다. 모터의 실제 이동 완료 시점은 STM32 상태 머신이 결정한다.

### 4.2 상태 번호

| 번호 | 이름 | 의미 |
|---:|---|---|
| 0 | UNREFERENCED | 기준점이 아직 설정되지 않음 |
| 1 | READY | 기준 설정 완료, 새 위치 명령을 받을 준비가 됨 |
| 2 | MOVING | 이동 중 |
| 3 | DONE | 목표 이동 완료 |
| 4 | FAULT | 오류로 정지 |

`p`, `n`, `r`은 마지막으로 수신한 상태가 READY(1) 또는 DONE(3)일 때만 PC에서 허용한다. `z`는 상태가 MOVING(2)일 때만 거부한다.

## 5. 실행 전에 필요한 것

### 5.1 운영체제

`msvcrt` 모듈을 사용하므로 Windows 터미널 전용이다. Linux나 macOS에서는 그대로 실행되지 않는다.

### 5.2 Python 패키지

`serial`은 Python 기본 모듈이 아니라 `pyserial` 패키지가 제공한다. 설치되어 있지 않다면 다음 명령이 필요하다.

~~~powershell
python -m pip install pyserial
~~~

패키지 이름은 `pyserial`이지만 코드에서 가져올 때는 `import serial`이라고 쓴다.

### 5.3 COM 포트

원본 13줄의 다음 값을 실제 ESP32 포트에 맞춰야 한다.

~~~python
SERIAL_PORT = "COM7"
~~~

다른 시리얼 모니터가 같은 COM 포트를 사용 중이면 이 프로그램이 연결하지 못할 수 있다. Arduino Serial Monitor, PuTTY 같은 프로그램을 먼저 닫아야 한다.

### 5.4 실행

저장소 루트에서 다음처럼 실행할 수 있다.

~~~powershell
python .\pc\robot_control_client_serial.py
~~~

실행 중에는 Enter를 누를 필요 없이 한 글자 키를 읽는다. 종료는 `Esc`이며, 비상 정지는 `k`이다.

## 6. 먼저 배우는 최소 Python 문법

### 6.1 변수와 대입

~~~python
BAUD_RATE = 115200
running = True
~~~

`=`는 오른쪽 값을 왼쪽 이름에 저장한다는 뜻이다. Python은 변수의 자료형을 미리 선언하지 않아도 된다.

### 6.2 주요 자료형

| 예 | 자료형 | 뜻 |
|---|---|---|
| `"COM7"` | 문자열(`str`) | 글자의 묶음 |
| `115200` | 정수(`int`) | 소수점 없는 숫자 |
| `0.1` | 실수(`float`) | 소수점이 있는 숫자 |
| `True`, `False` | 불리언(`bool`) | 참과 거짓 |
| `None` | 특별한 빈 값 | 아직 연결 객체나 상태가 없음을 표현 |
| `{"z", "p"}` | 집합(`set`) | 중복 없는 값의 모음 |

### 6.3 함수

~~~python
def connect():
    ...
~~~

`def`는 함수를 만든다. 함수는 특정 작업을 이름으로 묶은 코드이다. 함수 이름 뒤의 괄호 안에는 입력값을 적고, `return`으로 결과를 돌려줄 수 있다.

### 6.4 들여쓰기

Python은 중괄호 대신 들여쓰기로 코드 블록을 구분한다.

~~~python
if ser is None:
    return
~~~

`return` 앞의 네 칸 들여쓰기는 이 문장이 `if` 안에 속한다는 뜻이다.

### 6.5 조건문과 반복문

- `if 조건:`은 조건이 참일 때 아래 블록을 실행한다.
- `elif`는 앞 조건이 거짓일 때 검사하는 다음 조건이다.
- `while running:`은 `running`이 참인 동안 계속 반복한다.
- `continue`는 현재 반복의 남은 부분을 건너뛰고 다음 반복으로 간다.
- `break`는 반복문을 즉시 끝낸다.

### 6.6 예외 처리

~~~python
try:
    ...
except serial.SerialException as e:
    ...
~~~

`try` 안에서 오류가 발생할 수 있는 작업을 한다. 지정한 오류가 생기면 프로그램 전체가 바로 종료되는 대신 `except` 블록에서 처리한다. `as e`는 발생한 오류 설명을 `e`라는 변수에 담는다.

### 6.7 `with`

~~~python
with ser_lock:
    ...
~~~

이 블록에 들어갈 때 lock을 획득하고, 블록을 나갈 때 자동으로 반환한다. 여러 스레드가 동시에 `ser`를 바꾸거나 쓰는 일을 줄이기 위한 장치다.

### 6.8 f-string

~~~python
print(f"[연결됨] {SERIAL_PORT} @ {BAUD_RATE}bps")
~~~

문자열 앞의 `f`는 중괄호 안의 변수 값을 문자열에 넣으라는 뜻이다. 예를 들어 `SERIAL_PORT`가 `"COM7"`이면 화면에 `[연결됨] COM7 @ 115200bps`가 출력된다.

### 6.9 `global`

함수 밖에 만든 변수를 함수 안에서 새 값으로 바꾸려면 이 코드처럼 `global` 선언이 필요하다.

~~~python
global ser
ser = None
~~~

읽기만 할 때는 반드시 필요하지 않지만, 대입으로 값을 바꿀 때는 필요하다.

### 6.10 타입 힌트

~~~python
def send_command(cmd: str):
~~~

`cmd: str`은 “`cmd`에는 문자열을 넣을 예정”이라는 안내다. 실행 시 Python이 이를 강제로 검사하는 것은 아니다.

## 7. 코드 전체 구조

프로그램은 총 네 개의 실행 흐름을 사용한다.

| 실행 흐름 | 실행 함수 | 역할 |
|---|---|---|
| 메인 스레드 | `keyboard_loop()` | 사용자의 키 입력을 기다림 |
| 연결 스레드 | `connection_manager()` | 연결이 없으면 COM 포트 재연결 |
| 반복 송신 스레드 | `repeat_sender()` | 현재 명령을 0.1초마다 전송 |
| 상태 수신 스레드 | `status_receiver()` | ESP32 로그를 읽고 상태 번호 저장 |

대략적인 관계는 다음과 같다.

~~~text
connection_manager ── ser 연결/교체 ─┐
                                     │
keyboard_loop ─ active_move_key 설정 ├─ repeat_sender ─ USB로 명령 전송
                                     │
status_receiver ─ last_state 갱신 ───┘
~~~

메인 스레드가 모든 일을 차례로 처리하면 키 입력을 기다리는 동안 시리얼 수신이나 heartbeat 전송이 멈출 수 있다. 그래서 스레드를 나눠 동시에 처리한다.

## 8. 전역 설정값과 상태 변수

### 8.1 12~21줄: 설정값

~~~python
SERIAL_PORT = "COM7"
BAUD_RATE = 115200
REPEAT_INTERVAL = 0.1
RECONNECT_INTERVAL = 1.0
COMMAND_PULSE_SECONDS = 0.3

MOVE_KEYS = {"z", "p", "n", "r"}
TOGGLE_KEYS = set()
STOP_KEY = "k"
~~~

- `SERIAL_PORT`: ESP32가 연결된 Windows COM 포트 이름이다.
- `BAUD_RATE`: PC와 ESP32가 1초에 어느 속도로 직렬 데이터를 주고받을지 정한다. 양쪽 모두 115200으로 같아야 한다.
- `REPEAT_INTERVAL`: 현재 활성 명령을 보내는 간격이다. 0.1초이므로 이론상 초당 약 10회다.
- `RECONNECT_INTERVAL`: 연결 여부를 다시 확인하는 간격이다. 1초마다 재확인을 시도한다.
- `COMMAND_PULSE_SECONDS`: `z/p/n/r` 명령을 유지할 시간이다. ESP32가 약 100ms마다 확인하므로 한 번의 짧은 키 입력도 여러 polling 구간에서 보이게 한다.
- `MOVE_KEYS`: 위치 관련 명령으로 인정할 키 집합이다. `c in MOVE_KEYS`처럼 포함 여부를 빠르게 검사한다.
- `TOGGLE_KEYS`: 빈 집합이다. 현재 토글 명령은 하나도 없으므로 관련 분기는 실행될 수 없다. 향후 확장을 위해 남아 있는 구조다.
- `STOP_KEY`: 정지 키를 한 곳에서 정의한다.

`set()`은 빈 집합을 만드는 문법이다. 빈 집합을 `{}`로 쓰면 Python에서는 집합이 아니라 빈 사전(`dict`)이 되므로 `set()`을 사용한다.

### 8.2 23~29줄: 실행 중 변하는 상태

~~~python
ser = None
ser_lock = threading.Lock()
active_move_key = "k"
command_until = 0.0
last_state = None
running = True
~~~

| 변수 | 처음 값 | 의미 |
|---|---|---|
| `ser` | `None` | 연결된 시리얼 객체. `None`이면 미연결 |
| `ser_lock` | lock 객체 | 여러 스레드의 시리얼 접근 충돌 방지 |
| `active_move_key` | `"k"` | 반복해서 보낼 현재 명령 |
| `command_until` | `0.0` | 위치 명령을 언제까지 유지할지 나타내는 단조 시간 |
| `last_state` | `None` | ESP32 로그에서 마지막으로 읽은 상태 번호 |
| `running` | `True` | 전체 반복을 계속할지 결정하는 공용 종료 플래그 |

처음 활성 명령이 `k`인 것은 안전한 초기값이다. 연결되기 전이나 연결 직후에 임의의 이동 명령이 전송되는 것을 막고 정지 명령을 보낸다.

## 9. 줄 단위 상세 해설

### 9.1 1~3줄: 파일 설명 문자열

~~~python
"""Clutch-a carrier bench trial: every p/n press adds/subtracts 20 degrees.
Motor1/3 disabled. Reset requires a new reference. Windows terminal only.
"""
~~~

파일 맨 앞의 따옴표 세 개 문자열은 모듈 docstring이다. 이 파일의 목적과 전제 조건을 설명한다.

- 클러치 a 캐리어 벤치 시험용이다.
- `p/n`을 한 번 누를 때마다 목표 홈 번호가 한 칸, 즉 20도만큼 변한다.
- 모터1과 모터3은 비활성화되어야 한다.
- 리셋 후 새 기준 설정이 필요하다.
- Windows 터미널 전용이다.

docstring은 실행 동작을 직접 바꾸지 않지만 `help()` 같은 도구가 설명으로 사용할 수 있다.

### 9.2 5~10줄: 모듈 가져오기

~~~python
import msvcrt
import re
import threading
import time

import serial
~~~

- `msvcrt`: Windows 콘솔에서 Enter 없이 키 한 글자를 즉시 읽는 데 사용한다.
- `re`: 정규표현식으로 수신 로그의 `state=숫자` 부분을 찾는다.
- `threading`: 연결, 송신, 수신을 동시에 실행한다.
- `time`: 대기와 시간 제한 계산에 사용한다.
- `serial`: pyserial이 제공하는 직렬통신 기능이다.

기본 모듈과 외부 패키지 사이의 빈 줄은 기능 차이가 아니라 읽기 쉽게 묶어 놓은 코드 스타일이다.

### 9.3 31~41줄: `connect()`

~~~python
def connect():
    """ESP32에 시리얼로 연결. 실패하면 None 반환."""
    global ser
    try:
        s = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.1, write_timeout=0.2)
        time.sleep(2)
        print(f"[연결됨] {SERIAL_PORT} @ {BAUD_RATE}bps")
        return s
    except serial.SerialException as e:
        print(f"[연결 실패] {e} - {RECONNECT_INTERVAL}초 후 재시도")
        return None
~~~

줄별 의미는 다음과 같다.

- 31줄: `connect`라는 함수를 정의한다.
- 32줄: 함수 설명 docstring이다.
- 33줄: 전역 `ser`를 가리키겠다고 선언한다. 다만 이 함수는 실제로 `ser`에 대입하지 않고 지역 변수 `s`를 반환하므로 현재 구현에서는 이 `global ser`가 없어도 동작한다.
- 34줄: 연결 중 발생할 수 있는 예외를 처리하기 위한 `try` 시작이다.
- 35줄: COM 포트를 연다.
  - 첫 번째 인자는 `"COM7"` 같은 포트 이름이다.
  - 두 번째 인자는 115200 bps 통신 속도다.
  - `timeout=0.1`은 읽을 데이터가 없을 때 최대 약 0.1초 후 반환하라는 뜻이다.
  - `write_timeout=0.2`는 쓰기가 막힐 때 최대 약 0.2초까지만 기다리라는 뜻이다.
- 36줄: 연결 직후 2초 기다린다. USB 시리얼 연결 시 자동 리셋되는 ESP32 보드가 초기화될 시간을 준다.
- 37줄: 성공 메시지를 출력한다.
- 38줄: 열린 시리얼 객체 `s`를 호출한 곳에 돌려준다.
- 39줄: pyserial이 보고한 연결 오류만 잡는다.
- 40줄: 오류 내용과 재시도 간격을 출력한다.
- 41줄: 실패 표시로 `None`을 반환한다.

성공 시에도 이 함수 안에서 2초를 기다리므로 실제 `ser` 변수에 연결 객체가 들어가는 것은 2초 대기 후이다.

### 9.4 44~58줄: `send_command(cmd)`

~~~python
def send_command(cmd: str):
    """명령 1글자를 시리얼로 전송."""
    global ser
    with ser_lock:
        if ser is None:
            return
        try:
            ser.write((cmd + "\n").encode("ascii"))
        except serial.SerialException as e:
            print(f"[전송 실패] {e}")
            try:
                ser.close()
            except serial.SerialException:
                pass
            ser = None
~~~

이 함수는 문자 한 개를 ESP32가 읽을 수 있는 바이트로 바꿔 전송한다.

- 44줄: `cmd`라는 문자열 입력을 받는 함수를 정의한다.
- 45줄: 함수의 역할을 설명한다.
- 46줄: 오류 시 전역 `ser`를 `None`으로 바꾸기 위해 `global`을 선언한다.
- 47줄: 시리얼 객체를 검사하고 쓰는 동안 `ser_lock`을 잡는다.
- 48~49줄: 연결이 없으면 아무것도 보내지 않고 즉시 끝낸다. 오류도 출력하지 않으므로 미연결 중 반복 호출되어도 화면이 도배되지 않는다.
- 50줄: 전송 예외 처리를 시작한다.
- 51줄: 실제 전송 문장이다.
  1. `cmd + "\n"`으로 명령 뒤에 줄바꿈을 붙인다.
  2. `encode("ascii")`로 Python 문자열을 전송 가능한 bytes로 바꾼다.
  3. `ser.write(...)`로 시리얼 포트에 쓴다.
- 52~53줄: 전송 실패를 잡아 화면에 표시한다.
- 54~57줄: 고장 난 포트를 닫아 본다. 닫는 과정 자체가 실패해도 `pass`로 무시하고 정리 과정을 계속한다.
- 58줄: `ser = None`으로 만들어 연결 관리 스레드가 재연결을 시도하게 한다.

예를 들어 `send_command("p")`가 보내는 실제 ASCII 바이트는 다음과 같다.

~~~text
"p\n" → 0x70 0x0A
~~~

따라서 “한 글자 명령”이라고 해도 통신선에는 명령 글자와 줄바꿈을 합쳐 2바이트가 기록된다.

### 9.5 61~74줄: `connection_manager()`

~~~python
def connection_manager():
    """백그라운드에서 연결이 끊기면 계속 재연결을 시도."""
    global ser, active_move_key, command_until, last_state
    while running:
        with ser_lock:
            need_connect = ser is None
        if need_connect:
            new_ser = connect()
            with ser_lock:
                active_move_key = "k"
                command_until = 0.0
                last_state = None
                ser = new_ser
        time.sleep(RECONNECT_INTERVAL)
~~~

- 61~63줄: 함수 정의, 설명, 수정할 전역 변수 선언이다.
- 64줄: 프로그램이 실행 중인 동안 계속 반복한다.
- 65~66줄: lock을 잡고 `ser`가 `None`인지 확인한 결과를 `need_connect`에 저장한다.
- 67줄: 연결이 필요할 때만 아래 코드를 실행한다.
- 68줄: `connect()`를 호출한다. 성공하면 시리얼 객체, 실패하면 `None`이 `new_ser`에 들어간다.
- 69줄: 공유 상태를 한 묶음으로 바꾸기 위해 다시 lock을 잡는다.
- 70줄: 새 연결에서는 반드시 정지 명령부터 시작한다.
- 71줄: 이전 명령 pulse의 종료 시각을 초기화한다.
- 72줄: 이전 연결에서 받은 상태를 버린다. 새 상태를 받기 전까지 `last_state`는 알 수 없음이다.
- 73줄: 연결 결과를 전역 `ser`에 저장한다. 실패했다면 다시 `None`이다.
- 74줄: 1초 기다린 후 다시 연결 상태를 검사한다.

재연결 시 `active_move_key`를 `k`로 되돌리는 것이 중요하다. 연결이 끊기기 전에 `p`를 누르고 있었다고 해서 재연결 직후 그 오래된 이동 명령을 다시 보내지 않는다.

### 9.6 77~99줄: `status_receiver()`

~~~python
def status_receiver():
    """ESP32가 시리얼로 보내는 상태/디버그 줄을 그대로 화면에 출력."""
    global last_state
    while running:
        with ser_lock:
            s = ser
        if s is None:
            time.sleep(0.2)
            continue
        try:
            line = s.readline()
        except serial.SerialException:
            time.sleep(0.2)
            continue
        if line:
            try:
                text = line.decode("ascii", errors="ignore").rstrip()
                match = re.search(r"\bstate=(\d+)\b", text)
                if match:
                    last_state = int(match.group(1))
                print(text)
            except UnicodeDecodeError:
                pass
~~~

- 77~79줄: 수신 함수 정의와 수정할 `last_state` 선언이다.
- 80줄: 실행 중 계속 수신을 반복한다.
- 81~82줄: lock을 잡은 짧은 순간에 현재 `ser`를 지역 변수 `s`로 복사한다.
- 83~85줄: 연결이 없으면 0.2초 기다리고 반복문의 처음으로 돌아간다.
- 86~87줄: ESP32가 보낸 한 줄을 읽는다. 데이터가 없으면 연결 때 지정한 `timeout=0.1`까지만 기다린다.
- 88~90줄: 읽기 중 시리얼 오류가 나면 0.2초 쉬고 다시 시도한다.
- 91줄: 빈 bytes가 아닌 데이터가 있을 때만 처리한다.
- 92줄: bytes를 문자열로 바꾸는 과정의 예외 처리를 시작한다.
- 93줄:
  - `decode("ascii", errors="ignore")`는 ASCII bytes를 문자열로 바꾼다.
  - ASCII가 아닌 바이트는 `errors="ignore"` 때문에 버린다.
  - `rstrip()`은 줄 끝의 `\r`, `\n`과 기타 공백을 제거한다.
- 94줄: 수신 문자열에서 `state=숫자` 형태를 정규표현식으로 찾는다.
- 95~96줄: 찾았다면 첫 번째 괄호 그룹의 숫자 문자열을 꺼내 `int`로 변환하고 `last_state`에 저장한다.
- 97줄: 상태 줄이든 일반 디버그 줄이든 전체 문자열을 화면에 출력한다.
- 98~99줄: Unicode 변환 오류는 무시한다.

정규표현식 `r"\bstate=(\d+)\b"`를 부분별로 보면 다음과 같다.

| 부분 | 의미 |
|---|---|
| `r"..."` | 역슬래시를 정규표현식 문자로 편하게 쓰는 raw string |
| `\b` | 단어 경계 |
| `state=` | 이 글자와 정확히 일치 |
| `(\d+)` | 숫자 한 개 이상을 그룹 1로 저장 |
| 마지막 `\b` | 숫자가 끝나는 단어 경계 |

예를 들어 실제 ESP32의 다음과 같은 USB 로그에서는 `2`를 찾아 정수 2로 저장한다.

~~~text
leg[0] addr=0x10 ok=true state=2 carrier_deg=20.0 motor2_count=668  |
~~~

반면 `mode=2`만 있고 `state=2`가 없으면 `last_state`는 바뀌지 않는다.

참고로 `decode(..., errors="ignore")`를 사용하면 잘못된 바이트를 버리고 계속하므로 보통 `UnicodeDecodeError`가 발생하지 않는다. 따라서 98~99줄은 현재 옵션에서는 사실상 실행될 가능성이 거의 없는 방어 코드다.

### 9.7 102~109줄: `repeat_sender()`

~~~python
def repeat_sender():
    """명령 pulse 뒤 h heartbeat를 보내며 새 위치 명령을 만들지 않는다."""
    global active_move_key
    while running:
        if active_move_key in MOVE_KEYS and time.monotonic() >= command_until:
            active_move_key = "h"
        send_command(active_move_key)
        time.sleep(REPEAT_INTERVAL)
~~~

- 102~104줄: 반복 송신 함수와 변경할 전역 변수를 선언한다.
- 105줄: 실행 중 계속 반복한다.
- 106줄: 현재 명령이 `z/p/n/r` 중 하나이고, 현재 시간이 pulse 종료 시각 이상인지 동시에 검사한다.
- 107줄: pulse 시간이 끝났으면 활성 명령을 heartbeat인 `h`로 바꾼다.
- 108줄: 현재 활성 명령을 전송한다. 연결이 없다면 `send_command` 안에서 조용히 반환한다.
- 109줄: 0.1초 기다리고 반복한다.

여기서 `time.monotonic()`은 컴퓨터가 켜진 뒤 단조롭게 증가하는 시간이다. 사용자가 시스템 시계를 바꾸거나 인터넷 시간 동기화가 일어나도 뒤로 점프하지 않으므로 “지금부터 0.3초 동안” 같은 제한 시간을 계산하기에 적합하다.

대략적인 `p` 입력 시간선은 다음과 같다. 실제 횟수는 스레드 실행 시점에 따라 조금 달라질 수 있다.

~~~text
키 p 입력
  ├─ active_move_key = "p"
  ├─ command_until = 현재 단조 시간 + 0.3초
  ├─ 약 0.1초 간격으로 p 반복 전송
  └─ 0.3초가 지나면 active_move_key = "h"
       └─ 이후 약 0.1초 간격으로 h 반복 전송
~~~

`k`와 `h`는 `MOVE_KEYS`에 없으므로 시간 만료로 다른 문자로 바뀌지 않는다. `k`는 새 위치 키가 입력될 때까지 계속 전송되고, `h`도 새 키 입력 전까지 계속 전송된다.

### 9.8 112~147줄: `keyboard_loop()`

~~~python
def keyboard_loop():
    """한 번의 유효한 키 입력을 한 번의 목표 변경 pulse로 만든다."""
    global active_move_key, command_until, running

    while running:
        c = msvcrt.getwch()
~~~

- 112~114줄: 키보드 함수 정의와 변경할 전역 변수 선언이다.
- 116줄: 프로그램이 실행 중인 동안 키 입력 처리를 반복한다.
- 117줄: 키 한 글자를 누를 때까지 기다린다. Enter는 필요 없다. 입력 문자는 `c`에 저장된다.

#### 119~122줄: 방향키와 기능키 무시

~~~python
if c in ("\x00", "\xe0"):
    msvcrt.getwch()
    continue
~~~

Windows 콘솔에서 방향키나 일부 기능키는 첫 글자로 `\x00` 또는 `\xe0`을 주고, 다음 글자에 실제 확장 키 코드를 준다.

- 첫 글자가 확장 코드 시작인지 검사한다.
- 맞으면 `getwch()`를 한 번 더 호출해 나머지 글자도 소비한다.
- `continue`로 아래 명령 처리를 건너뛴다.

두 번째 글자를 소비하지 않으면 그것이 다음 일반 명령처럼 잘못 처리될 수 있다.

#### 124~126줄: Esc 종료

~~~python
if c == "\x1b":
    running = False
    break
~~~

`\x1b`는 Esc 키의 문자 코드다. Esc를 누르면 모든 스레드가 보는 `running`을 거짓으로 바꾸고 키보드 반복문을 끝낸다.

#### 128줄: 대문자를 소문자로 통일

~~~python
c = c.lower()
~~~

`P`를 눌러도 `p`로 바뀐다. 따라서 Caps Lock이나 Shift 여부와 관계없이 명령을 인식한다.

#### 129~141줄: 위치 관련 명령 처리

~~~python
if c in MOVE_KEYS:
    if ser is None:
        print("[미연결] 연결 후 다시 입력하세요")
        continue
    if c in {"p", "n", "r"} and last_state not in {1, 3}:
        print(f"[명령 거부] state={last_state}; READY(1) 또는 DONE(3)에서 입력하세요")
        continue
    if c == "z" and last_state == 2:
        print("[명령 거부] 이동 중에는 z를 사용할 수 없습니다")
        continue
    active_move_key = c
    command_until = time.monotonic() + COMMAND_PULSE_SECONDS
    print(f"[명령] {c}")
~~~

처리 순서는 중요하다.

1. 129줄: 입력이 `z/p/n/r` 중 하나인지 확인한다.
2. 130~132줄: 연결되지 않았으면 명령을 거부한다.
3. 133~135줄: `p/n/r`은 마지막 상태가 1 또는 3이 아니면 거부한다.
   - `last_state is None`인 초기 상태도 거부된다.
   - 이동 중인 2와 fault 4에서도 거부된다.
4. 136~138줄: `z`는 이동 중인 상태 2에서 거부한다.
   - 상태가 `None`, 0, 1, 3, 4일 때는 PC 코드상 전송 가능하다.
   - 실제 `z` 허용 조건과 정지 안정 300ms 판정은 하위 펌웨어에서도 검사해야 한다.
5. 139줄: 모든 검사를 통과하면 반복 송신할 문자를 바꾼다.
6. 140줄: 현재 시간에서 0.3초 뒤를 pulse 종료 시각으로 저장한다.
7. 141줄: 받아들인 명령을 화면에 표시한다.

`and`는 양쪽 조건이 모두 참이어야 전체가 참이라는 뜻이고, `not in`은 집합 안에 없다는 뜻이다.

#### 142~143줄: 토글 키 자리

~~~python
elif c in TOGGLE_KEYS:
    print(f"[키 입력] {c} (1회 전송)")
~~~

`TOGGLE_KEYS`가 빈 집합이므로 현재 어떤 키도 이 조건을 만족하지 않는다. 또한 메시지만 출력하고 `send_command`를 호출하지 않으므로, 나중에 집합에 키를 추가하기만 해서는 “1회 전송”이 실제 구현되지 않는다. 향후 기능을 만들 때 전송 코드도 함께 추가해야 한다.

#### 144~147줄: 정지 키

~~~python
elif c == STOP_KEY:
    active_move_key = "k"
    command_until = 0.0
    print("[키 입력] k (정지)")
~~~

- 입력이 `k`인지 확인한다.
- 활성 명령을 즉시 `k`로 바꾼다.
- 위치 명령 pulse 종료 시각을 초기화한다.
- 정지 입력을 화면에 표시한다.

그 다음 반복 송신 스레드가 `k`를 약 0.1초마다 계속 보낸다. 키보드 함수 자체가 직접 시리얼에 쓰는 구조가 아니므로, 키 입력과 실제 송신 사이에는 스레드 스케줄링에 따른 짧은 지연이 있을 수 있다.

`z/p/n/r/k/Esc`가 아닌 일반 키는 마지막 `elif` 뒤에 처리 코드가 없으므로 조용히 무시된다.

### 9.9 150~174줄: `main()`

~~~python
def main():
    global running, active_move_key, command_until
~~~

- 150줄: 프로그램 시작 절차를 묶은 `main` 함수를 정의한다.
- 151줄: 종료 시 바꿀 전역 변수들을 선언한다.

#### 153~157줄: 사용자 안내 출력

프로그램을 실행하면 시험 전제, 키 기능, 상태 번호, fault 복구 절차를 영어로 출력한다.

~~~text
Clutch-a bench: motor1/3 disabled; manually lock ring gear first.
k STOP, wait >=0.3s at reference groove, z SET ZERO
p next +20deg / n next -20deg / r ZERO; each key press changes one step
state: 0 unreferenced, 1 ready, 2 moving, 3 done, 4 fault
After fault: k, inspect/re-align reference, then z. No automatic retry.
~~~

핵심은 fault 뒤 자동 재시도를 하지 않는다는 점이다. `k`로 정지시키고 기구와 기준 홈을 직접 점검한 뒤 `z`로 새 기준을 잡아야 한다.

#### 159~161줄: 백그라운드 스레드 시작

~~~python
threading.Thread(target=connection_manager, daemon=True).start()
threading.Thread(target=repeat_sender, daemon=True).start()
threading.Thread(target=status_receiver, daemon=True).start()
~~~

각 줄은 다음 세 동작을 한 번에 한다.

1. `threading.Thread(...)`로 새 스레드 객체를 만든다.
2. `target=함수이름`으로 그 스레드가 실행할 함수를 지정한다.
3. `.start()`로 실제 실행을 시작한다.

`target=connection_manager`처럼 괄호 없이 함수 이름만 전달한다. `target=connection_manager()`라고 쓰면 새 스레드가 아니라 현재 자리에서 함수를 먼저 실행해 버리므로 의미가 완전히 달라진다.

`daemon=True`는 메인 프로그램이 완전히 끝날 때 이 백그라운드 스레드만 남아 있더라도 Python 종료를 막지 않게 한다.

#### 163~166줄: 키보드 루프와 Ctrl+C

~~~python
try:
    keyboard_loop()
except KeyboardInterrupt:
    pass
~~~

메인 스레드는 `keyboard_loop()` 안에서 키 입력을 처리한다. 터미널에서 Ctrl+C로 `KeyboardInterrupt`가 발생하면 이를 잡고 별도 오류 메시지 없이 정리 단계로 넘어간다.

#### 167~172줄: 반드시 실행되는 정지 정리

~~~python
finally:
    running = False
    active_move_key = "k"
    command_until = 0.0
    time.sleep(REPEAT_INTERVAL + 0.05)
    send_command(STOP_KEY)
~~~

`finally`는 정상 종료, Esc, Ctrl+C 등 앞 블록이 어떻게 끝나더라도 실행되는 정리 구역이다.

- 168줄: 모든 반복 스레드에 종료를 알린다.
- 169줄: 메모리상의 활성 명령도 정지로 바꾼다.
- 170줄: 남은 pulse 시간을 지운다.
- 171줄: 반복 송신 간격 0.1초보다 0.05초 더 긴 0.15초를 기다린다.
- 172줄: 마지막으로 `k`를 직접 전송한다.

이 마지막 `k` 전송은 종료 시 안전을 위한 중요한 동작이다. 다만 PC 프로세스 강제 종료, 전원 분리, 운영체제 정지처럼 `finally`가 실행되지 못하는 상황도 있으므로 ESP32와 STM32의 통신 timeout 정지가 반드시 필요하다.

#### 173~174줄: 종료 메시지

0.2초 더 기다린 후 `종료됨`을 출력한다. 이 시점에는 `running=False`이므로 백그라운드 반복문도 종료 방향으로 진행한다.

### 9.10 177~178줄: 직접 실행 여부 확인

~~~python
if __name__ == "__main__":
    main()
~~~

Python은 파일을 직접 실행할 때 특별 변수 `__name__`에 `"__main__"`을 넣는다. 따라서 직접 실행하면 `main()`이 호출된다.

다른 Python 파일이 이 파일을 `import`하면 `__name__`에는 모듈 이름이 들어간다. 그 경우 함수와 변수만 가져오고 실제 연결이나 키보드 루프는 자동으로 시작하지 않는다. 이 패턴 덕분에 나중에 함수 단위 테스트나 재사용이 쉬워진다.

## 10. 실제 실행 순서

### 10.1 시작부터 연결까지

1. Python이 import와 전역 변수 초기화를 실행한다.
2. 마지막 두 줄이 `main()`을 호출한다.
3. 주의 사항과 키 설명을 화면에 출력한다.
4. 연결, 반복 송신, 상태 수신 스레드를 시작한다.
5. 메인 스레드는 키 입력을 기다린다.
6. 연결 스레드가 COM7을 연다.
7. ESP32 자동 리셋 안정화를 위해 2초 기다린다.
8. 연결 객체를 `ser`에 저장하면서 명령을 `k`, 상태를 `None`으로 초기화한다.
9. 반복 송신 스레드가 `k`를 전송하기 시작한다.
10. 수신 스레드가 로그를 읽고 `state=숫자`가 보이면 `last_state`를 갱신한다.

### 10.2 `p`를 한 번 눌렀을 때

1. `getwch()`가 `"p"`를 반환한다.
2. 연결 여부를 확인한다.
3. 마지막 상태가 READY(1) 또는 DONE(3)인지 확인한다.
4. `active_move_key`를 `"p"`로 바꾼다.
5. `command_until`을 현재 시각 + 0.3초로 정한다.
6. 반복 송신 스레드가 약 0.1초마다 `p\n`을 보낸다.
7. 0.3초가 지나면 활성 명령을 `h`로 바꾼다.
8. 이후 `h\n`을 반복 전송한다.
9. ESP32/STM32가 이동 상태와 완료 상태를 보내면 수신 스레드가 화면에 출력하고 `last_state`를 바꾼다.

### 10.3 연결이 끊겼을 때

1. 쓰기 중 `SerialException`이 발생하면 포트를 닫고 `ser=None`으로 바꾼다.
2. 연결 관리 스레드가 미연결을 발견한다.
3. COM 포트 연결을 다시 시도한다.
4. 재연결 결과를 저장하면서 과거 명령을 버리고 `k`로 초기화한다.
5. 새 상태 로그를 받기 전까지 `last_state=None`이므로 `p/n/r`은 거부된다.

### 10.4 Esc로 종료할 때

1. 키보드 루프가 Esc 코드 `\x1b`를 확인한다.
2. `running=False`로 바꾸고 루프를 끝낸다.
3. `finally`에서 정지 상태를 다시 설정한다.
4. 마지막 `k`를 전송한다.
5. `종료됨`을 출력하고 프로세스가 끝난다.

## 11. 스레드와 lock을 조금 더 자세히 이해하기

여러 스레드는 같은 전역 변수를 함께 본다. 이 코드에서 특히 중요한 공유 값은 `ser`, `active_move_key`, `command_until`, `last_state`, `running`이다.

`ser_lock`이 보호하는 범위는 다음과 같다.

- `send_command`에서 `ser` 확인, 쓰기, 실패 시 닫기와 `None` 대입
- `connection_manager`에서 연결 필요 여부 확인
- `connection_manager`에서 새 연결과 명령·상태 초기화
- `status_receiver`에서 현재 `ser` 객체를 지역 변수로 복사

하지만 모든 공유 변수를 완전히 lock으로 보호하는 구조는 아니다.

- `keyboard_loop`는 `ser`와 `last_state`를 lock 없이 읽는다.
- `active_move_key`와 `command_until`은 키보드 스레드와 송신 스레드가 lock 없이 함께 읽고 쓴다.
- `status_receiver`는 `ser`만 잠깐 복사한 후 실제 `readline()`은 lock 밖에서 한다.

CPython에서 짧은 변수 참조와 대입은 보통 한 번에 처리되어 이 작은 프로그램이 실용적으로 동작할 가능성이 높다. 그러나 여러 값을 하나의 일관된 묶음으로 읽고 쓰는 것을 엄밀하게 보장하지는 않는다. 향후 명령 종류와 안전 조건이 늘어나면 명령 상태 전용 lock이나 queue를 두는 편이 더 명확하다.

## 12. 코드에서 눈여겨볼 설계 의도

### 12.1 계속 같은 위치 명령을 보내지 않는 장치

`p`를 무한히 보내면 하위 펌웨어가 이를 계속 새로운 “다음 칸” 명령으로 해석할 위험이 있다. 이 코드는 `p`를 약 0.3초만 보낸 뒤 새 동작을 만들지 않는 `h`로 바꾼다.

하위 펌웨어도 연속으로 받은 같은 문자를 한 번의 명령으로 구분해야 한다. PC의 pulse만으로 중복 실행 방지가 완전히 보장된다고 가정하면 안 된다.

### 12.2 재연결 시 과거 명령 폐기

통신이 복구되었을 때 끊기기 전 이동 명령을 이어 보내지 않고 `k`부터 보낸다. 예측하지 못한 재가동을 막기 위한 안전한 기본값이다.

### 12.3 상태 기반 사전 거부

PC는 이동 중, fault, 미보정 상태에서 `p/n/r`을 보내지 않는다. 사용자가 잘못 누르는 것을 줄이는 역할을 한다. 그러나 수신 로그와 실제 장치 상태 사이에는 통신 지연이 있을 수 있으므로 하위 제어기의 상태 전이 검사도 반드시 필요하다.

### 12.4 자동 fault 복구 없음

fault가 나면 자동으로 같은 명령을 재시도하지 않는다. 기구 걸림, 기준 이탈, 센서 이상을 확인하지 않은 채 재시작하는 위험을 피한다.

## 13. 현재 코드의 주의점과 한계

이 절은 코드가 틀렸다는 뜻이 아니라, 동작을 정확히 이해하고 확장할 때 확인해야 할 부분이다.

1. `z`는 `last_state == 2`일 때만 PC에서 거부된다.
   연결 직후 아직 상태를 받지 않아 `last_state is None`이어도 `z`는 전송할 수 있다. 기준 설정 절차상 의도된 동작일 수 있지만, 실제 정지와 안정 300ms는 STM32가 검증해야 한다.

2. 상태는 텍스트 로그 형식에 의존한다.
   ESP32 로그에 정확히 `state=숫자`가 들어 있어야 한다. 로그 형식이 `state:2`처럼 바뀌면 화면 출력은 되지만 `last_state`가 갱신되지 않는다.

3. ASCII가 아닌 수신 문자는 버린다.
   ESP32가 한글 UTF-8 로그를 보내면 한글 바이트가 제거되어 깨진 내용만 보일 수 있다.

4. 읽기 오류만으로는 `ser=None`을 만들지 않는다.
   `status_receiver`는 읽기 오류 후 다시 시도할 뿐이다. 보통 반복 송신도 곧 실패해 `send_command`가 연결을 초기화하지만, 쓰기는 성공하고 읽기만 계속 실패하는 특이 상황에서는 자동 재연결이 늦어질 수 있다.

5. 빠른 연속 키 입력에는 상태 지연 구간이 있다.
   첫 `p` 직후 장치의 MOVING(2) 로그가 오기 전에 `p`를 또 누르면 PC의 `last_state`는 아직 1 또는 3일 수 있다. 이때 두 번째 입력도 PC 검사를 통과할 수 있다. 최종 중복·상태 전이 방지는 ESP32/STM32가 담당해야 한다.

6. `TOGGLE_KEYS` 분기는 현재 미완성 자리다.
   집합이 비어 있어 실행되지 않으며, 나중에 키를 추가해도 현재 코드는 출력만 하고 실제 전송하지 않는다.

7. 일반 키는 아무 안내 없이 무시된다.
   초보 사용자는 키가 고장 났다고 오해할 수 있으므로 필요하면 도움말이나 “알 수 없는 키” 메시지를 추가할 수 있다.

8. `global ser` in `connect()`는 현재 불필요하다.
   함수가 전역 `ser`를 직접 바꾸지 않고 지역 `s`만 반환하기 때문이다. 동작 오류는 아니지만 읽는 사람에게 혼동을 줄 수 있다.

9. `UnicodeDecodeError` 처리 블록은 현재 거의 도달하지 않는다.
   `errors="ignore"` 옵션이 디코딩 오류를 예외로 만들지 않고 해당 바이트를 버리기 때문이다.

10. PC 강제 종료에는 마지막 `k`가 보장되지 않는다.
    작업 관리자 강제 종료, USB 분리, PC 전원 손실에서는 `finally`가 실행되지 않을 수 있다. 공용 규격에 있는 ESP32 500ms 입력 단절 정지와 STM32 500ms 유효 명령 단절 fault가 핵심 안전장치다.

11. 포트는 정상 종료 시 명시적으로 `close()`하지 않는다.
    프로세스가 끝나면 운영체제가 보통 포트를 회수하지만, 명시적으로 닫는 정리 코드를 추가하면 자원 수명이 더 분명해진다.

## 14. 공용 프로토콜과의 대응

현재 `protocol/protocol.md`의 우선 규격은 “누적 20도 캐리어 시험(버전 4)”이다.

| 공용 규격 | 이 Python 파일의 구현 |
|---|---|
| Python ↔ ESP32 115200 bps | `BAUD_RATE = 115200` |
| `p/n/r` 약 300ms 반복 | `COMMAND_PULSE_SECONDS = 0.3` |
| 100ms 간격 전송 | `REPEAT_INTERVAL = 0.1` |
| pulse 뒤 `h` heartbeat | `repeat_sender()`에서 `h`로 전환 |
| `p/n/r`은 상태 1 또는 3에서 허용 | `last_state not in {1, 3}`이면 거부 |
| `k` 전체 정지 | `STOP_KEY = "k"`와 종료 시 마지막 전송 |
| 상태 0~4 | 시작 안내와 `state=숫자` 파싱 |
| ESP32의 TCP 상태 문자열은 `STATUS_A4` | 이 Python 파일은 TCP를 사용하지 않고 USB 시리얼 로그를 수신 |
| ESP32의 USB 로그에는 `state=숫자`가 포함됨 | Python은 USB 로그 전체를 출력하고 그 안의 `state=`만 찾음 |

공용 문서 아래쪽의 `CommandPacket`, `StatusPacket` 구조체는 다음 개발 단계를 위한 목표 규격이다. 이 Python 파일은 아직 그 구조화 binary packet을 만들거나 checksum을 계산하지 않는다. 현재 구현처럼 ASCII 한 글자와 줄바꿈을 보낸다.

## 15. 흔히 생길 수 있는 실행 문제

### 15.1 `ModuleNotFoundError: No module named 'serial'`

원인: pyserial이 설치되지 않았다.

확인/조치:

~~~powershell
python -m pip install pyserial
~~~

### 15.2 `could not open port 'COM7'` 또는 접근 거부

가능한 원인:

- 실제 ESP32 포트가 COM7이 아님
- 다른 시리얼 모니터가 포트를 점유함
- USB 케이블 분리 또는 드라이버 문제
- 포트 번호가 바뀜

실제 포트를 확인한 후 `SERIAL_PORT` 값을 맞추고 포트를 점유한 프로그램을 닫는다.

### 15.3 연결은 됐지만 `p/n/r`이 계속 거부됨

화면에 `state=1` 또는 `state=3` 형식의 로그가 수신되는지 확인한다.

- 로그가 전혀 없으면 ESP32 송신, baud rate, 케이블을 확인한다.
- 상태 로그 형식이 다르면 정규표현식이 상태를 찾지 못한다.
- 상태 0이면 먼저 실제 기준 홈을 맞추고 `z` 절차가 필요하다.
- 상태 4면 `k` 정지 후 원인을 점검하고 재정렬한 다음 `z`가 필요하다.

### 15.4 한글 로그가 보이지 않음

수신 코드는 ASCII만 해석하고 ASCII가 아닌 바이트를 버린다. ESP32가 UTF-8 한글을 출력한다면 디코딩 방식을 함께 맞춰야 한다.

## 16. 초보자가 기억하면 좋은 핵심 요약

- 키보드 함수는 “무슨 명령을 보낼지”만 바꾼다.
- 실제 시리얼 전송은 별도의 반복 송신 스레드가 0.1초마다 한다.
- `z/p/n/r`은 약 0.3초만 반복되고 이후 `h`로 바뀐다.
- `k`는 시간 제한 없이 반복되는 정지 명령이다.
- 수신 스레드는 ESP32 로그를 그대로 출력하며 `state=숫자`만 따로 기억한다.
- `p/n/r`은 마지막 상태가 READY(1) 또는 DONE(3)일 때만 허용된다.
- 연결이 끊기면 재연결하되 과거 이동 명령은 버리고 `k`로 시작한다.
- Esc나 Ctrl+C로 정상 종료할 때 마지막 `k`를 보내려 한다.
- PC 프로그램만 믿지 말고 ESP32 통신 failsafe와 STM32 로컬 안전 정지를 반드시 유지해야 한다.

## 17. 검증 메모

- 문서 작성 시 원본 `pc/robot_control_client_serial.py` 1~178줄을 UTF-8로 확인했다.
- Python 3.13.15에서 `python -m py_compile pc/robot_control_client_serial.py` 문법 검사를 통과했다.
- 실제 COM7 연결, ESP32 수신, STM32 구동과 모터 실기 동작은 수행하지 않았다.
- 소스 코드와 공용 프로토콜은 변경하지 않았으며, 이 해설 문서만 추가했다.
