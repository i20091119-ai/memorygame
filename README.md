# 경남수학문화관 기억톡톡 (GNMC Memory TalkTalk)

Arduino UNO Q (Linux MPU + STM32 MCU) 기반의 키오스크형 색상 기억력 게임.

명세서: [`docs/SRS_v1.2.md`](docs/SRS_v1.2.md)

## 구조

```
memorygame/
├── docs/SRS_v1.2.md       명세서
├── mcu/memorygame_mcu.ino STM32 MCU 스케치
├── mpu/                   Linux MPU Python 앱
├── config/config.yaml     운영 설정 (기본값)
├── systemd/               자동 부팅 서비스
└── tests/                 pytest 단위 테스트
```

## MPU 실행

개발 머신에서 시뮬레이션 모드로 실행:

```
pip install -r requirements.txt
python -m mpu.main --sim --windowed
```

키보드 매핑:
- `R`/`B`/`Y`/`G` = 빨강/파랑/노랑/초록 버튼
- 화살표 위/오른/아래/왼 = 빨/파/초/노
- 마우스 클릭/터치로 4분면 또는 가상자판 입력
- `Esc` = 종료 (닉네임 입력 화면에서는 [취소])

## MCU 펌웨어

Arduino App Lab 또는 Arduino IDE에서 `mcu/memorygame_mcu.ino` 를 STM32U585 대상으로 빌드/업로드.

핀 배치:
| 색상   | 버튼 핀 (INPUT_PULLUP) | LED 핀 (PWM) |
|--------|------------------------|--------------|
| RED    | D2                     | D6           |
| BLUE   | D3                     | D9           |
| YELLOW | D4                     | D10          |
| GREEN  | D5                     | D11          |

## 테스트

```
PYTHONPATH=. pytest -q
```

## 배포 (UNO Q)

```
sudo cp -r . /opt/memorygame
sudo cp config/config.yaml /home/arduino/config.yaml
sudo cp systemd/memorygame.service /etc/systemd/system/
sudo systemctl enable --now memorygame.service
```

## 라이선스

내부 사용. 외부 폰트 동봉 시 각 폰트의 라이선스(Pretendard / Noto Sans KR 등)에 따른다.
