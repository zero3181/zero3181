from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd

from autotrader.models import OrderRequest, OrderResult, Position


class MarketData(ABC):
    """시세 조회."""

    @abstractmethod
    def get_bars(self, symbol: str, count: int) -> pd.DataFrame:
        """최근 `count`개 일봉. 컬럼: open, high, low, close, volume."""

    @abstractmethod
    def get_price(self, symbol: str) -> float:
        """현재가."""


class Broker(ABC):
    """계좌 조회와 주문."""

    @abstractmethod
    def get_cash(self) -> float:
        """주문 가능 현금."""

    @abstractmethod
    def get_positions(self) -> dict[str, Position]:
        """보유 종목 (수량 0인 종목은 제외)."""

    @abstractmethod
    def place_order(self, order: OrderRequest) -> OrderResult: ...
