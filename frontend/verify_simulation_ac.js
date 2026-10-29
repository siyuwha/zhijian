/**
 * frontend/verify_simulation_ac.js
 * 
 * 模拟交易沙盒页面 (frontend/src/app/simulation/page.tsx)
 * 纯离线状态逻辑模型断言脚本 (Model State Logic Check)
 * 
 * 【重要性质说明】：
 * 本脚本仅作为内部状态机与指标运算规则的纯逻辑断言，不挂载真实 React DOM，不连接浏览器引擎。
 * 独立审查报告中严格界定为“离线模型状态检查”，不视作真实浏览器 E2E 验收。
 * 
 * 覆盖测试点：
 * - AC01: 首次加载尚未获取统计 (指标为 null / '--')
 * - AC02: 有效零值 (胜率 0%, 已实现 -100 元, 盈亏比 null, 盈亏样本不足)
 * - AC03: 无平仓样本 (closed_trades: 0, 暂无平仓样本, 资金正常计算)
 * - AC04: 首次 409 (保留流水 ID 与原因, 统计与资金指标清空展示 '--')
 * - AC05: 成功后失败 (先成功后刷新 409, 必须清空旧 stats 与依赖指标)
 * - AC06: 通用故障分类 (网络断开/HTTP 500/200 空统计)
 * - AC07: 刷新恢复成功 (清除错误, 恢复新统计与资金指标)
 * - AC08: 部分接口失败隔离 (统计失败不冲垮持仓流水; 策略失败不影响成功统计)
 * - AC09: 提示独立性 (4.5 秒业务通知消失不影响持续的统计错误提示)
 * - AC10: 请求顺序防竞态控制 (早发晚到的陈旧响应不得覆盖新响应)
 * - AC11 (Codex 返修新增): total_realized_pnl 缺失/null 时不得按 0 算，依赖资金指标均为 '--'
 * - AC12 (Codex 返修新增): closed_trades 缺失/null 时不得拿 total_trades 冒充，展示 '--' 且不误报暂无平仓样本
 */

const assert = require('assert');

function computeMetrics({ positions, stats, statsError, isStatsInitialLoaded }) {
  const initialCapital = 1000000.0;
  const totalMarketValue = positions.reduce((acc, p) => acc + (p.market_value || (p.current_price || p.avg_cost) * p.quantity), 0);
  const totalCost = positions.reduce((acc, p) => acc + (p.total_cost || 0), 0);
  const totalFloatingPnl = positions.reduce((acc, p) => acc + (p.floating_pnl || 0), 0);

  // 依赖统计真实性的资产计算防线：已实现盈亏必须是接收到的真实有限数值，缺失/null/非数值时不参与资金重算，展示 '--'
  const isStatsAvailable = Boolean(stats && !statsError && isStatsInitialLoaded);
  const isRealizedPnlAvailable = Boolean(
    isStatsAvailable &&
    stats &&
    typeof stats.total_realized_pnl === 'number' &&
    Number.isFinite(stats.total_realized_pnl)
  );
  const totalRealizedPnl = isRealizedPnlAvailable ? stats.total_realized_pnl : null;

  // 依赖已实现盈亏的资金指标：已实现盈亏不可用时必须为 null 并展示 '--'，不得以 0 代替
  const availableCash = totalRealizedPnl !== null
    ? Math.max(0, initialCapital - totalCost + totalRealizedPnl)
    : null;
  const totalAssets = availableCash !== null ? availableCash + totalMarketValue : null;
  const totalPnlRatio = totalAssets !== null
    ? Number((((totalAssets - initialCapital) / initialCapital) * 100).toFixed(2))
    : null;
  const positionRatio = (totalAssets !== null && totalAssets > 0)
    ? Number(((totalMarketValue / totalAssets) * 100).toFixed(1))
    : null;
  const cashRatio = (availableCash !== null && totalAssets !== null && totalAssets > 0)
    ? Number(((availableCash / totalAssets) * 100).toFixed(1))
    : null;

  // 平仓腿数与盈利腿数必须严格来自平仓统计字段，不得以买卖流水总数 total_trades 代替
  const hasClosedTrades = Boolean(
    isStatsAvailable &&
    stats &&
    typeof stats.closed_trades === 'number' &&
    Number.isFinite(stats.closed_trades)
  );
  const closedTradesCount = hasClosedTrades ? stats.closed_trades : null;

  const hasWinTrades = Boolean(
    isStatsAvailable &&
    stats &&
    typeof stats.win_trades === 'number' &&
    Number.isFinite(stats.win_trades)
  );
  const winTradesCount = hasWinTrades ? stats.win_trades : null;

  // 胜率
  const winRateDisplay = isStatsAvailable && typeof stats.closed_leg_win_rate === 'number' && Number.isFinite(stats.closed_leg_win_rate)
    ? `${stats.closed_leg_win_rate}%`
    : '--';

  // 腿数
  const legCountDisplay = winTradesCount !== null && closedTradesCount !== null
    ? `(${winTradesCount} 盈利 / ${closedTradesCount} 平仓腿)`
    : closedTradesCount !== null
    ? `(-- 盈利 / ${closedTradesCount} 平仓腿)`
    : '(-- 盈利 / -- 平仓腿)';

  // 盈亏比
  const payoffDisplay = isStatsAvailable && typeof stats.payoff_ratio === 'number' && Number.isFinite(stats.payoff_ratio)
    ? `${stats.payoff_ratio} : 1`
    : '--';

  // 已实现盈亏
  const realizedDisplay = totalRealizedPnl !== null
    ? `${totalRealizedPnl > 0 ? `+${totalRealizedPnl.toFixed(2)}` : totalRealizedPnl.toFixed(2)} 元`
    : '--';

  // 样本说明
  const sampleNote = isStatsAvailable && stats
    ? (closedTradesCount === 0
        ? '暂无平仓样本'
        : (closedTradesCount !== null && closedTradesCount > 0 && stats.payoff_ratio == null)
        ? '盈亏样本不足'
        : null)
    : null;

  return {
    initialCapital,
    totalMarketValue,
    totalCost,
    totalFloatingPnl,
    isStatsAvailable,
    isRealizedPnlAvailable,
    totalRealizedPnl,
    availableCash,
    totalAssets,
    totalPnlRatio,
    positionRatio,
    cashRatio,
    winRateDisplay,
    legCountDisplay,
    payoffDisplay,
    realizedDisplay,
    sampleNote,
    statsError,
  };
}

