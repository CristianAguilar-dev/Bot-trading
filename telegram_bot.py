import sys
import time
import json
import os
import threading
import http.server
import socketserver
from datetime import datetime
from typing import Dict, Any, Optional
import requests
from colorama import Fore, Style, init

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

init(autoreset=True)

from config import BotConfig
from indicators import add_indicators
from strategy import EmaRsiStrategy
from risk_manager import RiskManager, Position
from exchange_client import ExchangeClient
from backtester import Backtester
from chart_generator import generate_candlestick_chart
from market_sentiment import get_fear_and_greed_index
from scanner import scan_multiple_cryptos

STATE_FILE = os.path.join(os.path.dirname(__file__), "trading_state.json")
DEBUG_LOGS = []

def log_debug(msg: str):
    entry = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(f"[DEBUG] {entry}")
    DEBUG_LOGS.append(entry)
    if len(DEBUG_LOGS) > 40:
        DEBUG_LOGS.pop(0)

class CloudServerHandler(http.server.BaseHTTPRequestHandler):
    """Servidor HTTP de alto rendimiento: sirve la Academia Web, atiende pings 24/7 y procesa Webhooks de Telegram."""
    bot_instance: Optional['TelegramTradingBot'] = None

    def do_GET(self):
        # 1. Endpoint de ping / health check para monitoreo 24/7 sin suspensiones
        if self.path in ("/ping", "/health", "/status-check"):
            self.send_response(200)
            self.send_header("Content-type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            is_active = self.bot_instance.is_trading_active if self.bot_instance else False
            resp_data = {
                "status": "online",
                "service": "crypto_trading_bot_24_7",
                "trading_active": is_active,
                "timestamp": datetime.now().isoformat()
            }
            self.wfile.write(json.dumps(resp_data).encode("utf-8"))
            return

        # 1.1 Endpoint de depuración en vivo para verificar recepción de eventos en la nube
        if self.path in ("/debug", "/logs", "/status-details"):
            self.send_response(200)
            self.send_header("Content-type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            info = {
                "server_time": datetime.now().isoformat(),
                "trading_active": self.bot_instance.is_trading_active if self.bot_instance else False,
                "symbol": self.bot_instance.config.symbol if self.bot_instance else "None",
                "exchange": self.bot_instance.config.exchange_id if self.bot_instance else "None",
                "chat_ids": list(self.bot_instance.authorized_chat_ids) if self.bot_instance else [],
                "recent_logs": DEBUG_LOGS[-25:]
            }
            self.wfile.write(json.dumps(info, indent=2).encode("utf-8"))
            return

        # 2. Servir la Academia de Trading Web
        html_path = os.path.join(os.path.dirname(__file__), "index.html")
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        if os.path.exists(html_path):
            with open(html_path, "r", encoding="utf-8") as f:
                content = f.read()
            self.wfile.write(content.encode("utf-8"))
        else:
            html = (
                "<!DOCTYPE html><html><head><meta charset='utf-8'><title>Trading Bot 24/7</title></head>"
                "<body style='font-family:sans-serif; text-align:center; padding-top:50px; background:#0f172a; color:#f8fafc;'>"
                "<h1>🟢 Bot de Trading Pro Operando 24/7 en la Nube</h1>"
                "<p>Academia Web, Gráficos, Escáner Radar, DCA y Sentimiento activos.</p>"
                "</body></html>"
            )
            self.wfile.write(html.encode("utf-8"))

    def do_POST(self):
        # 3. Endpoint de Webhook para Telegram (hace que cada mensaje de Telegram opere directamente en Render)
        if self.path.startswith("/webhook") or self.path.startswith("/telegram-webhook"):
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length)

                # Responder inmediatamente a Telegram 200 OK para evitar reintentos o timeouts
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"ok": true}')

                if self.bot_instance and body:
                    update_data = json.loads(body.decode("utf-8"))
                    up_id = update_data.get("update_id", "N/A")
                    log_debug(f"Webhook update id={up_id} recibido")
                    # Despachar procesamiento en un hilo independiente para velocidad máxima
                    threading.Thread(target=self.bot_instance.process_update, args=(update_data,), daemon=True).start()
            except Exception as e:
                log_debug(f"Webhook Error: {e}")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass

def start_self_ping_loop():
    """Bucle autónomo de auto-despertador interno: envía un ping HTTP público al propio servidor cada 4 minutos para evitar suspensión para siempre."""
    def pinger():
        time.sleep(25) # Esperar a que el servidor Web arranque
        cloud_url = os.environ.get("RENDER_EXTERNAL_URL") or os.environ.get("WEBHOOK_URL") or "https://bot-trading-593w.onrender.com"
        target_ping = f"{cloud_url.rstrip('/')}/ping"
        print(f"[KEEP-ALIVE 24/7] Auto-pinger interno activo hacia: {target_ping}")
        while True:
            try:
                r = requests.get(target_ping, timeout=12)
                log_debug(f"Auto-ping interno OK ({r.status_code})")
            except Exception as e:
                log_debug(f"Auto-ping interno fallo temporal: {e}")
            time.sleep(240) # Cada 4 minutos exactos (Render duerme a los 15 min, así que nunca entra en reposo)

    threading.Thread(target=pinger, daemon=True).start()

def start_health_server(bot: 'TelegramTradingBot'):
    """Inicia el servidor HTTP / Webhook en segundo plano."""
    CloudServerHandler.bot_instance = bot
    port = int(os.environ.get("PORT", "8080"))

    def run_server():
        try:
            socketserver.TCPServer.allow_reuse_address = True
            with socketserver.TCPServer(("", port), CloudServerHandler) as httpd:
                print(f"[NUBE] Servidor Web y Webhook activo en puerto {port}")
                httpd.serve_forever()
        except Exception as e:
            print(f"[NUBE Servidor] Error iniciando puerto {port}: {e}")

    threading.Thread(target=run_server, daemon=True).start()
    start_self_ping_loop()

