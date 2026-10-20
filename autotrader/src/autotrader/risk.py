"""리스크 관리. 전략 신호를 실제 주문으로 바꿀지, 몇 주를 살지 결정한다.

백테스트, 모의, 실전이 모두 이 코드를 그대로 쓴다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from autotrader.models import OrderRequest, Position, Side, Signal


@dataclass(frozen=True)
class RiskLimits:
    max_order_value: float  # 1회 매수 최대 금액 (계좌 통화 기준)
    max_positions: int = 5  # 동시에 보유할 최대 종목 수
    max_buys_per_day: int = 10  # 하루 최대 매수 주문 수 (버그로 인한 연속 주문 방지)
    daily_loss_limit_pct: float = 0.03  # 당일 시작 평가금 대비 손실이 이 비율을 넘으면 신규 매수 중단


@dataclass
class AccountState:
    cash: float
    positions: dict[str, Position]
    equity: float  # 현금 + 보유 평가금
    day_start_equity: float
    buys_today: int


@dataclass(frozen=True)
class Decision:
    order: OrderRequest | None
    reason: str

    @property
    def approved(self) -> bool:
        return self.order is not None


class RiskManager:
    def __init__(self, limits: RiskLimits, kill_switch_path: Path | None = None):
        self.limits = limits
        self.kill_switch_path = kill_switch_path

    def kill_switch_on(self) -> bool:
        """이 파일이 존재하면 모든 주문을 막는다 (비상 정지)."""
        return self.kill_switch_path is not None and self.kill_switch_path.exists()

    def evaluate(self, signal: Signal, price: float, account: AccountState) -> Decision:
        if self.kill_switch_on():
            return Decision(None, f"비상 정지 파일 존재: {self.kill_switch_path}")
        if price <= 0:
            return Decision(None, f"가격 이상: {price}")

        if signal.side == Side.SELL:
            return self._evaluate_sell(signal, account)
        return self._evaluate_buy(signal, price, account)

    def _evaluate_sell(self, signal: Signal, account: AccountState) -> Decision:
        # 매도는 위험을 줄이는 방향이므로 손실 한도나 주문 수 한도와 상관없이 허용한다.
        pos = account.positions.get(signal.symbol)
        if pos is None or pos.quantity <= 0:
            return Decision(None, "보유 수량 없음")
        return Decision(OrderRequest(signal.symbol, Side.SELL, pos.quantity), "전량 매도")

    def _evaluate_buy(self, signal: Signal, price: float, account: AccountState) -> Decision:
        lim = self.limits
        if account.buys_today >= lim.max_buys_per_day:
            return Decision(None, f"일일 매수 횟수 한도 도달 ({lim.max_buys_per_day})")

        if account.day_start_equity > 0:
            loss_pct = (account.day_start_equity - account.equity) / account.day_start_equity
            if loss_pct >= lim.daily_loss_limit_pct:
                return Decision(None, f"일일 손실 한도 도달 ({loss_pct:.2%})")

        if signal.symbol in account.positions and account.positions[signal.symbol].quantity > 0:
            return Decision(None, "이미 보유 중 (추가 매수 안 함)")
        if len(account.positions) >= lim.max_positions:
            return Decision(None, f"최대 보유 종목 수 도달 ({lim.max_positions})")

        budget = min(lim.max_order_value, account.cash)
        qty = math.floor(budget / price)
        if qty < 1:
            return Decision(None, f"주문 가능 금액 부족 (예산 {budget:,.0f}, 가격 {price:,.0f})")
        return Decision(OrderRequest(signal.symbol, Side.BUY, qty), f"{qty}주 매수")
