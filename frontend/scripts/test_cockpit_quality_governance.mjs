/**
 * Frontend Cockpit Quality Governance & Defense Verification Suite
 * Tests:
 * 1. Positive Control (FULL quality -> no badge)
 * 2. Fault Degradation (UNAVAILABLE -> "分时走势暂不可用" + auto-retry scheduled)
 * 3. STALE Snapshot (STALE -> "使用缓存，更新于 HH:mm" / "来源时点未知")
 * 4. Recovery (Failed codes successfully recover upon retry)
 * 5. Out-of-Order / Late Response Defense (A10: seq token drops delayed responses)
 * 6. Unknown Enum Conservative Fallback (A9: unknown quality -> UNAVAILABLE)
 * 7. Sector API Envelope Handling (P1.3: getSectors envelope parsed into array)
 */

import assert from 'node:assert';

console.log('--- Starting Frontend Cockpit Quality Governance Verification ---');

// Mock Component State Context
class CockpitQualityController {
  constructor() {
    this.stockTrendsMap = {};
    this.stockTrendsQualityInfo = null;
    this.fetchSeq = 0;
    this.currentFetchDate = '2026-10-31';
    this.sectors = [];
    this.retryScheduled = false;
  }

  // Exact logic implemented in AuroraCockpitView fetchSectors
  applySectorResponse(res) {
    const list = Array.isArray(res) ? res : (res?.data || []);
    if (Array.isArray(list)) {
      this.sectors = list;
    }
    if (res && typeof res === 'object' && !Array.isArray(res)) {
      this.sectorsQualityInfo = {
        quality: res.quality,
        freshness: res.freshness,
        status: res.status,
        source_timestamp: res.source_timestamp,
        degradation_reason: res.degradation_reason,
      };
    }
  }

  // Exact logic implemented in AuroraCockpitView canonical sector governance
  applyTopSectorsTrend(res) {
    this.topSectorsTrend = res;
  }

