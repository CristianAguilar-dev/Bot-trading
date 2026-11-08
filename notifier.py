import sys
import requests
from colorama import Fore, Style, init

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

init(autoreset=True)

class Notifier:
    def __init__(self, bot_token: str = "", chat_id: str = ""):
        self.bot_token = bot_token.strip()
        self.chat_id = chat_id.strip()
        self.enabled = bool(self.bot_token and self.chat_id)

    def log(self, message: str, level: str = "INFO"):
        """Imprime en consola con formato y color."""
        color = Fore.WHITE
        if level == "BUY":
            color = Fore.GREEN
            prefix = "[COMPRA]"
        elif level == "SELL":
            color = Fore.YELLOW
            prefix = "[VENTA]"
        elif level == "ALERT":
            color = Fore.MAGENTA
            prefix = "[ALERTA]"
        elif level == "ERROR":
            color = Fore.RED
            prefix = "[ERROR]"
        elif level == "SUCCESS":
            color = Fore.CYAN
            prefix = "[OK]"
        else:
            prefix = "[INFO]"

        print(f"{color}{prefix} {message}{Style.RESET_ALL}")

    def send_telegram(self, message: str):
        """Envia un mensaje a Telegram si las credenciales estan configuradas."""
        if not self.enabled:
            return

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "Markdown"
        }
        try:
            requests.post(url, json=payload, timeout=5)
        except Exception as e:
            print(f"{Fore.RED}[Telegram Error] No se pudo enviar el mensaje: {e}{Style.RESET_ALL}")

    def notify_trade(self, action: str, symbol: str, price: float, amount: float,
                     reason: str, pnl_pct: float = None):
        """Notifica tanto a consola como a Telegram."""
        if action == "BUY":
            cost = price * amount
            console_msg = f"{symbol} @ ${price:,.2f} | Cantidad: {amount:.6f} (${cost:.2f}) | Motivo: {reason}"
            self.log(console_msg, level="BUY")
            
            tg_msg = (
                f"🟢 *ORDEN DE COMPRA EJECUTADA*\n"
                f"• *Par:* `{symbol}`\n"
                f"• *Precio:* `${price:,.2f}`\n"
                f"• *Cantidad:* `{amount:.6f}`\n"
                f"• *Total:* `${cost:.2f}`\n"
                f"• *Motivo:* {reason}"
            )
            self.send_telegram(tg_msg)

        elif action == "SELL":
            revenue = price * amount
            pnl_str = f" | PnL: {pnl_pct:+.2f}%" if pnl_pct is not None else ""
            console_msg = f"{symbol} @ ${price:,.2f} | Cantidad: {amount:.6f} (${revenue:.2f}){pnl_str} | Motivo: {reason}"
            self.log(console_msg, level="SELL")
            
            pnl_tg = f"\n• *PnL:* `{pnl_pct:+.2f}%`" if pnl_pct is not None else ""
            tg_msg = (
                f"🔴 *ORDEN DE VENTA EJECUTADA*\n"
                f"• *Par:* `{symbol}`\n"
                f"• *Precio:* `${price:,.2f}`\n"
                f"• *Total recibido:* `${revenue:.2f}`{pnl_tg}\n"
                f"• *Motivo:* {reason}"
            )
            self.send_telegram(tg_msg)
