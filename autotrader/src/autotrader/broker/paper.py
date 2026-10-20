"""가상 체결 브로커. 시세는 진짜(MarketData)를 쓰고 주문만 흉내 낸다.

토스 API가 모의투자를 지원하는지 확인되지 않아서, 실제 돈 없이 전체 흐름을
점검하는 용도로 만든다.

한계: 상태가 메모리에만 있어서 프로그램을 재시작하면 초기화된다.
"""

from __future__ import annotations

import itertools

from autotrader.broker.base import Broker, MarketData
from autotrader.models import OrderRequest, OrderResult, Position, Side


class PaperBroker(Broker):
    def __init__(
        self,
        market_data: MarketData,
        initial_cash: float,
        fee_rate: float = 0.0,
        sell_tax_rate: float = 0.0,
        slippage_rate: float = 0.0,
    ):
        self.market_data = market_data
        self.cash = initial_cash
        self.fee_rate = fee_rate
        self.sell_tax_rate = sell_tax_rate
        self.slippage_rate = slippage_rate
        self.positions: dict[str, Position] = {}
        self._ids = itertools.count(1)

    def get_cash(self) -> float:
        return self.cash

    def get_positions(self) -> dict[str, Position]:
        return dict(self.positions)

    def place_order(self, order: OrderRequest) -> OrderResult:
        order_id = f"paper-{next(self._ids)}"
        if order.quantity <= 0:
            return OrderResult(order_id, order, "REJECTED")

        price = self.market_data.get_price(order.symbol)

        if order.side == Side.BUY:
            fill = price * (1 + self.slippage_rate)
            cost = fill * order.quantity * (1 + self.fee_rate)
            if cost > self.cash:
                return OrderResult(order_id, order, "REJECTED")
            self.cash -= cost
            prev = self.positions.get(order.symbol)
            if prev:
                qty = prev.quantity + order.quantity
                avg = (prev.avg_price * prev.quantity + fill * order.quantity) / qty
                self.positions[order.symbol] = Position(order.symbol, qty, avg)
            else:
                self.positions[order.symbol] = Position(order.symbol, order.quantity, fill)
        else:
            pos = self.positions.get(order.symbol)
            if pos is None or pos.quantity < order.quantity:
                return OrderResult(order_id, order, "REJECTED")
            fill = price * (1 - self.slippage_rate)
            self.cash += fill * order.quantity * (1 - self.fee_rate - self.sell_tax_rate)
            remaining = pos.quantity - order.quantity
            if remaining:
                self.positions[order.symbol] = Position(order.symbol, remaining, pos.avg_price)
            else:
                del self.positions[order.symbol]

        return OrderResult(order_id, order, "FILLED", order.quantity, fill)