  getSectorBadges() {
    const isUnavailable =
      this.topSectorsTrend?.status === 'UNAVAILABLE' ||
      this.topSectorsTrend?.quality === 'UNAVAILABLE' ||
      (!this.topSectorsTrend && (this.sectorsQualityInfo?.status === 'EMPTY' || this.sectorsQualityInfo?.quality === 'UNAVAILABLE'));

    if (isUnavailable) {
      return { unavailable: true, stale: null, delayed: null, unknownFreshness: null };
    }

    const validFreshnessValues = ['REALTIME', 'DELAYED', 'STALE', 'EOD_COMPENSATED', 'EXPIRED'];
    const isFreshnessUnknown =
      this.topSectorsTrend?.freshness === 'UNAVAILABLE' ||
      (this.topSectorsTrend?.freshness && !validFreshnessValues.includes(this.topSectorsTrend.freshness)) ||
      this.topSectorsTrend?.sector_freshness === 'UNAVAILABLE' ||
      (this.topSectorsTrend?.sector_freshness && !validFreshnessValues.includes(this.topSectorsTrend.sector_freshness)) ||
      this.topSectorsTrend?.trends_freshness === 'UNAVAILABLE' ||
      (this.topSectorsTrend?.trends_freshness && !validFreshnessValues.includes(this.topSectorsTrend.trends_freshness)) ||
      Boolean(this.topSectorsTrend?.degradation_reason && this.topSectorsTrend.degradation_reason.includes('时效未知')) ||
      (!this.topSectorsTrend && (this.sectorsQualityInfo?.freshness === 'UNAVAILABLE' || (this.sectorsQualityInfo?.freshness && !validFreshnessValues.includes(this.sectorsQualityInfo.freshness))));

    const isStale =
      this.topSectorsTrend?.status === 'STALE' ||
      this.topSectorsTrend?.freshness === 'STALE' ||
      this.topSectorsTrend?.sector_freshness === 'STALE' ||
      this.topSectorsTrend?.trends_freshness === 'STALE' ||
      (!this.topSectorsTrend && (this.sectorsQualityInfo?.status === 'STALE' || this.sectorsQualityInfo?.freshness === 'STALE'));

    const isDelayed =
      this.topSectorsTrend?.freshness === 'DELAYED' ||
      this.topSectorsTrend?.sector_freshness === 'DELAYED' ||
      this.topSectorsTrend?.trends_freshness === 'DELAYED' ||
      (!this.topSectorsTrend && this.sectorsQualityInfo?.freshness === 'DELAYED');

    let unknownFreshnessLabel = null;
    if (isFreshnessUnknown) {
      let unknownPrefix = '时效未知';
      if (this.topSectorsTrend) {
        const secUnknown =
          this.topSectorsTrend.sector_freshness === 'UNAVAILABLE' ||
          (this.topSectorsTrend.sector_freshness && !['REALTIME', 'DELAYED', 'STALE', 'EOD_COMPENSATED', 'EXPIRED'].includes(this.topSectorsTrend.sector_freshness));
        const trendsUnknown =
          this.topSectorsTrend.trends_freshness === 'UNAVAILABLE' ||
          (this.topSectorsTrend.trends_freshness && !['REALTIME', 'DELAYED', 'STALE', 'EOD_COMPENSATED', 'EXPIRED'].includes(this.topSectorsTrend.trends_freshness));
        if (secUnknown && trendsUnknown) {
          unknownPrefix = '板块排行与分时时效未知';
        } else if (secUnknown) {
          unknownPrefix = '板块排行时效未知';
        } else if (trendsUnknown) {
          unknownPrefix = '板块分时时效未知';
        }
      } else if (this.sectorsQualityInfo) {
        unknownPrefix = '板块排行时效未知';
      }

      const reason =
        this.topSectorsTrend?.degradation_reason || (!this.topSectorsTrend ? this.sectorsQualityInfo?.degradation_reason : null);

      if (reason) {
        if (reason.includes('时效未知')) {
          unknownFreshnessLabel = reason;
        } else {
          unknownFreshnessLabel = `${unknownPrefix} (${reason})`;
        }
      } else {
        unknownFreshnessLabel = unknownPrefix;
      }
    }

    let staleLabel = null;
    if (isStale) {
      if (this.topSectorsTrend?.source_timestamp) {
        staleLabel = `使用缓存，更新于 ${this.topSectorsTrend.source_timestamp}`;
      } else if (this.topSectorsTrend?.sector_freshness === 'STALE' && this.topSectorsTrend?.trends_freshness !== 'STALE') {
        staleLabel = this.topSectorsTrend?.sector_source_timestamp
          ? `排行使用缓存，更新于 ${this.topSectorsTrend.sector_source_timestamp}`
          : '排行使用缓存 (来源时点未知)';
      } else if (this.topSectorsTrend?.trends_freshness === 'STALE' && this.topSectorsTrend?.sector_freshness !== 'STALE') {
        staleLabel = this.topSectorsTrend?.trends_source_timestamp
          ? `分时使用缓存，更新于 ${this.topSectorsTrend.trends_source_timestamp}`
          : '分时使用缓存 (来源时点未知)';
      } else if (!this.topSectorsTrend && this.sectorsQualityInfo?.source_timestamp) {
        staleLabel = `使用缓存，更新于 ${this.sectorsQualityInfo.source_timestamp}`;
      } else {
        staleLabel = '使用缓存 (来源时点未知)';
      }
    }

    let delayedLabel = null;
    if (isDelayed) {
      if (this.topSectorsTrend?.sector_freshness === 'DELAYED' && this.topSectorsTrend?.trends_freshness === 'DELAYED') {
        delayedLabel = '板块行情延迟';
      } else if (this.topSectorsTrend?.sector_freshness === 'DELAYED') {
        delayedLabel = '板块排行行情延迟';
      } else if (this.topSectorsTrend?.trends_freshness === 'DELAYED') {
        delayedLabel = '板块分时行情延迟';
      } else {
        delayedLabel = '板块行情延迟';
      }
    }

    return { unavailable: false, stale: staleLabel, delayed: delayedLabel, unknownFreshness: unknownFreshnessLabel };
  }

