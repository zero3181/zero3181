"""토스증권 Open API 클라이언트 (뼈대).

주의: 이 파일의 엔드포인트 경로, 인증 방식, 응답 필드는 아직 공식 문서로
확인하지 않았다. 아래 TODO(공식문서) 표시가 붙은 부분은 토스증권 공식 Open API
문서를 보고 채워야 한다. 추측으로 채우지 않기 위해 해당 메서드는
NotImplementedError를 던진다.

이미 구현된 공통 부분:
- 액세스 토큰 발급/캐시 (OAuth 2.0 client credentials로 가정. 공식 문서와 대조 필요)
- 호출 간 최소 간격 유지 (초당 호출 한도 대응)
- 429/5xx 응답 시 지수 백오프 재시도
- 주문(POST)은 자동 재시도하지 않음 (중복 주문 방지)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import pandas as pd
import requests

from autotrader.broker.base import Broker, MarketData
from autotrader.models import OrderRequest, OrderResult, Position

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class TossCredentials:
    client_id: str
    client_secret: str


@dataclass(frozen=True)
class TossEndpoints:
    # TODO(공식문서): 아래 값은 전부 자리표시자다. 공식 문서의 실제 값으로 바꿔야 한다.
    base_url: str = "https://openapi.tossinvest.com"
    token_path: str = "/TODO/oauth2/token"
    bars_path: str = "/TODO/quotations/daily"
    price_path: str = "/TODO/quotations/price"
    balance_path: str = "/TODO/accounts/balance"
    positions_path: str = "/TODO/accounts/positions"
    order_path: str = "/TODO/orders"


class TossApiError(RuntimeError):
    pass


class TossClient(MarketData, Broker):
    RETRYABLE_STATUS = {429, 500, 502, 503, 504}

    def __init__(
        self,
        credentials: TossCredentials,
        account_id: str,
        endpoints: TossEndpoints | None = None,
        min_interval_sec: float = 0.25,
        max_retries: int = 3,
        timeout_sec: float = 10.0,
        session: requests.Session | None = None,
    ):
        self.credentials = credentials
        self.account_id = account_id
        self.endpoints = endpoints or TossEndpoints()
        self.min_interval_sec = min_interval_sec
        self.max_retries = max_retries
        self.timeout_sec = timeout_sec
        self.session = session or requests.Session()
        self._token: str | None = None
        self._token_expires_at = 0.0
        self._last_call = 0.0

    # ---------- 공통 ----------

    def _access_token(self) -> str:
        if self._token and time.time() < self._token_expires_at - 60:
            return self._token
        # TODO(공식문서): grant_type, 요청 형식(form/json), 응답 필드명 확인
        resp = self.session.post(
            self.endpoints.base_url + self.endpoints.token_path,
            data={
                "grant_type": "client_credentials",
                "client_id": self.credentials.client_id,
                "client_secret": self.credentials.client_secret,
            },
            timeout=self.timeout_sec,
        )
        if resp.status_code != 200:
            raise TossApiError(f"토큰 발급 실패: HTTP {resp.status_code} {resp.text[:200]}")
        body = resp.json()
        self._token = body["access_token"]
        self._token_expires_at = time.time() + float(body.get("expires_in", 3600))
        return self._token

    def _throttle(self) -> None:
        wait = self.min_interval_sec - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.monotonic()

    def _request(self, method: str, path: str, *, retry: bool = True, **kwargs) -> dict:
        attempts = self.max_retries + 1 if retry else 1
        for attempt in range(attempts):
            self._throttle()
            headers = {"Authorization": f"Bearer {self._access_token()}"}
            resp = self.session.request(
                method,
                self.endpoints.base_url + path,
                headers=headers,
                timeout=self.timeout_sec,
                **kwargs,
            )
            if resp.status_code == 401:
                self._token = None  # 토큰 만료 가능성: 다음 시도에서 재발급
            if resp.ok:
                return resp.json()
            retryable = resp.status_code in self.RETRYABLE_STATUS or resp.status_code == 401
            if not retryable or attempt == attempts - 1:
                raise TossApiError(f"{method} {path} 실패: HTTP {resp.status_code} {resp.text[:200]}")
            delay = 2**attempt
            log.warning("HTTP %s, %ss 후 재시도 (%s/%s)", resp.status_code, delay, attempt + 1, attempts - 1)
            time.sleep(delay)
        raise AssertionError("unreachable")

    # ---------- MarketData ----------

    def get_bars(self, symbol: str, count: int) -> pd.DataFrame:
        # TODO(공식문서): 일봉 조회 파라미터와 응답 필드를 확인한 뒤
        # open/high/low/close/volume 컬럼, 시간순 DatetimeIndex의 DataFrame으로 변환
        raise NotImplementedError("토스 일봉 조회: 공식 문서 확인 후 구현 필요")

    def get_price(self, symbol: str) -> float:
        # TODO(공식문서)
        raise NotImplementedError("토스 현재가 조회: 공식 문서 확인 후 구현 필요")

    # ---------- Broker ----------

    def get_cash(self) -> float:
        # TODO(공식문서)
        raise NotImplementedError("토스 주문가능금액 조회: 공식 문서 확인 후 구현 필요")

    def get_positions(self) -> dict[str, Position]:
        # TODO(공식문서)
        raise NotImplementedError("토스 보유종목 조회: 공식 문서 확인 후 구현 필요")

    def place_order(self, order: OrderRequest) -> OrderResult:
        # TODO(공식문서): 주문 요청 형식 확인. 구현 시 반드시 _request(..., retry=False)로 호출할 것.
        # 네트워크 오류로 응답을 못 받았을 때 재전송하면 같은 주문이 두 번 나갈 수 있다.
        # 그런 경우에는 주문 목록을 조회해서 실제로 들어갔는지 확인해야 한다.
        raise NotImplementedError("토스 주문: 공식 문서 확인 후 구현 필요")
