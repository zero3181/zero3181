"""설정 로딩. 일반 설정은 TOML 파일, 비밀값(API 키)은 환경변수에서 읽는다."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from autotrader.backtest import CostModel
from autotrader.models import Market
from autotrader.risk import RiskLimits

MODES = ("paper", "live")


@dataclass(frozen=True)
class AppConfig:
    mode: str
    market: Market
    symbols: list[str]
    interval_sec: int
    strategy_name: str
    strategy_params: dict
    limits: RiskLimits
    costs: CostModel
    paper_initial_cash: float
    kill_switch_path: Path
    journal_path: Path
    account_id: str = ""
    toss_base_url: str | None = None
    extra: dict = field(default_factory=dict)


def load_config(path: str | Path) -> AppConfig:
    path = Path(path)
    with path.open("rb") as f:
        raw = tomllib.load(f)

    trading = raw.get("trading", {})
    mode = trading.get("mode", "paper")
    if mode not in MODES:
        raise ValueError(f"trading.mode는 {MODES} 중 하나여야 합니다: {mode}")

    strategy = raw.get("strategy", {})
    risk = raw.get("risk", {})
    costs = raw.get("costs", {})
    paths = raw.get("paths", {})
    base_dir = path.parent

    return AppConfig(
        mode=mode,
        market=Market(trading.get("market", "KR")),
        symbols=list(trading.get("symbols", [])),
        interval_sec=int(trading.get("interval_sec", 300)),
        strategy_name=strategy.get("name", "ma_cross"),
        strategy_params=dict(strategy.get("params", {})),
        limits=RiskLimits(**risk),
        costs=CostModel(**costs),
        paper_initial_cash=float(raw.get("paper", {}).get("initial_cash", 10_000_000)),
        kill_switch_path=base_dir / paths.get("kill_switch", "STOP"),
        journal_path=base_dir / paths.get("journal", "logs/journal.jsonl"),
        account_id=raw.get("toss", {}).get("account_id", ""),
        toss_base_url=raw.get("toss", {}).get("base_url"),
    )


def load_toss_secrets() -> tuple[str, str]:
    client_id = os.environ.get("TOSS_CLIENT_ID", "")
    client_secret = os.environ.get("TOSS_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        raise RuntimeError("환경변수 TOSS_CLIENT_ID, TOSS_CLIENT_SECRET을 설정하세요 (.env.example 참고)")
    return client_id, client_secret