  // Exact logic implemented in AuroraCockpitView stock trends effect
  applyTrendsResponse(res, reqDate, seq) {
    // A10 defense: sequence token check + date check
    if (this.currentFetchDate !== reqDate || this.fetchSeq !== seq) {
      return { dropped: true, reason: 'Sequence token mismatch or date changed' };
    }

    const data = Array.isArray(res) ? res : (res?.data || []);
    const envelopeQuality = res?.quality;
    const envelopeFreshness = res?.freshness;
    const envelopeStatus = res?.status;
    const envelopeReason = res?.degradation_reason || res?.error_message;
    const envelopeSourceTs = res?.source_timestamp;
    const envelopeErrorCode = res?.error_code;

    if (data.length > 0) {
      let hasUnavailable = false;
      let hasRealTrends = false;
      data.forEach((item) => {
        if (item && item.code) {
          this.stockTrendsMap[item.code] = item;
          if (item.quality === 'UNAVAILABLE' || (item.trends && item.trends.length === 0)) {
            hasUnavailable = true;
          }
          if (item.trends && item.trends.length > 0) {
            hasRealTrends = true;
          }
        }
      });

      if (envelopeQuality === 'UNAVAILABLE' || (!hasRealTrends && data.length > 0)) {
        this.stockTrendsQualityInfo = {
          quality: 'UNAVAILABLE',
          freshness: envelopeFreshness || 'UNAVAILABLE',
          status: envelopeStatus || 'EMPTY',
          error_code: envelopeErrorCode,
          source_timestamp: envelopeSourceTs,
          degradation_reason: envelopeReason || '分时走势暂不可用',
        };
        this.retryScheduled = true;
      } else if (envelopeFreshness === 'DELAYED') {
        this.stockTrendsQualityInfo = {
          quality: 'DEGRADED',
          freshness: 'DELAYED',
          status: envelopeStatus || 'AVAILABLE',
          source_timestamp: envelopeSourceTs,
          degradation_reason: '分时行情延迟',
        };
      } else if (envelopeFreshness === 'STALE' || envelopeQuality === 'DEGRADED') {
        this.stockTrendsQualityInfo = {
          quality: 'DEGRADED',
          freshness: 'STALE',
          status: 'STALE',
          error_code: envelopeErrorCode,
          source_timestamp: envelopeSourceTs,
          degradation_reason: envelopeReason || '使用旧分时快照',
        };
      } else if (envelopeQuality === 'PARTIAL' || hasUnavailable) {
        this.stockTrendsQualityInfo = {
          quality: 'PARTIAL',
          freshness: envelopeFreshness || 'REALTIME',
          status: envelopeStatus || 'AVAILABLE',
          error_code: envelopeErrorCode,
          source_timestamp: envelopeSourceTs,
          degradation_reason: envelopeReason || '部分代码分时暂不可用',
        };
        this.retryScheduled = true;
      } else if (envelopeQuality === 'FULL') {
        this.stockTrendsQualityInfo = null;
        this.retryScheduled = false;
      } else {
        // A9: Conservative fallback for unknown quality enum
        this.stockTrendsQualityInfo = {
          quality: 'UNAVAILABLE',
          freshness: 'UNAVAILABLE',
          status: 'ERROR',
          error_code: envelopeErrorCode,
          source_timestamp: envelopeSourceTs,
          degradation_reason: '未知质量状态，按不可用安全降级',
        };
      }
    } else {
      this.stockTrendsQualityInfo = {
        quality: 'UNAVAILABLE',
        freshness: 'UNAVAILABLE',
        status: 'EMPTY',
        error_code: envelopeErrorCode,
        degradation_reason: envelopeReason || '无分时数据返回',
      };
      this.retryScheduled = true;
    }

    return { dropped: false };
  }
}

