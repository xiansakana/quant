# 炸裂收益ETF轮动 v2.0
# 改进说明：
#   1. 合并三子策略为单一逻辑，等权持仓，消除人工调权重带来的过拟合
#   2. ETF池动态过滤上市不足250天的标的，消除幸存者偏差
#   3. 动量计算只用历史收盘价，不拼接当日实时价，消除前视偏差
#   4. RSRS过滤简化为 slope > beta，去掉硬编码的5日/10日均线分档
#   5. 过滤层从6层减至3层：动量得分 + RSRS趋势确认 + 成交量异常剔除
#   6. 所有参数集中在顶部，便于参数平原测试

from jqdata import *
import numpy as np
import pandas as pd
import math
from prettytable import PrettyTable
from typing import List

# ========================= 参数区（改这里做参数平原测试） =========================

# 动量参数
M_DAYS        = 25     # 动量回看天数，建议测试范围：15~35
M_SCORE_LOW   = 0      # 动量得分下限
M_SCORE_HIGH  = 5      # 动量得分上限，建议测试范围：3~8

# RSRS参数
RSRS_SLOPE_DAYS   = 18   # 当前斜率计算窗口，建议测试范围：10~25
RSRS_LOOKBACK     = 250  # Beta计算历史长度
RSRS_WINDOW       = 20   # Beta滚动窗口

# 成交量异常过滤（剔除放量异常标的，防止追高）
VOLUME_LOOKBACK   = 7    # 成交量均值回看天数
VOLUME_THRESHOLD  = 2.0  # 当日量/均量 超过此值视为异常

# 持仓数量
HOLDINGS_NUM = 1         # 同时持有ETF数量

# 最小上市天数（消除幸存者偏差的核心参数）
MIN_LISTED_DAYS = 250

# 下单参数
MIN_ORDER_VALUE = 2000.0
ROUND_LOT       = 100

# ETF池（只放逻辑上合理的标的，上市时间由代码动态过滤）
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

    # 每日缓存，避免同一天重复计算RSRS
    g.rsrs_cache = {}

    run_daily(trade,            time='10:30', reference_security='000300.XSHG')
    run_daily(after_market_close, time='15:01')

def after_code_changed(context):
    unschedule_all()
    g.rsrs_cache = {}
    run_daily(trade,            time='10:30', reference_security='000300.XSHG')
    run_daily(after_market_close, time='15:01')

# ========================= 核心：ETF过滤与排名 =========================

def get_valid_pool(context):
    """动态过滤ETF池：剔除上市不足MIN_LISTED_DAYS天的标的"""
    today = context.current_dt.date()
    valid = []
    for etf in ETF_POOL:
        try:
            info = get_security_info(etf)
            if (today - info.start_date).days >= MIN_LISTED_DAYS:
                valid.append(etf)
        except:
            continue
    return valid


def calc_momentum_score(etf):
    """
    计算动量得分 = 年化收益率 × R²
    只用历史收盘价，不拼接当日实时价，消除前视偏差
    """
    try:
        hist = attribute_history(etf, M_DAYS, "1d", ["close"])
        if hist is None or len(hist) < M_DAYS:
            return None
        prices = hist["close"].values
        y = np.log(prices)
        x = np.arange(len(y))
        weights = np.linspace(1, 2, len(y))
        slope, intercept = np.polyfit(x, y, 1, w=weights)
        annualized_return = math.exp(slope * 250) - 1
        ss_res = np.sum(weights * (y - (slope * x + intercept)) ** 2)
        ss_tot = np.sum(weights * (y - np.mean(y)) ** 2)
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0
        return annualized_return * r2
    except:
        return None


def calc_rsrs(context, etf):
    """
    计算RSRS：当前斜率 slope 与历史基准 beta 的关系
    beta = mean(rolling_slopes) - 2*std(rolling_slopes)
    缓存到当日，避免重复计算
    """
    trade_date = context.current_dt.date()
    key = (etf, trade_date)
    if key in g.rsrs_cache:
        return g.rsrs_cache[key]

    result = (None, None)
    try:
        # 当前斜率
        hist_slope = attribute_history(etf, RSRS_SLOPE_DAYS, '1d', ['high', 'low'])
        if len(hist_slope) < RSRS_SLOPE_DAYS:
            g.rsrs_cache[key] = result
            return result
        slope = np.polyfit(hist_slope['low'].values, hist_slope['high'].values, 1)[0]

        # Beta（向量化滚动回归）
        hist_beta = attribute_history(etf, RSRS_LOOKBACK, '1d', ['high', 'low'])
        if len(hist_beta) < RSRS_LOOKBACK:
            g.rsrs_cache[key] = result
            return result

        x = hist_beta['low'].values.astype(float)
        y = hist_beta['high'].values.astype(float)
        k = np.ones(RSRS_WINDOW, dtype=float)
        Sx  = np.convolve(x,   k, mode='valid')
        Sy  = np.convolve(y,   k, mode='valid')
        Sxx = np.convolve(x*x, k, mode='valid')
        Sxy = np.convolve(x*y, k, mode='valid')
        Ex, Ey = Sx / RSRS_WINDOW, Sy / RSRS_WINDOW
        Varx  = Sxx / RSRS_WINDOW - Ex * Ex
        Covxy = Sxy / RSRS_WINDOW - Ex * Ey
        with np.errstate(divide='ignore', invalid='ignore'):
            slopes = Covxy / Varx
        slopes = slopes[np.isfinite(slopes) & (Varx > 0)]
        if len(slopes) < 2:
            g.rsrs_cache[key] = result
            return result
        beta = float(np.mean(slopes) - 2.0 * np.std(slopes))

        result = (slope, beta)
    except Exception as e:
        log.warning(f"RSRS计算失败 {etf}: {e}")

    g.rsrs_cache[key] = result
    return result


