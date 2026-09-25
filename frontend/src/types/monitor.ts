/**
 * G5-Phase 2: M4 盘中动态监控与异动感知系统 - 前端强类型契约
 * 遵循 7+1 铁律项：全量统计指标均采用可空类型 (number | null, string | null)，杜绝 0 伪造
 */

export type TradingSessionState = 'PRE_MARKET' | 'ACTIVE' | 'NOON_BREAK' | 'CLOSED';

export type AnomalySeverity = 'CRITICAL' | 'TRANSITION' | 'INFO';

export type AnomalyCategory = 
  | 'LIMIT_UP_SEAL'       // 涨停封板 (Edge Trigger)
  | 'LIMIT_UP_BROKEN'     // 突发炸板 (Edge Trigger)
  | 'LIMIT_DOWN'          // 触及跌停 (Edge Trigger)
  | 'VOL_PULSE'           // 流动性脉冲比率突增 (R_vol >= 3.0)
  | 'MOMENTUM_BREAK'      // 动量突变拉升 (5分钟急拉)
  | 'RESONANCE';          // 系统性共振拉升

export type WatchlistStatus = 'NORMAL' | 'SEALED' | 'BROKEN' | 'HALTED';

export type VolumeProjStatus = 'NOT_READY' | 'ESTIMATED' | 'COMPLETED';

export interface MacroSnapshotItem {
  id?: number;
  date: string;
  timestamp: string;
  minute_index: number;
  sh_price: number | null;
  sh_pct: number | null;
  total_amount_yi: number | null;
  volume_proj_yi: number | null;
  volume_proj_status: VolumeProjStatus;
  up_count: number | null;
  down_count: number | null;
  limit_up_count: number | null;
  limit_down_count: number | null;
  broken_count: number | null;
  max_height: number | null;
  leader_stock: string | null;
}

export interface WatchlistItem {
  symbol: string;
  name: string;
  board_count: number | null;
  open_pct: number | null;
  current_pct: number | null;
  status: WatchlistStatus;
  amount_yi: number | null;
}

export interface IntradayAnomalyEventItem {
  id?: number;
  date: string;
  timestamp: string;
  minute_index: number;
  event_category: AnomalyCategory;
  severity_level: AnomalySeverity;
  symbol: string | null;
  name: string | null;
  price: number | null;
  pct_change: number | null;
  window_delta_pct: number | null;
  window_amount_wan: number | null;
  surge_ratio: number | null;
  details: Record<string, any> | null;
}

export interface MonitorRealtimeResponse {
  session_state: TradingSessionState;
  freshness_seconds: number;
  is_delayed: boolean;
  timestamp: string;
  macro: MacroSnapshotItem | null;
  watchlist: WatchlistItem[];
  recent_events: IntradayAnomalyEventItem[];
  disclaimer: string;
}