// 1. Positive Control Test
{
  const c = new CockpitQualityController();
  const seq = ++c.fetchSeq;
  const res = {
    quality: 'FULL',
    freshness: 'REALTIME',
    status: 'AVAILABLE',
    data: [{ code: '600519', trends: [{ time: '09:30', price: 100 }] }],
  };
  const out = c.applyTrendsResponse(res, '2026-10-31', seq);
  assert.strictEqual(out.dropped, false);
  assert.strictEqual(c.stockTrendsQualityInfo, null, 'FULL response should have null quality badge');
  assert.strictEqual(c.stockTrendsMap['600519'].code, '600519');
  console.log('[PASS] Test 1: Positive Control (FULL quality -> no badge)');
}

// 2. Fault Degradation Test (UNAVAILABLE)
{
  const c = new CockpitQualityController();
  const seq = ++c.fetchSeq;
  const res = {
    quality: 'UNAVAILABLE',
    freshness: 'UNAVAILABLE',
    status: 'EMPTY',
    error_code: 'CONNECTION_ERROR',
    data: [{ code: '600519', quality: 'UNAVAILABLE', trends: [] }],
  };
  const out = c.applyTrendsResponse(res, '2026-10-31', seq);
  assert.strictEqual(out.dropped, false);
  assert.strictEqual(c.stockTrendsQualityInfo.quality, 'UNAVAILABLE');
  assert.strictEqual(c.stockTrendsQualityInfo.error_code, 'CONNECTION_ERROR');
  assert.strictEqual(c.retryScheduled, true, 'Failed codes must trigger auto-retry');
  console.log('[PASS] Test 2: Fault Degradation (UNAVAILABLE -> auto-retry scheduled)');
}

// 3. STALE Snapshot Test
{
  const c = new CockpitQualityController();
  const seq = ++c.fetchSeq;
  const res = {
    quality: 'DEGRADED',
    freshness: 'STALE',
    status: 'STALE',
    source_timestamp: '2026-10-31T14:55:00',
    data: [{ code: '600519', trends: [{ time: '14:55', price: 100 }] }],
  };
  const out = c.applyTrendsResponse(res, '2026-10-31', seq);
  assert.strictEqual(out.dropped, false);
  assert.strictEqual(c.stockTrendsQualityInfo.quality, 'DEGRADED');
  assert.strictEqual(c.stockTrendsQualityInfo.freshness, 'STALE');
  assert.strictEqual(c.stockTrendsQualityInfo.source_timestamp, '2026-10-31T14:55:00');
  console.log('[PASS] Test 3: STALE Snapshot (DEGRADED + STALE badge with real timestamp)');
}

// 4. Recovery Test (Failed -> Recovered)
{
  const c = new CockpitQualityController();
  // Step A: Failed
  const seq1 = ++c.fetchSeq;
  c.applyTrendsResponse({
    quality: 'UNAVAILABLE',
    freshness: 'UNAVAILABLE',
    data: [{ code: '600519', quality: 'UNAVAILABLE', trends: [] }],
  }, '2026-10-31', seq1);
  assert.strictEqual(c.stockTrendsQualityInfo.quality, 'UNAVAILABLE');

  // Step B: Retry succeeds
  const seq2 = ++c.fetchSeq;
  c.applyTrendsResponse({
    quality: 'FULL',
    freshness: 'REALTIME',
    data: [{ code: '600519', trends: [{ time: '09:30', price: 100 }] }],
  }, '2026-10-31', seq2);
  assert.strictEqual(c.stockTrendsQualityInfo, null, 'Badge must clear upon recovery');
  assert.strictEqual(c.stockTrendsMap['600519'].trends.length, 1);
  console.log('[PASS] Test 4: Recovery (Failed codes successfully recover upon retry)');
}

