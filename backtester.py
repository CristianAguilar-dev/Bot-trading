import sys
import pandas as pd
from tabulate import tabulate
from colorama import Fore, Style
from indicators import add_indicators

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

class Backtester:
    def __init__(self, initial_balance: float = 1000.0, fee_pct: float = 0.001,
                 fast_ema: int = 9, slow_ema: int = 21,
                 rsi_period: int = 14, rsi_buy_threshold: float = 50.0,
                 rsi_overbought: float = 70.0, rsi_oversold: float = 30.0,
                 stop_loss_pct: float = 1.5, take_profit_pct: float = 3.0,
                 trailing_stop: bool = False, max_position_pct: float = 25.0):
        self.initial_balance = initial_balance
        self.fee_pct = fee_pct
        self.fast_ema = fast_ema
        self.slow_ema = slow_ema
        self.rsi_period = rsi_period
        self.rsi_buy_threshold = rsi_buy_threshold
        self.rsi_overbought = rsi_overbought
        self.rsi_oversold = rsi_oversold
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.trailing_stop = trailing_stop
        self.max_position_pct = max_position_pct

    def run(self, df: pd.DataFrame) -> dict:
        """Ejecuta la simulacion historica vela por vela."""
        df_ind = add_indicators(df, self.fast_ema, self.slow_ema, self.rsi_period)
        
        balance = self.initial_balance
        trades = []
        position = None
        equity_curve = [balance]

        warmup = max(self.slow_ema, self.rsi_period) + 5
        
        for i in range(warmup, len(df_ind)):
            row = df_ind.iloc[i]
            prev_row = df_ind.iloc[i - 1]
            price = row['close']
            high = row['high']
            low = row['low']
            rsi = row['rsi']
            timestamp = row.name

            # Si tenemos posicion abierta, verificar TP / SL o salida por estrategia
            if position is not None:
                entry_price = position['entry_price']
                highest_price = max(position['highest_price'], high)
                position['highest_price'] = highest_price

                sl_price = position['stop_loss_price']
                if self.trailing_stop:
                    new_sl = highest_price * (1.0 - self.stop_loss_pct / 100.0)
                    if new_sl > sl_price:
                        sl_price = new_sl
                        position['stop_loss_price'] = sl_price

                tp_price = position['take_profit_price']
                exit_price = None
                exit_reason = None

                if high >= tp_price:
                    exit_price = tp_price
                    exit_reason = "Take-Profit"
                elif low <= sl_price:
                    exit_price = sl_price
                    exit_reason = "Stop-Loss / Trailing"
                elif row['ema_cross_bearish'] or rsi >= self.rsi_overbought:
                    exit_price = price
                    exit_reason = "Cruce Bajista EMA" if row['ema_cross_bearish'] else "Sobrecompra RSI"

                if exit_price is not None:
                    amount = position['amount']
                    gross_revenue = amount * exit_price
                    fee = gross_revenue * self.fee_pct
                    net_revenue = gross_revenue - fee
                    
                    pnl = net_revenue - position['cost']
                    pnl_pct = (pnl / position['cost']) * 100.0

                    balance += net_revenue
                    trades.append({
                        'entry_time': position['time'],
                        'exit_time': timestamp,
                        'entry_price': entry_price,
                        'exit_price': exit_price,
                        'amount': amount,
                        'pnl': pnl,
                        'pnl_pct': pnl_pct,
                        'reason': exit_reason
                    })
                    position = None

            elif position is None:
                bull_cross = row['ema_cross_bullish'] and (rsi >= self.rsi_buy_threshold) and (rsi < self.rsi_overbought)
                oversold_bounce = (prev_row['rsi'] <= self.rsi_oversold) and (rsi > self.rsi_oversold) and (row['fast_ema'] > row['slow_ema'])

                if bull_cross or oversold_bounce:
                    trade_capital = balance * (self.max_position_pct / 100.0)
                    if trade_capital > 10.0:
                        amount = trade_capital / price
                        fee = trade_capital * self.fee_pct
                        total_cost = trade_capital + fee
                        
                        balance -= total_cost
                        position = {
                            'time': timestamp,
                            'entry_price': price,
                            'amount': amount,
                            'cost': total_cost,
                            'highest_price': price,
                            'take_profit_price': price * (1.0 + self.take_profit_pct / 100.0),
                            'stop_loss_price': price * (1.0 - self.stop_loss_pct / 100.0)
                        }

            current_equity = balance
            if position:
                current_equity += position['amount'] * price
            equity_curve.append(current_equity)

        if position:
            last_price = df_ind.iloc[-1]['close']
            revenue = position['amount'] * last_price * (1 - self.fee_pct)
            pnl = revenue - position['cost']
            pnl_pct = (pnl / position['cost']) * 100.0
            balance += revenue
            trades.append({
                'entry_time': position['time'],
                'exit_time': df_ind.iloc[-1].name,
                'entry_price': position['entry_price'],
                'exit_price': last_price,
                'amount': position['amount'],
                'pnl': pnl,
                'pnl_pct': pnl_pct,
                'reason': "Cierre al final de datos"
            })

        total_trades = len(trades)
        winning_trades = [t for t in trades if t['pnl'] > 0]
        losing_trades = [t for t in trades if t['pnl'] <= 0]
        
        win_rate = (len(winning_trades) / total_trades * 100.0) if total_trades > 0 else 0.0
        gross_profit = sum(t['pnl'] for t in winning_trades)
        gross_loss = abs(sum(t['pnl'] for t in losing_trades))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)
        
        total_pnl = balance - self.initial_balance
        total_return_pct = (total_pnl / self.initial_balance) * 100.0
        
        peak = self.initial_balance
        max_dd = 0.0
        for eq in equity_curve:
            if eq > peak:
                peak = eq
            dd = ((peak - eq) / peak) * 100.0 if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd

        first_close = df_ind.iloc[warmup]['close']
        last_close = df_ind.iloc[-1]['close']
        buy_hold_pct = ((last_close - first_close) / first_close) * 100.0

        return {
            'initial_balance': self.initial_balance,
            'final_balance': balance,
            'total_pnl': total_pnl,
            'total_return_pct': total_return_pct,
            'buy_hold_pct': buy_hold_pct,
            'total_trades': total_trades,
            'wins': len(winning_trades),
            'losses': len(losing_trades),
            'win_rate': win_rate,
            'profit_factor': profit_factor,
            'max_drawdown_pct': max_dd,
            'trades': trades
        }

    def print_report(self, results: dict, symbol: str, timeframe: str):
        """Muestra un reporte formateado y legible."""
        color = Fore.GREEN if results['total_return_pct'] >= 0 else Fore.RED
        print(f"\n{Fore.CYAN}===================================================={Style.RESET_ALL}")
        print(f"{Fore.CYAN}    [REPORTE BACKTESTING]: {symbol} ({timeframe})    {Style.RESET_ALL}")
        print(f"{Fore.CYAN}===================================================={Style.RESET_ALL}")
        
        table_data = [
            ["Capital Inicial", f"${results['initial_balance']:,.2f} USDT"],
            ["Capital Final", f"${results['final_balance']:,.2f} USDT"],
            ["Ganancia Neta (PnL)", f"{color}${results['total_pnl']:+,.2f} USDT ({results['total_return_pct']:+.2f}%){Style.RESET_ALL}"],
            ["Comparativa Buy & Hold", f"{results['buy_hold_pct']:+.2f}%"],
            ["Total Operaciones", f"{results['total_trades']} (Ganadas: {results['wins']} | Perdidas: {results['losses']})"],
            ["Tasa de Acierto (Win Rate)", f"{results['win_rate']:.1f}%"],
            ["Profit Factor", f"{results['profit_factor']:.2f}"],
            ["Drawdown Maximo", f"{Fore.YELLOW}{results['max_drawdown_pct']:.2f}%{Style.RESET_ALL}"],
            ["Configuracion", f"EMA {self.fast_ema}/{self.slow_ema} | RSI({self.rsi_period}) | SL: {self.stop_loss_pct}% | TP: {self.take_profit_pct}%"]
        ]
        print(tabulate(table_data, tablefmt="grid"))

        if results['trades']:
            print(f"\n{Fore.YELLOW}Ultimas operaciones simuladas:{Style.RESET_ALL}")
            sample_trades = results['trades'][-5:]
            trade_rows = []
            for t in sample_trades:
                p_col = Fore.GREEN if t['pnl'] > 0 else Fore.RED
                trade_rows.append([
                    str(t['entry_time'])[:16],
                    str(t['exit_time'])[:16],
                    f"${t['entry_price']:,.2f}",
                    f"${t['exit_price']:,.2f}",
                    f"{p_col}{t['pnl_pct']:+.2f}%{Style.RESET_ALL}",
                    t['reason']
                ])
            print(tabulate(trade_rows, headers=["Entrada", "Salida", "P. Entrada", "P. Salida", "PnL %", "Motivo"], tablefmt="simple"))
