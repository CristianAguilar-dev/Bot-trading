import ccxt
import pandas as pd
from typing import Dict, Any, Optional, List

class ExchangeClient:
    def __init__(self, exchange_id: str = "binance", api_key: str = "",
                 api_secret: str = "", use_testnet: bool = False,
                 paper_mode: bool = True, initial_balance: float = 1000.0):
        self.exchange_id = exchange_id.lower()
        self.api_key = api_key
        self.api_secret = api_secret
        self.use_testnet = use_testnet
        self.paper_mode = paper_mode
        
        # Estado de Paper Trading
        self.paper_balance = {
            'USDT': initial_balance,
            'crypto': 0.0
        }
        self.paper_history = []

        # Inicializar CCXT principal
        exchange_class = getattr(ccxt, self.exchange_id, None)
        if not exchange_class:
            exchange_class = ccxt.bybit
            self.exchange_id = "bybit"

        config = {
            'enableRateLimit': True,
            'timeout': 15000,
        }
        if not self.paper_mode and self.api_key and self.api_secret:
            config['apiKey'] = self.api_key
            config['secret'] = self.api_secret

        self.client = exchange_class(config)

        # En paper trading NUNCA activamos sandbox para evitar bloqueos por IP de Binance en servidores de la nube
        if not self.paper_mode and self.use_testnet and hasattr(self.client, 'set_sandbox_mode'):
            try:
                self.client.set_sandbox_mode(True)
            except Exception:
                pass

        # Clientes de respaldo automáticos (Kraken y Coinbase operan 100% legal en servidores de EE. UU. sin bloqueo)
        self.fallback_clients = []
        for fb_id in ['kraken', 'coinbase', 'bybit', 'kucoin']:
            if fb_id != self.exchange_id:
                try:
                    fb_class = getattr(ccxt, fb_id, None)
                    if fb_class:
                        self.fallback_clients.append(fb_class({'enableRateLimit': True, 'timeout': 10000}))
                except Exception:
                    pass

    def fetch_ohlcv(self, symbol: str, timeframe: str = "1h", limit: int = 100) -> pd.DataFrame:
        """Descarga velas japonesas recientes con tolerancia a fallos por geo-bloqueo."""
        raw_candles = None
        last_error = None

        # 1. Intentar con el exchange principal
        try:
            raw_candles = self.client.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        except Exception as e:
            last_error = e

        # 2. Si falló (ej. error 451 en servidores de EE. UU.), recurrir a los de respaldo
        if raw_candles is None:
            for fb in self.fallback_clients:
                try:
                    raw_candles = fb.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
                    if raw_candles:
                        break
                except Exception:
                    continue

        if raw_candles is None:
            raise RuntimeError(f"No se pudieron descargar velas para {symbol}: {last_error}")

        df = pd.DataFrame(raw_candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('datetime', inplace=True)
        return df

    def fetch_current_price(self, symbol: str) -> float:
        """Obtiene el último precio del par con tolerancia a fallos."""
        # 1. Intentar con el exchange principal
        try:
            ticker = self.client.fetch_ticker(symbol)
            price = ticker.get('last') or ticker.get('close')
            if price:
                return float(price)
        except Exception:
            pass

        # 2. Respaldo automático
        for fb in self.fallback_clients:
            try:
                ticker = fb.fetch_ticker(symbol)
                price = ticker.get('last') or ticker.get('close')
                if price:
                    return float(price)
            except Exception:
                continue

        raise RuntimeError(f"No se pudo obtener precio para {symbol}")

    def get_balances(self, base_currency: str = "BTC", quote_currency: str = "USDT") -> Dict[str, float]:
        """Obtiene el saldo disponible."""
        if self.paper_mode:
            return {
                quote_currency: self.paper_balance.get(quote_currency, 0.0),
                base_currency: self.paper_balance.get('crypto', 0.0)
            }
        else:
            balance = self.client.fetch_balance()
            return {
                quote_currency: float(balance.get(quote_currency, {}).get('free', 0.0)),
                base_currency: float(balance.get(base_currency, {}).get('free', 0.0))
            }

    def create_market_buy_order(self, symbol: str, amount: float, current_price: float) -> Dict[str, Any]:
        """Ejecuta una orden de compra a mercado (en simulación o real)."""
        if self.paper_mode:
            fee_pct = 0.001
            cost = amount * current_price
            fee = cost * fee_pct
            total_needed = cost + fee

            if self.paper_balance['USDT'] < total_needed:
                amount = (self.paper_balance['USDT'] * 0.999) / current_price
                cost = amount * current_price
                fee = cost * fee_pct
                total_needed = cost + fee

            self.paper_balance['USDT'] -= total_needed
            self.paper_balance['crypto'] += amount
            
            order = {
                'id': f"paper_{len(self.paper_history) + 1}",
                'symbol': symbol,
                'side': 'buy',
                'price': current_price,
                'amount': amount,
                'cost': cost,
                'fee': fee,
                'status': 'closed'
            }
            self.paper_history.append(order)
            return order
        else:
            return self.client.create_market_buy_order(symbol, amount)

    def create_market_sell_order(self, symbol: str, amount: float, current_price: float) -> Dict[str, Any]:
        """Ejecuta una orden de venta a mercado (en simulación o real)."""
        if self.paper_mode:
            fee_pct = 0.001
            revenue = amount * current_price
            fee = revenue * fee_pct
            net_revenue = revenue - fee

            self.paper_balance['USDT'] += net_revenue
            self.paper_balance['crypto'] = max(0.0, self.paper_balance['crypto'] - amount)

            order = {
                'id': f"paper_{len(self.paper_history) + 1}",
                'symbol': symbol,
                'side': 'sell',
                'price': current_price,
                'amount': amount,
                'cost': revenue,
                'fee': fee,
                'status': 'closed'
            }
            self.paper_history.append(order)
            return order
        else:
            return self.client.create_market_sell_order(symbol, amount)