class TelegramTradingBot:
    def __init__(self, token: str):
        self.token = token.strip()
        self.base_url = f"https://api.telegram.org/bot{self.token}"
        self.config = BotConfig()
        
        self.authorized_chat_ids = set()
        self.is_trading_active = False
        self.trade_thread: Optional[threading.Thread] = None
        self.digest_thread: Optional[threading.Thread] = None
        self.stop_signal = threading.Event()
        
        self.client = ExchangeClient(
            exchange_id=self.config.exchange_id,
            api_key=self.config.api_key,
            api_secret=self.config.api_secret,
            use_testnet=self.config.use_testnet,
            paper_mode=self.config.is_paper(),
            initial_balance=self.config.initial_balance
        )
        self.risk_mgr = RiskManager(
            stop_loss_pct=self.config.stop_loss_pct,
            take_profit_pct=self.config.take_profit_pct,
            trailing_stop=self.config.trailing_stop,
            max_position_pct=self.config.max_position_pct,
            dca_enabled=False
        )
        self.strategy = EmaRsiStrategy(
            fast_ema=self.config.fast_ema,
            slow_ema=self.config.slow_ema,
            rsi_period=self.config.rsi_period,
            rsi_buy_threshold=self.config.rsi_buy_threshold,
            rsi_overbought=self.config.rsi_overbought,
            rsi_oversold=self.config.rsi_oversold
        )
        
        self.load_state()
        self._start_daily_digest_scheduler()

    def load_state(self):
        """Carga el estado previo guardado."""
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.authorized_chat_ids = set(data.get("authorized_chat_ids", []))
                    if "paper_balance" in data and self.config.is_paper():
                        self.client.paper_balance = data["paper_balance"]
                    if "paper_history" in data:
                        self.client.paper_history = data["paper_history"]
                    if "dca_enabled" in data:
                        self.risk_mgr.dca_enabled = bool(data["dca_enabled"])
                    if data.get("active_position"):
                        p = data["active_position"]
                        self.risk_mgr.active_position = Position(
                            symbol=p["symbol"],
                            entry_price=p["entry_price"],
                            amount=p["amount"],
                            cost=p["cost"],
                            take_profit_price=p["take_profit_price"],
                            stop_loss_price=p["stop_loss_price"],
                            highest_price=p["highest_price"],
                            trailing_stop=p["trailing_stop"],
                            trailing_pct=p["trailing_pct"],
                            opened_at=p["opened_at"],
                            dca_count=p.get("dca_count", 1),
                            dca_enabled=p.get("dca_enabled", False),
                            break_even_hit=p.get("break_even_hit", False),
                            tp1_price=p.get("tp1_price", p["entry_price"] * 1.02),
                            tp2_price=p.get("tp2_price", p["entry_price"] * 1.06),
                            tp1_hit=p.get("tp1_hit", False)
                        )
                    if "cooldown_until" in data:
                        self.risk_mgr.cooldown_until = float(data["cooldown_until"])
                    if data.get("is_trading_active"):
                        self.is_trading_active = True
                        self.stop_signal.clear()
                        self.trade_thread = threading.Thread(target=self._trading_loop, daemon=True)
                        self.trade_thread.start()
                        print(f"{Fore.GREEN}[TRADING 24/7] Reanudado automáticamente en la nube.{Style.RESET_ALL}")
                    print(f"{Fore.GREEN}[OK] Estado anterior cargado correctamente.{Style.RESET_ALL}")
            except Exception as e:
                print(f"{Fore.RED}[WARN] No se pudo leer estado: {e}{Style.RESET_ALL}")

    def save_state(self):
        """Guarda el estado actual en disco."""
        try:
            pos_dict = None
            if self.risk_mgr.active_position:
                p = self.risk_mgr.active_position
                pos_dict = {
                    "symbol": p.symbol,
                    "entry_price": p.entry_price,
                    "amount": p.amount,
                    "cost": p.cost,
                    "take_profit_price": p.take_profit_price,
                    "stop_loss_price": p.stop_loss_price,
                    "highest_price": p.highest_price,
                    "trailing_stop": p.trailing_stop,
                    "trailing_pct": p.trailing_pct,
                    "opened_at": p.opened_at,
                    "dca_count": p.dca_count,
                    "dca_enabled": p.dca_enabled,
                    "break_even_hit": p.break_even_hit,
                    "tp1_price": p.tp1_price,
                    "tp2_price": p.tp2_price,
                    "tp1_hit": p.tp1_hit
                }

            data = {
                "authorized_chat_ids": list(self.authorized_chat_ids),
                "paper_balance": self.client.paper_balance,
                "paper_history": self.client.paper_history,
                "dca_enabled": self.risk_mgr.dca_enabled,
                "cooldown_until": self.risk_mgr.cooldown_until,
                "is_trading_active": self.is_trading_active,
                "active_position": pos_dict
            }
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"{Fore.RED}[WARN] Error guardando estado: {e}{Style.RESET_ALL}")

    # ==================== COMUNICACIÓN TELEGRAM ====================

    def send_message(self, chat_id: int, text: str, reply_markup: Optional[Dict] = None):
        url = f"{self.base_url}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        try:
            resp = requests.post(url, json=payload, timeout=10)
            if resp.status_code != 200:
                log_debug(f"SendMessage error code={resp.status_code}: {resp.text}")
                # Si falló (ej. error 400 por sintaxis Markdown), reenviar en texto plano
                payload.pop("parse_mode", None)
                resp2 = requests.post(url, json=payload, timeout=10)
                log_debug(f"SendMessage retry plaintext status={resp2.status_code}")
            else:
                log_debug(f"SendMessage OK chat={chat_id}")
        except Exception as e:
            log_debug(f"SendMessage Exception: {e}")

    def send_photo(self, chat_id: int, photo_bytes, caption: str = "", reply_markup: Optional[Dict] = None):
        """Envía una imagen (gráfico) directamente al chat de Telegram."""
        url = f"{self.base_url}/sendPhoto"
        files = {"photo": ("chart.png", photo_bytes, "image/png")}
        data = {"chat_id": chat_id, "caption": caption, "parse_mode": "Markdown"}
        if reply_markup:
            data["reply_markup"] = json.dumps(reply_markup)
        try:
            resp = requests.post(url, files=files, data=data, timeout=15)
            if resp.status_code != 200:
                log_debug(f"SendPhoto error code={resp.status_code}: {resp.text}")
                data.pop("parse_mode", None)
                photo_bytes.seek(0)
                files = {"photo": ("chart.png", photo_bytes, "image/png")}
                resp2 = requests.post(url, files=files, data=data, timeout=15)
                log_debug(f"SendPhoto retry status={resp2.status_code}")
            else:
                log_debug(f"SendPhoto OK chat={chat_id}")
        except Exception as e:
            log_debug(f"SendPhoto Exception: {e}")

    def answer_callback_query(self, callback_query_id: str, text: str = ""):
        url = f"{self.base_url}/answerCallbackQuery"
        try:
            requests.post(url, json={"callback_query_id": callback_query_id, "text": text}, timeout=5)
        except Exception:
            pass

    def broadcast(self, text: str):
        for cid in self.authorized_chat_ids:
            self.send_message(cid, text)

    # ==================== TECLADOS MÓVILES ====================

    def get_main_keyboard(self) -> Dict:
        """Teclado táctil completo con todas las nuevas mejoras."""
        return {
            "keyboard": [
                [{"text": "📊 Mi Saldo & Estado"}, {"text": "📈 Precio & Señal"}],
                [{"text": "📸 Ver Gráfico en Foto"}, {"text": "🦅 Escáner Radar"}],
                [{"text": "🚀 Iniciar Trading"}, {"text": "⏹️ Pausar Trading"}],
                [{"text": "🧠 Miedo & Codicia"}, {"text": "☀️ Resumen Diario"}],
                [{"text": "📜 Historial"}, {"text": "🔄 Reiniciar Bot"}],
                [{"text": "⚙️ Ajustes"}, {"text": "🎓 Academia Web"}]
            ],
            "resize_keyboard": True,
            "is_persistent": True
        }

    # ==================== CONTROLADORES DE ACCIÓN ====================

    def handle_start(self, chat_id: int, user_first_name: str):
        self.authorized_chat_ids.add(chat_id)
        self.save_state()
        
        status_text = "🟢 ACTIVO" if self.is_trading_active else "⏸️ PAUSADO"
        dca_badge = "Activado ✅" if self.risk_mgr.dca_enabled else "Desactivado ⚪"
        welcome_text = (
            f"👋 ¡Hola, *{user_first_name}*!\n\n"
            f"Bienvenido a tu *Bot de Cripto Trading Pro*.\n\n"
            f"🌟 *Funciones Profesionales Activas:*\n"
            f"• 📊 *Estrategia:* `EMA 9/21 + RSI Filter`\n"
            f"• 📸 *Gráficos en Foto:* Velas japonesas en directo.\n"
            f"• 🦅 *Escáner Radar:* Rastrea las 8 mejores monedas.\n"
            f"• 🧠 *Sentimiento:* Índice oficial Fear & Greed.\n"
            f"• 🎯 *Modo DCA:* {dca_badge}\n"
            f"• ☀️ *Reporte:* Resumen diario matutino automático.\n\n"
            f"📌 *Configuración:* `{self.config.symbol}` ({self.config.timeframe}) | {status_text}\n\n"
            f"👇 *Toca los botones táctiles abajo para operar:*"
        )
        self.send_message(chat_id, welcome_text, reply_markup=self.get_main_keyboard())

    def handle_status(self, chat_id: int):
        base_curr, quote_curr = self.config.symbol.split('/')
        try:
            price = self.client.fetch_current_price(self.config.symbol)
            balances = self.client.get_balances(base_curr, quote_curr)
            quote_bal = balances[quote_curr]
            crypto_bal = balances[base_curr]
        except Exception as e:
            self.send_message(chat_id, f"❌ Error al consultar exchange: `{e}`")
            return

        status_icon = "🟢 ACTIVO (Operando)" if self.is_trading_active else "⏸️ PAUSADO"
        dca_badge = "✅ Activado" if self.risk_mgr.dca_enabled else "⚪ Desactivado"

        in_cool, rem_mins = self.risk_mgr.is_in_cooldown()
        cool_text = f"\n• *Pausa Inteligente:* 🧘 Activa ({rem_mins} min restantes)" if in_cool else ""

        msg = [
            f"📊 *ESTADO GENERAL DEL BOT*",
            f"━━━━━━━━━━━━━━━━━━",
            f"• *Estado:* `{status_icon}`",
            f"• *Par Activo:* `{self.config.symbol}`",
            f"• *Precio:* `${price:,.2f} USD`",
            f"• *Saldo USDT:* `${quote_bal:,.2f}`",
            f"• *Saldo Crypto:* `{crypto_bal:.6f} {base_curr}`",
            f"• *Estrategia DCA:* {dca_badge}{cool_text}",
            f"━━━━━━━━━━━━━━━━━━"
        ]

        inline_buttons = []
        if self.risk_mgr.active_position:
            pos = self.risk_mgr.active_position
            pnl_pct = ((price - pos.entry_price) / pos.entry_price) * 100.0
            pnl_val = (price - pos.entry_price) * pos.amount
            emoji_pnl = "🟢 +" if pnl_pct >= 0 else "🔴 "
            dca_info = f" (Compras DCA: {pos.dca_count})" if pos.dca_count > 1 else ""
            be_status = "✅ Activo (Riesgo Cero)" if pos.break_even_hit else "Pendiente (+1.2%)"
            tp1_status = "✅ 50% Cobrado" if pos.tp1_hit else f"${pos.tp1_price:,.2f} (+2.0%)"

            msg.extend([
                f"🎯 *POSICIÓN ABIERTA ACTIVA{dca_info}:*",
                f"• *Precio Entrada:* `${pos.entry_price:,.2f}`",
                f"• *PnL en Vivo:* {emoji_pnl}*{pnl_val:+.2f} USD ({pnl_pct:+.2f}%)*",
                f"• *Break-Even:* `{be_status}`",
                f"• *TP1 (50%):* `{tp1_status}`",
                f"• *TP2 Final:* `${pos.tp2_price:,.2f} (+6.0%)`",
                f"• *Stop-Loss:* `${pos.stop_loss_price:,.2f}`",
                f"• *Abierta el:* `{pos.opened_at}`"
            ])
            inline_buttons.append([{"text": "⚡ Cerrar Posición Ahora", "callback_data": "force_sell"}])
        else:
            msg.append("💤 *Sin posición abierta.* Escaneando el mercado...")

        inline_buttons.append([
            {"text": "🔄 Actualizar", "callback_data": "refresh_status"},
            {"text": "📸 Ver Gráfico", "callback_data": "get_chart"}
        ])
        reply_markup = {"inline_keyboard": inline_buttons}
        self.send_message(chat_id, "\n".join(msg), reply_markup=reply_markup)

    def handle_chart(self, chat_id: int):
        """Genera y envía el gráfico de velas y EMAs como una foto."""
        self.send_message(chat_id, f"🎨 Generando gráfico profesional de *{self.config.symbol}* ({self.config.timeframe})...")
        try:
            df = self.client.fetch_ohlcv(self.config.symbol, timeframe=self.config.timeframe, limit=50)
            img_buf = generate_candlestick_chart(
                df, self.config.symbol, self.config.timeframe,
                self.config.fast_ema, self.config.slow_ema, self.config.rsi_period
            )
            caption = (
                f"📊 *Gráfico en Vivo: {self.config.symbol} ({self.config.timeframe})*\n"
                f"• Azul: EMA {self.config.fast_ema} | Naranja: EMA {self.config.slow_ema}\n"
                f"• Púrpura: RSI ({self.config.rsi_period})"
            )
            self.send_photo(chat_id, img_buf, caption=caption)
        except Exception as e:
            self.send_message(chat_id, f"❌ Error generando gráfico: `{e}`")

    def handle_scanner(self, chat_id: int):
        """Escanea las mejores 8 criptomonedas y muestra las mejores señales."""
        self.send_message(chat_id, "🦅 *Escáner Radar activado...* Analizando el TOP de criptomonedas en tiempo real...")
        try:
            results = scan_multiple_cryptos(self.client, timeframe=self.config.timeframe, strategy=self.strategy)
            
            lines = [
                f"🦅 *RADAR DE OPORTUNIDADES ({self.config.timeframe})*",
                f"━━━━━━━━━━━━━━━━━━"
            ]

            buy_buttons = []
            for r in results:
                icon = "🟢 COMPRA" if r["action"] == "BUY" else ("🔴 VENTA" if r["action"] == "SELL" else "⚪ NEUTRAL")
                lines.append(
                    f"*{r['symbol']}* | `${r['price']:,.2f}`\n"
                    f"• Señal: *{icon}* (RSI: `{r['rsi']:.1f}`)\n"
                    f"• {r['reason'][:45]}...\n"
                )
                if r["action"] == "BUY":
                    buy_buttons.append([{"text": f"🎯 Cambiar y Operar {r['symbol']}", "callback_data": f"set_pair_{r['symbol']}"}])

            lines.append("━━━━━━━━━━━━━━━━━━")
            lines.append("💡 *Tip:* Las monedas con 🟢 COMPRA tienen cruce favorable de medias.")

            reply_markup = {"inline_keyboard": buy_buttons} if buy_buttons else None
            self.send_message(chat_id, "\n".join(lines), reply_markup=reply_markup)
        except Exception as e:
            self.send_message(chat_id, f"❌ Error en escáner: `{e}`")

    def handle_sentiment(self, chat_id: int):
        """Muestra el índice Fear & Greed oficial del mercado."""
        fng = get_fear_and_greed_index()
        val = fng["value"]
        
        # Barra visual
        filled = int(val / 10)
        bar = "🟩" * filled + "⬜" * (10 - filled)

        msg = (
            f"🧠 *ÍNDICE DE MIEDO Y CODICIA (FEAR & GREED)*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"• *Puntuación:* `{val} / 100`\n"
            f"• *Nivel:* {bar}\n"
            f"• *Diagnóstico:* *{fng['status']}*\n\n"
            f"📌 *Estrategia del Bot:* \n{fng['advice']}\n"
            f"━━━━━━━━━━━━━━━━━━"
        )
        self.send_message(chat_id, msg)

    def handle_daily_digest(self, chat_id: int):
        """Genera el reporte matutino / diario."""
        history = self.client.paper_history
        total_trades = len(history)
        
        wins = 0
        losses = 0
        total_pnl = 0.0

        for t in history:
            if "pnl" in t:
                p = t["pnl"]
                total_pnl += p
                if p > 0:
                    wins += 1
                else:
                    losses += 1

        base_curr, quote_curr = self.config.symbol.split('/')
        balances = self.client.get_balances(base_curr, quote_curr)
        quote_bal = balances[quote_curr]

        pnl_emoji = "🟢 +" if total_pnl >= 0 else "🔴 "
        msg = (
            f"☀️ *REPORTE DIARIO DE RENDIMIENTO*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"• *Saldo Actual:* `${quote_bal:,.2f} USDT`\n"
            f"• *Total Operaciones:* `{total_trades}`\n"
            f"• *Victorias:* `{wins}` | *Derrotas:* `{losses}`\n"
            f"• *Ganancia Neta Acumulada:* {pnl_emoji}*${total_pnl:+.2f} USD*\n"
            f"• *Estado del Robot:* `{'🟢 Operando' if self.is_trading_active else '⏸️ Pausado'}`\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"¡Que tengas un excelente día de trading! 🚀"
        )
        self.send_message(chat_id, msg)

    def handle_toggle_dca(self, chat_id: int):
        """Activa o desactiva las compras escalonadas (DCA)."""
        self.risk_mgr.dca_enabled = not self.risk_mgr.dca_enabled
        self.save_state()
        state_str = "ACTIVADO ✅" if self.risk_mgr.dca_enabled else "DESACTIVADO ⚪"
        expl = (
            "Ahora el bot dividirá la inversión y hará una recompra más abajo si el precio cae, para promediar a la baja y ganar en el rebote."
            if self.risk_mgr.dca_enabled else
            "Ahora el bot operará con entrada simple y Stop-Loss estricto estándar."
        )
        self.send_message(chat_id, f"🎯 *Modo DCA {state_str}*\n\n{expl}", reply_markup=self.get_main_keyboard())

    def handle_price_and_signal(self, chat_id: int):
        self.send_message(chat_id, f"⏳ Analizando mercado en vivo para `{self.config.symbol}`...")
        try:
            df = self.client.fetch_ohlcv(self.config.symbol, timeframe=self.config.timeframe, limit=220)
            price = self.client.fetch_current_price(self.config.symbol)
            has_pos = self.risk_mgr.active_position is not None
            signal = self.strategy.analyze(df, has_open_position=has_pos)
            
            signal_emoji = "🟢 COMPRA" if signal.action == "BUY" else ("🔴 VENTA" if signal.action == "SELL" else "⚪ ESPERAR (HOLD)")
            macro_emoji = "🌊 Alcista (> EMA 200)" if price >= signal.ema_200 else "🐻 Bajista (< EMA 200)"
            vol_emoji = "🐳 Confirmado (Inyección institucional)" if signal.volume_confirmed else "⚪ Normal"
            
            msg = (
                f"📈 *ANÁLISIS TÉCNICO EN VIVO*\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"• *Par:* `{self.config.symbol}`\n"
                f"• *Precio:* `${price:,.2f} USD`\n"
                f"• *EMA {self.config.fast_ema} (Rápida):* `${signal.fast_ema:,.2f}`\n"
                f"• *EMA {self.config.slow_ema} (Lenta):* `${signal.slow_ema:,.2f}`\n"
                f"• *EMA 200 (Macro):* `${signal.ema_200:,.2f}` ({macro_emoji})\n"
                f"• *RSI (14):* `{signal.rsi:.1f}` / 100\n"
                f"• *Volumen Ballenas:* {vol_emoji}\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"• *Diagnóstico:* *{signal_emoji}*\n"
                f"• *Detalle:* {signal.reason}"
            )
            markup = {"inline_keyboard": [[{"text": "📸 Ver en Gráfico con Foto", "callback_data": "get_chart"}]]}
            self.send_message(chat_id, msg, reply_markup=markup)
        except Exception as e:
            self.send_message(chat_id, f"❌ Error: `{e}`")

    def handle_start_trading(self, chat_id: int):
        if self.is_trading_active:
            self.send_message(chat_id, "⚠️ El bot *ya se encuentra activo y operando*.")
            return

        self.is_trading_active = True
        self.stop_signal.clear()
        self.trade_thread = threading.Thread(target=self._trading_loop, daemon=True)
        self.trade_thread.start()
        
        self.send_message(
            chat_id,
            f"🚀 *¡TRADING AUTOMÁTICO INICIADO!*\n\n"
            f"Monitoreando `{self.config.symbol}` cada 15 segundos con DCA={self.risk_mgr.dca_enabled}.\n"
            f"Recibirás alertas con sonido en tu móvil cuando compre o venda.",
            reply_markup=self.get_main_keyboard()
        )

    def handle_pause_trading(self, chat_id: int):
        if not self.is_trading_active:
            self.send_message(chat_id, "ℹ️ El bot ya está pausado.")
            return

        self.is_trading_active = False
        self.stop_signal.set()
        self.send_message(chat_id, "⏸️ *Bot Pausado.* Se detuvo la apertura de nuevas operaciones automáticas.")

    def handle_history(self, chat_id: int):
        history = self.client.paper_history
        if not history:
            self.send_message(chat_id, "📜 *Aún no hay operaciones registradas.*")
            return

        msg = ["📜 *HISTORIAL DE OPERACIONES RECIENTES:*", "━━━━━━━━━━━━━━━━━━"]
        for o in history[-6:]:
            side_icon = "🟢 COMPRA" if o['side'] == 'buy' else "🔴 VENTA"
            pnl_tag = f" | PnL: `{o['pnl']:+.2f}`" if "pnl" in o else ""
            msg.append(f"{side_icon} | `{o['amount']:.5f}` @ `${o['price']:,.2f}`{pnl_tag}")
        
        msg.append("━━━━━━━━━━━━━━━━━━")
        self.send_message(chat_id, "\n".join(msg))

    def handle_settings(self, chat_id: int):
        dca_text = "🎯 Desactivar DCA" if self.risk_mgr.dca_enabled else "🎯 Activar DCA (Recompras)"
        markup = {
            "inline_keyboard": [
                [
                    {"text": "🪙 Bitcoin", "callback_data": "set_pair_BTC/USDT"},
                    {"text": "🪙 Ethereum", "callback_data": "set_pair_ETH/USDT"},
                    {"text": "🪙 Solana", "callback_data": "set_pair_SOL/USDT"}
                ],
                [
                    {"text": "⏱️ Velas 15m", "callback_data": "set_tf_15m"},
                    {"text": "⏱️ Velas 1h", "callback_data": "set_tf_1h"},
                    {"text": "⏱️ Velas 4h", "callback_data": "set_tf_4h"}
                ],
                [
                    {"text": dca_text, "callback_data": "toggle_dca"}
                ],
                [
                    {"text": "🔄 Reiniciar Bot", "callback_data": "do_restart"},
                    {"text": "♻️ Restablecer Saldo", "callback_data": "reset_balance"}
                ]
            ]
        }
        text = (
            f"⚙️ *PANEL DE AJUSTES*\n\n"
            f"• *Par activo:* `{self.config.symbol}`\n"
            f"• *Temporalidad:* `{self.config.timeframe}`\n"
            f"• *Estrategia DCA:* `{'ACTIVADA' if self.risk_mgr.dca_enabled else 'DESACTIVADA'}`\n"
            f"• *Take-Profit:* `{self.config.take_profit_pct}%`\n"
            f"• *Stop-Loss:* `{self.config.stop_loss_pct}%`\n\n"
            f"👇 *Toca un botón para cambiar opciones:*"
        )
        self.send_message(chat_id, text, reply_markup=markup)

    def handle_restart(self, chat_id: int):
        """Reinicia los subsistemas del bot, recarga la configuración y verifica conexiones."""
        self.send_message(chat_id, "⏳ *Reiniciando subsistemas del bot...* Por favor espera unos segundos.")
        was_active = self.is_trading_active
        if was_active:
            self.is_trading_active = False
            self.stop_signal.set()
            time.sleep(1)

        try:
            from dotenv import load_dotenv
            load_dotenv(override=True)
            self.config = BotConfig()

            self.client = ExchangeClient(
                exchange_id=self.config.exchange_id,
                api_key=self.config.api_key,
                api_secret=self.config.api_secret,
                use_testnet=self.config.use_testnet,
                paper_mode=self.config.is_paper(),
                initial_balance=self.config.initial_balance
            )
            self.strategy = EmaRsiStrategy(
                fast_ema=self.config.fast_ema,
                slow_ema=self.config.slow_ema,
                rsi_period=self.config.rsi_period,
                rsi_buy_threshold=self.config.rsi_buy_threshold,
                rsi_overbought=self.config.rsi_overbought,
                rsi_oversold=self.config.rsi_oversold
            )
            self.load_state()

            # Probar conexion con Binance
            price = self.client.fetch_current_price(self.config.symbol)

            # Reanudar trading si estaba activo
            if was_active:
                self.is_trading_active = True
                self.stop_signal.clear()
                self.trade_thread = threading.Thread(target=self._trading_loop, daemon=True)
                self.trade_thread.start()

            status_str = "🟢 ACTIVO (Operando)" if was_active else "⏸️ PAUSADO"
            msg = (
                f"🔄 *¡BOT REINICIADO CON ÉXITO!*\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"• *Exchange:* `{self.config.exchange_id.upper()}` (🟢 Conectado)\n"
                f"• *Par Activo:* `{self.config.symbol}` (${price:,.2f})\n"
                f"• *Estrategia:* `EMA {self.config.fast_ema}/{self.config.slow_ema} + RSI`\n"
                f"• *Estado Operativo:* `{status_str}`\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"Todos los subsistemas se recargaron desde cero sin desconectar el servidor."
            )
            markup = {"inline_keyboard": [[{"text": "♻️ Restablecer Saldo a $1,000 USDT", "callback_data": "reset_balance"}]]}
            self.send_message(chat_id, msg, reply_markup=markup)
        except Exception as e:
            self.send_message(chat_id, f"❌ Error durante el reinicio: `{e}`")

    def handle_reset_balance(self, chat_id: int):
        """Restablece el saldo virtual y limpia el historial."""
        self.client.paper_balance = {'USDT': self.config.initial_balance, 'crypto': 0.0}
        self.client.paper_history = []
        self.risk_mgr.active_position = None
        self.save_state()
        self.send_message(
            chat_id,
            f"♻️ *CARTERA RESTABLECIDA*\n\n"
            f"• *Saldo Virtual:* `${self.config.initial_balance:,.2f} USDT`\n"
            f"• *Posiciones:* Ninguna\n"
            f"• *Historial:* Limpio y listo para empezar de cero.",
            reply_markup=self.get_main_keyboard()
        )

    def handle_academia(self, chat_id: int):
        """Envía el enlace a la Academia Web interactiva."""
        url = os.environ.get("RENDER_EXTERNAL_URL", "https://bot-trading-593w.onrender.com")
        msg = (
            f"🎓 *ACADEMIA DE TRADING & ESTRATEGIAS PRO*\n\n"
            f"Hemos preparado una *plataforma web completa e interactiva* para aprender a operar con este bot como un profesional:\n\n"
            f"• 📚 *6 Módulos de Formación:* De principiante a cuantitativo.\n"
            f"• 🧠 *El Cerebro Algorítmico:* EMA 9/21, RSI 14 y EMA 200.\n"
            f"• 🛡️ *Matemáticas del Ratio 1:2:* Ganar a largo plazo.\n"
            f"• 🧮 *Simulador Cuantitativo:* Interés compuesto y proyección.\n"
            f"• 🏆 *Examen y Certificación:* Insignia de Trader Oficial.\n"
            f"• 📖 *Glosario A-Z:* Diccionario financiero completo.\n\n"
            f"🌐 *Toca el botón abajo para abrir la academia en tu celular:*"
        )
        markup = {"inline_keyboard": [[{"text": "🌐 Abrir Academia de Trading 🚀", "url": url}]]}
        self.send_message(chat_id, msg, reply_markup=markup)

    def handle_force_sell(self, chat_id: int):
        if not self.risk_mgr.active_position:
            self.send_message(chat_id, "ℹ️ No hay ninguna posición abierta.")
            return

        try:
            pos = self.risk_mgr.active_position
            price = self.client.fetch_current_price(pos.symbol)
            pnl_pct = ((price - pos.entry_price) / pos.entry_price) * 100.0
            order = self.client.create_market_sell_order(pos.symbol, pos.amount, price)
            order["pnl"] = (price - pos.entry_price) * pos.amount
            self.risk_mgr.close_position()
            self.save_state()
            
            pnl_emoji = "🟢 +" if pnl_pct >= 0 else "🔴 "
            self.send_message(
                chat_id,
                f"⚡ *VENTA MANUAL EJECUTADA*\n\n"
                f"• *Par:* `{pos.symbol}`\n"
                f"• *Precio:* `${price:,.2f}`\n"
                f"• *PnL:* {pnl_emoji}{pnl_pct:+.2f}%\n"
                f"• *Motivo:* Orden manual desde el celular."
            )
        except Exception as e:
            self.send_message(chat_id, f"❌ Error ejecutando venta: `{e}`")

    # ==================== SCHEDULER REPORTE DIARIO ====================

    def _start_daily_digest_scheduler(self):
        """Hilo para enviar el reporte cada 24 horas."""
        def digest_loop():
            while True:
                time.sleep(86400) # 24 horas
                for cid in self.authorized_chat_ids:
                    self.handle_daily_digest(cid)

        self.digest_thread = threading.Thread(target=digest_loop, daemon=True)
        self.digest_thread.start()

    # ==================== CICLO DE TRADING AUTOMÁTICO ====================

    def _trading_loop(self):
        base_curr, quote_curr = self.config.symbol.split('/')
        print(f"{Fore.GREEN}[TRADING] Ciclo continuo iniciado para {self.config.symbol}.{Style.RESET_ALL}")

        while not self.stop_signal.is_set():
            try:
                current_price = self.client.fetch_current_price(self.config.symbol)
                balances = self.client.get_balances(base_curr, quote_curr)
                quote_balance = balances[quote_curr]

                # 1. Evaluar eventos de posición activa (Break-Even, TP1 parcial 50%, TP2 final, SL)
                has_position = self.risk_mgr.active_position is not None
                if has_position:
                    event = self.risk_mgr.check_position_events(current_price)
                    if event:
                        pos = self.risk_mgr.active_position
                        ev_type = event["event"]
                        pnl_pct = event["pnl_pct"]

                        # A) Evento BREAK-EVEN (Riesgo Cero activado al +1.2%)
                        if ev_type == "BREAK_EVEN":
                            self.save_state()
                            self.broadcast(
                                f"🛡️ *¡OPERACIÓN A RIESGO CERO (BREAK-EVEN)!*\n\n"
                                f"• *Par:* `{self.config.symbol}`\n"
                                f"• *Precio Actual:* `${current_price:,.2f}` (+{pnl_pct:.2f}%)\n"
                                f"• *Nuevo Stop-Loss:* `${pos.stop_loss_price:,.2f}` (Precio Entrada)\n\n"
                                f"🎉 *¡Esta operación ya no puede perder dinero! Solo ganar o empatar.*"
                            )

                        # B) Evento TP1 Parcial (+2.0% - Venta del 50% asegurada)
                        elif ev_type == "TP1_PARTIAL":
                            sell_amt = event["sell_amount"]
                            order = self.client.create_market_sell_order(self.config.symbol, sell_amt, current_price)
                            order["pnl"] = (current_price - pos.entry_price) * sell_amt
                            self.save_state()
                            self.broadcast(
                                f"💰 *¡TAKE-PROFIT 1 ALCANZADO (+{pnl_pct:.2f}%)!*\n\n"
                                f"• *Par:* `{self.config.symbol}`\n"
                                f"• *Ganancia:* ¡El 50% de la posición fue vendido y asegurado en balance!\n"
                                f"• *Cantidad restante:* `{pos.amount:.6f}`\n"
                                f"• *Objetivo TP2:* `${pos.tp2_price:,.2f} (+6.0%)` con Stop-Loss en Break-Even."
                            )

                        # C) Salida Completa (TP2 final o Stop-Loss)
                        elif ev_type == "FULL_EXIT":
                            sell_amt = event["sell_amount"]
                            order = self.client.create_market_sell_order(self.config.symbol, sell_amt, current_price)
                            order["pnl"] = (current_price - pos.entry_price) * sell_amt
                            reason = event["reason"]
                            self.risk_mgr.close_position()
                            self.save_state()

                            emoji = "🎉 ¡OPERACIÓN CERRADA CON GANANCIA!" if pnl_pct > 0 else "🛡️ SALIDA DE PROTECCIÓN"
                            self.broadcast(
                                f"{emoji}\n\n"
                                f"• *Par:* `{self.config.symbol}`\n"
                                f"• *Precio Salida:* `${current_price:,.2f}`\n"
                                f"• *Resultado Final:* *{pnl_pct:+.2f}%*\n"
                                f"• *Motivo:* {reason}"
                            )
                            has_position = False

                    # 1.1 Si DCA está activo, verificar si amerita recompra escalonada
                    elif self.risk_mgr.dca_enabled:
                        should_dca, dca_amt = self.risk_mgr.check_dca_opportunity(current_price, quote_balance)
                        if should_dca:
                            self.client.create_market_buy_order(self.config.symbol, dca_amt, current_price)
                            self.risk_mgr.apply_dca_buy(dca_amt, current_price)
                            self.save_state()
                            pos = self.risk_mgr.active_position
                            self.broadcast(
                                f"🎯 *RECOMPRA ESCALONADA (DCA) EJECUTADA*\n\n"
                                f"• *Par:* `{self.config.symbol}`\n"
                                f"• *Precio Recompra:* `${current_price:,.2f}`\n"
                                f"• *Nuevo Precio Promedio:* `${pos.entry_price:,.2f}`\n"
                                f"• *Cantidad Total:* `{pos.amount:.6f}`\n"
                                f"• *Nuevo Take-Profit:* `${pos.take_profit_price:,.2f}`"
                            )

                # 2. Descargar velas con límite suficiente para calcular EMA 200 y volumen
                df = self.client.fetch_ohlcv(self.config.symbol, timeframe=self.config.timeframe, limit=220)
                signal = self.strategy.analyze(df, has_open_position=has_position)

                # 3. Comprobar pausa inteligente anti-revancha antes de comprar
                in_cool, rem_mins = self.risk_mgr.is_in_cooldown()

                # 4. Ejecutar compra si hay señal
                if signal.action == "BUY" and not has_position:
                    if in_cool:
                        pass # En pausa inteligente tras pérdida previa
                    else:
                        amount = self.risk_mgr.calculate_order_amount(quote_balance, current_price)
                        if amount * current_price >= 10.0:
                            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            self.client.create_market_buy_order(self.config.symbol, amount, current_price)
                            self.risk_mgr.open_position(self.config.symbol, current_price, amount, now_str)
                            self.save_state()

                            dca_text = " (Tramo inicial con DCA)" if self.risk_mgr.dca_enabled else ""
                            self.broadcast(
                                f"🟢 *¡NUEVA COMPRA AUTOMÁTICA!*{dca_text}\n\n"
                                f"• *Par:* `{self.config.symbol}`\n"
                                f"• *Precio:* `${current_price:,.2f}`\n"
                                f"• *Cantidad:* `{amount:.6f}`\n"
                                f"• *Inversión:* `${(amount * current_price):,.2f} USD`\n"
                                f"• *Señal:* {signal.reason}\n\n"
                                f"💰 *TP1 (50%):* `${(current_price * 1.02):,.2f} (+2.0%)`\n"
                                f"🚀 *TP2 (50%):* `${(current_price * 1.06):,.2f} (+6.0%)`\n"
                                f"🛡️ *Break-Even:* Se activa al +1.2%\n"
                                f"🛡️ *Stop-Loss:* `${(current_price * 0.985):,.2f} (-1.5%)`"
                            )

                elif signal.action == "SELL" and has_position:
                    pos = self.risk_mgr.active_position
                    pnl_pct = ((current_price - pos.entry_price) / pos.entry_price) * 100.0
                    order = self.client.create_market_sell_order(self.config.symbol, pos.amount, current_price)
                    order["pnl"] = (current_price - pos.entry_price) * pos.amount
                    self.risk_mgr.close_position()
                    self.save_state()

                    self.broadcast(
                        f"🔴 *VENTA POR ESTRATEGIA (EMA/RSI)*\n\n"
                        f"• *Par:* `{self.config.symbol}`\n"
                        f"• *Precio:* `${current_price:,.2f}`\n"
                        f"• *Resultado:* `{pnl_pct:+.2f}%`\n"
                        f"• *Motivo:* {signal.reason}"
                    )

            except Exception as e:
                print(f"{Fore.RED}[WARN Loop] {e}{Style.RESET_ALL}")

            self.stop_signal.wait(timeout=15)

    # ==================== RECEPCIÓN DE MENSAJES (LONG POLLING) ====================

    def process_update(self, update: Dict[str, Any]):
        try:
            if "callback_query" in update:
                cq = update["callback_query"]
                cid = cq["message"]["chat"]["id"]
                data = cq.get("data", "")
                self.answer_callback_query(cq["id"], "Procesando...")

                if data == "refresh_status":
                    self.handle_status(cid)
                elif data == "get_chart":
                    self.handle_chart(cid)
                elif data == "force_sell":
                    self.handle_force_sell(cid)
                elif data == "toggle_dca":
                    self.handle_toggle_dca(cid)
                elif data == "do_restart":
                    self.handle_restart(cid)
                elif data == "reset_balance":
                    self.handle_reset_balance(cid)
                elif data.startswith("set_pair_"):
                    self.config.symbol = data.replace("set_pair_", "")
                    self.send_message(cid, f"✅ Par actualizado a *{self.config.symbol}*")
                elif data.startswith("set_tf_"):
                    self.config.timeframe = data.replace("set_tf_", "")
                    self.send_message(cid, f"✅ Temporalidad actualizada a *{self.config.timeframe}*")
                return

            if "message" in update and "text" in update["message"]:
                msg = update["message"]
                cid = msg["chat"]["id"]
                text = msg["text"].strip()
                first_name = msg.get("from", {}).get("first_name", "Amigo")
                log_debug(f"Comando recibido de {first_name} ({cid}): {text}")

                if text == "/start" or text.startswith("/start"):
                    self.handle_start(cid, first_name)
                elif text in ("📊 Mi Saldo & Estado", "/status", "/saldo"):
                    self.handle_status(cid)
                elif text in ("📈 Precio & Señal", "/precio", "/signal"):
                    self.handle_price_and_signal(cid)
                elif text in ("📸 Ver Gráfico en Foto", "/chart", "/grafico"):
                    self.handle_chart(cid)
                elif text in ("🦅 Escáner Radar", "/radar", "/scan"):
                    self.handle_scanner(cid)
                elif text in ("🧠 Miedo & Codicia", "/fng", "/sentimiento"):
                    self.handle_sentiment(cid)
                elif text in ("☀️ Resumen Diario", "/reporte", "/digest"):
                    self.handle_daily_digest(cid)
                elif text in ("🚀 Iniciar Trading", "/iniciar", "/start_trade"):
                    self.handle_start_trading(cid)
                elif text in ("⏹️ Pausar Trading", "/pausar", "/stop_trade"):
                    self.handle_pause_trading(cid)
                elif text in ("📜 Historial", "/historial"):
                    self.handle_history(cid)
                elif text in ("🔄 Reiniciar Bot", "/restart", "/reiniciar"):
                    self.handle_restart(cid)
                elif text in ("♻️ Restablecer Saldo", "/reset_balance"):
                    self.handle_reset_balance(cid)
                elif text in ("⚙️ Ajustes", "/ajustes", "/config"):
                    self.handle_settings(cid)
                elif text in ("🎓 Academia Web", "/academia", "/aprender", "/guia"):
                    self.handle_academia(cid)
                elif text in ("❓ Ayuda", "/ayuda", "/help"):
                    help_text = (
                        f"📖 *GUÍA COMPLETA DE COMANDOS PRO*\n\n"
                        f"• *📊 Mi Saldo:* Muestra tus USDT y posición activa.\n"
                        f"• *📸 Ver Gráfico:* Te envía una foto de velas japonesas y EMAs.\n"
                        f"• *🦅 Escáner:* Revisa las 8 mejores criptos para encontrar compras.\n"
                        f"• *🧠 Miedo & Codicia:* Consulta el termómetro general de mercado.\n"
                        f"• *☀️ Resumen Diario:* Ganancias acumuladas de las últimas 24h.\n"
                        f"• *🚀 Iniciar / ⏹️ Pausar:* Control del bot autónomo.\n"
                        f"• *⚙️ Ajustes:* Cambia entre BTC, ETH, SOL o activa modo DCA."
                    )
                    self.send_message(cid, help_text)
                else:
                    self.send_message(cid, f"🤖 No reconocí ese comando. Usa los botones táctiles abajo 👇", reply_markup=self.get_main_keyboard())
        except Exception as e:
            log_debug(f"Error procesando update: {e}")
            cid = None
            if "message" in update:
                cid = update["message"].get("chat", {}).get("id")
            elif "callback_query" in update:
                cid = update["callback_query"].get("message", {}).get("chat", {}).get("id")
            if cid:
                self.send_message(cid, f"⚠️ Error al procesar: {e}\nPor favor intenta nuevamente.")

    def run(self):
        """Inicia el bot en modo Webhook para la nube (Render 24/7) o Long-Polling para desarrollo local."""
        is_cloud = bool(os.environ.get("RENDER") or os.environ.get("PORT") or os.environ.get("RENDER_EXTERNAL_URL"))
        cloud_url = os.environ.get("RENDER_EXTERNAL_URL") or os.environ.get("WEBHOOK_URL") or "https://bot-trading-593w.onrender.com"

        if is_cloud:
            webhook_url = f"{cloud_url.rstrip('/')}/webhook"
            print(f"\n{Fore.CYAN}===================================================================={Style.RESET_ALL}")
            print(f"{Fore.GREEN}{Style.BRIGHT}     ☁️ TELEGRAM PRO NUBE: MODO WEBHOOK 24/7 OPERATIVO     {Style.RESET_ALL}")
            print(f"  {Fore.WHITE}Receptor Webhook: {webhook_url}{Style.RESET_ALL}")
            print(f"{Fore.CYAN}===================================================================={Style.RESET_ALL}\n")
            try:
                set_hook = f"{self.base_url}/setWebhook?url={webhook_url}&drop_pending_updates=False"
                resp = requests.get(set_hook, timeout=15)
                res_data = resp.json()
                if res_data.get("ok"):
                    print(f"{Fore.GREEN}[OK] Webhook registrado exitosamente en Telegram.{Style.RESET_ALL}")
                else:
                    print(f"{Fore.YELLOW}[AVISO Webhook] {res_data}{Style.RESET_ALL}")
            except Exception as e:
                print(f"{Fore.RED}[Error Webhook] {e}{Style.RESET_ALL}")

            # En la nube, CloudServerHandler atiende todas las peticiones POST de Telegram en segundo plano.
            # Mantenemos vivo el hilo principal sin gastar CPU.
            while True:
                time.sleep(3600)
        else:
            # Modo local en PC: eliminamos cualquier webhook previo para que getUpdates funcione
            try:
                requests.get(f"{self.base_url}/deleteWebhook", timeout=10)
            except Exception:
                pass
            self.start_polling()

    def start_polling(self):
        print(f"\n{Fore.CYAN}===================================================================={Style.RESET_ALL}")
        print(f"{Fore.GREEN}{Style.BRIGHT}     📱 TELEGRAM PRO CONTROLLER INICIADO (MODO LOCAL)     {Style.RESET_ALL}")
        print(f"  {Fore.WHITE}Gráficos, Escáner Radar, DCA y Sentimiento 100% operativos.{Style.RESET_ALL}")
        print(f"{Fore.CYAN}===================================================================={Style.RESET_ALL}\n")

        offset = 0
        while True:
            try:
                url = f"{self.base_url}/getUpdates?offset={offset}&timeout=20"
                resp = requests.get(url, timeout=25)
                if resp.status_code == 200:
                    data = resp.json()
                    for update in data.get("result", []):
                        offset = update["update_id"] + 1
                        self.process_update(update)
                elif resp.status_code == 401:
                    print(f"{Fore.RED}[ERROR] El Token de Telegram es inválido.{Style.RESET_ALL}")
                    time.sleep(10)
                else:
                    time.sleep(2)
            except requests.exceptions.RequestException:
                time.sleep(3)
            except Exception as e:
                print(f"{Fore.RED}[Error Polling] {e}{Style.RESET_ALL}")
                time.sleep(2)

def main():
    config = BotConfig()
    token = config.telegram_bot_token.strip() or "9241639178:AAHPcbUfPkxhIsFwCjxe-ireM82NL8bjY2E"
    
    bot = TelegramTradingBot(token)
    start_health_server(bot)
    bot.run()

if __name__ == "__main__":
    main()