class SimulationStateEngine {
  constructor() {
    this.positions = [];
    this.records = [];
    this.stats = null;
    this.statsError = null;
    this.isStatsInitialLoaded = false;
    this.strategyData = null;
    this.isLoading = true;
    this.isRefreshing = false;
    this.actionNotice = null;
    this.reqSequence = 0;
  }

  showNotice(text, type = 'success') {
    this.actionNotice = { text, type };
  }

  clearNotice() {
    this.actionNotice = null;
  }

  async loadAllData(quiet, apiMocks) {
    const currentReqSeq = ++this.reqSequence;
    if (!quiet) this.isLoading = true;
    else this.isRefreshing = true;

    try {
      const [posRes, recRes, statsRes, stratRes] = await Promise.allSettled([
        apiMocks.getSimPositions ? apiMocks.getSimPositions() : Promise.resolve([]),
        apiMocks.getSimRecords ? apiMocks.getSimRecords() : Promise.resolve({ items: [] }),
        apiMocks.getSimStats ? apiMocks.getSimStats() : Promise.resolve(null),
        apiMocks.getClassicStrategies ? apiMocks.getClassicStrategies() : Promise.resolve(null),
      ]);

      if (currentReqSeq !== this.reqSequence) {
        return;
      }

      if (posRes.status === 'fulfilled' && Array.isArray(posRes.value)) {
        this.positions = posRes.value;
      }
      if (recRes.status === 'fulfilled' && recRes.value?.items) {
        this.records = recRes.value.items;
      }

      if (statsRes.status === 'fulfilled') {
        const val = statsRes.value;
        if (val && typeof val === 'object' && val.total_trades !== undefined) {
          this.stats = val;
          this.statsError = null;
        } else {
          this.stats = null;
          this.statsError = '统计数据为空或无法解析，请重试';
        }
      } else {
        this.stats = null;
        const errMsg = statsRes.reason?.message || '统计加载失败，请重试';
        this.statsError = errMsg;
      }

      if (stratRes.status === 'fulfilled' && stratRes.value) {
        this.strategyData = stratRes.value;
      }
    } catch (err) {
      // safe fallback
    } finally {
      if (currentReqSeq === this.reqSequence) {
        this.isLoading = false;
        this.isRefreshing = false;
        this.isStatsInitialLoaded = true;
      }
    }
  }

