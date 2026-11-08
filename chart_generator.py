import io
import matplotlib
matplotlib.use('Agg')  # Modo sin pantalla para servidores y nube
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
from indicators import add_indicators

def generate_candlestick_chart(df: pd.DataFrame, symbol: str, timeframe: str,
                              fast_ema: int = 9, slow_ema: int = 21, rsi_period: int = 14) -> io.BytesIO:
    """
    Genera un grafico profesional con tema oscuro:
    - Panel superior: Velas japonesas + EMAs
    - Panel inferior: Oscilador RSI con bandas 30 y 70
    Retorna un buffer en memoria (BytesIO) listo para enviar por Telegram.
    """
    df_ind = add_indicators(df, fast_ema, slow_ema, rsi_period)
    # Tomar las ultimas 40 velas para que se vea claro en celulares
    df_plot = df_ind.tail(40).copy()

    plt.style.use('dark_background')
    fig, (ax_main, ax_rsi) = plt.subplots(
        2, 1, figsize=(10, 7),
        gridspec_kw={'height_ratios': [3, 1]},
        dpi=120
    )
    fig.patch.set_facecolor('#0f172a')
    ax_main.set_facecolor('#1e293b')
    ax_rsi.set_facecolor('#1e293b')

    # 1. Dibujar velas japonesas
    width = 0.6
    width2 = 0.1
    indices = range(len(df_plot))
    
    up = df_plot[df_plot.close >= df_plot.open]
    down = df_plot[df_plot.close < df_plot.open]
    
    col_up = '#10b981'    # Verde brillante
    col_down = '#ef4444'  # Rojo brillante

    # Velas alcistas
    ax_main.bar(up.index, up.close - up.open, width, bottom=up.open, color=col_up, alpha=0.9)
    ax_main.bar(up.index, up.high - up.close, width2, bottom=up.close, color=col_up)
    ax_main.bar(up.index, up.low - up.open, width2, bottom=up.open, color=col_up)

    # Velas bajistas
    ax_main.bar(down.index, down.close - down.open, width, bottom=down.open, color=col_down, alpha=0.9)
    ax_main.bar(down.index, down.high - down.open, width2, bottom=down.open, color=col_down)
    ax_main.bar(down.index, down.low - down.close, width2, bottom=down.close, color=col_down)

    # 2. Medias Moviles
    ax_main.plot(df_plot.index, df_plot['fast_ema'], color='#38bdf8', linewidth=1.8, label=f'EMA {fast_ema} (Rápida)')
    ax_main.plot(df_plot.index, df_plot['slow_ema'], color='#f59e0b', linewidth=1.8, label=f'EMA {slow_ema} (Lenta)')
    if 'ema_200' in df_plot.columns:
        ax_main.plot(df_plot.index, df_plot['ema_200'], color='#a855f7', linewidth=1.5, linestyle=':', label='EMA 200 (Macro)')

    last_price = df_plot['close'].iloc[-1]
    ax_main.set_title(f"{symbol} ({timeframe}) | Último Precio: ${last_price:,.2f}", fontsize=13, fontweight='bold', color='#f8fafc', pad=10)
    ax_main.legend(loc='upper left', facecolor='#0f172a', edgecolor='#334155', fontsize=9)
    ax_main.grid(True, linestyle='--', alpha=0.2, color='#94a3b8')
    ax_main.yaxis.tick_right()

    # 3. Oscilador RSI
    ax_rsi.plot(df_plot.index, df_plot['rsi'], color='#c084fc', linewidth=1.6, label=f'RSI ({rsi_period})')
    ax_rsi.axhline(70, color='#ef4444', linestyle='--', linewidth=1, alpha=0.7)
    ax_rsi.axhline(30, color='#10b981', linestyle='--', linewidth=1, alpha=0.7)
    ax_rsi.fill_between(df_plot.index, 30, 70, color='#6366f1', alpha=0.1)
    
    latest_rsi = df_plot['rsi'].iloc[-1]
    ax_rsi.set_ylim(10, 90)
    ax_rsi.set_ylabel('RSI', color='#cbd5e1', fontsize=9)
    ax_rsi.legend(loc='upper left', facecolor='#0f172a', edgecolor='#334155', fontsize=8)
    ax_rsi.grid(True, linestyle='--', alpha=0.2, color='#94a3b8')
    ax_rsi.yaxis.tick_right()

    # Formatear eje de fechas
    ax_main.xaxis.set_major_formatter(mdates.DateFormatter('%d %b %H:%M'))
    fig.autofmt_xdate()

    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', facecolor=fig.get_facecolor(), dpi=120)
    buf.seek(0)
    plt.close(fig)
    return buf
