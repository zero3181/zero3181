# autotrader

토스증권 Open API 기반 룰 자동매매 프로그램 (뼈대 단계).
요구사항과 계획은 [docs/PRD.md](docs/PRD.md)를 보세요.

> ⚠️ 토스 API 연동부(`src/autotrader/broker/toss.py`)는 아직 **미완성**입니다.
> 엔드포인트를 공식 문서로 확인하지 못해 `TODO(공식문서)`로 남겨 두었고, 호출하면 `NotImplementedError`가 납니다.

## 설치

```bash
cd autotrader
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## 사용법

```bash
# 1) 가짜 데이터로 백테스트 (구조 확인용)
autotrader backtest --demo

# 2) 내 CSV로 백테스트 (첫 열 날짜, open/high/low/close/volume)
autotrader backtest --csv data/005930.csv --symbol 005930 --short 5 --long 20

# 3) 모의 운영 (토스 연동 구현 후)
cp config.example.toml config.toml
cp .env.example .env   # 키 입력
set -a; source .env; set +a
autotrader run --config config.toml --once

# 4) 실전: config.toml의 mode="live" + --live 플래그 둘 다 필요
autotrader run --config config.toml --live

# 비상 정지
touch STOP
```

## 구조

```
src/autotrader/
  models.py          # Signal, OrderRequest, Position 등
  strategy/          # 매매 룰 (Strategy 상속해 추가)
  risk.py            # 수량 결정, 한도, 비상 정지
  backtest.py        # 일봉 백테스트 (다음 봉 시가 체결)
  broker/
    base.py          # MarketData / Broker 인터페이스
    paper.py         # 가상 체결
    toss.py          # 토스 API 클라이언트 (TODO)
  engine.py          # 실시간 루프, 저널 기록
  cli.py
```

## 다음 할 일

1. 토스 공식 문서 보고 `broker/toss.py`의 TODO 채우기 (PRD 10장 Q1~Q9)
2. 실제 과거 데이터로 백테스트
3. 모의 운영 4주
