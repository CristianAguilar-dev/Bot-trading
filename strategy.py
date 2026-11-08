from dataclasses import dataclass
from typing import Optional
import pandas as pd
from indicators import add_indicators

@dataclass
class TradeSignal:
    action: str              # 'BUY', 'SELL', 'HOLD'
    price: float
    reason: str
    rsi: float
    fast_ema: float
    slow_ema: float
    timestamp: str

class EmaRsiStrategy:
    def __init__(self, fast_ema: int = 9, slow_ema: int = 21,
                 rsi_period: int = 14, rsi_buy_threshold: float = 50.0,
                 rsi_overbought: float = 70.0, rsi_oversold: float = 30.0):
        self.fast_ema = fast_ema
        self.slow_ema = slow_ema
        self.rsi_period = rsi_period
        self.rsi_buy_threshold = rsi_buy_threshold
        self.rsi_overbought = rsi_overbought
        self.rsi_oversold = rsi_oversold

    def analyze(self, df: pd.DataFrame, has_open_position: bool = False) -> TradeSignal:
        """
        Analiza las velas mas recientes y genera una senal BUY, SELL o HOLD.
        """
        df_ind = add_indicators(df, self.fast_ema, self.slow_ema, self.rsi_period)
        latest = df_ind.iloc[-1]
        timestamp = str(latest.name if hasattr(latest, 'name') else 'N/A')
        
        price = float(latest['close'])
        rsi_val = float(latest['rsi'])
        fast_ema_val = float(latest['fast_ema'])
        slow_ema_val = float(latest['slow_ema'])
        is_bull_cross = bool(latest['ema_cross_bullish'])
        is_bear_cross = bool(latest['ema_cross_bearish'])

        # Condicion de COMPRA:
        # Cruce alcista EMA + RSI confirma fuerza alcista (> buy_threshold) y no sobrecomprado (< overbought)
        if not has_open_position:
            if is_bull_cross and (rsi_val >= self.rsi_buy_threshold) and (rsi_val < self.rsi_overbought):
                return TradeSignal(
                    action='BUY',
                    price=price,
                    reason=f"Cruce Alcista EMA ({self.fast_ema} > {self.slow_ema}) + RSI saludable ({rsi_val:.1f})",
                    rsi=rsi_val,
                    fast_ema=fast_ema_val,
                    slow_ema=slow_ema_val,
                    timestamp=timestamp
                )
            # Rebote desde sobreventa con tendencia alcista
            prev = df_ind.iloc[-2]
            if (prev['rsi'] <= self.rsi_oversold) and (rsi_val > self.rsi_oversold) and (fast_ema_val > slow_ema_val):
                return TradeSignal(
                    action='BUY',
                    price=price,
                    reason=f"Rebote desde Sobreventa (RSI salio de {prev['rsi']:.1f} a {rsi_val:.1f}) con EMA favorable",
                    rsi=rsi_val,
                    fast_ema=fast_ema_val,
                    slow_ema=slow_ema_val,
                    timestamp=timestamp
                )

        # Condicion de VENTA (si tenemos posicion abierta):
        if has_open_position:
            if is_bear_cross:
                return TradeSignal(
                    action='SELL',
                    price=price,
                    reason=f"Cruce Bajista EMA ({self.fast_ema} < {self.slow_ema})",
                    rsi=rsi_val,
                    fast_ema=fast_ema_val,
                    slow_ema=slow_ema_val,
                    timestamp=timestamp
                )
            if rsi_val >= self.rsi_overbought:
                return TradeSignal(
                    action='SELL',
                    price=price,
                    reason=f"Zona de Sobrecompra extrema (RSI {rsi_val:.1f} >= {self.rsi_overbought})",
                    rsi=rsi_val,
                    fast_ema=fast_ema_val,
                    slow_ema=slow_ema_val,
                    timestamp=timestamp
                )

        return TradeSignal(
            action='HOLD',
            price=price,
            reason=f"Sin senal fuerte. EMA {self.fast_ema}: {fast_ema_val:.2f}, EMA {self.slow_ema}: {slow_ema_val:.2f}, RSI: {rsi_val:.1f}",
            rsi=rsi_val,
            fast_ema=fast_ema_val,
            slow_ema=slow_ema_val,
            timestamp=timestamp
        )