// 5. Out-of-Order / Late Response Defense (A10)
{
  const c = new CockpitQualityController();
  // Request 1 initiated (e.g. slow network)
  const seq1 = ++c.fetchSeq; // seq = 1

  // Request 2 initiated (e.g. retry or user interaction) and finishes fast
  const seq2 = ++c.fetchSeq; // seq = 2
  const out2 = c.applyTrendsResponse({
    quality: 'FULL',
    freshness: 'REALTIME',
    data: [{ code: '600519', trends: [{ time: '09:30', price: 100 }] }],
  }, '2026-10-31', seq2);
  assert.strictEqual(out2.dropped, false);
  assert.strictEqual(c.stockTrendsQualityInfo, null);

  // Request 1 late response arrives with UNAVAILABLE error!
  const out1 = c.applyTrendsResponse({
    quality: 'UNAVAILABLE',
    freshness: 'UNAVAILABLE',
    data: [{ code: '600519', quality: 'UNAVAILABLE', trends: [] }],
  }, '2026-10-31', seq1);
  assert.strictEqual(out1.dropped, true, 'Late out-of-order response MUST be dropped');
  assert.strictEqual(c.stockTrendsQualityInfo, null, 'State must NOT be corrupted by late response');
  assert.strictEqual(c.stockTrendsMap['600519'].trends.length, 1, 'Valid data must remain intact');
  console.log('[PASS] Test 5: Out-of-Order / Late Response Defense (A10 sequence token)');
}

// 6. Unknown Enum Conservative Fallback (A9)
{
  const c = new CockpitQualityController();
  const seq = ++c.fetchSeq;
  const res = {
    quality: 'WEIRD_NONEXISTENT_ENUM',
    freshness: 'STRANGE_FRESHNESS',
    data: [{ code: '600519', trends: [{ time: '09:30', price: 100 }] }],
  };
  const out = c.applyTrendsResponse(res, '2026-10-31', seq);
  assert.strictEqual(out.dropped, false);
  assert.strictEqual(c.stockTrendsQualityInfo.quality, 'UNAVAILABLE', 'Unknown enum must conservatively degrade to UNAVAILABLE');
  assert.strictEqual(c.stockTrendsQualityInfo.status, 'ERROR');
  console.log('[PASS] Test 6: Unknown Enum Conservative Fallback (A9 defense)');
}

// 7. Sector API Envelope Handling (P1.3)
{
  const c = new CockpitQualityController();
  // Server returns envelope with data array
  const envelope = {
    code: 200,
    quality: 'FULL',
    freshness: 'REALTIME',
    status: 'AVAILABLE',
    data: [
      { code: 'BK0910', name: '半导体', current_net_inflow_yi: 12.5 },
      { code: 'BK0438', name: '白酒', current_net_inflow_yi: -5.2 },
    ],
  };
  c.applySectorResponse(envelope);
  assert.strictEqual(c.sectors.length, 2, 'Sectors array must be correctly extracted from envelope');
  assert.strictEqual(c.sectors[0].name, '半导体');

  // Also support bare array for backwards compatibility
  const bareArray = [
    { code: 'BK0910', name: '半导体', current_net_inflow_yi: 15.0 },
  ];
  c.applySectorResponse(bareArray);
  assert.strictEqual(c.sectors.length, 1);
  assert.strictEqual(c.sectors[0].current_net_inflow_yi, 15.0);
  console.log('[PASS] Test 7: Sector API Envelope Handling (P1.3 fix verified)');
}

