"""Local browser UI for motor2 telemetry, button control, and source tuning.

Requires the STM32/ESP32 wire-version 7 firmware in this repository.
The tuning editor changes carrier_test.h only; rebuild and flash STM32 to apply it.
"""

from __future__ import annotations

import argparse
import csv
from collections import deque
from dataclasses import asdict, dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import queue
import re
import threading
import time
from typing import Any
import webbrowser

import serial
from serial.tools import list_ports


BAUD_RATE = 115200
COMMAND_PERIOD_S = 0.1
COMMAND_PULSE_S = 0.3
DEFAULT_HTTP_PORT = 8765
HEADER_PATH = (Path(__file__).resolve().parents[1] /
               "stm32" / "mobility" / "Core" / "Inc" / "carrier_test.h")

STATE_NAMES = {
    0: "기준 미설정", 1: "이동 준비", 2: "모터2 이동 중",
    3: "이동 완료", 4: "오류 정지",
}
ERROR_NAMES = {
    0: "정상", 1: "명령 순서 오류", 2: "통신 오류", 3: "이동 시간 초과",
    4: "모터2 정체", 5: "반대 방향 이동", 6: "모터1 움직임 감지",
    7: "이동 범위 초과", 8: "완료 후 위치 이탈", 9: "클러치 인터록",
}
CLUTCH_NAMES = {0: "미선택", 1: "A (링 고정/캐리어)", 2: "B (캐리어 고정/링)"}

# name, Korean label, minimum, maximum, optional allowed-values
TUNABLES = (
    ("CARRIER_MOVE_PWM_PERCENT", "모터2 이동 PWM (%)", 0, 100, None),
    ("CARRIER_COUNT_TOLERANCE", "목표 허용오차 (count)", 0, 1000, None),
    ("CARRIER_SETTLE_MS", "정지 확인 시간 (ms)", 10, 10000, None),
    ("CARRIER_MOVE_TIMEOUT_MS", "모터2 최대 이동시간 (ms)", 100, 120000, None),
    ("CARRIER_STALL_MS", "모터2 정체 판정시간 (ms)", 50, 60000, None),
    ("CARRIER_LINK_TIMEOUT_MS", "통신 단절 판정시간 (ms)", 100, 10000, None),
    ("CARRIER_MAX_ABS_STEPS", "최대 20도 칸 수", 1, 1000, None),
    ("CARRIER_MAX_ABS_COUNT", "최대 기준거리 (count)", 1, 2_000_000_000, None),
    ("CARRIER_OBSERVATION_MODE", "관찰 모드 (0/1)", 0, 1, {0, 1}),
    ("CLUTCH_JOG_PWM_PERCENT", "모터3 조그 PWM (%)", 0, 100, None),
    ("CLUTCH_JOG_DURATION_MS", "모터3 조그 시간 (ms)", 10, 10000, None),
    ("CLUTCH_JOG_ENCODER_TOLERANCE", "클러치 인터록 허용 (count)", 0, 1000, None),
    ("MOTOR2_PWM_TO_COUNT_SIGN", "모터2 PWM/count 부호", -1, 1, {-1, 1}),
)


@dataclass(frozen=True)
class TelemetrySample:
    host_time: float
    esp_ms: int
    ok: bool
    state: int | None = None
    clutch_mode: int | None = None
    angle_tenths: int | None = None
    motor3_pwm: int | None = None
    error: int | None = None
    motor2_count: int | None = None
    target_count: int | None = None
    motor2_pwm: int | None = None
    target_step: int | None = None
    write_error: int | None = None
    bytes_received: int | None = None


def parse_telemetry_line(line: str, host_time: float | None = None) -> TelemetrySample:
    """Parse one TELEM_M37 CSV line; raise ValueError for another format."""
    fields = line.strip().split(",")
    if len(fields) < 5 or fields[0] != "TELEM_M37":
        raise ValueError("not a TELEM_M37 line")
    timestamp = time.monotonic() if host_time is None else host_time
    esp_ms = int(fields[1])
    ok = int(fields[2]) == 1
    if not ok:
        if len(fields) != 5:
            raise ValueError("invalid failed telemetry field count")
        return TelemetrySample(timestamp, esp_ms, False,
                               write_error=int(fields[3]), bytes_received=int(fields[4]))
    if len(fields) != 12:
        raise ValueError("invalid normal telemetry field count")
    values = [int(value) for value in fields[3:]]
    return TelemetrySample(timestamp, esp_ms, True, *values)


