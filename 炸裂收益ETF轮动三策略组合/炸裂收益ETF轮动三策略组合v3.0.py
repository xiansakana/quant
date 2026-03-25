# 炸裂收益ETF轮动 v3.0
# 在v2.0基础上改进：
#   - 动量得分改为多周期平均（15天+25天），降低单一M_DAYS参数敏感性
#   - 参数平原测试结果显示M_DAYS从15到35收益差13倍，属于孤岛，用多周期平均平滑噪声

from jqdata import *
import numpy as np
import math
from prettytable import PrettyTable

# ========================= 参数区 =========================

# 多周期动量（取平均，降低单周期敏感性）
M_DAYS_LIST   = [15, 25]   # 同时计算这几个周期的动量得分，取平均
M_SCORE_LOW   = 0           # 平均得分下限
M_SCORE_HIGH  = 5           # 平均得分上限

# RSRS参数
RSRS_SLOPE_DAYS = 18
RSRS_LOOKBACK   = 250
RSRS_WINDOW     = 20

# 成交量异常过滤
VOLUME_LOOKBACK  = 7
VOLUME_THRESHOLD = 2.0

# 持仓与下单
HOLDINGS_NUM    = 1
MIN_LISTED_DAYS = 250
MIN_ORDER_VALUE = 2000.0
ROUND_LOT       = 100

ETF_POOL = [
    # 宽基
    "510300.XSHG", "510500.XSHG", "159915.XSHE", "588000.XSHG", "512100.XSHG",
    # 海外
    "513100.XSHG", "159509.XSHE", "513030.XSHG", "513520.XSHG", "513500.XSHG",
    # 大宗
    "518880.XSHG", "501018.XSHG", "159985.XSHE", "159980.XSHE",
    # 行业
    "512880.XSHG", "512480.XSHG", "512710.XSHG", "515790.XSHG", "159852.XSHE",
    "515050.XSHG", "512980.XSHG", "512170.XSHG", "512800.XSHG", "515880.XSHG",
    "562500.XSHG", "512690.XSHG", "510880.XSHG", "515220.XSHG", "512010.XSHG",
    # 债券/防御
    "511220.XSHG", "511880.XSHG",
]

# ========================= 初始化 =========================

def initialize(context):
    set_benchmark('000300.XSHG')
    set_option('use_real_price', True)
    set_option('avoid_future_data', True)
    set_order_cost(OrderCost(
        open_tax=0, close_tax=0,
        open_commission=0.0002, close_commission=0.0002,
        close_today_commission=0, min_commission=5
    ), type='fund')
    set_slippage(PriceRelatedSlippage(0.0003), type="fund")
    log.set_level('order', 'error')
    log.set_level('system', 'error')
    g.rsrs_cache = {}
    run_daily(trade,             time='10:30', reference_security='000300.XSHG')
    run_daily(after_market_close, time='15:01')

def after_code_changed(context):
    unschedule_all()
    g.rsrs_cache = {}
    run_daily(trade,             time='10:30', reference_security='000300.XSHG')
    run_daily(after_market_close, time='15:01')

# ========================= 核心逻辑 =========================

def get_valid_pool(context):
    """动态过滤：剔除上市不足MIN_LISTED_DAYS天的标的，消除幸存者偏差"""
    today = context.current_dt.date()
    valid = []
    for etf in ETF_POOL:
        try:
            if (today - get_security_info(etf).start_date).days >= MIN_LISTED_DAYS:
                valid.append(etf)
        except:
            continue
    return valid


def _single_momentum_score(etf, days):
    """计算单周期动量得分 = 年化收益率 × R²，只用历史收盘价"""
    try:
        hist = attribute_history(etf, days, "1d", ["close"])
        if hist is None or len(hist) < days:
            return None
        prices = hist["close"].values
        y = np.log(prices)
        x = np.arange(len(y))
        w = np.linspace(1, 2, len(y))
        slope, intercept = np.polyfit(x, y, 1, w=w)
        ann_ret = math.exp(slope * 250) - 1
        ss_res = np.sum(w * (y - (slope * x + intercept)) ** 2)
        ss_tot = np.sum(w * (y - np.mean(y)) ** 2)
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0
        return ann_ret * r2
    except:
        return None


def calc_momentum_score(etf):
    """
    多周期动量得分：对 M_DAYS_LIST 中每个周期分别计算得分，取平均。
    任一周期计算失败则整体返回 None。
    这是 v2.1 的核心改动，用于降低单一周期参数的敏感性。
    """
    scores = []
    for days in M_DAYS_LIST:
        s = _single_momentum_score(etf, days)
        if s is None:
            return None
        scores.append(s)
    return sum(scores) / len(scores)