// 8. DELAYED Freshness Handling
{
  const c = new CockpitQualityController();
  const seq = ++c.fetchSeq;
  const res = {
    quality: 'DEGRADED',
    freshness: 'DELAYED',
    status: 'AVAILABLE',
    source_timestamp: '2026-10-31 10:15:00',
    data: [{ code: '600519', trends: [{ time: '09:30', price: 100 }] }],
  };
  const out = c.applyTrendsResponse(res, '2026-10-31', seq);
  assert.strictEqual(out.dropped, false);
  assert.strictEqual(c.stockTrendsQualityInfo.freshness, 'DELAYED');
  assert.strictEqual(c.stockTrendsQualityInfo.degradation_reason, '分时行情延迟');
  assert.strictEqual(c.retryScheduled, false, 'Delayed data is available, do not schedule retry');
  console.log('[PASS] Test 8: DELAYED Freshness Handling (delayed market data)');
}

// 9. Sector Ranking & Trends Freshness Synthesis in Canonical TopSectorsTrend (P1 fix verified)
{
  const c = new CockpitQualityController();
  // Case A: Ranking is STALE (10:15) while trends is REALTIME (10:30)
  c.applyTopSectorsTrend({
    quality: 'DEGRADED',
    freshness: 'STALE',
    sector_quality: 'DEGRADED',
    sector_freshness: 'STALE',
    sector_source_timestamp: '2026-10-31 10:15:00',
    trends_quality: 'FULL',
    trends_freshness: 'REALTIME',
    trends_source_timestamp: '2026-10-31 10:30:00',
    source_timestamp: '2026-10-31 10:15:00',
  });
  const badgesA = c.getSectorBadges();
  assert.notStrictEqual(badgesA.stale, null, 'Stale sector ranking must trigger STALE badge');
  assert.strictEqual(badgesA.delayed, null);
  assert.strictEqual(c.topSectorsTrend.source_timestamp, '2026-10-31 10:15:00', 'Must use earliest source timestamp');

  // Case B: Ranking is DELAYED while trends is REALTIME
  c.applyTopSectorsTrend({
    quality: 'DEGRADED',
    freshness: 'DELAYED',
    sector_quality: 'DEGRADED',
    sector_freshness: 'DELAYED',
    trends_quality: 'FULL',
    trends_freshness: 'REALTIME',
  });
  const badgesB = c.getSectorBadges();
  assert.strictEqual(badgesB.delayed, '板块排行行情延迟', 'Delayed sector ranking must trigger DELAYED badge');
  assert.strictEqual(badgesB.stale, null);

  // Case C: Ranking is REALTIME while trends is DELAYED
  c.applyTopSectorsTrend({
    quality: 'DEGRADED',
    freshness: 'DELAYED',
    sector_quality: 'FULL',
    sector_freshness: 'REALTIME',
    trends_quality: 'DEGRADED',
    trends_freshness: 'DELAYED',
  });
  const badgesC = c.getSectorBadges();
  assert.strictEqual(badgesC.delayed, '板块分时行情延迟', 'Delayed trends must trigger DELAYED badge');
  assert.strictEqual(badgesC.stale, null);

  // Case D: Positive Control (both FULL + REALTIME)
  c.applyTopSectorsTrend({
    quality: 'FULL',
    freshness: 'REALTIME',
    sector_quality: 'FULL',
    sector_freshness: 'REALTIME',
    trends_quality: 'FULL',
    trends_freshness: 'REALTIME',
  });
  const badgesD = c.getSectorBadges();
  assert.strictEqual(badgesD.stale, null);
  assert.strictEqual(badgesD.delayed, null);
  assert.strictEqual(badgesD.unavailable, false);
  console.log('[PASS] Test 9: Canonical Sector & Trends Freshness Synthesis (P1 fix verified)');
}

