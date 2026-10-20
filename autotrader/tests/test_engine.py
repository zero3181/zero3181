import json
from datetime import datetime
from zoneinfo import ZoneInfo

from autotrader.broker.paper import PaperBroker
from autotrader.engine import TradingEngine, is_market_open
from autotrader.models import Market, OrderRequest, Side
from autotrader.risk import RiskLimits, RiskManager
from autotrader.strategy import MovingAverageCross

from conftest import FakeMarketData, bars_from_closes


def test_paper_broker_buy_sell_with_costs():
    md = FakeMarketData({"A": bars_from_closes([1000])})
    b = PaperBroker(md, 100_000, fee_rate=0.01, sell_tax_rate=0.01)
    assert b.place_order(OrderRequest("A", Side.BUY, 10)).status == "FILLED"
    assert b.get_cash() == 100_000 - 10_100
    assert b.get_positions()["A"].quantity == 10
    b.place_order(OrderRequest("A", Side.SELL, 10))
    assert b.get_positions() == {}
    assert b.get_cash() == 100_000 - 10_100 + 9_800


def test_paper_broker_rejects_oversell_and_overspend():
    md = FakeMarketData({"A": bars_from_closes([1000])})
    b = PaperBroker(md, 5_000)
    assert b.place_order(OrderRequest("A", Side.BUY, 10)).status == "REJECTED"
    assert b.place_order(OrderRequest("A", Side.SELL, 1)).status == "REJECTED"


def test_engine_run_once_buys_and_journals(tmp_path):
    md = FakeMarketData({"A": bars_from_closes([10, 9, 8, 7, 6, 5, 20])})
    broker = PaperBroker(md, 1_000)
    engine = TradingEngine(
        md, broker, MovingAverageCross(2, 5),
        RiskManager(RiskLimits(max_order_value=500)),
        ["A"], Market.KR, tmp_path / "j.jsonl",
    )
    engine.run_once()
    assert broker.get_positions()["A"].quantity == 25  # 500 / 20
    kinds = [json.loads(l)["kind"] for l in (tmp_path / "j.jsonl").read_text().splitlines()]
    assert kinds == ["decision", "order"]

    # 같은 상태로 다시 돌려도 중복 매수하지 않는다
    engine.run_once()
    assert broker.get_positions()["A"].quantity == 25


def test_engine_survives_symbol_error(tmp_path):
    md = FakeMarketData({"A": bars_from_closes([10, 9, 8, 7, 6, 5, 20])})
    broker = PaperBroker(md, 1_000)
    engine = TradingEngine(
        md, broker, MovingAverageCross(2, 5),
        RiskManager(RiskLimits(max_order_value=500)),
        ["MISSING", "A"], Market.KR, tmp_path / "j.jsonl",
    )
    engine.run_once()  # MISSING에서 KeyError가 나도 A는 처리된다
    assert "A" in broker.get_positions()


def test_market_hours_kr():
    kst = ZoneInfo("Asia/Seoul")
    assert is_market_open(Market.KR, datetime(2026, 10, 20, 10, 0, tzinfo=kst))   # 화요일
    assert not is_market_open(Market.KR, datetime(2026, 10, 20, 15, 30, tzinfo=kst))
    assert not is_market_open(Market.KR, datetime(2026, 10, 18, 10, 0, tzinfo=kst))  # 일요일
