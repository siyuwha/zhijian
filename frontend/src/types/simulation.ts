export interface SimAccount {
  id: number;
  name: string;
  initial_capital: number;
  current_capital: number;
  market_value: number;
  total_asset: number;
  total_pnl: number;
  total_pnl_pct: number;
}

export interface SimPosition {
  id: number;
  account_id: number;
  code: string;
  name: string;
  quantity: number;
  available_quantity?: number;
  avg_cost: number;
  total_cost: number;
  current_price: number;
  market_value: number;
  floating_pnl: number;
  floating_pnl_pct: number;
  updated_at?: string;
}

export interface SimTrade {
  id: number;
  account_id: number;
  code: string;
  name: string;
  direction: 'buy' | 'sell';
  price: number;
  quantity: number;
  amount: number;
  trade_time: string;
  strategy_id?: number | null;
  decision_summary?: string;
  trade_reason?: string;
  record_type?: string;
  created_at?: string;
}

export interface SimStats {
  total_trades: number;
  win_trades: number;
  loss_trades: number;
  closed_trades?: number;
  win_rate: number | null;
  closed_leg_win_rate?: number | null;
  payoff_ratio?: number | null;
  total_pnl: number;
  total_realized_pnl?: number;
  available_cash: number;
  market_value: number;
  total_asset: number;
}

export interface SimTradeCreatePayload {
  code: string;
  name?: string;
  direction: 'buy' | 'sell';
  price: number;
  quantity: number;
  trade_time?: string;
  strategy_id?: number | null;
  decision_summary?: string;
}
