"""Manual clutch A/B 20-degree bench trial using a compact key layout.
Motor1/3 disabled. Every manual clutch change requires a new reference.
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

PULSE_COMMANDS = {"a", "b", "z", "p", "n", "r"}
STOP_KEY = "k"
EXTENDED_KEY_COMMANDS = {
    "K": "n",  # left arrow
    "M": "p",  # right arrow
    "H": "z",  # up arrow: set current groove as zero
    "P": "r",  # down arrow: return to zero
}
LEGACY_KEY_COMMANDS = {"p": "p", "n": "n", "z": "z", "r": "r", "k": "k"}
COMMAND_LABELS = {
    "a": "클러치 A 선택(링 고정, 캐리어 15:1)",
    "b": "클러치 B 선택(캐리어 고정, 링 12:1)",
    "p": "+20도",
    "n": "-20도",
    "z": "현재 홈을 0도로 설정",
    "r": "0도로 복귀",
    "k": "정지",
}

# ---- 상태 ----
ser = None
ser_lock = threading.Lock()
active_move_key = "k"
command_until = 0.0
stop_since = time.monotonic()
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
    global ser, active_move_key, command_until, stop_since, last_state
    while running:
        with ser_lock:
            need_connect = ser is None
        if need_connect:
            new_ser = connect()
            with ser_lock:
                active_move_key = "k"
                command_until = 0.0
                stop_since = time.monotonic()
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
        if active_move_key in PULSE_COMMANDS and time.monotonic() >= command_until:
            active_move_key = "h"
        send_command(active_move_key)
        time.sleep(REPEAT_INTERVAL)


def keyboard_loop():
    """한 번의 유효한 키 입력을 한 번의 목표 변경 pulse로 만든다."""
    global active_move_key, command_until, stop_since, running

    while running:
        c = msvcrt.getwch()

        command = None
        if c in ("\x00", "\xe0"):
            command = EXTENDED_KEY_COMMANDS.get(msvcrt.getwch())
            if command is None:
                continue

        elif c == "\x1b":
            running = False
            break
        elif c == " ":
            command = STOP_KEY
        else:
            key = c.lower()
            if key == "1":
                command = "a"
            elif key == "2":
                command = "b"
            else:
                command = LEGACY_KEY_COMMANDS.get(key)

        if command in PULSE_COMMANDS:
            if ser is None:
                print("[미연결] 연결 후 다시 입력하세요")
                continue
            if command in {"a", "b"}:
                if active_move_key != STOP_KEY or time.monotonic() - stop_since < 0.3:
                    print("[모드 선택 거부] Space로 정지하고 0.3초 후 다시 선택하세요")
                    continue
                if last_state == 2:
                    print("[모드 선택 거부] 모터2가 이동 중입니다")
                    continue
            if command in {"p", "n", "r"} and last_state not in {1, 3}:
                print(f"[명령 거부] state={last_state}; READY(1) 또는 DONE(3)에서 입력하세요")
                continue
            if command == "z" and last_state == 2:
                print("[명령 거부] 이동 중에는 기준을 설정할 수 없습니다")
                continue
            active_move_key = command
            command_until = time.monotonic() + COMMAND_PULSE_SECONDS
            print(f"[명령] {COMMAND_LABELS[command]}")
        elif command == STOP_KEY:
            active_move_key = "k"
            command_until = 0.0
            stop_since = time.monotonic()
            send_command(STOP_KEY)
            print("[명령] Space 정지")


def main():
    global running, active_move_key, command_until

    print("수동 클러치 A/B 20도 시험: 모터1/3은 비활성화됩니다.")
    print("1=A(링 고정/캐리어 15:1), 2=B(캐리어 고정/링 12:1)")
    print("← -20도 | → +20도 | ↑ 현재 홈=0도 | ↓ 0도 복귀 | Space 정지")
    print("모드 변경: Space → 손으로 클러치 변경 → 1/2 → ↑")
    print("state: 0 unreferenced, 1 ready, 2 moving, 3 done, 4 fault")
    print("fault 발생 시 Space → 원인 확인/홈 재정렬 → 1/2 → ↑ 순서로 복구하세요.")

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