def calc_rsrs(context, etf):
    """RSRS趋势确认：slope > beta 才通过，结果按交易日缓存"""
    key = (etf, context.current_dt.date())
    if key in g.rsrs_cache:
        return g.rsrs_cache[key]

    result = (None, None)
    try:
        hist_s = attribute_history(etf, RSRS_SLOPE_DAYS, '1d', ['high', 'low'])
        if len(hist_s) < RSRS_SLOPE_DAYS:
            g.rsrs_cache[key] = result; return result
        slope = np.polyfit(hist_s['low'].values, hist_s['high'].values, 1)[0]

        hist_b = attribute_history(etf, RSRS_LOOKBACK, '1d', ['high', 'low'])
        if len(hist_b) < RSRS_LOOKBACK:
            g.rsrs_cache[key] = result; return result

        x = hist_b['low'].values.astype(float)
        y = hist_b['high'].values.astype(float)
        k = np.ones(RSRS_WINDOW, dtype=float)
        Sx  = np.convolve(x,   k, mode='valid')
        Sxx = np.convolve(x*x, k, mode='valid')
        Sxy = np.convolve(x*y, k, mode='valid')
        Ex  = Sx / RSRS_WINDOW
        Ey  = np.convolve(y, k, mode='valid') / RSRS_WINDOW
        Varx  = Sxx / RSRS_WINDOW - Ex * Ex
        Covxy = Sxy / RSRS_WINDOW - Ex * Ey
        with np.errstate(divide='ignore', invalid='ignore'):
            rolling_slopes = Covxy / Varx
        rolling_slopes = rolling_slopes[np.isfinite(rolling_slopes) & (Varx > 0)]
        if len(rolling_slopes) < 2:
            g.rsrs_cache[key] = result; return result
        beta = float(np.mean(rolling_slopes) - 2.0 * np.std(rolling_slopes))
        result = (slope, beta)
    except Exception as e:
        log.warning(f"RSRS计算失败 {etf}: {e}")

    g.rsrs_cache[key] = result
    return result


def is_volume_abnormal(context, etf):
    """当日累计量 > 近N日均量 × 阈值，视为放量异常"""
    try:
        hist = attribute_history(etf, VOLUME_LOOKBACK, '1d', ['volume'])
        if hist.empty or len(hist) < VOLUME_LOOKBACK:
            return False
        avg_vol = hist['volume'].mean()
        if avg_vol <= 0:
            return False
        df_vol = get_price(etf, start_date=context.current_dt.date(),
                           end_date=context.current_dt, frequency='1m',
                           fields=['volume'], skip_paused=False, fq='pre',
                           panel=True, fill_paused=False)
        if df_vol is None or df_vol.empty:
            return False
        ratio = df_vol['volume'].sum() / avg_vol
        if ratio > VOLUME_THRESHOLD:
            log.info(f"[放量过滤] {etf} 量比={ratio:.2f}，剔除")
            return True
        return False
    except:
        return False


def rank_etfs(context):
    """
    3层过滤后按多周期平均动量得分排序：
      1. 多周期平均动量得分在 (M_SCORE_LOW, M_SCORE_HIGH)
      2. RSRS slope > beta
      3. 无放量异常
    """
    pool = get_valid_pool(context)
    current_data = get_current_data()
    scored = []
    for etf in pool:
        if current_data[etf].paused:
            continue
        score = calc_momentum_score(etf)
        if score is None or not (M_SCORE_LOW < score < M_SCORE_HIGH):
            continue
        slope, beta = calc_rsrs(context, etf)
        if slope is None or beta is None or slope <= beta:
            continue
        if is_volume_abnormal(context, etf):
            continue
        scored.append((etf, score))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored

# ========================= 交易 =========================

def trade(context):
    log.info(f"===== 交易决策 {context.current_dt.strftime('%Y-%m-%d %H:%M')} =====")
    ranked = rank_etfs(context)
    targets = [etf for etf, _ in ranked[:HOLDINGS_NUM]]

    if ranked:
        top_str = " > ".join([f"{e[:6]}({s:.3f})" for e, s in ranked[:5]])
        log.info(f"动量排名(前5): {top_str}")
    else:
        log.info("无符合条件ETF，清仓等待")

    all_pool_set = set(ETF_POOL)
    for security in list(context.portfolio.positions.keys()):
        if security in all_pool_set and security not in targets:
            if context.portfolio.positions[security].closeable_amount > 0:
                log.info(f"卖出: {security}")
                order_target_value(security, 0)

    if not targets:
        return

    target_value = context.portfolio.total_value / len(targets)
    if target_value < MIN_ORDER_VALUE:
        return

    for etf in targets:
        log.info(f"买入: {etf}，目标金额: {target_value:.2f}")
        _order_etf(etf, target_value, context)


def _order_etf(etf, target_value, context):
    current_data = get_current_data()
    price = current_data[etf].last_price
    if price <= 0 or price >= current_data[etf].high_limit:
        return
    amount = int(target_value / price / ROUND_LOT) * ROUND_LOT
    if amount <= 0:
        return
    pos = context.portfolio.positions.get(etf)
    current_amount = pos.total_amount if pos else 0
    diff = amount - current_amount
    if diff != 0:
        order(etf, diff)

# ========================= 收盘 =========================

def after_market_close(context):
    g.rsrs_cache = {}
    pt = PrettyTable(["代码", "名称", "成本", "现价", "收益%", "市值", "仓位%"])
    total = context.portfolio.total_value
    for s, p in context.portfolio.positions.items():
        try:
            name = get_security_info(s).display_name
        except:
            name = "N/A"
        pt.add_row([
            s[:6], name,
            f"{p.avg_cost:.3f}", f"{p.price:.3f}",
            f"{(p.price/p.avg_cost - 1)*100:.2f}%",
            f"{p.value/10000:.2f}万",
            f"{p.value/total*100:.1f}%" if total > 0 else "0%"
        ])
    log.info("持仓:\n" + str(pt) if context.portfolio.positions else "当前空仓")
