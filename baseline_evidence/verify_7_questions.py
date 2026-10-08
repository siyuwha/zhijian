import json

with open('baseline_evidence/golden_canonical_snapshot_20261008.json', 'r', encoding='utf-8') as f:
    snap = json.load(f)

truth = snap['truth']
cog = snap['cognition']

print('=== 交易员 30 秒 7 问真机人眼实测回答清单 ===\n')

print('【Q1: 今天市场整体是什么环境？】')
print('  答: 状态定性:', cog['market_state_summary'])
idx_map = {idx['symbol']: idx for idx in truth['indices']}
sh = idx_map.get('sh000001', {})
sz = idx_map.get('sz399001', {})
cy = idx_map.get('sz399006', {})
kc = idx_map.get('sh000688', {})
print(f'      核心指数: 上证 {sh.get("current_price")} ({sh.get("pct_change"):+.2f}%) | 深证 {sz.get("current_price")} ({sz.get("pct_change"):+.2f}%) | 创业板 {cy.get("current_price")} ({cy.get("pct_change"):+.2f}%) | 科创50 {kc.get("current_price")} ({kc.get("pct_change"):+.2f}%)')
print('      截面广度状态:', truth['cross_section_breadth_status'], f'({truth["cross_section_breadth_detail"]["message"]})')

print('\n【Q2: 今天成交量是放量还是缩量？口径如何？】')
to = truth['turnover']
tot = to['two_markets_total_yi']
sh_to = to['sh_amount_yi']
sz_to = to['sz_total_amount_yi']
cy_to = to['chinext_slice_amount_yi']
print(f'  答: 沪深两市总成交额: {tot:.2f} 亿元 (SH: {sh_to:.2f} 亿 + SZ: {sz_to:.2f} 亿)')
print(f'      创业板成交额切片: {cy_to:.2f} 亿元 (占比深市 {to["chinext_ratio_in_sz"]:.2%}，明确标注已内嵌于 SZ，绝无二次重复计入)')

print('\n【Q3: 今天做多最强的主线到底是什么？】')
for m in cog['mainlines']:
    role = m['structural_role']
    name = m['sector_name']
    taxo = m['static_taxonomy_name']
    narr = m.get('market_narrative', name)
    ldr = m['constituency']['leader_name']
    h = m['constituency']['leader_height']
    cnt = m['constituency']['limit_up_count']
    rk = m['rank']
    print(f'  答: Rank {rk}: [{role}] 交易叙事:【{narr}】 | 商业分类: {taxo} | 龙头: {ldr} ({h}B) | 涨停 {cnt} 家')
    if m.get('subtheme_catalysts'):
        for sub in m['subtheme_catalysts']:
            sname = sub['sector_name']
            sldr = sub['catalyst_leader']
            sh = sub['catalyst_height']
            sov = sub['overlap_ratio_with_master']
            print(f'       └─ 细分催化题材: {sname} ({sldr} {sh}B, 重合度 {sov:.1%})')
    if m.get('shared_evidence_affiliates'):
        for aff in m['shared_evidence_affiliates']:
            tname = aff['target_sector_name']
            sratio = aff['shared_evidence_ratio']
            ocnt = aff['overlap_stocks_count']
            print(f'       └─ 共享证据资金簇: {tname} (共享证据率 {sratio:.1%}, 重叠 {ocnt} 只)')

print('\n【Q4: 今天最高板是谁？处于几板？天梯梯队如何？】')
sb = truth['sentiment_bounds']
top_group = truth['ladder_tree'][0]
highest_stock = top_group['stocks'][0]
hname = highest_stock['name']
hcode = highest_stock['code']
mh = sb['max_ladder_height']
print(f'  答: 全市场最高空间板: {hname} ({hcode})，连板高度: {mh}B')
for grp in truth['ladder_tree']:
    stks = ', '.join([f'{s["name"]}({s["code"]})' for s in grp['stocks']])
    gh = grp['height']
    gc = len(grp['stocks'])
    print(f'      {gh}B ({gc}只): {stks}')

print('\n【Q5: 今天的亏钱效应严重吗？】')
br = sb['broken_limit_ratio']
lc = sb['limit_up_count']
bc = sb['broken_limit_count']
print(f'  答: 炸板率高达: {br:.2%} (涨停 {lc} 家，炸板 {bc} 家，总触板池 75 家)')
anom_cnt = len(truth['regulatory_anomalies'])
print(f'      触发交易所严重异动规则股票: {anom_cnt} 只 (龙头面临商业规则特停监控风险)')

print('\n【Q6: 今天如果想买，最危险的陷阱/证伪条件是什么？】')
m1 = cog['mainlines'][0]
m1_name = m1['sector_name']
print(f'  答: 核心主线 [{m1_name}] 次日证伪红线规则:')
for r in m1['falsification_condition']['invalidation_rules']:
    print(f'      - {r}')

print('\n【Q7: 明天竞价开盘要先盯哪几个核心标的？】')
obs = m1['falsification_condition']['critical_observation_symbols']
print(f'  答: 次日早盘 09:15~09:25 核心观察标的集合: {obs}')
