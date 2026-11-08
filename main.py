import time
import sys
import argparse
from datetime import datetime
from colorama import Fore, Back, Style, init

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from config import BotConfig
from indicators import add_indicators
from strategy import EmaRsiStrategy
from risk_manager import RiskManager
from exchange_client import ExchangeClient
from notifier import Notifier
from backtester import Backtester

init(autoreset=True)

def print_header(config: BotConfig):
    print(f"\n{Fore.CYAN}===================================================================={Style.RESET_ALL}")
    print(f"{Fore.GREEN}{Style.BRIGHT}        [BOT] CRIPTO TRADING BOT (EMA CROSS + RSI FILTER)          {Style.RESET_ALL}")
    if config.bot_mode == "backtest":
        mode_text = f"{Fore.CYAN}[MODO: BACKTESTING HISTORICO]"
    elif config.is_paper():
        mode_text = f"{Fore.YELLOW}[MODO VIRTUAL: PAPER TRADING]"
    else:
        mode_text = f"{Fore.RED}[MODO REAL / TESTNET]"
    print(f"  {mode_text} {Fore.WHITE}| Exchange: {config.exchange_id.upper()} | Par: {config.symbol} | Marco: {config.timeframe}")
    print(f"{Fore.CYAN}===================================================================={Style.RESET_ALL}\n")

def run_backtest_mode(config: BotConfig, client: ExchangeClient, symbol: str = None, timeframe: str = None, limit: int = 500):
    sym = symbol or config.symbol
    tf = timeframe or config.timeframe
    print(f"{Fore.YELLOW}[...] Descargando {limit} velas historicas de {sym} ({tf}) desde {config.exchange_id}...{Style.RESET_ALL}")
    try:
        df = client.fetch_ohlcv(sym, timeframe=tf, limit=limit)
    except Exception as e:
        print(f"{Fore.RED}[ERROR] Error al descargar datos: {e}{Style.RESET_ALL}")
        return

    print(f"{Fore.GREEN}[OK] {len(df)} velas descargadas ({df.index[0]} a {df.index[-1]}). Ejecutando simulacion...{Style.RESET_ALL}")
    backtester = Backtester(
        initial_balance=config.initial_balance,
        fast_ema=config.fast_ema,
        slow_ema=config.slow_ema,
        rsi_period=config.rsi_period,
        rsi_buy_threshold=config.rsi_buy_threshold,
        rsi_overbought=config.rsi_overbought,
        rsi_oversold=config.rsi_oversold,
        stop_loss_pct=config.stop_loss_pct,
        take_profit_pct=config.take_profit_pct,
        trailing_stop=config.trailing_stop,
        max_position_pct=config.max_position_pct
    )
    results = backtester.run(df)
    backtester.print_report(results, sym, tf)

