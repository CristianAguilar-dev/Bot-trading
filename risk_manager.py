import time
from dataclasses import dataclass
from typing import Optional, Tuple, Dict, Any

@dataclass
class Position:
    symbol: str
    entry_price: float
    amount: float
    cost: float
    take_profit_price: float
    stop_loss_price: float
    highest_price: float
    trailing_stop: bool
    trailing_pct: float
    opened_at: str
    dca_count: int = 1
    dca_enabled: bool = False
    break_even_hit: bool = False
    tp1_price: float = 0.0
    tp2_price: float = 0.0
    tp1_hit: bool = False

class RiskManager:
    def __init__(self, stop_loss_pct: float = 1.5, take_profit_pct: float = 3.0,
                 trailing_stop: bool = False, max_position_pct: float = 25.0,
                 dca_enabled: bool = False, dca_step_pct: float = 2.0, dca_max_steps: int = 2,
                 break_even_pct: float = 1.2, tp1_pct: float = 2.0, tp2_pct: float = 6.0,
                 cooldown_minutes: int = 30):
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.trailing_stop = trailing_stop
        self.max_position_pct = max_position_pct
        self.dca_enabled = dca_enabled
        self.dca_step_pct = dca_step_pct
        self.dca_max_steps = dca_max_steps
        self.break_even_pct = break_even_pct
        self.tp1_pct = tp1_pct
        self.tp2_pct = tp2_pct
        self.cooldown_minutes = cooldown_minutes
        
        self.active_position: Optional[Position] = None
        self.cooldown_until: float = 0.0

    def is_in_cooldown(self) -> Tuple[bool, int]:
        """Comprueba si el bot está en pausa inteligente tras una pérdida."""
        now = time.time()
        if now < self.cooldown_until:
            rem = int((self.cooldown_until - now) / 60) + 1
            return True, rem
        return False, 0

    def trigger_cooldown(self):
        """Activa la pausa inteligente anti-revancha de 30 minutos."""
        self.cooldown_until = time.time() + (self.cooldown_minutes * 60)

    def calculate_order_amount(self, current_balance: float, current_price: float) -> float:
        """Calcula la cantidad de criptomoneda según el capital disponible."""
        trade_capital = current_balance * (self.max_position_pct / 100.0)
        if self.dca_enabled:
            trade_capital = trade_capital * 0.5
        if current_price <= 0:
            return 0.0
        return trade_capital / current_price

    def open_position(self, symbol: str, entry_price: float, amount: float, timestamp: str) -> Position:
        """Abre una posición con TP1, TP2, Break-Even y Stop-Loss."""
        cost = entry_price * amount
        tp_price = entry_price * (1.0 + self.take_profit_pct / 100.0)
        sl_price = entry_price * (1.0 - (self.stop_loss_pct * (2.0 if self.dca_enabled else 1.0)) / 100.0)
        
        tp1 = entry_price * (1.0 + self.tp1_pct / 100.0)
        tp2 = entry_price * (1.0 + self.tp2_pct / 100.0)

        self.active_position = Position(
            symbol=symbol,
            entry_price=entry_price,
            amount=amount,
            cost=cost,
            take_profit_price=tp_price,
            stop_loss_price=sl_price,
            highest_price=entry_price,
            trailing_stop=self.trailing_stop,
            trailing_pct=self.stop_loss_pct,
            opened_at=timestamp,
            dca_count=1,
            dca_enabled=self.dca_enabled,
            break_even_hit=False,
            tp1_price=tp1,
            tp2_price=tp2,
            tp1_hit=False
        )
        return self.active_position

    def check_position_events(self, current_price: float) -> Optional[Dict[str, Any]]:
        """
        Evalúa en tiempo real:
        1. Activación de Break-Even (Riesgo Cero)
        2. Cobro parcial de ganancia TP1 (50%)
        3. Cobro final de ganancia TP2 o TP clásico
        4. Cierre por Stop-Loss
        """
        pos = self.active_position
        if not pos:
            return None

        # Actualizar máximo alcanzado para trailing
        if current_price > pos.highest_price:
            pos.highest_price = current_price
            if pos.trailing_stop:
                new_sl = pos.highest_price * (1.0 - pos.trailing_pct / 100.0)
                if new_sl > pos.stop_loss_price:
                    pos.stop_loss_price = new_sl

        pnl_pct = ((current_price - pos.entry_price) / pos.entry_price) * 100.0

        # 1. Break-Even Automático al alcanzar +1.2%
        if not pos.break_even_hit and pnl_pct >= self.break_even_pct:
            pos.break_even_hit = True
            pos.stop_loss_price = max(pos.stop_loss_price, pos.entry_price * 1.001) # Cubre comisión
            return {
                "event": "BREAK_EVEN",
                "pnl_pct": pnl_pct,
                "price": current_price,
                "reason": "Break-Even activado (+1.2% tocado). Stop-Loss subido a precio de entrada."
            }

        # 2. TP1 Parcial (+2.0%): Venta del 50% para asegurar ganancia
        if not pos.tp1_hit and current_price >= pos.tp1_price:
            pos.tp1_hit = True
            pos.break_even_hit = True
            pos.stop_loss_price = max(pos.stop_loss_price, pos.entry_price * 1.001)
            sell_amt = pos.amount * 0.5
            pos.amount -= sell_amt
            pos.cost -= (sell_amt * pos.entry_price)
            return {
                "event": "TP1_PARTIAL",
                "sell_amount": sell_amt,
                "pnl_pct": pnl_pct,
                "price": current_price,
                "reason": f"Take-Profit 1 (+{pnl_pct:.2f}%) alcanzado. 50% vendido y asegurado en ganancia."
            }

        # 3. TP2 Final (+6.0%) o TP clásico
        target_tp = pos.tp2_price if pos.tp1_hit else pos.take_profit_price
        if current_price >= target_tp:
            reason = "Take-Profit 2 (+6.0%)" if pos.tp1_hit else "Take-Profit"
            return {
                "event": "FULL_EXIT",
                "sell_amount": pos.amount,
                "pnl_pct": pnl_pct,
                "price": current_price,
                "reason": f"{reason} alcanzado (+{pnl_pct:.2f}%)"
            }

        # 4. Stop Loss o salida en Break-Even
        if current_price <= pos.stop_loss_price:
            is_be = pos.break_even_hit and pos.stop_loss_price >= (pos.entry_price * 0.999)
            reason = "Break-Even (Riesgo Cero)" if is_be else "Stop-Loss"
            if not is_be and pnl_pct < 0:
                self.trigger_cooldown() # Activa pausa anti-revancha si hubo pérdida real
            return {
                "event": "FULL_EXIT",
                "sell_amount": pos.amount,
                "pnl_pct": pnl_pct,
                "price": current_price,
                "reason": f"{reason} ejecutado ({pnl_pct:+.2f}%)"
            }

        return None

    def check_dca_opportunity(self, current_price: float, available_balance: float) -> Tuple[bool, float]:
        pos = self.active_position
        if not pos or not self.dca_enabled or pos.dca_count >= self.dca_max_steps:
            return False, 0.0

        drop_pct = ((pos.entry_price - current_price) / pos.entry_price) * 100.0
        if drop_pct >= self.dca_step_pct:
            needed = pos.amount * current_price
            if available_balance >= needed:
                return True, pos.amount
        return False, 0.0

    def apply_dca_buy(self, add_amount: float, add_price: float):
        pos = self.active_position
        if not pos:
            return
        new_cost = pos.cost + (add_amount * add_price)
        new_amount = pos.amount + add_amount
        new_entry = new_cost / new_amount

        pos.entry_price = new_entry
        pos.amount = new_amount
        pos.cost = new_cost
        pos.dca_count += 1
        pos.take_profit_price = new_entry * (1.0 + self.take_profit_pct / 100.0)
        pos.stop_loss_price = new_entry * (1.0 - self.stop_loss_pct / 100.0)
        pos.tp1_price = new_entry * (1.0 + self.tp1_pct / 100.0)
        pos.tp2_price = new_entry * (1.0 + self.tp2_pct / 100.0)

    def close_position(self) -> Optional[Position]:
        pos = self.active_position
        self.active_position = None
        return pos
