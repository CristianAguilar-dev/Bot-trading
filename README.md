# 🤖 Cripto Trading Bot (EMA Cross + RSI Filter)

Bot algorítmico y modular de trading de criptomonedas desarrollado en Python utilizando la librería estándar de la industria **CCXT**. Permite operar en múltiples exchanges (Binance, Bybit, KuCoin, OKX, etc.) tanto en modo de **Simulación en Tiempo Real (Paper Trading)**, **Backtesting histórico**, como en **Modo Real / Testnet**.

---

## 🚀 Características Principales

1. **Estrategia EMA Cross + RSI Filter**:
   - **Señal de Compra**: Cruce alcista de Media Móvil Rápida (EMA 9) sobre la Lenta (EMA 21), confirmado con un RSI saludable (> 50 y < 70) o rebotes desde sobreventa (RSI < 30).
   - **Señal de Venta**: Cruce bajista de EMA o llegada a zona extrema de sobrecompra (RSI >= 70).
2. **Gestión de Riesgo Avanzada**:
   - **Stop-Loss** automático parametrizable (por defecto 1.5%).
   - **Take-Profit** automático parametrizable (por defecto 3.0%).
   - **Trailing-Stop** dinámico opcional (protege ganancias a medida que el precio sube).
   - Tamaño de orden según porcentaje de balance disponible (por defecto 25% por operación).
3. **Modos de Operación**:
   - **Paper Trading (Por defecto)**: Simula operaciones en tiempo real con datos en vivo del exchange sin arriesgar capital ni requerir claves API.
   - **Backtesting**: Analiza el rendimiento histórico de cualquier par (BTC/USDT, ETH/USDT, SOL/USDT, etc.) en cualquier marco temporal (15m, 1h, 4h), mostrando Win Rate, PnL, Profit Factor y Drawdown.
   - **Live / Testnet**: Operaciones reales conectadas a través de API Keys.
4. **Alertas por Telegram**: Notificaciones instantáneas en tu móvil ante cada orden de compra, venta, TP o SL ejecutado.

---

## 📁 Estructura del Proyecto

```
crypto_trading_bot/
├── config.py             # Configuración central y lectura de .env
├── indicators.py         # Cálculo de EMA, RSI, ATR y Bandas de Bollinger
├── strategy.py           # Reglas lógicas de entrada y salida
├── risk_manager.py       # Control de Stop-Loss, Take-Profit y Trailing Stop
├── exchange_client.py    # Integración con CCXT (Binance, Bybit) y simulador
├── backtester.py         # Motor de simulación y métricas históricas
├── notifier.py           # Sistema de logs coloridos y alertas por Telegram
├── main.py               # Menú interactivo y ejecución por CLI
├── iniciar_bot.bat       # Lanzador rápido de un clic para Windows
├── .env                  # Archivo de configuración activa
├── .env.example          # Plantilla de variables de entorno
└── requirements.txt      # Dependencias necesarias
```

---

## ⚡ Inicio Rápido

### 1. Iniciar con el menú interactivo
Puedes hacer doble clic en `iniciar_bot.bat` o ejecutar en tu consola:
```powershell
python crypto_trading_bot/main.py
```

El menú te permitirá:
1. Iniciar el bot en vivo en modo simulación (Paper Trading).
2. Ejecutar un Backtest histórico de cualquier par.
3. Probar la conexión y consultar el precio en tiempo real.
4. Cambiar el par o temporalidad.

### 2. Ejecutar comandos directos por consola

**Para simular en tiempo real (Paper Trading con Bitcoin a 15m):**
```powershell
python crypto_trading_bot/main.py --mode paper --symbol BTC/USDT --timeframe 15m
```

**Para hacer Backtesting de los últimos 500 periodos de Ethereum a 1 hora:**
```powershell
python crypto_trading_bot/main.py --mode backtest --symbol ETH/USDT --timeframe 1h --candles 500
```

---

## ⚙️ Personalización de Parámetros (`.env`)

Puedes editar el archivo `.env` para ajustar los indicadores y la gestión de riesgo a tu gusto:

```ini
# Configuración básica
BOT_MODE=paper               # paper o live
EXCHANGE_ID=binance          # binance, bybit, kucoin, etc.
SYMBOL=BTC/USDT
TIMEFRAME=1h

# Estrategia técnica
FAST_EMA=9
SLOW_EMA=21
RSI_PERIOD=14
RSI_BUY_THRESHOLD=50.0
RSI_OVERBOUGHT=70.0
RSI_OVERSOLD=30.0

# Gestión de riesgo
TAKE_PROFIT_PCT=3.0          # Ganancia objetivo (%)
STOP_LOSS_PCT=1.5            # Pérdida máxima tolerada (%)
TRAILING_STOP=false          # true para activar trailing stop
MAX_POSITION_PCT=25.0        # Porcentaje del saldo por operación

# Notificaciones Telegram (opcional)
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```