def run_live_loop(config: BotConfig, client: ExchangeClient, notifier: Notifier):
    strategy = EmaRsiStrategy(
        fast_ema=config.fast_ema,
        slow_ema=config.slow_ema,
        rsi_period=config.rsi_period,
        rsi_buy_threshold=config.rsi_buy_threshold,
        rsi_overbought=config.rsi_overbought,
        rsi_oversold=config.rsi_oversold
    )
    risk_mgr = RiskManager(
        stop_loss_pct=config.stop_loss_pct,
        take_profit_pct=config.take_profit_pct,
        trailing_stop=config.trailing_stop,
        max_position_pct=config.max_position_pct
    )

    base_curr = config.symbol.split('/')[0]
    quote_curr = config.symbol.split('/')[1]

    notifier.log(f"Iniciando ciclo continuo para {config.symbol} ({config.timeframe}). Presione Ctrl+C para detener.", "SUCCESS")
    if config.has_telegram():
        notifier.send_telegram(f"🤖 *Bot de Trading Iniciado*\n• *Par:* `{config.symbol}`\n• *Modo:* `{config.bot_mode.upper()}`\n• *Estrategia:* `EMA {config.fast_ema}/{config.slow_ema} + RSI`")

    iteration = 0
    try:
        while True:
            iteration += 1
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            try:
                # 1. Obtener precio actual y velas
                df = client.fetch_ohlcv(config.symbol, timeframe=config.timeframe, limit=max(config.slow_ema * 3, 60))
                current_price = client.fetch_current_price(config.symbol)
                balances = client.get_balances(base_curr, quote_curr)
                quote_balance = balances[quote_curr]

                # 2. Verificar salida de posicion activa por TP/SL
                has_position = risk_mgr.active_position is not None
                if has_position:
                    should_exit, exit_reason, pnl_pct = risk_mgr.check_exit(current_price)
                    if should_exit:
                        pos = risk_mgr.active_position
                        client.create_market_sell_order(config.symbol, pos.amount, current_price)
                        notifier.notify_trade("SELL", config.symbol, current_price, pos.amount, exit_reason, pnl_pct)
                        risk_mgr.close_position()
                        has_position = False

                # 3. Analizar indicadores y senales de la estrategia
                signal = strategy.analyze(df, has_open_position=has_position)

                # 4. Mostrar estado en consola
                pos_info = "NINGUNA"
                if has_position:
                    pos = risk_mgr.active_position
                    cur_pnl = ((current_price - pos.entry_price) / pos.entry_price) * 100.0
                    pnl_color = Fore.GREEN if cur_pnl >= 0 else Fore.RED
                    pos_info = f"Entrada: ${pos.entry_price:,.2f} | PnL: {pnl_color}{cur_pnl:+.2f}%{Style.RESET_ALL} | SL: ${pos.stop_loss_price:,.2f} | TP: ${pos.take_profit_price:,.2f}"

                print(
                    f"\r[{now_str}] #{iteration:03d} | "
                    f"Precio: {Fore.YELLOW}${current_price:,.2f}{Style.RESET_ALL} | "
                    f"RSI: {Fore.CYAN}{signal.rsi:.1f}{Style.RESET_ALL} | "
                    f"EMA {config.fast_ema}/{config.slow_ema}: {signal.fast_ema:,.1f}/{signal.slow_ema:,.1f} | "
                    f"Saldo: ${quote_balance:,.2f} {quote_curr} | "
                    f"Pos: {pos_info}",
                    end="",
                    flush=True
                )

                # 5. Ejecutar senal si aplica
                if signal.action == "BUY" and not has_position:
                    print()
                    amount = risk_mgr.calculate_order_amount(quote_balance, current_price)
                    if amount * current_price >= 10.0:
                        order = client.create_market_buy_order(config.symbol, amount, current_price)
                        risk_mgr.open_position(config.symbol, current_price, amount, now_str)
                        notifier.notify_trade("BUY", config.symbol, current_price, amount, signal.reason)
                    else:
                        notifier.log("Senal BUY detectada pero saldo insuficiente para comprar.", "ALERT")

                elif signal.action == "SELL" and has_position:
                    print()
                    pos = risk_mgr.active_position
                    pnl_pct = ((current_price - pos.entry_price) / pos.entry_price) * 100.0
                    client.create_market_sell_order(config.symbol, pos.amount, current_price)
                    notifier.notify_trade("SELL", config.symbol, current_price, pos.amount, signal.reason, pnl_pct)
                    risk_mgr.close_position()

            except Exception as e:
                print(f"\n{Fore.RED}[WARN] Error en ciclo #{iteration}: {e}{Style.RESET_ALL}")

            time.sleep(15)

    except KeyboardInterrupt:
        print(f"\n\n{Fore.YELLOW}[STOP] Bot detenido por el usuario.{Style.RESET_ALL}")
        if config.has_telegram():
            notifier.send_telegram("⏹️ *Bot de Trading detenido por el usuario.*")

