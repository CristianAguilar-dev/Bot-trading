from typing import List, Dict, Any
from strategy import EmaRsiStrategy

DEFAULT_SCAN_SYMBOLS = [
    'BTC/USDT',
    'ETH/USDT',
    'SOL/USDT',
    'BNB/USDT',
    'DOGE/USDT',
    'XRP/USDT',
    'ADA/USDT',
    'AVAX/USDT'
]

def scan_multiple_cryptos(exchange_client, symbols: List[str] = None, timeframe: str = "1h",
                          strategy: EmaRsiStrategy = None) -> List[Dict[str, Any]]:
    """
    Escanea múltiples criptomonedas simultáneamente y detecta oportunidades de compra o venta.
    """
    syms = symbols or DEFAULT_SCAN_SYMBOLS
    strat = strategy or EmaRsiStrategy()
    results = []

    for sym in syms:
        try:
            df = exchange_client.fetch_ohlcv(sym, timeframe=timeframe, limit=40)
            price = exchange_client.fetch_current_price(sym)
            signal = strat.analyze(df, has_open_position=False)

            results.append({
                "symbol": sym,
                "price": price,
                "action": signal.action,
                "rsi": signal.rsi,
                "fast_ema": signal.fast_ema,
                "slow_ema": signal.slow_ema,
                "reason": signal.reason
            })
        except Exception:
            pass

    # Ordenar: primero las que tienen señal de compra (BUY), luego venta (SELL), luego HOLD
    def sort_key(item):
        if item["action"] == "BUY":
            return 0
        elif item["action"] == "SELL":
            return 1
        return 2

    results.sort(key=sort_key)
    return results
