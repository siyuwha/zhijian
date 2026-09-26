export type DirectionType = 'buy' | 'sell';
export type RecordType = 'TRADE' | 'REVERSAL';
export type PriceType = 'REALTIME' | 'PREV_CLOSE' | 'UNAVAILABLE';

export interface TradeNote {
  id: number;
  trade_id: number;
  date: string;
  mental_state?: string | null;
  decision_logic?: string | null;
  reflection?: string | null;
  lessons?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface TradeRecord {
  id: number;
  code: string;
  name?: string | null;
  direction: DirectionType;
  price: number;
  quantity: number;
  amount: number;
  trade_time: string;
  trade_reason?: string | null;
  source: string;
  record_type: RecordType;
  reversed_record_id?: number | null;
  idempotency_key?: string | null;
  created_at?: string | null;
  note?: TradeNote | null;
}

export interface Position {
  id: number;
  code: string;
  name?: string | null;
  quantity: number;
  avg_cost: number;
  total_cost: number;
  current_price?: number | null;
  price_type: PriceType;
  quote_time?: string | null;
  floating_pnl?: number | null;
  floating_pnl_pct?: number | null;
  market_value?: number | null;
  updated_at?: string | null;
}

export interface TradeStats {
  total_trades: number;
  closed_trades: number;
  win_trades: number;
  loss_trades: number;
  closed_leg_win_rate?: number | null;
  payoff_ratio?: number | null;
  total_realized_pnl: number;
  total_floating_pnl?: number | null;
  total_market_value?: number | null;
  total_pnl?: number | null;
  quote_status: 'FULL' | 'PARTIAL' | 'UNAVAILABLE';
}

export interface TradeRecordCreatePayload {
  code: string;
  name?: string;
  direction: DirectionType;
  price: number;
  quantity: number;
  trade_time: string;
  trade_reason?: string;
  source?: string;
  idempotency_key?: string;
}

export interface ReversalTradeCreatePayload {
  target_record_id: number;
  reason: string;
  idempotency_key?: string;
}

export interface TradeNoteCreatePayload {
  trade_id: number;
  date: string;
  mental_state?: string;
  decision_logic?: string;
  reflection?: string;
  lessons?: string;
  append_mode?: boolean;
}
