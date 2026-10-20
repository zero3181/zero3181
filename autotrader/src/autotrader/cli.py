"""명령행 진입점.

    autotrader backtest --demo
    autotrader backtest --csv data/005930.csv --symbol 005930
    autotrader run --config config.toml            # 모의(paper) 모드
    autotrader run --config config.toml --live     # 실전: config의 mode="live"와 함께 둘 다 필요
"""

from __future__ import annotations

import argparse
import logging
import sys

import pandas as pd

from autotrader.backtest import CostModel, make_demo_bars, run_backtest
from autotrader.risk import RiskLimits, RiskManager
from autotrader.strategy import build_strategy


def _cmd_backtest(args: argparse.Namespace) -> int:
    if args.demo:
        bars = make_demo_bars()
        symbol = "DEMO"
        print("※ 랜덤으로 만든 가짜 데이터입니다. 결과에 의미를 두지 마세요.\n")
    elif args.csv:
        bars = pd.read_csv(args.csv, index_col=0, parse_dates=True)
        bars.columns = [c.lower() for c in bars.columns]
        symbol = args.symbol or "CSV"
    else:
        print("--demo 또는 --csv 중 하나가 필요합니다", file=sys.stderr)
        return 2

    strategy = build_strategy("ma_cross", {"short": args.short, "long": args.long})
    risk = RiskManager(RiskLimits(max_order_value=args.cash))
    result = run_backtest(symbol, bars, strategy, risk, initial_cash=args.cash, costs=CostModel())
    print(f"[{symbol}] {strategy.name}({args.short}/{args.long}), {bars.index[0].date()} ~ {bars.index[-1].date()}")
    print(result.summary())
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    from autotrader.broker import PaperBroker, TossClient, TossCredentials, TossEndpoints
    from autotrader.config import load_config, load_toss_secrets
    from autotrader.engine import TradingEngine

    cfg = load_config(args.config)

    # 실전 주문은 설정 파일과 명령행 플래그 두 곳에서 모두 켜야 한다 (실수 방지).
    live = cfg.mode == "live" and args.live
    if cfg.mode == "live" and not args.live:
        print("config는 live지만 --live 플래그가 없어 중단합니다.", file=sys.stderr)
        return 2
    if args.live and cfg.mode != "live":
        print("--live 플래그가 있지만 config의 trading.mode가 live가 아니라 중단합니다.", file=sys.stderr)
        return 2

    client_id, client_secret = load_toss_secrets()
    endpoints = TossEndpoints(base_url=cfg.toss_base_url) if cfg.toss_base_url else None
    toss = TossClient(TossCredentials(client_id, client_secret), cfg.account_id, endpoints)

    if live:
        broker = toss
        logging.warning("=== 실전 모드: 실제 주문이 나갑니다 ===")
    else:
        broker = PaperBroker(
            toss,
            cfg.paper_initial_cash,
            cfg.costs.fee_rate,
            cfg.costs.sell_tax_rate,
            cfg.costs.slippage_rate,
        )
        logging.info("모의(paper) 모드: 주문은 가상으로 체결됩니다")

    engine = TradingEngine(
        market_data=toss,
        broker=broker,
        strategy=build_strategy(cfg.strategy_name, cfg.strategy_params),
        risk=RiskManager(cfg.limits, cfg.kill_switch_path),
        symbols=cfg.symbols,
        market=cfg.market,
        journal_path=cfg.journal_path,
    )
    if args.once:
        engine.run_once()
    else:
        engine.run_forever(cfg.interval_sec)
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(prog="autotrader", description="룰 기반 자동매매 (토스증권 Open API)")
    sub = parser.add_subparsers(dest="command", required=True)

    bt = sub.add_parser("backtest", help="과거 데이터로 전략 검증")
    bt.add_argument("--demo", action="store_true", help="가짜 데이터로 실행")
    bt.add_argument("--csv", help="일봉 CSV (첫 열 날짜, open/high/low/close/volume)")
    bt.add_argument("--symbol")
    bt.add_argument("--short", type=int, default=5)
    bt.add_argument("--long", type=int, default=20)
    bt.add_argument("--cash", type=float, default=10_000_000)
    bt.set_defaults(func=_cmd_backtest)

    run = sub.add_parser("run", help="모의/실전 매매 루프 실행")
    run.add_argument("--config", default="config.toml")
    run.add_argument("--live", action="store_true", help="실전 주문 (config의 mode=live도 필요)")
    run.add_argument("--once", action="store_true", help="한 번만 실행하고 종료")
    run.set_defaults(func=_cmd_run)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