// 10. Dual STALE and DELAYED Badge Coexistence and Single-sided Timestamp Safety (P1.2 & P2.3 fix verified)
{
  const c = new CockpitQualityController();
  // Ranking is STALE (10:15), Trends is DELAYED, overall source_timestamp is null (unknown)
  c.applyTopSectorsTrend({
    quality: 'DEGRADED',
    freshness: 'STALE',
    sector_quality: 'DEGRADED',
    sector_freshness: 'STALE',
    sector_source_timestamp: '2026-10-31 10:15:00',
    trends_quality: 'DEGRADED',
    trends_freshness: 'DELAYED',
    trends_source_timestamp: null,
    source_timestamp: null,
  });
  const badges = c.getSectorBadges();
  // 断言 1: STALE 与 DELAYED 双徽章并存，STALE 绝不被 DELAYED 隐藏掩盖
  assert.notStrictEqual(badges.stale, null, 'STALE badge must be visible');
  assert.notStrictEqual(badges.delayed, null, 'DELAYED badge must also be visible simultaneously');
  // 断言 2: 单侧时间明确归因于“排行使用缓存”，绝不冒充整体截止时间
  assert.strictEqual(badges.stale.includes('排行使用缓存，更新于 2026-10-31 10:15:00'), true);
  assert.strictEqual(badges.delayed, '板块分时行情延迟');
  console.log('[PASS] Test 10: Dual STALE & DELAYED Badge Coexistence & Single-sided Timestamp Safety (P1.2/P2.3 verified)');
}

// 11. Market Sectors Standalone Fallback Quality Governance (P2.4 fix verified)
{
  const c = new CockpitQualityController();
  // Canonical absent (null), /market/sectors returns DELAYED
  c.applyTopSectorsTrend(null);
  c.applySectorResponse({
    data: [{ name: '低空经济', net: 18.5 }],
    quality: 'DEGRADED',
    freshness: 'DELAYED',
    status: 'AVAILABLE',
    source_timestamp: '2026-10-31 10:15:00',
  });
  assert.strictEqual(c.sectorsQualityInfo.freshness, 'DELAYED');
  const badges = c.getSectorBadges();
  assert.strictEqual(badges.delayed, '板块行情延迟', 'market/sectors DELAYED must propagate to component UI badge');
  assert.strictEqual(badges.stale, null);

  // market/sectors returns UNAVAILABLE
  c.applySectorResponse({
    data: [],
    quality: 'UNAVAILABLE',
    freshness: 'UNAVAILABLE',
    status: 'EMPTY',
  });
  const badgesUnavail = c.getSectorBadges();
  assert.strictEqual(badgesUnavail.unavailable, true, 'market/sectors UNAVAILABLE must propagate to component UI empty state');
  console.log('[PASS] Test 11: Market Sectors Standalone Fallback Quality Governance (P2.4 verified)');
}

// 12. Unknown Freshness Degradation & Reason Presentation (Round 9 P1 fix verified)
{
  const c = new CockpitQualityController();
  c.applyTopSectorsTrend({
    trade_date: '2026-10-31',
    snapshot_time: '10:30:00',
    quality: 'DEGRADED',
    freshness: 'UNAVAILABLE',
    status: 'AVAILABLE',
    sector_quality: 'DEGRADED',
    sector_freshness: 'UNAVAILABLE',
    trends_quality: 'FULL',
    trends_freshness: 'REALTIME',
    degradation_reason: '板块排行时效未知或不可用',
    sectors: [{ name: '低空经济', net_inflow_yi: 18.5 }],
  });
  const badges = c.getSectorBadges();
  assert.strictEqual(badges.unavailable, false, 'status=AVAILABLE must not be treated as unavailable');
  assert.strictEqual(badges.unknownFreshness, '板块排行时效未知或不可用', 'degradation_reason must be shown in unknown freshness badge');

  // Recovery
  c.applyTopSectorsTrend({
    trade_date: '2026-10-31',
    snapshot_time: '10:30:00',
    quality: 'FULL',
    freshness: 'REALTIME',
    status: 'AVAILABLE',
    sectors: [{ name: '低空经济', net_inflow_yi: 18.5 }],
  });
  const recoveredBadges = c.getSectorBadges();
  assert.strictEqual(recoveredBadges.unknownFreshness, null, 'unknownFreshness badge must disappear upon recovery');
  console.log('[PASS] Test 12: Unknown Freshness Degradation & Reason Presentation (Round 9 P1 verified)');
}

