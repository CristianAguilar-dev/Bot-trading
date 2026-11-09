import os
from dataclasses import dataclass
from dotenv import load_dotenv

# Cargar variables del archivo .env si existe
load_dotenv()

@dataclass
class BotConfig:
    bot_mode: str = os.getenv("BOT_MODE", "live").lower()
    exchange_id: str = os.getenv("EXCHANGE_ID", "binance").lower()
    use_testnet: bool = os.getenv("USE_TESTNET", "false").lower() in ("true", "1", "yes")
    
    api_key: str = os.getenv("API_KEY", "UqIcLja2FrzfcpT8p8BlklOh0dBl2gWMc5mMOLW5VLOIgUWlOiSovHUIUCunskc7")
    api_secret: str = os.getenv("API_SECRET", "TZgNm2ybFOU8oCDSf95ew63dKG28TgINyz2lHvzIp0hQZ0AabDkhCr2Wp3OD9E7I")
    
    symbol: str = os.getenv("SYMBOL", "BTC/USDT")
    timeframe: str = os.getenv("TIMEFRAME", "1h")
    
    # Parámetros técnicos
    fast_ema: int = int(os.getenv("FAST_EMA", "9"))
    slow_ema: int = int(os.getenv("SLOW_EMA", "21"))
    rsi_period: int = int(os.getenv("RSI_PERIOD", "14"))
    rsi_buy_threshold: float = float(os.getenv("RSI_BUY_THRESHOLD", "50.0"))
    rsi_overbought: float = float(os.getenv("RSI_OVERBOUGHT", "70.0"))
    rsi_oversold: float = float(os.getenv("RSI_OVERSOLD", "30.0"))
    
    # Gestión de riesgo
    take_profit_pct: float = float(os.getenv("TAKE_PROFIT_PCT", "3.0"))
    stop_loss_pct: float = float(os.getenv("STOP_LOSS_PCT", "1.5"))
    trailing_stop: bool = os.getenv("TRAILING_STOP", "false").lower() in ("true", "1", "yes")
    max_position_pct: float = float(os.getenv("MAX_POSITION_PCT", "25.0"))
    
    # Simulación
    initial_balance: float = float(os.getenv("INITIAL_BALANCE", "1000.0"))
    
    # Notificaciones Telegram
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "9241639178:AAHPcbUfPkxhIsFwCjxe-ireM82NL8bjY2E")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "6902080959")

    def is_paper(self) -> bool:
        # Si tiene API Keys de Binance configuradas, opera siempre en VIVO con dinero real
        if self.api_key and self.api_secret and len(self.api_key) > 20:
            return False
        return self.bot_mode != "live"

    def has_telegram(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)
