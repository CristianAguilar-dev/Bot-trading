import pandas as pd
import numpy as np

def calculate_ema(series: pd.Series, period: int) -> pd.Series:
    """Calcula la Media Movil Exponencial (EMA)."""
    return series.ewm(span=period, adjust=False).mean()

def calculate_sma(series: pd.Series, period: int) -> pd.Series:
    """Calcula la Media Movil Simple (SMA)."""
    return series.rolling(window=period, min_periods=1).mean()

def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Calcula el Relative Strength Index (RSI)."""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    
    avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi.fillna(50.0)

def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calcula el Average True Range (ATR)."""
    high = df['high']
    low = df['low']
    close = df['close']
    prev_close = close.shift(1)
    
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.ewm(alpha=1/period, min_periods=period, adjust=False).mean()

def add_indicators(df: pd.DataFrame, fast_ema: int = 9, slow_ema: int = 21, rsi_period: int = 14) -> pd.DataFrame:
    """Anade indicadores tecnicos y filtros de volumen y macro tendencia (EMA 200)."""
    df = df.copy()
    close = df['close']
    
    df['fast_ema'] = calculate_ema(close, fast_ema)
    df['slow_ema'] = calculate_ema(close, slow_ema)
    df['ema_200'] = calculate_ema(close, min(200, max(50, len(df))))
    df['rsi'] = calculate_rsi(close, rsi_period)
    df['atr'] = calculate_atr(df, 14)
    
    # Filtro de volumen institucional
    if 'volume' in df.columns:
        df['vol_ma'] = calculate_sma(df['volume'], 20)
        df['vol_spike'] = df['volume'] >= (df['vol_ma'] * 1.2)
    else:
        df['vol_spike'] = True

    # Cruces de EMA
    df['ema_cross_bullish'] = (df['fast_ema'] > df['slow_ema']) & (df['fast_ema'].shift(1) <= df['slow_ema'].shift(1))
    df['ema_cross_bearish'] = (df['fast_ema'] < df['slow_ema']) & (df['fast_ema'].shift(1) >= df['slow_ema'].shift(1))
    
    # Filtro macro tendencia (precio sobre EMA 200)
    df['macro_bullish'] = df['close'] >= df['ema_200']
    
    return df
