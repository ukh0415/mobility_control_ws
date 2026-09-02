"""
로봇 키보드 제어 클라이언트 - USB 시리얼 버전

WiFi(ROBOT_AP) 대신 USB 케이블로 ESP32와 직접 통신합니다.
노트북 WiFi를 인터넷용으로 그대로 쓸 수 있어서 테스트할 때 편합니다.

사용법:
    1. pip install pyserial
    2. Arduino IDE의 시리얼 모니터가 열려있다면 반드시 닫기
       (같은 COM 포트를 동시에 두 프로그램이 못 씀)
    3. 아래 SERIAL_PORT를 본인 환경의 COM 포트 번호로 수정
       (Arduino IDE의 포트 메뉴에서 확인 가능, 예: COM11, COM18 등)
    4. python robot_control_client_serial.py 실행

3개 모터 독립 제어 키 매핑:
    i/, 바퀴축 정/역   j/l 선기어 정/역   u/o 고정전환 정/역
    k 전체 정지
    ESC 프로그램 종료
"""

import msvcrt
import threading
import time

import serial

# ---- 설정값 ----
SERIAL_PORT = "COM7"        # 본인 환경에 맞게 수정하세요
BAUD_RATE = 115200
REPEAT_INTERVAL = 0.1        # 이동 명령 재전송 주기(초)
RECONNECT_INTERVAL = 1.0     # 연결 끊겼을 때 재시도 주기(초)

MOVE_KEYS = {"i", ",", "j", "l", "u", "o"}
TOGGLE_KEYS = set()
STOP_KEY = "k"

# ---- 상태 ----
ser = None
ser_lock = threading.Lock()
active_move_key = None
running = True

def connect():
    """ESP32에 시리얼로 연결. 실패하면 None 반환."""
    global ser
    try:
        s = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.1)
        time.sleep(2)  # ESP32가 시리얼 연결 시 자동 리셋되는 보드가 많아서 안정화 대기
        print(f"[연결됨] {SERIAL_PORT} @ {BAUD_RATE}bps")
        return s
    except serial.SerialException as e:
        print(f"[연결 실패] {e} - {RECONNECT_INTERVAL}초 후 재시도")
        return None


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


def connection_manager():
    """백그라운드에서 연결이 끊기면 계속 재연결을 시도."""
    global ser
    while running:
        with ser_lock:
            need_connect = ser is None
        if need_connect:
            new_ser = connect()
            with ser_lock:
                ser = new_ser
        time.sleep(RECONNECT_INTERVAL)


def status_receiver():
    """ESP32가 시리얼로 보내는 상태/디버그 줄을 그대로 화면에 출력."""
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
                print(line.decode("ascii", errors="ignore").rstrip())
            except UnicodeDecodeError:
                pass


def repeat_sender():
    """이동 키가 눌려있는 동안 주기적으로 재전송, 없으면 정지 상태 유지."""
    last_sent_stop = False
    while running:
        key = active_move_key
        if key is not None:
            send_command(key)
            last_sent_stop = False
        else:
            if not last_sent_stop:
                send_command(STOP_KEY)
                last_sent_stop = True
        time.sleep(REPEAT_INTERVAL)


def keyboard_loop():
    """PowerShell 콘솔 입력을 직접 읽는다. 이동은 k를 누를 때까지 유지된다."""
    global active_move_key, running

    while running:
        c = msvcrt.getwch()

        # 방향키/기능키는 2바이트 확장 코드이므로 나머지 1바이트도 소비한다.
        if c in ("\x00", "\xe0"):
            msvcrt.getwch()
            continue

        if c == "\x1b":
            running = False
            break

        c = c.lower()
        if c in MOVE_KEYS:
            active_move_key = c
            send_command(c)
            print(f"[키 입력] {c} (이동 시작, k를 누르면 정지)")
        elif c in TOGGLE_KEYS:
            send_command(c)
            print(f"[키 입력] {c} (1회 전송)")
        elif c == STOP_KEY:
            active_move_key = None
            send_command(STOP_KEY)
            print("[키 입력] k (정지)")


def main():
    global running

    print("로봇 키보드 컨트롤러 시작 (USB 시리얼 모드)")
    print(f"포트: {SERIAL_PORT} @ {BAUD_RATE}bps")
    print("i/, 바퀴축 정/역 | j/l 선기어 정/역 | u/o 고정전환 정/역")
    print("각 모터는 다음 명령 후에도 유지 / k 전체 정지 / ESC 종료")

    threading.Thread(target=connection_manager, daemon=True).start()
    threading.Thread(target=repeat_sender, daemon=True).start()
    threading.Thread(target=status_receiver, daemon=True).start()

    keyboard_loop()

    running = False
    send_command(STOP_KEY)
    time.sleep(0.2)
    print("종료됨")


if __name__ == "__main__":
    main()
