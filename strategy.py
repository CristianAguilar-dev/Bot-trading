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
    ema_200: float
    volume_confirmed: bool
    timestamp: str

class EmaRsiStrategy:
    def __init__(self, fast_ema: int = 9, slow_ema: int = 21,
                 rsi_period: int = 14, rsi_buy_threshold: float = 50.0,
                 rsi_overbought: float = 70.0, rsi_oversold: float = 30.0,
                 use_ema200_filter: bool = True, use_volume_filter: bool = True):
        self.fast_ema = fast_ema
        self.slow_ema = slow_ema
        self.rsi_period = rsi_period
        self.rsi_buy_threshold = rsi_buy_threshold
        self.rsi_overbought = rsi_overbought
        self.rsi_oversold = rsi_oversold
        self.use_ema200_filter = use_ema200_filter
        self.use_volume_filter = use_volume_filter

    def analyze(self, df: pd.DataFrame, has_open_position: bool = False) -> TradeSignal:
        """
        Analiza velas con EMA 9/21, RSI 14, Filtro Macro EMA 200 y Volumen Institucional.
        """
        df_ind = add_indicators(df, self.fast_ema, self.slow_ema, self.rsi_period)
        latest = df_ind.iloc[-1]
        timestamp = str(latest.name if hasattr(latest, 'name') else 'N/A')
        
        price = float(latest['close'])
        rsi_val = float(latest['rsi'])
        fast_ema_val = float(latest['fast_ema'])
        slow_ema_val = float(latest['slow_ema'])
        ema_200_val = float(latest.get('ema_200', price))
        is_bull_cross = bool(latest['ema_cross_bullish'])
        is_bear_cross = bool(latest['ema_cross_bearish'])
        is_macro_bull = bool(latest.get('macro_bullish', True))
        is_vol_confirmed = bool(latest.get('vol_spike', True))

        # CONDICIÓN DE COMPRA (BUY)
        if not has_open_position:
            # 1. Filtro Macro EMA 200: Solo compras si el precio está sobre la EMA 200 (o rebote extremo de sobreventa)
            macro_ok = (not self.use_ema200_filter) or is_macro_bull or (rsi_val < self.rsi_oversold + 5)

            # 2. Cruce Alcista clásico con volumen y RSI
            if is_bull_cross and (rsi_val >= self.rsi_buy_threshold) and (rsi_val < self.rsi_overbought) and macro_ok:
                vol_text = " + Ballenas 🐳" if is_vol_confirmed else ""
                macro_text = " (Macro Alcista > EMA 200 🌊)" if is_macro_bull else ""
                return TradeSignal(
                    action='BUY',
                    price=price,
                    reason=f"Cruce Alcista EMA {self.fast_ema}/{self.slow_ema} + RSI {rsi_val:.1f}{macro_text}{vol_text}",
                    rsi=rsi_val,
                    fast_ema=fast_ema_val,
                    slow_ema=slow_ema_val,
                    ema_200=ema_200_val,
                    volume_confirmed=is_vol_confirmed,
                    timestamp=timestamp
                )

            # 3. Rebote desde Sobreventa extrema
            prev = df_ind.iloc[-2]
            if (prev['rsi'] <= self.rsi_oversold) and (rsi_val > self.rsi_oversold) and (fast_ema_val > slow_ema_val):
                return TradeSignal(
                    action='BUY',
                    price=price,
                    reason=f"Rebote desde Sobreventa (RSI de {prev['rsi']:.1f} a {rsi_val:.1f})",
                    rsi=rsi_val,
                    fast_ema=fast_ema_val,
                    slow_ema=slow_ema_val,
                    ema_200=ema_200_val,
                    volume_confirmed=is_vol_confirmed,
                    timestamp=timestamp
                )

        # CONDICIÓN DE VENTA (SELL)
        if has_open_position:
            if is_bear_cross:
                return TradeSignal(
                    action='SELL',
                    price=price,
                    reason=f"Cruce Bajista EMA ({self.fast_ema} < {self.slow_ema})",
                    rsi=rsi_val,
                    fast_ema=fast_ema_val,
                    slow_ema=slow_ema_val,
                    ema_200=ema_200_val,
                    volume_confirmed=is_vol_confirmed,
                    timestamp=timestamp
                )
            if rsi_val >= self.rsi_overbought:
                return TradeSignal(
                    action='SELL',
                    price=price,
                    reason=f"Agotamiento por Sobrecompra extrema (RSI {rsi_val:.1f} >= {self.rsi_overbought})",
                    rsi=rsi_val,
                    fast_ema=fast_ema_val,
                    slow_ema=slow_ema_val,
                    ema_200=ema_200_val,
                    volume_confirmed=is_vol_confirmed,
                    timestamp=timestamp
                )

        return TradeSignal(
            action='HOLD',
            price=price,
            reason=f"Esperando señal. EMA {self.fast_ema}/{self.slow_ema}: {fast_ema_val:.1f}/{slow_ema_val:.1f} | RSI: {rsi_val:.1f}",
            rsi=rsi_val,
            fast_ema=fast_ema_val,
            slow_ema=slow_ema_val,
            ema_200=ema_200_val,
            volume_confirmed=is_vol_confirmed,
            timestamp=timestamp
        )
