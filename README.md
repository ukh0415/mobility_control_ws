# 스마트 모빌리티 제어 시스템

휠 주행과 트랙 주행을 전환하는 모빌리티의 PC, ESP32, STM32 제어 코드와 설계 문서를 관리한다.

## 구성

```text
.
├─ AGENTS.md                    프로젝트 공통 작업 지침
├─ VERSION.md                   구성요소 및 도구 버전 기준
├─ pc/                          Windows PC 상위 제어 프로그램
├─ Arduino/esp32_i2c_master/    ESP32 통신 허브 펌웨어
├─ mobility/                    STM32CubeIDE 프로젝트
├─ protocol/                    공용 명령·상태 프로토콜
├─ agents/docs/                 설계·시험·troubleshooting 문서
├─ tests/                       자동 및 수동 테스트 자산
└─ archive/                     Git 비추적 참고 백업
```

## 주요 실행 경로

Python 클라이언트:

```powershell
python -m pip install -r requirements.txt
python .\pc\robot_control_client_serial.py
```

STM32CubeIDE에서는 저장소 내부의 `mobility/` 프로젝트를 import하거나 현재 워크스페이스에서 연다. ESP32는 `Arduino/esp32_i2c_master/esp32_i2c_master.ino`를 연다.

## 작업 전 필독

모든 작업자는 [AGENTS.md](./AGENTS.md)와 [통신 프로토콜](./protocol/protocol.md)을 먼저 확인한다. 모드 전환 설계는 [휠·트랙 시퀀스](./agents/docs/휠_트랙_모드_전환_시퀀스.md)에 기록되어 있다.
