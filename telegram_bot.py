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

STATE_FILE = os.path.join(os.path.dirname(__file__), "trading_state.json")

def start_health_server():
    """Servidor HTTP ligero para permitir alojamiento gratuito 24/7 en la nube (Render, Railway, Koyeb)."""
    port = int(os.environ.get("PORT", "8080"))
    class HealthHandler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            html = (
                "<!DOCTYPE html><html><head><meta charset='utf-8'><title>Trading Bot 24/7</title></head>"
                "<body style='font-family:sans-serif; text-align:center; padding-top:50px; background:#0f172a; color:#f8fafc;'>"
                "<h1>🟢 Bot de Trading Operando 24/7 en la Nube</h1>"
                "<p>Conectado a Telegram y procesando ordenes sin depender de tu PC.</p>"
                "</body></html>"
            )
            self.wfile.write(html.encode("utf-8"))
        def log_message(self, format, *args):
            pass

    def run_server():
        try:
            socketserver.TCPServer.allow_reuse_address = True
            with socketserver.TCPServer(("", port), HealthHandler) as httpd:
                print(f"[NUBE] Servidor de salud activo en puerto {port}")
                httpd.serve_forever()
        except Exception as e:
            print(f"[NUBE Servidor] Error iniciando puerto {port}: {e}")

    threading.Thread(target=run_server, daemon=True).start()