def read_tuning_values(path: Path = HEADER_PATH) -> dict[str, int]:
    """Read known integer #define values from carrier_test.h."""
    text = path.read_text(encoding="utf-8")
    result: dict[str, int] = {}
    for name, _label, _minimum, _maximum, _allowed in TUNABLES:
        match = re.search(rf"(?m)^\s*#define\s+{re.escape(name)}\s+(-?\d+)U?\b", text)
        if not match:
            raise ValueError(f"{name}을(를) {path}에서 찾지 못했습니다")
        result[name] = int(match.group(1))
    return result


def validate_tuning_values(values: dict[str, int]) -> None:
    for name, _label, minimum, maximum, allowed in TUNABLES:
        if name not in values:
            raise ValueError(f"{name} 값이 없습니다")
        value = values[name]
        if allowed is not None and value not in allowed:
            choices = ", ".join(str(item) for item in sorted(allowed))
            raise ValueError(f"{name}은(는) {choices} 중 하나여야 합니다")
        if value < minimum or value > maximum:
            raise ValueError(f"{name}은(는) {minimum}~{maximum} 범위여야 합니다")


def write_tuning_values(values: dict[str, int], path: Path = HEADER_PATH) -> None:
    """Atomically replace known #define numbers while preserving suffixes/comments."""
    validate_tuning_values(values)
    text = path.read_text(encoding="utf-8")
    for name, _label, _minimum, _maximum, _allowed in TUNABLES:
        pattern = re.compile(rf"(?m)^(\s*#define\s+{re.escape(name)}\s+)(-?\d+)(U?\b.*)$")
        text, count = pattern.subn(lambda match, value=values[name]:
                                   f"{match.group(1)}{value}{match.group(3)}", text, count=1)
        if count != 1:
            raise ValueError(f"{name} 정의를 정확히 한 개 찾지 못했습니다")
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


class SerialBridge:
    """Own the serial port in one worker thread and expose queued events."""

    def __init__(self) -> None:
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._active_command = "k"
        self._command_until = 0.0

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def connect(self, port: str) -> None:
        if self.running:
            raise ValueError("이미 시리얼 연결 중입니다")
        self._stop_event.clear()
        self._active_command = "k"
        self._command_until = 0.0
        self._thread = threading.Thread(target=self._worker, args=(port,), daemon=True)
        self._thread.start()

    def pulse(self, command: str) -> None:
        with self._lock:
            self._active_command = command
            self._command_until = time.monotonic() + COMMAND_PULSE_S

    def stop_motors(self) -> None:
        with self._lock:
            self._active_command = "k"
            self._command_until = 0.0

    def disconnect(self) -> None:
        self.stop_motors()
        self._stop_event.set()

    def _current_command(self) -> str:
        with self._lock:
            if (self._active_command not in {"k", "h"} and
                    time.monotonic() >= self._command_until):
                self._active_command = "h"
            return self._active_command

    def _worker(self, port: str) -> None:
        connection: serial.Serial | None = None
        try:
            connection = serial.Serial(port, BAUD_RATE, timeout=0.04, write_timeout=0.2)
            time.sleep(2.0)
            connection.write(b"k\nv\n")
            self.events.put(("connected", port))
            next_command = 0.0
            while not self._stop_event.is_set():
                now = time.monotonic()
                if now >= next_command:
                    connection.write((self._current_command() + "\n").encode("ascii"))
                    next_command = now + COMMAND_PERIOD_S
                raw = connection.readline()
                if raw:
                    self.events.put(("line", raw.decode("ascii", errors="ignore").strip()))
        except (serial.SerialException, OSError) as exc:
            self.events.put(("error", str(exc)))
        finally:
            if connection is not None:
                try:
                    connection.write(b"k\nV\n")
                    connection.close()
                except (serial.SerialException, OSError):
                    pass
            self.events.put(("disconnected", port))