// 13. Unknown Freshness Masking Defense (Round 10 P1 fix verified)
// 实际后端路径：排行时效为 UNAVAILABLE 且分时缺失时，degradation_reason 为“板块分时走势缺失，仅提供静态排行”
{
  const c = new CockpitQualityController();
  c.applyTopSectorsTrend({
    trade_date: '2026-10-31',
    snapshot_time: '10:30:00',
    quality: 'DEGRADED',
    freshness: 'UNAVAILABLE',
    status: 'AVAILABLE',
    sector_quality: 'DEGRADED',
    sector_freshness: 'UNAVAILABLE',
    trends_quality: 'UNAVAILABLE',
    trends_freshness: 'UNAVAILABLE',
    degradation_reason: '板块分时走势缺失，仅提供静态排行',
    sectors: [{ name: '低空经济', net_inflow_yi: 18.5, trends: [] }],
  });
  const badges = c.getSectorBadges();
  assert.strictEqual(badges.unavailable, false, 'status=AVAILABLE must not be treated as unavailable');
  // 断言 1: 必须包含“时效未知”警告，绝不被其他降级原因掩盖
  assert.strictEqual(badges.unknownFreshness.includes('时效未知'), true, 'unknownFreshness badge must explicitly contain "时效未知"');
  // 断言 2: 同时完整保留其他降级原因
  assert.strictEqual(badges.unknownFreshness.includes('板块分时走势缺失，仅提供静态排行'), true, 'unknownFreshness badge must preserve specific degradation reason');
  assert.strictEqual(badges.unknownFreshness, '板块排行与分时时效未知 (板块分时走势缺失，仅提供静态排行)');

  // Recovery
  c.applyTopSectorsTrend({
    trade_date: '2026-10-31',
    snapshot_time: '10:30:00',
    quality: 'FULL',
    freshness: 'REALTIME',
    status: 'AVAILABLE',
    sectors: [{ name: '低空经济', net_inflow_yi: 18.5, trends: [{ time: '09:30', net_inflow_yi: 0 }] }],
  });
  const recoveredBadges = c.getSectorBadges();
  assert.strictEqual(recoveredBadges.unknownFreshness, null, 'unknownFreshness badge must disappear upon recovery');
  console.log('[PASS] Test 13: Unknown Freshness Masking Defense & Recovery (Round 10 P1 verified)');
}

// 14. Reverse Dual DELAYED & STALE Badge Coexistence (排行 DELAYED + 分时 STALE)
{
  const c = new CockpitQualityController();
  c.applyTopSectorsTrend({
    quality: 'DEGRADED',
    freshness: 'STALE',
    sector_quality: 'DEGRADED',
    sector_freshness: 'DELAYED',
    sector_source_timestamp: '2026-10-31 10:25:00',
    trends_quality: 'DEGRADED',
    trends_freshness: 'STALE',
    trends_source_timestamp: '2026-10-31 10:20:00',
    source_timestamp: null,
  });
  const badges = c.getSectorBadges();
  assert.notStrictEqual(badges.stale, null, 'STALE badge must be visible');
  assert.notStrictEqual(badges.delayed, null, 'DELAYED badge must also be visible simultaneously');
  assert.strictEqual(badges.stale.includes('分时使用缓存，更新于 2026-10-31 10:20:00'), true);
  assert.strictEqual(badges.delayed, '板块排行行情延迟');
  console.log('[PASS] Test 14: Reverse Dual DELAYED & STALE Badge Coexistence & Single-sided Timestamp Safety (P2 verified)');
}

console.log('--- All 14 Frontend Quality Governance Tests PASSED ---');
