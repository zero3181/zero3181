from autotrader.strategy.base import Strategy
from autotrader.strategy.ma_cross import MovingAverageCross

STRATEGIES: dict[str, type[Strategy]] = {
    MovingAverageCross.name: MovingAverageCross,
}


def build_strategy(name: str, params: dict | None = None) -> Strategy:
    try:
        cls = STRATEGIES[name]
    except KeyError:
        raise ValueError(f"알 수 없는 전략: {name} (가능: {list(STRATEGIES)})") from None
    return cls(**(params or {}))


__all__ = ["Strategy", "MovingAverageCross", "STRATEGIES", "build_strategy"]