class AppState:
    def __init__(self) -> None:
        self.bridge = SerialBridge()
        self.lock = threading.Lock()
        self.connected = False
        self.port = ""
        self.latest: TelemetrySample | None = None
        self.records: deque[TelemetrySample] = deque(maxlen=20000)
        self.logs: deque[str] = deque(maxlen=120)
        self.delayed_timer: threading.Timer | None = None
        self.closed = False
        self.monitor = threading.Thread(target=self._monitor_events, daemon=True)
        self.monitor.start()

    def _log(self, text: str) -> None:
        with self.lock:
            self.logs.append(text)

    def _monitor_events(self) -> None:
        while not self.closed:
            try:
                kind, payload = self.bridge.events.get(timeout=0.1)
            except queue.Empty:
                continue
            if kind == "connected":
                with self.lock:
                    self.connected = True
                    self.port = str(payload)
                    self.logs.append(f"[연결됨] {payload} @ {BAUD_RATE}bps")
            elif kind == "disconnected":
                with self.lock:
                    self.connected = False
                    self.logs.append("[연결 종료]")
            elif kind == "error":
                self._log(f"[통신 오류] {payload}")
            elif kind == "line":
                self._handle_line(str(payload))

    def _handle_line(self, line: str) -> None:
        if line.startswith("TELEM_M37,"):
            try:
                sample = parse_telemetry_line(line)
            except (ValueError, TypeError) as exc:
                self._log(f"[텔레메트리 해석 오류] {exc}: {line}")
                return
            if not sample.ok:
                self._log(f"[I2C 오류] writeErr={sample.write_error} "
                          f"bytes={sample.bytes_received}")
                return
            with self.lock:
                self.latest = sample
                self.records.append(sample)
        elif line:
            self._log(line)

    def connect(self, port: str) -> None:
        if not port:
            raise ValueError("COM 포트를 선택하세요")
        self.bridge.connect(port)
        self._log(f"[연결 시도] {port}")

    def disconnect(self) -> None:
        self.bridge.disconnect()

    def command(self, command: str) -> None:
        if command == "k":
            self.bridge.stop_motors()
            self._log("[명령] 전체 정지")
            return
        with self.lock:
            connected = self.connected
            sample = self.latest
        if not connected or sample is None:
            raise ValueError("상태 수신 후 명령할 수 있습니다")
        if command in {"u", "o", "a", "b"}:
            if command in {"u", "o"} and (sample.state not in {0, 1, 3, 4} or
                                               sample.motor3_pwm != 0):
                raise ValueError("모터1·2 정지와 모터3 PWM 0을 확인하세요")
            self.bridge.stop_motors()
            if self.delayed_timer is not None:
                self.delayed_timer.cancel()
            self.delayed_timer = threading.Timer(0.35, self._delayed_pulse,
                                                 args=(command,))
            self.delayed_timer.daemon = True
            self.delayed_timer.start()
            self._log("[명령] 정지 후 350ms 대기")
            return
        if command == "z":
            if sample.state == 2 or sample.clutch_mode not in {1, 2}:
                raise ValueError("모터2 정지와 A/B 계산모드 선택을 확인하세요")
        elif command in {"p", "n", "r"} and sample.state not in {1, 3}:
            raise ValueError("state=1 또는 state=3에서만 위치 이동할 수 있습니다")
        elif command not in {"z", "p", "n", "r"}:
            raise ValueError("지원하지 않는 명령입니다")
        self.bridge.pulse(command)
        self._log(f"[명령] {command}")

    def _delayed_pulse(self, command: str) -> None:
        with self.lock:
            connected = self.connected
        if connected:
            self.bridge.pulse(command)
            labels = {"u": "클러치 A 조그", "o": "클러치 B 조그",
                      "a": "A 계산모드", "b": "B 계산모드"}
            self._log(f"[명령] {labels[command]}")

    def clear_records(self) -> None:
        with self.lock:
            self.records.clear()

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            sample = self.latest
            records = list(self.records)[-300:]
            logs = list(self.logs)[-30:]
            connected = self.connected
            port = self.port
        start = records[0].host_time if records else 0.0
        sample_dict = asdict(sample) if sample is not None else None
        if sample_dict is not None:
            sample_dict["state_name"] = STATE_NAMES.get(sample.state, "알 수 없음")
            sample_dict["error_name"] = ERROR_NAMES.get(sample.error, "알 수 없음")
            sample_dict["clutch_name"] = CLUTCH_NAMES.get(sample.clutch_mode, "알 수 없음")
            if sample.target_count is not None and sample.motor2_count is not None:
                sample_dict["position_error"] = sample.target_count - sample.motor2_count
        graph = [{"t": round(item.host_time - start, 3), "count": item.motor2_count,
                  "target": item.target_count, "pwm": item.motor2_pwm, "state": item.state}
                 for item in records]
        return {"connected": connected, "port": port, "latest": sample_dict,
                "samples": graph, "logs": logs}

    def csv_bytes(self) -> bytes:
        with self.lock:
            records = list(self.records)
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(("elapsed_s", "esp_ms", "state", "clutch_mode", "angle_deg",
                         "motor3_pwm", "error", "motor2_count", "target_count",
                         "position_error", "motor2_pwm", "target_step"))
        start = records[0].host_time if records else 0.0
        for item in records:
            writer.writerow((f"{item.host_time - start:.3f}", item.esp_ms, item.state,
                             item.clutch_mode, f"{(item.angle_tenths or 0) / 10:.1f}",
                             item.motor3_pwm, item.error, item.motor2_count, item.target_count,
                             (item.target_count - item.motor2_count
                              if item.target_count is not None and item.motor2_count is not None else ""),
                             item.motor2_pwm, item.target_step))
        return b"\xef\xbb\xbf" + output.getvalue().encode("utf-8")

    def close(self) -> None:
        self.closed = True
        if self.delayed_timer is not None:
            self.delayed_timer.cancel()
        self.bridge.disconnect()