def is_volume_abnormal(context, etf):
    """成交量异常检测：当日累计量 > 近N日均量 × 阈值，视为放量异常"""
    try:
        hist = attribute_history(etf, VOLUME_LOOKBACK, '1d', ['volume'])
        if hist.empty or len(hist) < VOLUME_LOOKBACK:
            return False
        avg_vol = hist['volume'].mean()
        if avg_vol <= 0:
            return False
        df_vol = get_price(
            etf,
            start_date=context.current_dt.date(),
            end_date=context.current_dt,
            frequency='1m', fields=['volume'],
            skip_paused=False, fq='pre', panel=True, fill_paused=False
        )
        if df_vol is None or df_vol.empty:
            return False
        current_vol = df_vol['volume'].sum()
        ratio = current_vol / avg_vol
        if ratio > VOLUME_THRESHOLD:
            log.info(f"[放量过滤] {etf} 当日量/均量={ratio:.2f}，剔除")
            return True
        return False
    except:
        return False


def rank_etfs(context):
    """
    主排名函数，返回按动量得分降序排列的ETF列表
    过滤流程（3层）：
      1. 动量得分在 [M_SCORE_LOW, M_SCORE_HIGH] 区间内
      2. RSRS slope > beta（趋势确认）
      3. 成交量无异常放量
    """
    pool = get_valid_pool(context)
    current_data = get_current_data()

    scored = []
    for etf in pool:
        # 跳过停牌
        if current_data[etf].paused:
            continue

        # 第1层：动量得分
        score = calc_momentum_score(etf)
        if score is None or not (M_SCORE_LOW < score < M_SCORE_HIGH):
            continue

        # 第2层：RSRS趋势确认
        slope, beta = calc_rsrs(context, etf)
        if slope is None or beta is None or slope <= beta:
            continue

        # 第3层：成交量异常剔除
        if is_volume_abnormal(context, etf):
            continue

        scored.append((etf, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored

# ========================= 交易逻辑 =========================

def trade(context):
    log.info(f"===== 开始交易决策 {context.current_dt.strftime('%Y-%m-%d %H:%M')} =====")

    ranked = rank_etfs(context)
    targets = [etf for etf, _ in ranked[:HOLDINGS_NUM]]

    if ranked:
        top_str = " > ".join([f"{etf[:6]}({score:.3f})" for etf, score in ranked[:5]])
        log.info(f"动量排名(前5): {top_str}")
    else:
        log.info("无符合条件ETF，清仓等待")

    # 卖出不在目标列表的持仓
    all_pool_set = set(ETF_POOL)
    for security in list(context.portfolio.positions.keys()):
        if security in all_pool_set and security not in targets:
            pos = context.portfolio.positions[security]
            if pos.closeable_amount > 0:
                log.info(f"卖出: {security}")
                order_target_value(security, 0)

    if not targets:
        return

    # 等权买入
    target_value = context.portfolio.total_value / len(targets)
    if target_value < MIN_ORDER_VALUE:
        log.info(f"资金不足，跳过买入")
        return

    for etf in targets:
        log.info(f"买入目标: {etf}，目标金额: {target_value:.2f}")
        _order_etf(etf, target_value, context)

    log.info("===== 交易决策完毕 =====")


def _order_etf(etf, target_value, context):
    """ETF下单封装，处理涨跌停和最小手数"""
    current_data = get_current_data()
    price = current_data[etf].last_price
    if price <= 0:
        return
    if price >= current_data[etf].high_limit:
        log.info(f"{etf} 涨停，跳过买入")
        return
    amount = int(target_value / price / ROUND_LOT) * ROUND_LOT
    if amount <= 0:
        return
    current_amount = context.portfolio.positions.get(etf, None)
    current_amount = current_amount.total_amount if current_amount else 0
    diff = amount - current_amount
    if diff != 0:
        order(etf, diff)

# ========================= 收盘打印 =========================

def after_market_close(context):
    # 清空RSRS缓存（隔日重算）
    g.rsrs_cache = {}

    pt = PrettyTable(["代码", "名称", "成本", "现价", "收益%", "市值", "仓位%"])
    positions = context.portfolio.positions
    total = context.portfolio.total_value
    for s, p in positions.items():
        ratio = p.value / total * 100 if total > 0 else 0
        try:
            name = get_security_info(s).display_name
        except:
            name = "N/A"
        pt.add_row([
            s[:6], name,
            f"{p.avg_cost:.3f}", f"{p.price:.3f}",
            f"{(p.price/p.avg_cost - 1)*100:.2f}%",
            f"{p.value/10000:.2f}万", f"{ratio:.1f}%"
        ])
    if positions:
        log.info("持仓:\n" + str(pt))
    else:
        log.info("当前空仓")
