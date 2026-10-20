"""실시간(모의/실전) 매매 루프."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict
from datetime import date, datetime, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

from autotrader.broker.base import Broker, MarketData
from autotrader.models import Market, Side
from autotrader.risk import AccountState, RiskManager
from autotrader.strategy.base import Strategy

log = logging.getLogger(__name__)

_SESSIONS = {
    Market.KR: (ZoneInfo("Asia/Seoul"), dtime(9, 0), dtime(15, 30)),
    Market.US: (ZoneInfo("America/New_York"), dtime(9, 30), dtime(16, 0)),
}


def is_market_open(market: Market, now: datetime | None = None) -> bool:
    """정규장 시간인지 확인. 주말만 거른다.

    한계: 공휴일, 임시 휴장, 단축 거래일은 고려하지 않는다 (PRD 미확정 사항 참고).
    """
    tz, open_t, close_t = _SESSIONS[market]
    local = (now or datetime.now(tz)).astimezone(tz)
    if local.weekday() >= 5:
        return False
    return open_t <= local.time() < close_t


class TradingEngine:
    def __init__(
        self,
        market_data: MarketData,
        broker: Broker,
        strategy: Strategy,
        risk: RiskManager,
        symbols: list[str],
        market: Market,
        journal_path: Path,
        bars_lookback: int = 120,
    ):
        self.market_data = market_data
        self.broker = broker
        self.strategy = strategy
        self.risk = risk
        self.symbols = symbols
        self.market = market
        self.journal_path = journal_path
        self.bars_lookback = max(bars_lookback, strategy.min_bars)
        self._day: date | None = None
        self._day_start_equity = 0.0
        self._buys_today = 0

    def _equity(self, cash: float, positions) -> float:
        return cash + sum(p.quantity * self.market_data.get_price(s) for s, p in positions.items())

    def _roll_day(self, equity: float) -> None:
        tz = _SESSIONS[self.market][0]
        today = datetime.now(tz).date()
        if today != self._day:
            self._day = today
            self._day_start_equity = equity
            self._buys_today = 0
            log.info(f"새 거래일 {today}, 시작 평가금 {equity:,.0f}")

    def run_once(self) -> None:
        """모든 종목에 대해 한 번씩 신호 확인 → 리스크 검사 → 주문."""
        cash = self.broker.get_cash()
        positions = self.broker.get_positions()
        self._roll_day(self._equity(cash, positions))

        for symbol in self.symbols:
            try:
                self._process_symbol(symbol)
            except Exception:
                # 한 종목 오류로 전체가 멈추지 않게 하되, 반드시 기록한다.
                log.exception("%s 처리 중 오류", symbol)

    def _process_symbol(self, symbol: str) -> None:
        positions = self.broker.get_positions()
        bars = self.market_data.get_bars(symbol, self.bars_lookback)
        signal = self.strategy.generate(symbol, bars, positions.get(symbol))
        if signal is None:
            return

        price = self.market_data.get_price(symbol)
        cash = self.broker.get_cash()
        account = AccountState(
            cash=cash,
            positions=positions,
            equity=self._equity(cash, positions),
            day_start_equity=self._day_start_equity,
            buys_today=self._buys_today,
        )
        decision = self.risk.evaluate(signal, price, account)
        self._journal("decision", symbol=symbol, signal=asdict(signal), price=price, reason=decision.reason)
        log.info("%s %s 신호 (%s) → %s", symbol, signal.side.value, signal.reason, decision.reason)
        if not decision.approved:
            return

        result = self.broker.place_order(decision.order)
        if result.status != "REJECTED" and decision.order.side == Side.BUY:
            self._buys_today += 1
        self._journal(
            "order",
            symbol=symbol,
            order=asdict(decision.order),
            order_id=result.order_id,
            status=result.status,
            filled_qty=result.filled_qty,
            avg_price=result.avg_price,
        )

    def run_forever(self, interval_sec: int = 60) -> None:
        log.info("매매 루프 시작: %s, 종목 %s, %s초 간격", self.market.value, self.symbols, interval_sec)
        while True:
            if self.risk.kill_switch_on():
                log.warning("비상 정지 파일이 감지되어 종료합니다")
                return
            if is_market_open(self.market):
                self.run_once()
            time.sleep(interval_sec)

    def _journal(self, kind: str, **data) -> None:
        self.journal_path.parent.mkdir(parents=True, exist_ok=True)
        record = {"ts": datetime.now().isoformat(timespec="seconds"), "kind": kind, **data}
        with self.journal_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