class TelegramTradingBot:
    def __init__(self, token: str):
        self.token = token.strip()
        self.base_url = f"https://api.telegram.org/bot{self.token}"
        self.config = BotConfig()
        
        # Estado y persistencia
        self.authorized_chat_ids = set()
        self.is_trading_active = False
        self.trade_thread: Optional[threading.Thread] = None
        self.stop_signal = threading.Event()
        
        # Clientes
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
            max_position_pct=self.config.max_position_pct
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

    def load_state(self):
        """Carga el estado previo guardado (saldo, posiciones, chats autorizados)."""
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.authorized_chat_ids = set(data.get("authorized_chat_ids", []))
                    if "paper_balance" in data and self.config.is_paper():
                        self.client.paper_balance = data["paper_balance"]
                    if "paper_history" in data:
                        self.client.paper_history = data["paper_history"]
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
                            opened_at=p["opened_at"]
                        )
                    print(f"{Fore.GREEN}[OK] Estado anterior cargado correctamente desde disco.{Style.RESET_ALL}")
            except Exception as e:
                print(f"{Fore.RED}[WARN] No se pudo leer el estado anterior: {e}{Style.RESET_ALL}")

    def save_state(self):
        """Guarda el estado actual en disco para que no se pierda nada al reiniciar."""
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
                    "opened_at": p.opened_at
                }

            data = {
                "authorized_chat_ids": list(self.authorized_chat_ids),
                "paper_balance": self.client.paper_balance,
                "paper_history": self.client.paper_history,
                "active_position": pos_dict
            }
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"{Fore.RED}[WARN] Error guardando estado: {e}{Style.RESET_ALL}")

    # ==================== COMUNICACIÓN TELEGRAM ====================

    def send_message(self, chat_id: int, text: str, reply_markup: Optional[Dict] = None):
        """Envía un mensaje formateado a un chat de Telegram."""
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
            requests.post(url, json=payload, timeout=8)
        except Exception as e:
            print(f"{Fore.RED}[Telegram Error] Envio fallido: {e}{Style.RESET_ALL}")

    def answer_callback_query(self, callback_query_id: str, text: str = ""):
        """Responde a un toque de botón inline."""
        url = f"{self.base_url}/answerCallbackQuery"
        try:
            requests.post(url, json={"callback_query_id": callback_query_id, "text": text}, timeout=5)
        except Exception:
            pass

    def broadcast(self, text: str):
        """Notifica a todos los usuarios autorizados en su móvil."""
        for cid in self.authorized_chat_ids:
            self.send_message(cid, text)

    # ==================== TECLADOS MÓVILES ====================

    def get_main_keyboard(self) -> Dict:
        """Teclado táctil permanente en la pantalla del celular."""
        return {
            "keyboard": [
                [{"text": "📊 Mi Saldo & Estado"}, {"text": "📈 Precio & Señal"}],
                [{"text": "🚀 Iniciar Trading"}, {"text": "⏹️ Pausar Trading"}],
                [{"text": "📜 Historial"}, {"text": "🧪 Probar Backtest"}],
                [{"text": "⚙️ Ajustes"}, {"text": "❓ Ayuda"}]
            ],
            "resize_keyboard": True,
            "is_persistent": True
        }

    # ==================== CONTROLADORES DE ACCIÓN ====================

    def handle_start(self, chat_id: int, user_first_name: str):
        """Da la bienvenida y autoriza al familiar."""
        self.authorized_chat_ids.add(chat_id)
        self.save_state()
        
        status_text = "🟢 ACTIVO" if self.is_trading_active else "⏸️ PAUSADO"
        welcome_text = (
            f"👋 ¡Hola, *{user_first_name}*!\n\n"
            f"Bienvenido a tu **Bot de Cripto Trading Móvil**.\n"
            f"Este sistema opera de forma automática analizando el mercado con **Medias Móviles (EMA) y RSI**.\n\n"
            f"📌 *Configuración Actual:*\n"
            f"• *Modo:* `{self.config.bot_mode.upper()} (Simulación Segura)`\n"
            f"• *Par:* `{self.config.symbol}`\n"
            f"• *Temporalidad:* `{self.config.timeframe}`\n"
            f"• *Estado:* {status_text}\n\n"
            f"👇 *Toca los botones de abajo para controlar todo desde tu celular:*"
        )
        self.send_message(chat_id, welcome_text, reply_markup=self.get_main_keyboard())

    def handle_status(self, chat_id: int):
        """Muestra el saldo, precio actual y posición abierta."""
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
        
        msg = [
            f"📊 *ESTADO GENERAL DEL BOT*",
            f"━━━━━━━━━━━━━━━━━━",
            f"• *Estado:* `{status_icon}`",
            f"• *Exchange:* `{self.config.exchange_id.upper()}`",
            f"• *Par:* `{self.config.symbol}`",
            f"• *Precio Actual:* `${price:,.2f} USD`",
            f"• *Saldo USDT:* `${quote_bal:,.2f}`",
            f"• *Saldo Crypto:* `{crypto_bal:.6f} {base_curr}`",
            f"━━━━━━━━━━━━━━━━━━"
        ]

        inline_buttons = []
        if self.risk_mgr.active_position:
            pos = self.risk_mgr.active_position
            pnl_pct = ((price - pos.entry_price) / pos.entry_price) * 100.0
            pnl_val = (price - pos.entry_price) * pos.amount
            emoji_pnl = "🟢 +" if pnl_pct >= 0 else "🔴 "
            
            msg.extend([
                f"🎯 *POSICIÓN ABIERTA ACTIVA:*",
                f"• *Precio de Entrada:* `${pos.entry_price:,.2f}`",
                f"• *Ganancia/Pérdida (PnL):* {emoji_pnl}*{pnl_val:+.2f} USD ({pnl_pct:+.2f}%)*",
                f"• *Take-Profit:* `${pos.take_profit_price:,.2f} (+{self.config.take_profit_pct}%)`",
                f"• *Stop-Loss:* `${pos.stop_loss_price:,.2f} (-{self.config.stop_loss_pct}%)`",
                f"• *Abierta el:* `{pos.opened_at}`"
            ])
            inline_buttons.append([{"text": "⚡ Cerrar Posición Ahora (Vender)", "callback_data": "force_sell"}])
        else:
            msg.append("💤 *Sin posición abierta en este momento.* Buscando oportunidad de compra...")

        inline_buttons.append([{"text": "🔄 Actualizar", "callback_data": "refresh_status"}])
        reply_markup = {"inline_keyboard": inline_buttons}
        self.send_message(chat_id, "\n".join(msg), reply_markup=reply_markup)

    def handle_price_and_signal(self, chat_id: int):
        """Analiza la vela actual y emite la recomendación de la estrategia."""
        self.send_message(chat_id, f"⏳ Analizando mercado en vivo para `{self.config.symbol}` ({self.config.timeframe})...")
        try:
            df = self.client.fetch_ohlcv(self.config.symbol, timeframe=self.config.timeframe, limit=50)
            price = self.client.fetch_current_price(self.config.symbol)
            has_pos = self.risk_mgr.active_position is not None
            signal = self.strategy.analyze(df, has_open_position=has_pos)
            
            signal_emoji = "🟢 COMPRA" if signal.action == "BUY" else ("🔴 VENTA" if signal.action == "SELL" else "⚪ ESPERAR (HOLD)")
            
            msg = (
                f"📈 *ANÁLISIS TÉCNICO EN VIVO*\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"• *Par:* `{self.config.symbol}`\n"
                f"• *Precio:* `${price:,.2f} USD`\n"
                f"• *EMA {self.config.fast_ema} (Rápida):* `${signal.fast_ema:,.2f}`\n"
                f"• *EMA {self.config.slow_ema} (Lenta):* `${signal.slow_ema:,.2f}`\n"
                f"• *RSI (14):* `{signal.rsi:.1f}` / 100\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"• *Diagnóstico:* *{signal_emoji}*\n"
                f"• *Detalle:* {signal.reason}"
            )
            self.send_message(chat_id, msg)
        except Exception as e:
            self.send_message(chat_id, f"❌ Error al analizar: `{e}`")

    def handle_start_trading(self, chat_id: int):
        """Inicia el ciclo automático en segundo plano."""
        if self.is_trading_active:
            self.send_message(chat_id, "⚠️ El bot *ya se encuentra activo y operando* en segundo plano.")
            return

        self.is_trading_active = True
        self.stop_signal.clear()
        self.trade_thread = threading.Thread(target=self._trading_loop, daemon=True)
        self.trade_thread.start()
        
        self.send_message(
            chat_id,
            f"🚀 *¡TRADING INICIADO!*\n\n"
            f"El bot está ahora monitoreando `{self.config.symbol}` cada 15 segundos.\n"
            f"Te enviará una alerta automática a tu celular cada vez que compre o venda.",
            reply_markup=self.get_main_keyboard()
        )

    def handle_pause_trading(self, chat_id: int):
        """Pausa el ciclo automático."""
        if not self.is_trading_active:
            self.send_message(chat_id, "ℹ️ El bot ya está pausado.")
            return

        self.is_trading_active = False
        self.stop_signal.set()
        self.send_message(chat_id, "⏸️ *Bot Pausado.* Ya no abrirá nuevas operaciones automáticas hasta que lo vuelvas a iniciar.")

    def handle_history(self, chat_id: int):
        """Muestra las últimas operaciones ejecutadas."""
        history = self.client.paper_history
        if not history:
            self.send_message(chat_id, "📜 *Aún no hay operaciones registradas en el historial.*")
            return

        msg = ["📜 *HISTORIAL RECIENTE DE OPERACIONES:*", "━━━━━━━━━━━━━━━━━━"]
        for o in history[-6:]:
            side_icon = "🟢 COMPRA" if o['side'] == 'buy' else "🔴 VENTA"
            cost_str = f"${o.get('cost', 0):,.2f} USD"
            msg.append(f"{side_icon} | Cantidad: `{o['amount']:.5f}` | Precio: `${o['price']:,.2f}` ({cost_str})")
        
        msg.append("━━━━━━━━━━━━━━━━━━")
        self.send_message(chat_id, "\n".join(msg))

    def handle_backtest_prompt(self, chat_id: int):
        """Envía opciones para hacer backtesting rápido con botones inline."""
        markup = {
            "inline_keyboard": [
                [
                    {"text": "📊 Bitcoin (BTC/USDT)", "callback_data": "bt_BTC/USDT"},
                    {"text": "📊 Ethereum (ETH/USDT)", "callback_data": "bt_ETH/USDT"}
                ],
                [
                    {"text": "📊 Solana (SOL/USDT)", "callback_data": "bt_SOL/USDT"},
                    {"text": "📊 Dogecoin (DOGE/USDT)", "callback_data": "bt_DOGE/USDT"}
                ]
            ]
        }
        self.send_message(chat_id, "🧪 *Elige una moneda para probar la estrategia con datos reales históricos:*", reply_markup=markup)

    def run_backtest_for_chat(self, chat_id: int, symbol: str):
        self.send_message(chat_id, f"⏳ Descargando velas históricas de *{symbol}* (1h) y simulando... Por favor espera unos segundos.")
        try:
            df = self.client.fetch_ohlcv(symbol, timeframe="1h", limit=300)
            bt = Backtester(
                initial_balance=self.config.initial_balance,
                fast_ema=self.config.fast_ema,
                slow_ema=self.config.slow_ema,
                rsi_period=self.config.rsi_period,
                rsi_buy_threshold=self.config.rsi_buy_threshold,
                rsi_overbought=self.config.rsi_overbought,
                rsi_oversold=self.config.rsi_oversold,
                stop_loss_pct=self.config.stop_loss_pct,
                take_profit_pct=self.config.take_profit_pct,
                trailing_stop=self.config.trailing_stop,
                max_position_pct=self.config.max_position_pct
            )
            res = bt.run(df)
            
            pnl_emoji = "🟢 +" if res['total_return_pct'] >= 0 else "🔴 "
            report = (
                f"📊 *RESULTADOS BACKTEST: {symbol} (1h)*\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"• *Período:* Últimas 300 velas (12 días)\n"
                f"• *Saldo Inicial:* `${res['initial_balance']:,.2f} USDT`\n"
                f"• *Saldo Final:* `${res['final_balance']:,.2f} USDT`\n"
                f"• *Ganancia Neta:* {pnl_emoji}*${res['total_pnl']:+,.2f} ({res['total_return_pct']:+.2f}%)*\n"
                f"• *Mercado Pasivo (Buy & Hold):* `{res['buy_hold_pct']:+.2f}%`\n"
                f"• *Operaciones Totales:* `{res['total_trades']}` (Ganadas: {res['wins']} | Perdidas: {res['losses']})\n"
                f"• *Tasa de Acierto:* `{res['win_rate']:.1f}%`\n"
                f"• *Drawdown Máximo:* `{res['max_drawdown_pct']:.2f}%`\n"
                f"━━━━━━━━━━━━━━━━━━"
            )
            self.send_message(chat_id, report)
        except Exception as e:
            self.send_message(chat_id, f"❌ Error en backtest: `{e}`")

    def handle_settings(self, chat_id: int):
        """Muestra opciones para cambiar par o temporalidad."""
        markup = {
            "inline_keyboard": [
                [
                    {"text": "🪙 Cambiar a BTC", "callback_data": "set_pair_BTC/USDT"},
                    {"text": "🪙 Cambiar a ETH", "callback_data": "set_pair_ETH/USDT"},
                    {"text": "🪙 Cambiar a SOL", "callback_data": "set_pair_SOL/USDT"}
                ],
                [
                    {"text": "⏱️ Marco 15m", "callback_data": "set_tf_15m"},
                    {"text": "⏱️ Marco 1h", "callback_data": "set_tf_1h"},
                    {"text": "⏱️ Marco 4h", "callback_data": "set_tf_4h"}
                ]
            ]
        }
        text = (
            f"⚙️ *AJUSTES DEL BOT*\n\n"
            f"• *Par activo:* `{self.config.symbol}`\n"
            f"• *Temporalidad:* `{self.config.timeframe}`\n"
            f"• *Stop-Loss:* `{self.config.stop_loss_pct}%`\n"
            f"• *Take-Profit:* `{self.config.take_profit_pct}%`\n\n"
            f"👇 *Toca un botón para cambiar la configuración:*"
        )
        self.send_message(chat_id, text, reply_markup=markup)

    def handle_force_sell(self, chat_id: int):
        """Cierre manual de emergencia solicitado por el usuario desde el celular."""
        if not self.risk_mgr.active_position:
            self.send_message(chat_id, "ℹ️ No tienes ninguna posición abierta actualmente.")
            return

        try:
            pos = self.risk_mgr.active_position
            price = self.client.fetch_current_price(pos.symbol)
            pnl_pct = ((price - pos.entry_price) / pos.entry_price) * 100.0
            self.client.create_market_sell_order(pos.symbol, pos.amount, price)
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
            self.send_message(chat_id, f"❌ Error ejecutando venta manual: `{e}`")

    # ==================== CICLO DE TRADING AUTOMÁTICO ====================

    def _trading_loop(self):
        """Hilo en segundo plano que monitorea velas y ejecuta órdenes."""
        base_curr, quote_curr = self.config.symbol.split('/')
        print(f"{Fore.GREEN}[TRADING] Ciclo en segundo plano iniciado para {self.config.symbol}.{Style.RESET_ALL}")

        while not self.stop_signal.is_set():
            try:
                current_price = self.client.fetch_current_price(self.config.symbol)
                balances = self.client.get_balances(base_curr, quote_curr)
                quote_balance = balances[quote_curr]

                # 1. Comprobar salida de posición activa por TP / SL
                has_position = self.risk_mgr.active_position is not None
                if has_position:
                    should_exit, exit_reason, pnl_pct = self.risk_mgr.check_exit(current_price)
                    if should_exit:
                        pos = self.risk_mgr.active_position
                        self.client.create_market_sell_order(self.config.symbol, pos.amount, current_price)
                        self.risk_mgr.close_position()
                        self.save_state()

                        emoji = "🎉 ¡TAKE PROFIT!" if pnl_pct > 0 else "🛡️ STOP LOSS"
                        self.broadcast(
                            f"{emoji} *ORDEN CERRADA AUTOMÁTICAMENTE*\n\n"
                            f"• *Par:* `{self.config.symbol}`\n"
                            f"• *Precio Salida:* `${current_price:,.2f}`\n"
                            f"• *Resultado:* *{pnl_pct:+.2f}%*\n"
                            f"• *Motivo:* {exit_reason}"
                        )
                        has_position = False

                # 2. Descargar velas y evaluar estrategia
                df = self.client.fetch_ohlcv(self.config.symbol, timeframe=self.config.timeframe, limit=50)
                signal = self.strategy.analyze(df, has_open_position=has_position)

                # 3. Ejecutar compra si hay señal
                if signal.action == "BUY" and not has_position:
                    amount = self.risk_mgr.calculate_order_amount(quote_balance, current_price)
                    if amount * current_price >= 10.0:
                        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        self.client.create_market_buy_order(self.config.symbol, amount, current_price)
                        self.risk_mgr.open_position(self.config.symbol, current_price, amount, now_str)
                        self.save_state()

                        self.broadcast(
                            f"🟢 *¡NUEVA COMPRA AUTOMÁTICA!*\n\n"
                            f"• *Par:* `{self.config.symbol}`\n"
                            f"• *Precio:* `${current_price:,.2f}`\n"
                            f"• *Cantidad:* `{amount:.6f}`\n"
                            f"• *Inversión:* `${(amount * current_price):,.2f} USD`\n"
                            f"• *Señal:* {signal.reason}\n\n"
                            f"🎯 *Take-Profit:* `${(current_price * (1 + self.config.take_profit_pct/100)):,.2f}`\n"
                            f"🛡️ *Stop-Loss:* `${(current_price * (1 - self.config.stop_loss_pct/100)):,.2f}`"
                        )

                elif signal.action == "SELL" and has_position:
                    pos = self.risk_mgr.active_position
                    pnl_pct = ((current_price - pos.entry_price) / pos.entry_price) * 100.0
                    self.client.create_market_sell_order(self.config.symbol, pos.amount, current_price)
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

            # Esperar 15 segundos entre chequeos
            self.stop_signal.wait(timeout=15)

    # ==================== RECEPCIÓN DE MENSAJES (LONG POLLING) ====================

    def process_update(self, update: Dict[str, Any]):
        """Procesa cada mensaje o click de botón recibido desde Telegram."""
        # Manejo de botones inline
        if "callback_query" in update:
            cq = update["callback_query"]
            cid = cq["message"]["chat"]["id"]
            data = cq.get("data", "")
            self.answer_callback_query(cq["id"], "Procesando...")

            if data == "refresh_status":
                self.handle_status(cid)
            elif data == "force_sell":
                self.handle_force_sell(cid)
            elif data.startswith("bt_"):
                sym = data.replace("bt_", "")
                self.run_backtest_for_chat(cid, sym)
            elif data.startswith("set_pair_"):
                self.config.symbol = data.replace("set_pair_", "")
                self.send_message(cid, f"✅ Par actualizado a *{self.config.symbol}*")
            elif data.startswith("set_tf_"):
                self.config.timeframe = data.replace("set_tf_", "")
                self.send_message(cid, f"✅ Temporalidad actualizada a *{self.config.timeframe}*")
            return

        # Manejo de texto y comandos
        if "message" in update and "text" in update["message"]:
            msg = update["message"]
            cid = msg["chat"]["id"]
            text = msg["text"].strip()
            first_name = msg.get("from", {}).get("first_name", "Amigo")

            if text == "/start" or text.startswith("/start"):
                self.handle_start(cid, first_name)
            elif text in ("📊 Mi Saldo & Estado", "/status", "/saldo"):
                self.handle_status(cid)
            elif text in ("📈 Precio & Señal", "/precio", "/signal"):
                self.handle_price_and_signal(cid)
            elif text in ("🚀 Iniciar Trading", "/iniciar", "/start_trade"):
                self.handle_start_trading(cid)
            elif text in ("⏹️ Pausar Trading", "/pausar", "/stop_trade"):
                self.handle_pause_trading(cid)
            elif text in ("📜 Historial", "/historial"):
                self.handle_history(cid)
            elif text in ("🧪 Probar Backtest", "/backtest"):
                self.handle_backtest_prompt(cid)
            elif text in ("⚙️ Ajustes", "/ajustes", "/config"):
                self.handle_settings(cid)
            elif text in ("❓ Ayuda", "/ayuda", "/help"):
                help_text = (
                    f"📖 *GUÍA RÁPIDA DE USO*\n\n"
                    f"• *📊 Mi Saldo:* Muestra tus fondos y si hay operaciones abiertas.\n"
                    f"• *🚀 Iniciar:* Activa el robot para que busque compras y ventas 24/7.\n"
                    f"• *⏹️ Pausar:* Detiene temporalmente las compras automáticas.\n"
                    f"• *📈 Precio & Señal:* Consulta qué recomienda el indicador EMA+RSI ahora.\n"
                    f"• *🧪 Backtest:* Prueba cómo habría rendido la estrategia en los últimos días.\n"
                    f"• *⚙️ Ajustes:* Cambia entre BTC, ETH o SOL y el tiempo de las velas."
                )
                self.send_message(cid, help_text)
            else:
                self.send_message(cid, f"🤖 No reconocí ese comando. Usa los botones táctiles de abajo 👇", reply_markup=self.get_main_keyboard())

    def start_polling(self):
        """Inicia la escucha de mensajes continua."""
        print(f"\n{Fore.CYAN}===================================================================={Style.RESET_ALL}")
        print(f"{Fore.GREEN}{Style.BRIGHT}     📱 TELEGRAM MOBILE CONTROLLER INICIADO (100% OPERATIVO)     {Style.RESET_ALL}")
        print(f"  {Fore.WHITE}Dile a tu familiar que abra el bot en Telegram y pulse {Fore.YELLOW}/start{Style.RESET_ALL}")
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
                    print(f"{Fore.RED}[ERROR] El Token de Telegram es inválido. Revisa tu archivo .env{Style.RESET_ALL}")
                    time.sleep(10)
                else:
                    time.sleep(2)
            except requests.exceptions.RequestException:
                time.sleep(3)
            except Exception as e:
                print(f"{Fore.RED}[Error Polling] {e}{Style.RESET_ALL}")
                time.sleep(2)

def main():
    start_health_server()
    config = BotConfig()
    token = config.telegram_bot_token.strip()
    
    if not token:
        print(f"{Fore.YELLOW}No se encontró TELEGRAM_BOT_TOKEN en el archivo .env.{Style.RESET_ALL}")
        token = input("Ingresa el Token de Telegram proporcionado por @BotFather: ").strip()
        if not token:
            print(f"{Fore.RED}Token no proporcionado. Saliendo...{Style.RESET_ALL}")
            sys.exit(1)
        # Guardar en .env para la próxima vez
        env_path = os.path.join(os.path.dirname(__file__), ".env")
        try:
            with open(env_path, "a", encoding="utf-8") as f:
                f.write(f"\nTELEGRAM_BOT_TOKEN={token}\n")
        except Exception:
            pass

    bot = TelegramTradingBot(token)
    bot.start_polling()

if __name__ == "__main__":
    main()
