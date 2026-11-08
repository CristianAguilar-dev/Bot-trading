from dataclasses import dataclass
from typing import Optional

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

class RiskManager:
    def __init__(self, stop_loss_pct: float = 1.5, take_profit_pct: float = 3.0,
                 trailing_stop: bool = False, max_position_pct: float = 25.0):
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.trailing_stop = trailing_stop
        self.max_position_pct = max_position_pct
        self.active_position: Optional[Position] = None

    def calculate_order_amount(self, current_balance: float, current_price: float) -> float:
        """Calcula la cantidad de moneda a comprar segun el porcentaje maximo por operacion."""
        trade_capital = current_balance * (self.max_position_pct / 100.0)
        if current_price <= 0:
            return 0.0
        return trade_capital / current_price

    def open_position(self, symbol: str, entry_price: float, amount: float, timestamp: str) -> Position:
        """Registra la apertura de una posicion larga."""
        cost = entry_price * amount
        tp_price = entry_price * (1.0 + self.take_profit_pct / 100.0)
        sl_price = entry_price * (1.0 - self.stop_loss_pct / 100.0)
        
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
            opened_at=timestamp
        )
        return self.active_position

    def check_exit(self, current_price: float) -> tuple[bool, Optional[str], float]:
        """
        Evalua si el precio actual activa Take-Profit, Stop-Loss o Trailing-Stop.
        Retorna: (debe_cerrar, razon, pnl_pct)
        """
        pos = self.active_position
        if not pos:
            return False, None, 0.0

        # Actualizar maximo alcanzado para trailing stop
        if current_price > pos.highest_price:
            pos.highest_price = current_price
            if pos.trailing_stop:
                new_sl = pos.highest_price * (1.0 - pos.trailing_pct / 100.0)
                if new_sl > pos.stop_loss_price:
                    pos.stop_loss_price = new_sl

        pnl_pct = ((current_price - pos.entry_price) / pos.entry_price) * 100.0

        # Take Profit alcanzado
        if current_price >= pos.take_profit_price:
            return True, f"Take-Profit alcanzado (+{pnl_pct:.2f}%)", pnl_pct

        # Stop Loss alcanzado
        if current_price <= pos.stop_loss_price:
            reason = "Trailing Stop" if pos.trailing_stop and pos.stop_loss_price > pos.entry_price else "Stop-Loss"
            return True, f"{reason} alcanzado ({pnl_pct:.2f}%)", pnl_pct

        return False, None, pnl_pct

    def close_position(self) -> Optional[Position]:
        """Limpia la posicion activa al cerrarse."""
        pos = self.active_position
        self.active_position = None
        return pos
