"""공통 데이터 모델.

시세(bars)는 pandas DataFrame으로 다룬다.
- 인덱스: 시간순 DatetimeIndex
- 컬럼: open, high, low, close, volume
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

BAR_COLUMNS = ["open", "high", "low", "close", "volume"]


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class Market(str, Enum):
    KR = "KR"  # 국내 (KRX)
    US = "US"  # 미국


@dataclass(frozen=True)
class Signal:
    """전략이 내는 매매 신호. 수량은 리스크 관리자가 정한다."""

    symbol: str
    side: Side
    reason: str = ""


@dataclass(frozen=True)
class OrderRequest:
    symbol: str
    side: Side
    quantity: int
    limit_price: float | None = None  # None이면 시장가


@dataclass
class OrderResult:
    order_id: str
    request: OrderRequest
    status: str  # "FILLED" | "SUBMITTED" | "REJECTED" ...
    filled_qty: int = 0
    avg_price: float | None = None
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class Position:
    symbol: str
    quantity: int
    avg_price: float
