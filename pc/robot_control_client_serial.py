"""Clutch-a carrier bench trial: every p/n press adds/subtracts 20 degrees.
Motor1/3 disabled. Reset requires a new reference. Windows terminal only.
"""

import msvcrt
import re
import threading
import time

import serial

# ---- 설정값 ----
SERIAL_PORT = "COM7"        # 본인 환경에 맞게 수정하세요
BAUD_RATE = 115200
REPEAT_INTERVAL = 0.1        # 이동 명령 재전송 주기(초)
RECONNECT_INTERVAL = 1.0     # 연결 끊겼을 때 재시도 주기(초)
COMMAND_PULSE_SECONDS = 0.3  # ESP32의 100ms polling에서 여러 번 보이도록 유지

MOVE_KEYS = {"z", "p", "n", "r"}
TOGGLE_KEYS = set()
STOP_KEY = "k"

# ---- 상태 ----
ser = None
ser_lock = threading.Lock()
active_move_key = "k"
command_until = 0.0
last_state = None
running = True

def connect():
    """ESP32에 시리얼로 연결. 실패하면 None 반환."""
    global ser
    try:
        s = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.1, write_timeout=0.2)
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


def repeat_sender():
    """명령 pulse 뒤 h heartbeat를 보내며 새 위치 명령을 만들지 않는다."""
    global active_move_key
    while running:
        if active_move_key in MOVE_KEYS and time.monotonic() >= command_until:
            active_move_key = "h"
        send_command(active_move_key)
        time.sleep(REPEAT_INTERVAL)


def keyboard_loop():
    """한 번의 유효한 키 입력을 한 번의 목표 변경 pulse로 만든다."""
    global active_move_key, command_until, running

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
        elif c in TOGGLE_KEYS:
            print(f"[키 입력] {c} (1회 전송)")
        elif c == STOP_KEY:
            active_move_key = "k"
            command_until = 0.0
            print("[키 입력] k (정지)")


def main():
    global running, active_move_key, command_until

    print("Clutch-a bench: motor1/3 disabled; manually lock ring gear first.")
    print("k STOP, wait >=0.3s at reference groove, z SET ZERO")
    print("p next +20deg / n next -20deg / r ZERO; each key press changes one step")
    print("state: 0 unreferenced, 1 ready, 2 moving, 3 done, 4 fault")
    print("After fault: k, inspect/re-align reference, then z. No automatic retry.")

    threading.Thread(target=connection_manager, daemon=True).start()
    threading.Thread(target=repeat_sender, daemon=True).start()
    threading.Thread(target=status_receiver, daemon=True).start()

    try:
        keyboard_loop()
    except KeyboardInterrupt:
        pass
    finally:
        running = False
        active_move_key = "k"
        command_until = 0.0
        time.sleep(REPEAT_INTERVAL + 0.05)
        send_command(STOP_KEY)
    time.sleep(0.2)
    print("종료됨")


if __name__ == "__main__":
    main()