def main():
    parser = argparse.ArgumentParser(description="Bot de Trading de Criptomonedas (EMA + RSI)")
    parser.add_argument("--mode", choices=["live", "paper", "backtest", "telegram"], help="Modo directo de ejecucion")
    parser.add_argument("--symbol", type=str, help="Par a operar (ej. BTC/USDT)")
    parser.add_argument("--timeframe", type=str, help="Temporalidad (ej. 1h, 15m, 5m)")
    parser.add_argument("--candles", type=int, default=500, help="Cantidad de velas para backtesting")
    args = parser.parse_args()

    config = BotConfig()
    if args.symbol:
        config.symbol = args.symbol.upper()
    if args.timeframe:
        config.timeframe = args.timeframe
    if args.mode:
        config.bot_mode = args.mode

    print_header(config)

    if args.mode == "telegram":
        from telegram_bot import main as run_telegram_main
        run_telegram_main()
        return

    client = ExchangeClient(
        exchange_id=config.exchange_id,
        api_key=config.api_key,
        api_secret=config.api_secret,
        use_testnet=config.use_testnet,
        paper_mode=config.is_paper(),
        initial_balance=config.initial_balance
    )
    notifier = Notifier(config.telegram_bot_token, config.telegram_chat_id)

    if args.mode == "backtest":
        run_backtest_mode(config, client, limit=args.candles)
        return
    elif args.mode in ("paper", "live"):
        run_live_loop(config, client, notifier)
        return

    while True:
        print(f"\n{Fore.CYAN}Seleccione una opcion:{Style.RESET_ALL}")
        print(f"  {Fore.GREEN}{Style.BRIGHT}1. Iniciar Modo Celular / Telegram (Para tu familiar en móvil){Style.RESET_ALL}")
        print("  2. Iniciar Simulación en Consola Local (Paper Trading)")
        print("  3. Ejecutar Backtesting con datos historicos")
        print("  4. Probar conexion y ver precio actual")
        print("  5. Cambiar Par / Temporalidad")
        print("  6. Salir")
        
        choice = input(f"\n{Fore.GREEN}Opcion [1-6]: {Style.RESET_ALL}").strip()
        
        if choice == "1":
            from telegram_bot import main as run_telegram_main
            run_telegram_main()
            break
        elif choice == "2":
            config.bot_mode = "paper"
            run_live_loop(config, client, notifier)
            break
        elif choice == "3":
            sym = input(f"Par a analizar [{config.symbol}]: ").strip() or config.symbol
            tf = input(f"Temporalidad [{config.timeframe}]: ").strip() or config.timeframe
            candles_input = input("Cantidad de velas [500]: ").strip()
            candles = int(candles_input) if candles_input.isdigit() else 500
            run_backtest_mode(config, client, symbol=sym, timeframe=tf, limit=candles)
        elif choice == "4":
            try:
                price = client.fetch_current_price(config.symbol)
                balances = client.get_balances()
                print(f"\n{Fore.GREEN}[OK] Conexion con {config.exchange_id.upper()} exitosa:{Style.RESET_ALL}")
                print(f"  • {config.symbol}: ${price:,.2f}")
                print(f"  • Saldo USDT: ${balances.get('USDT', 0.0):,.2f}")
                print(f"  • Saldo Crypto: {balances.get('BTC', 0.0)}")
            except Exception as e:
                print(f"{Fore.RED}[ERROR] Error al conectar: {e}{Style.RESET_ALL}")
        elif choice == "5":
            new_sym = input("Nuevo par (ej. ETH/USDT, SOL/USDT): ").strip().upper()
            if new_sym:
                config.symbol = new_sym
            new_tf = input("Nueva temporalidad (ej. 15m, 1h, 4h): ").strip()
            if new_tf:
                config.timeframe = new_tf
            print(f"{Fore.GREEN}Actualizado a {config.symbol} ({config.timeframe}){Style.RESET_ALL}")
        elif choice == "6":
            print(f"{Fore.YELLOW}Hasta luego!{Style.RESET_ALL}")
            sys.exit(0)
        else:
            print(f"{Fore.RED}Opcion no valida.{Style.RESET_ALL}")
            print(f"{Fore.RED}Opcion no valida.{Style.RESET_ALL}")

if __name__ == "__main__":
    main()