HTML = r"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>모터2 위치제어 튜닝</title><style>
:root{--bg:#0b1220;--panel:#111b2e;--line:#25324a;--text:#e5edf9;--muted:#91a0b8;--blue:#38bdf8;--orange:#f59e0b;--red:#ef4444;--green:#22c55e}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:12px "Malgun Gothic",sans-serif;overflow-x:hidden}
header{min-height:46px;padding:7px 10px;border-bottom:1px solid var(--line);display:flex;gap:7px;align-items:center;flex-wrap:wrap}
h1{font-size:17px;margin:0 10px 0 0}
button,select,input{background:#18243a;color:var(--text);border:1px solid #354563;border-radius:5px;padding:6px 8px;font:inherit}
button{cursor:pointer}button:hover:not(:disabled){border-color:var(--blue)}button:disabled{opacity:.35;cursor:not-allowed}
.danger{background:#7f1d1d}.primary{background:#075985}
.layout{display:grid;grid-template-columns:minmax(560px,2fr) minmax(300px,1fr);gap:7px;padding:7px}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:7px;padding:8px;margin-bottom:7px}
.panel h2{font-size:13px;margin:0 0 6px}
.status-grid{display:grid;grid-template-columns:repeat(5,minmax(95px,1fr));gap:4px}
.metric{background:#0d1627;border-radius:5px;padding:5px 7px;min-height:43px}
.metric span{display:block;color:var(--muted);font-size:10px;margin-bottom:2px}
.metric strong{font-size:13px}
.controls{display:grid;grid-template-columns:repeat(3,1fr);gap:4px}
.controls button{min-height:31px;padding:5px 6px}
.controls button:not(:disabled){box-shadow:inset 0 0 0 1px #46658d}
.guide{margin:0 0 6px;padding:6px 8px;border-radius:5px;background:#0c2b45;color:#bae6fd;font-weight:700}
.revision{color:#7dd3fc;font-size:10px}.click-status{margin:4px 0;color:#a7f3d0;font-size:10.5px}
.graph-head{display:flex;justify-content:space-between;align-items:center;gap:6px}
canvas{width:100%;height:min(36vh,330px);min-height:250px;background:#0a1020;border-radius:5px}
.legend{color:var(--muted);font-size:11px;margin-bottom:3px}
.tuning-row{display:grid;grid-template-columns:minmax(0,1fr) 72px;gap:5px;align-items:center;margin:2px 0}
.tuning-row label{font-size:10.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tuning-row input{width:72px;padding:3px 5px;text-align:right}
.note{color:#fca5a5;line-height:1.35;margin:6px 0 4px;font-size:10.5px}
.small{color:var(--muted);font-size:10.5px;margin:5px 0}
.log{height:125px;overflow:auto;white-space:pre-wrap;background:#080e19;padding:6px;border-radius:5px;color:#cbd5e1;font-size:10.5px}
@media(max-width:900px){.layout{grid-template-columns:1fr}.status-grid{grid-template-columns:repeat(5,minmax(82px,1fr))}canvas{height:300px}}
@media(max-width:620px){.status-grid{grid-template-columns:repeat(2,1fr)}.controls{grid-template-columns:repeat(2,1fr)}}
</style></head><body>
<header><h1>모터2 위치제어 시각화·튜닝</h1><span class="revision">UI rev.2</span><select id="port"></select><button onclick="loadPorts()">포트 새로고침</button><button class="primary" id="connect" onclick="toggleConnection()">연결</button><strong id="connection">연결 안 됨</strong><span class="small">UI 사용 중에만 100ms 텔레메트리</span></header>
<main class="layout"><section><div class="panel"><h2>실시간 상태</h2><div class="status-grid">
<div class="metric"><span>제어 상태</span><strong id="state">-</strong></div><div class="metric"><span>오류</span><strong id="error">-</strong></div><div class="metric"><span>계산 모드</span><strong id="clutch">-</strong></div><div class="metric"><span>실제 count</span><strong id="count">-</strong></div><div class="metric"><span>목표 count</span><strong id="target">-</strong></div><div class="metric"><span>목표-실제</span><strong id="poserr">-</strong></div><div class="metric"><span>모터2 PWM</span><strong id="pwm2">-</strong></div><div class="metric"><span>모터3 PWM</span><strong id="pwm3">-</strong></div><div class="metric"><span>출력각</span><strong id="angle">-</strong></div><div class="metric"><span>목표 홈</span><strong id="step">-</strong></div></div></div>
<div class="panel"><h2>버튼 제어</h2><div class="guide" id="nextAction">상태 수신을 기다리는 중입니다.</div><div class="controls"><button class="danger" data-always="1" onclick="sendMotorCommand('k')">■ 전체 정지</button><button data-clutch="1" onclick="sendMotorCommand('u')">클러치 A 방향 조그</button><button data-clutch="1" onclick="sendMotorCommand('o')">클러치 B 방향 조그</button><button data-mode="1" onclick="sendMotorCommand('a')">A 계산모드 선택 (15:1)</button><button data-mode="1" onclick="sendMotorCommand('b')">B 계산모드 선택 (12:1)</button><button data-home="1" onclick="sendMotorCommand('z')">현재 홈을 0°로 저장</button><button data-move="1" onclick="sendMotorCommand('n')">← 출력축 -20°</button><button data-move="1" onclick="sendMotorCommand('r')">저장한 0°로 복귀</button><button data-move="1" onclick="sendMotorCommand('p')">출력축 +20° →</button></div><div class="click-status" id="clickStatus">최근 버튼: 없음</div><p class="small">클러치/계산모드 버튼은 먼저 정지하고 350ms 뒤 명령합니다. 최종 인터록은 STM32가 판정합니다.</p></div>
<div class="panel"><div class="graph-head"><h2>최근 20초 위치·PWM</h2><div><button onclick="clearGraph()">그래프 지우기</button> <button onclick="location.href='/api/csv'">CSV 저장</button></div></div><div class="legend">실제 count <b style="color:#38bdf8">하늘색</b> · 목표 <b style="color:#f59e0b">주황색</b> · 모터2 PWM <b style="color:#ef4444">빨강</b></div><canvas id="graph"></canvas></div></section>
<aside><div class="panel"><h2>carrier_test.h 튜닝값</h2><div id="tuning"></div><div style="display:flex;justify-content:space-between;margin-top:10px"><button onclick="loadTuning()">소스 다시 읽기</button><button onclick="saveTuning()">헤더에 저장</button></div><p class="note">저장은 소스만 변경합니다. STM32CubeIDE에서 Build/Flash해야 실제 보드에 적용됩니다.</p><div class="small" id="sourceStatus"></div></div><div class="panel"><h2>통신 로그</h2><div class="log" id="log"></div></div></aside></main>
<script>
let connected=false,lastStatus=null,tuningMeta=[];async function api(path,method='GET',body=null){let o={method,headers:{}};if(body!==null){o.headers['Content-Type']='application/json';o.body=JSON.stringify(body)}let r=await fetch(path,o);let data=await r.json();if(!r.ok)throw new Error(data.error||'요청 실패');return data}
async function loadPorts(){let d=await api('/api/ports');let s=document.getElementById('port'),old=s.value;s.innerHTML='';d.ports.forEach(p=>{let o=document.createElement('option');o.value=p;o.textContent=p;s.appendChild(o)});if(d.ports.includes(old))s.value=old;else if(d.default_port)s.value=d.default_port}async function toggleConnection(){try{if(connected)await api('/api/disconnect','POST',{});else await api('/api/connect','POST',{port:document.getElementById('port').value})}catch(e){alert(e.message)}}async function sendMotorCommand(cmd){try{await api('/api/command','POST',{command:cmd});document.getElementById('clickStatus').textContent='최근 버튼: '+cmd+' (서버 접수 완료)'}catch(e){document.getElementById('clickStatus').textContent='최근 버튼 실패: '+cmd;alert(e.message)}}async function clearGraph(){await api('/api/clear','POST',{})}
async function loadTuning(){try{let d=await api('/api/tuning'),box=document.getElementById('tuning');tuningMeta=d.definitions;box.innerHTML='';d.definitions.forEach(x=>{let row=document.createElement('div');row.className='tuning-row';row.innerHTML=`<label title="${x.name}">${x.label}</label><input id="t_${x.name}" type="number" min="${x.min}" max="${x.max}" value="${d.values[x.name]}">`;box.appendChild(row)});document.getElementById('sourceStatus').textContent='읽은 파일: '+d.path}catch(e){document.getElementById('sourceStatus').textContent=e.message}}async function saveTuning(){let values={};tuningMeta.forEach(x=>values[x.name]=Number(document.getElementById('t_'+x.name).value));try{let d=await api('/api/tuning','POST',{values});document.getElementById('sourceStatus').textContent=d.message}catch(e){alert(e.message)}}function text(id,value){document.getElementById(id).textContent=value}
function updateButtons(s){let guide=document.getElementById('nextAction');document.querySelectorAll('.controls button').forEach(b=>b.disabled=true);if(!connected){guide.textContent='먼저 COM 포트에 연결하세요.';return}document.querySelector('[data-always]').disabled=false;if(!s){guide.textContent='텔레메트리 상태 수신을 기다리는 중입니다.';return}let m3=s.motor3_pwm===0;if([0,1,3,4].includes(s.state)&&m3)document.querySelectorAll('[data-clutch]').forEach(b=>b.disabled=false);if(s.state!==2&&m3)document.querySelectorAll('[data-mode]').forEach(b=>b.disabled=false);if(s.state===0&&[1,2].includes(s.clutch_mode)&&m3)document.querySelector('[data-home]').disabled=false;if([1,3].includes(s.state)&&m3)document.querySelectorAll('[data-move]').forEach(b=>b.disabled=false);if(s.state===2)guide.textContent='모터2 이동 중입니다. 완료될 때까지 기다리거나 전체 정지를 누르세요.';else if(s.motor3_pwm!==0)guide.textContent='모터3 클러치 조그 중입니다. 자동 정지를 기다리세요.';else if(s.state===4)guide.textContent='오류 정지 상태입니다. 전체 정지 후 오류 원인을 확인하세요.';else if(s.state===0&&s.clutch_mode===0)guide.textContent='① 실제 클러치 상태에 맞춰 A 또는 B 계산모드를 먼저 선택하세요.';else if(s.state===0)guide.textContent='② 실제 홈을 맞춘 뒤 “현재 홈을 0°로 저장”을 누르세요.';else guide.textContent='③ 기준 설정 완료: ±20° 이동 또는 0° 복귀 버튼을 사용할 수 있습니다.'}
function draw(samples){let c=document.getElementById('graph'),dpr=devicePixelRatio||1,w=c.clientWidth,h=c.clientHeight;c.width=w*dpr;c.height=h*dpr;let x=c.getContext('2d');x.scale(dpr,dpr);x.fillStyle='#0a1020';x.fillRect(0,0,w,h);if(samples.length<2){x.fillStyle='#91a0b8';x.fillText('텔레메트리 수신 대기 중',w/2-70,h/2);return}let end=samples[samples.length-1].t,start=Math.max(samples[0].t,end-20),v=samples.filter(q=>q.t>=start),vals=[];v.forEach(q=>{if(q.count!==null)vals.push(q.count);if(q.target!==null)vals.push(q.target)});let mn=Math.min(...vals),mx=Math.max(...vals);if(mx-mn<20){let m=(mx+mn)/2;mn=m-10;mx=m+10}let margin=Math.max((mx-mn)*.08,2);mn-=margin;mx+=margin;let L=65,R=w-15,T=25,B=h*.7,PT=B+35,PB=h-25,dur=Math.max(end-start,1),xc=q=>L+(q.t-start)/dur*(R-L),yc=n=>B-(n-mn)/(mx-mn)*(B-T);x.font='12px Malgun Gothic';for(let f of [0,.25,.5,.75,1]){let y=T+f*(B-T);x.strokeStyle='#25324a';x.beginPath();x.moveTo(L,y);x.lineTo(R,y);x.stroke();x.fillStyle='#91a0b8';x.fillText((mx-f*(mx-mn)).toFixed(0),5,y+4)}function line(key,color,yfn){x.strokeStyle=color;x.lineWidth=2;x.beginPath();let first=true;v.forEach(q=>{if(q[key]===null)return;let px=xc(q),py=yfn(q[key]);if(first){x.moveTo(px,py);first=false}else x.lineTo(px,py)});x.stroke()}line('target','#f59e0b',yc);line('count','#38bdf8',yc);for(let y of [PT,(PT+PB)/2,PB]){x.strokeStyle='#25324a';x.beginPath();x.moveTo(L,y);x.lineTo(R,y);x.stroke()}line('pwm','#ef4444',p=>PT+(100-Math.max(-100,Math.min(100,p)))/200*(PB-PT));x.fillStyle='#91a0b8';x.fillText('PWM +100',5,PT+4);x.fillText('0',35,(PT+PB)/2+4);x.fillText('-100',28,PB+4)}
async function poll(){try{let d=await api('/api/status');connected=d.connected;lastStatus=d.latest;text('connection',connected?(d.port+' 연결됨 / 텔레메트리 켜짐'):'연결 안 됨');document.getElementById('connect').textContent=connected?'연결 해제':'연결';let s=d.latest;if(s){text('state',`${s.state}: ${s.state_name}`);text('error',`${s.error}: ${s.error_name}`);text('clutch',s.clutch_name);text('count',s.motor2_count);text('target',s.target_count);text('poserr',s.position_error);text('pwm2',s.motor2_pwm+'%');text('pwm3',s.motor3_pwm+'%');text('angle',(s.angle_tenths/10).toFixed(1)+'°');text('step',s.target_step+'칸')}updateButtons(s);draw(d.samples);let logBox=document.getElementById('log'),newLog=d.logs.join('\n');if(logBox.textContent!==newLog){logBox.textContent=newLog;logBox.scrollTop=logBox.scrollHeight}}catch(e){text('connection','UI 서버 오류: '+e.message)}setTimeout(poll,100)}loadPorts();loadTuning();poll();
</script></body></html>"""


class RequestHandler(BaseHTTPRequestHandler):
    state: AppState
    default_port: str

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _send_json(self, data: Any, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length).decode("utf-8")) if length > 0 else {}

    def do_GET(self) -> None:  # noqa: N802
        try:
            if self.path == "/":
                body = HTML.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif self.path == "/api/status":
                self._send_json(self.state.snapshot())
            elif self.path == "/api/ports":
                self._send_json({"ports": [item.device for item in list_ports.comports()],
                                 "default_port": self.default_port})
            elif self.path == "/api/tuning":
                definitions = [{"name": name, "label": label, "min": minimum,
                                "max": maximum, "allowed": sorted(allowed) if allowed else None}
                               for name, label, minimum, maximum, allowed in TUNABLES]
                self._send_json({"values": read_tuning_values(), "definitions": definitions,
                                 "path": str(HEADER_PATH)})
            elif self.path == "/api/csv":
                body = self.state.csv_bytes()
                filename = time.strftime("motor2_telemetry_%Y%m%d_%H%M%S.csv")
                self.send_response(200)
                self.send_header("Content-Type", "text/csv; charset=utf-8")
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self._send_json({"error": "not found"}, 404)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            self._send_json({"error": str(exc)}, 400)

    def do_POST(self) -> None:  # noqa: N802
        try:
            data = self._read_json()
            if self.path == "/api/connect":
                self.state.connect(str(data.get("port", "")))
            elif self.path == "/api/disconnect":
                self.state.disconnect()
            elif self.path == "/api/command":
                self.state.command(str(data.get("command", "")))
            elif self.path == "/api/clear":
                self.state.clear_records()
            elif self.path == "/api/tuning":
                raw_values = data.get("values")
                if not isinstance(raw_values, dict):
                    raise ValueError("values 객체가 필요합니다")
                values = {name: int(raw_values[name]) for name, *_rest in TUNABLES}
                write_tuning_values(values)
                self._send_json({"ok": True,
                                 "message": "carrier_test.h 저장 완료. STM32 Build/Flash가 필요합니다."})
                return
            else:
                self._send_json({"error": "not found"}, 404)
                return
            self._send_json({"ok": True})
        except (KeyError, OSError, ValueError, json.JSONDecodeError) as exc:
            self._send_json({"error": str(exc)}, 400)


def create_server(host: str, port: int, default_port: str,
                  state: AppState | None = None) -> tuple[ThreadingHTTPServer, AppState]:
    app_state = state or AppState()
    handler = type("MotorUIHandler", (RequestHandler,),
                   {"state": app_state, "default_port": default_port})
    return ThreadingHTTPServer((host, port), handler), app_state


def main() -> None:
    parser = argparse.ArgumentParser(description="Motor2 browser-based position tuning UI")
    parser.add_argument("--port", default="COM7", help="ESP32 USB serial port")
    parser.add_argument("--http-port", type=int, default=DEFAULT_HTTP_PORT,
                        help="local browser UI port")
    parser.add_argument("--no-browser", action="store_true", help="do not open a browser")
    args = parser.parse_args()
    server, state = create_server("127.0.0.1", args.http_port, args.port)
    url = f"http://127.0.0.1:{args.http_port}/"
    print(f"모터2 튜닝 UI: {url}")
    print("종료: Ctrl+C (종료 시 모터 정지 명령 전송)")
    if not args.no_browser:
        threading.Timer(0.3, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever(poll_interval=0.1)
    except KeyboardInterrupt:
        pass
    finally:
        state.close()
        server.server_close()
        print("UI 종료됨")


if __name__ == "__main__":
    main()