  getMetrics() {
    return computeMetrics({
      positions: this.positions,
      stats: this.stats,
      statsError: this.statsError,
      isStatsInitialLoaded: this.isStatsInitialLoaded,
    });
  }
}

async function runAllTests() {
  const results = [];

  // AC01 首次加载
  {
    const engine = new SimulationStateEngine();
    const m = engine.getMetrics();
    assert.strictEqual(m.isStatsAvailable, false);
    assert.strictEqual(m.totalAssets, null, '首次加载中总资产应为 null(--)');
    assert.strictEqual(m.availableCash, null, '首次加载中可用现金应为 null(--)');
    assert.strictEqual(m.totalPnlRatio, null, '首次加载中收益率应为 null(--)');
    assert.strictEqual(m.winRateDisplay, '--', '首次加载中胜率应为 --');
    assert.strictEqual(m.legCountDisplay, '(-- 盈利 / -- 平仓腿)');
    assert.strictEqual(m.realizedDisplay, '--', '首次加载中已实现盈亏应为 --');
    results.push({ id: 'AC01', name: '首次加载状态', pass: true });
  }

  // AC02 有效零值
  {
    const engine = new SimulationStateEngine();
    await engine.loadAllData(false, {
      getSimPositions: () => Promise.resolve([]),
      getSimRecords: () => Promise.resolve({ items: [] }),
      getSimStats: () => Promise.resolve({
        total_trades: 2,
        win_trades: 0,
        loss_trades: 1,
        closed_trades: 1,
        win_rate: 0,
        closed_leg_win_rate: 0,
        payoff_ratio: null,
        total_pnl: -100,
        total_realized_pnl: -100,
        available_cash: 999900,
        market_value: 0,
        total_asset: 999900,
      }),
      getClassicStrategies: () => Promise.resolve(null),
    });
    const m = engine.getMetrics();
    assert.strictEqual(m.winRateDisplay, '0%', '胜率应显示 0%');
    assert.strictEqual(m.legCountDisplay, '(0 盈利 / 1 平仓腿)', '腿数应展示 0/1');
    assert.strictEqual(m.realizedDisplay, '-100.00 元', '已实现应展示 -100.00 元');
    assert.strictEqual(m.payoffDisplay, '--', '盈亏比应为 --');
    assert.strictEqual(m.sampleNote, '盈亏样本不足', '说明样本不足');
    assert.strictEqual(m.statsError, null, '无加载失败提示');
    results.push({ id: 'AC02', name: '有效零值', pass: true });
  }

  // AC03 无平仓
  {
    const engine = new SimulationStateEngine();
    await engine.loadAllData(false, {
      getSimPositions: () => Promise.resolve([{
        code: '600519',
        name: '贵州茅台',
        quantity: 100,
        avg_cost: 10.0,
        total_cost: 1000.0,
        current_price: 10.0,
        market_value: 1000.0,
        floating_pnl: 0.0,
        floating_pnl_pct: 0.0,
      }]),
      getSimRecords: () => Promise.resolve({ items: [] }),
      getSimStats: () => Promise.resolve({
        total_trades: 1,
        win_trades: 0,
        loss_trades: 0,
        closed_trades: 0,
        win_rate: null,
        closed_leg_win_rate: null,
        payoff_ratio: null,
        total_pnl: 0,
        total_realized_pnl: 0,
        available_cash: 999000,
        market_value: 1000,
        total_asset: 1000000,
      }),
      getClassicStrategies: () => Promise.resolve(null),
    });
    const m = engine.getMetrics();
    assert.strictEqual(m.sampleNote, '暂无平仓样本');
    assert.strictEqual(m.winRateDisplay, '--');
    assert.strictEqual(m.payoffDisplay, '--');
    assert.strictEqual(m.realizedDisplay, '0.00 元');
    assert.strictEqual(m.legCountDisplay, '(0 盈利 / 0 平仓腿)');
    assert.strictEqual(m.availableCash, 999000.0);
    assert.strictEqual(m.totalAssets, 1000000.0);
    assert.strictEqual(m.statsError, null);
    results.push({ id: 'AC03', name: '无平仓样本', pass: true });
  }

  // AC04 首次 409
  {
    const engine = new SimulationStateEngine();
    await engine.loadAllData(false, {
      getSimPositions: () => Promise.resolve([]),
      getSimRecords: () => Promise.resolve({ items: [] }),
      getSimStats: () => Promise.reject(new Error('模拟交易统计失败: 流水 ID 42 存在超卖异常')),
      getClassicStrategies: () => Promise.resolve(null),
    });
    const m = engine.getMetrics();
    assert.strictEqual(m.statsError, '模拟交易统计失败: 流水 ID 42 存在超卖异常');
    assert.strictEqual(m.isStatsAvailable, false);
    assert.strictEqual(m.totalAssets, null, '总资产必须为 --');
    assert.strictEqual(m.availableCash, null, '可用现金必须为 --');
    assert.strictEqual(m.totalPnlRatio, null, '收益率必须为 --');
    assert.strictEqual(m.cashRatio, null, '现金储备率必须为 --');
    assert.strictEqual(m.positionRatio, null, '仓位比例必须为 --');
    assert.strictEqual(m.winRateDisplay, '--');
    assert.strictEqual(m.legCountDisplay, '(-- 盈利 / -- 平仓腿)');
    assert.strictEqual(m.realizedDisplay, '--');
    results.push({ id: 'AC04', name: '首次 409', pass: true });
  }

  // AC05 成功后失败
  {
    const engine = new SimulationStateEngine();
    await engine.loadAllData(false, {
      getSimPositions: () => Promise.resolve([]),
      getSimRecords: () => Promise.resolve({ items: [] }),
      getSimStats: () => Promise.resolve({
        total_trades: 4,
        win_trades: 2,
        loss_trades: 2,
        closed_trades: 4,
        win_rate: 50,
        closed_leg_win_rate: 50,
        payoff_ratio: 1.5,
        total_pnl: 100,
        total_realized_pnl: 100,
        available_cash: 1000100,
        market_value: 0,
        total_asset: 1000100,
      }),
      getClassicStrategies: () => Promise.resolve(null),
    });
    assert.strictEqual(engine.getMetrics().winRateDisplay, '50%');

    await engine.loadAllData(true, {
      getSimPositions: () => Promise.resolve([]),
      getSimRecords: () => Promise.resolve({ items: [] }),
      getSimStats: () => Promise.reject(new Error('模拟交易统计失败: 流水 ID 42 存在超卖异常')),
      getClassicStrategies: () => Promise.resolve(null),
    });
    const m = engine.getMetrics();
    assert.strictEqual(engine.stats, null, '原成功 stats 必须清除');
    assert.strictEqual(m.statsError, '模拟交易统计失败: 流水 ID 42 存在超卖异常');
    assert.strictEqual(m.totalAssets, null, '依赖资金指标不能展示旧值');
    assert.strictEqual(m.availableCash, null, '可用现金不能展示旧值');
    assert.strictEqual(m.winRateDisplay, '--');
    assert.strictEqual(m.realizedDisplay, '--');
    results.push({ id: 'AC05', name: '成功后失败清空旧值', pass: true });
  }

  // AC06 通用故障 (网络断开/HTTP 500/200 空统计)
  {
    const engineNet = new SimulationStateEngine();
    await engineNet.loadAllData(false, {
      getSimStats: () => Promise.reject(new TypeError('Failed to fetch')),
    });
    assert.strictEqual(engineNet.getMetrics().statsError, 'Failed to fetch');
    assert.strictEqual(engineNet.getMetrics().totalAssets, null);

    const engine500 = new SimulationStateEngine();
    await engine500.loadAllData(false, {
      getSimStats: () => Promise.reject(new Error('后端服务内部错误 (500 Internal Server Error)')),
    });
    assert.strictEqual(engine500.getMetrics().statsError, '后端服务内部错误 (500 Internal Server Error)');
    assert.strictEqual(engine500.getMetrics().totalAssets, null);

    const engineEmpty = new SimulationStateEngine();
    await engineEmpty.loadAllData(false, {
      getSimStats: () => Promise.resolve(null),
    });
    assert.strictEqual(engineEmpty.getMetrics().statsError, '统计数据为空或无法解析，请重试');
    assert.strictEqual(engineEmpty.getMetrics().totalAssets, null);

    results.push({ id: 'AC06', name: '通用故障分类处理', pass: true });
  }

  // AC07 恢复成功
  {
    const engine = new SimulationStateEngine();
    await engine.loadAllData(false, {
      getSimStats: () => Promise.reject(new Error('模拟交易统计失败: 流水 ID 42 存在超卖异常')),
    });
    assert.strictEqual(engine.getMetrics().isStatsAvailable, false);

    await engine.loadAllData(true, {
      getSimStats: () => Promise.resolve({
        total_trades: 2,
        win_trades: 1,
        loss_trades: 1,
        closed_trades: 2,
        win_rate: 50,
        closed_leg_win_rate: 50,
        payoff_ratio: 2.0,
        total_pnl: 100,
        total_realized_pnl: 100,
        available_cash: 1000100,
        market_value: 0,
        total_asset: 1000100,
      }),
    });
    const m = engine.getMetrics();
    assert.strictEqual(m.isStatsAvailable, true);
    assert.strictEqual(m.statsError, null, '错误提示已清除');
    assert.strictEqual(m.winRateDisplay, '50%');
    assert.strictEqual(m.totalAssets, 1000100.0, '资产指标恢复');
    results.push({ id: 'AC07', name: '刷新恢复成功', pass: true });
  }

  // AC08 部分接口失败隔离
  {
    const engine = new SimulationStateEngine();
    await engine.loadAllData(false, {
      getSimPositions: () => Promise.resolve([{
        code: '000001',
        name: '平安银行',
        quantity: 200,
        avg_cost: 10.0,
        total_cost: 2000.0,
        current_price: 11.0,
        market_value: 2200.0,
        floating_pnl: 200.0,
        floating_pnl_pct: 10.0,
      }]),
      getSimRecords: () => Promise.resolve({ items: [{ id: 1, code: '000001', direction: 'buy', price: 10, quantity: 200, amount: 2000, trade_time: '2026-10-28 10:00:00' }] }),
      getSimStats: () => Promise.reject(new Error('模拟交易统计失败: 流水 ID 42 存在超卖异常')),
      getClassicStrategies: () => Promise.resolve({ strategies: [] }),
    });
    assert.strictEqual(engine.positions.length, 1, '持仓继续保留显示');
    assert.strictEqual(engine.records.length, 1, '流水继续保留显示');
    assert.strictEqual(engine.getMetrics().totalMarketValue, 2200.0, '市值继续计算');
    assert.strictEqual(engine.getMetrics().totalFloatingPnl, 200.0, '浮动盈亏继续计算');
    assert.strictEqual(engine.getMetrics().statsError, '模拟交易统计失败: 流水 ID 42 存在超卖异常', '统计区域明确失败');

    await engine.loadAllData(true, {
      getSimPositions: () => Promise.resolve([]),
      getSimRecords: () => Promise.resolve({ items: [] }),
      getSimStats: () => Promise.resolve({
        total_trades: 1,
        win_trades: 1,
        loss_trades: 0,
        closed_trades: 1,
        win_rate: 100,
        closed_leg_win_rate: 100,
        payoff_ratio: null,
        total_pnl: 50,
        total_realized_pnl: 50,
        available_cash: 1000050,
        market_value: 0,
        total_asset: 1000050,
      }),
      getClassicStrategies: () => Promise.reject(new Error('Strategy service 503')),
    });
    assert.strictEqual(engine.getMetrics().isStatsAvailable, true, '策略失败不得把成功统计标成失败');
    assert.strictEqual(engine.getMetrics().winRateDisplay, '100%');
    results.push({ id: 'AC08', name: '部分接口失败隔离', pass: true });
  }

  // AC09 提示独立性
  {
    const engine = new SimulationStateEngine();
    await engine.loadAllData(false, {
      getSimStats: () => Promise.reject(new Error('模拟交易统计失败: 流水 ID 42 存在超卖异常')),
    });
    assert.strictEqual(engine.statsError, '模拟交易统计失败: 流水 ID 42 存在超卖异常');
    
    engine.showNotice('这是一条 4.5 秒后自动消失的交易通知', 'success');
    assert.strictEqual(engine.actionNotice.text, '这是一条 4.5 秒后自动消失的交易通知');
    engine.clearNotice();
    assert.strictEqual(engine.actionNotice, null);
    assert.strictEqual(engine.statsError, '模拟交易统计失败: 流水 ID 42 存在超卖异常', '统计提示不随交易通知消失');
    results.push({ id: 'AC09', name: '提示独立性', pass: true });
  }

  // AC10 请求顺序防竞态
  {
    const engine = new SimulationStateEngine();
    let resolveReqA;
    let resolveReqB;

    const promiseA = new Promise((resolve) => { resolveReqA = resolve; });
    const promiseB = new Promise((resolve) => { resolveReqB = resolve; });

    const runA = engine.loadAllData(false, {
      getSimStats: () => promiseA,
    });
    const runB = engine.loadAllData(true, {
      getSimStats: () => promiseB,
    });

    resolveReqB({
      total_trades: 2,
      win_trades: 1,
      loss_trades: 1,
      closed_trades: 2,
      win_rate: 50,
      closed_leg_win_rate: 50,
      payoff_ratio: 1.0,
      total_pnl: 10,
      total_realized_pnl: 10,
      available_cash: 1000010,
      market_value: 0,
      total_asset: 1000010,
    });
    await runB;
    assert.strictEqual(engine.getMetrics().winRateDisplay, '50%');

    resolveReqA({
      total_trades: 1,
      win_trades: 1,
      loss_trades: 0,
      closed_trades: 1,
      win_rate: 100,
      closed_leg_win_rate: 100,
      payoff_ratio: null,
      total_pnl: 50,
      total_realized_pnl: 50,
      available_cash: 1000050,
      market_value: 0,
      total_asset: 1000050,
    });
    await runA;

    assert.strictEqual(engine.getMetrics().winRateDisplay, '50%', '较早结果不得覆盖新结果');
    assert.strictEqual(engine.getMetrics().totalRealizedPnl, 10, '已实现盈亏服从请求 B');
    results.push({ id: 'AC10', name: '请求顺序防竞态控制', pass: true });
  }

  // AC11 total_realized_pnl 缺失/null 保护 (Codex 返修项 1)
  {
    const engine = new SimulationStateEngine();
    await engine.loadAllData(false, {
      getSimStats: () => Promise.resolve({
        total_trades: 2,
        win_trades: 1,
        loss_trades: 1,
        closed_trades: 2,
        win_rate: 50,
        closed_leg_win_rate: 50,
        payoff_ratio: 1.0,
        total_pnl: 0,
        total_realized_pnl: undefined, // 缺失
        available_cash: 1000000,
        market_value: 0,
        total_asset: 1000000,
      }),
    });
    const m = engine.getMetrics();
    assert.strictEqual(m.isRealizedPnlAvailable, false, 'total_realized_pnl 缺失不可用');
    assert.strictEqual(m.totalRealizedPnl, null, '已实现盈亏为 null');
    assert.strictEqual(m.realizedDisplay, '--', '已实现盈亏显示 --');
    assert.strictEqual(m.availableCash, null, '可用现金不可用，显示 --');
    assert.strictEqual(m.totalAssets, null, '总资产不可用，显示 --');
    assert.strictEqual(m.totalPnlRatio, null, '收益率不可用，显示 --');
    assert.strictEqual(m.cashRatio, null, '现金储备率显示 --');
    assert.strictEqual(m.positionRatio, null, '仓位比例显示 --');
    // 其他统计字段正常展示
    assert.strictEqual(m.winRateDisplay, '50%', '胜率字段正常显示');
    assert.strictEqual(m.payoffDisplay, '1 : 1', '盈亏比正常显示');
    assert.strictEqual(m.legCountDisplay, '(1 盈利 / 2 平仓腿)', '平仓腿正常显示');
    results.push({ id: 'AC11', name: '已实现盈亏缺失展示--', pass: true });
  }

  // AC12 closed_trades 缺失/null 保护 (Codex 返修项 2)
  {
    const engine = new SimulationStateEngine();
    await engine.loadAllData(false, {
      getSimStats: () => Promise.resolve({
        total_trades: 10, // 买卖总流水 10 笔
        win_trades: 2,
        loss_trades: 1,
        closed_trades: undefined, // 平仓统计缺失
        win_rate: null,
        closed_leg_win_rate: null,
        payoff_ratio: null,
        total_pnl: 100,
        total_realized_pnl: 100,
        available_cash: 1000100,
        market_value: 0,
        total_asset: 1000100,
      }),
    });
    const m = engine.getMetrics();
    // 必须显示 --，不得拿 10 冒充平仓腿
    assert.strictEqual(m.legCountDisplay, '(-- 盈利 / -- 平仓腿)', '平仓腿缺失必须展示 --');
    // 且不得误报“暂无平仓样本”
    assert.strictEqual(m.sampleNote, null, '平仓腿缺失不得显示暂无平仓样本');
    results.push({ id: 'AC12', name: '平仓腿数缺失保护', pass: true });
  }

  console.log(JSON.stringify({ status: 'ALL_PASSED', total: results.length, details: results }, null, 2));
}

runAllTests().catch((err) => {
  console.error('AC Verification Failed:', err);
  process.exit(1);
});
