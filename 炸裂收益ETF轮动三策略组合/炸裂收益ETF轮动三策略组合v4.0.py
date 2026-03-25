# 炸裂收益ETF轮动 v4.0
# 在v3.0基础上新增市场环境判断，解决震荡/熊市下无脑轮动的问题
#
# 市场环境三档：
#   BULL  : 沪深300 在200日均线上方 且 20日波动率 < 高波动阈值 → 正常轮动，满仓
#   CAUTION: 沪深300 在200日均线上方 但 20日波动率 >= 高波动阈值 → 谨慎，半仓
#   BEAR  : 沪深300 在200日均线下方 → 防御，切换货币/债券ETF，不参与轮动
#
# 设计原则：
#   - 均线和波动率都是经典指标，参数（200日、20日）有充分的学术和实践支撑，不是调出来的
#   - 防御标的固定为货币ETF，逻辑简单可解释

from jqdata import *
import numpy as np
import math
from prettytable import PrettyTable

# ========================= 参数区 =========================

# 多周期动量
M_DAYS_LIST  = [15, 25]
M_SCORE_LOW  = 0
M_SCORE_HIGH = 5

# RSRS
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

# ---- 市场环境判断参数 ----
MARKET_INDEX      = '000300.XSHG'  # 用沪深300判断大盘环境
MA_LONG           = 200            # 趋势判断均线，200日是国际通用标准
VOL_WINDOW        = 20             # 波动率计算窗口
VOL_HIGH_THRESH   = 0.025          # 20日日收益率标准差超过此值视为高波动（约年化40%）
DEFENSIVE_ETF     = '511880.XSHG'  # 防御标的：货币ETF（熊市/高波动时持有）

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
    # 债券/防御（不参与动量轮动，只作为防御备选）
    "511220.XSHG",
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
    run_daily(trade,              time='10:30', reference_security='000300.XSHG')
    run_daily(after_market_close, time='15:01')

def after_code_changed(context):
    unschedule_all()
    g.rsrs_cache = {}
    run_daily(trade,              time='10:30', reference_security='000300.XSHG')
    run_daily(after_market_close, time='15:01')

# ========================= 市场环境判断 =========================

# 环境常量
BULL    = 'BULL'
CAUTION = 'CAUTION'
BEAR    = 'BEAR'

def get_market_regime(context):
    """
    判断当前市场环境：
      BULL    : 指数 > MA200 且 波动率低
      CAUTION : 指数 > MA200 但 波动率高
      BEAR    : 指数 < MA200
    只用历史数据，无前视偏差。
    """
    try:
        hist = attribute_history(MARKET_INDEX, MA_LONG + VOL_WINDOW, '1d', ['close'])
        if len(hist) < MA_LONG + VOL_WINDOW:
            return BULL  # 数据不足时默认正常运行

        closes = hist['close'].values
        ma200  = closes[-MA_LONG:].mean()
        current_price = closes[-1]

        # 20日日收益率标准差
        recent_returns = np.diff(np.log(closes[-VOL_WINDOW - 1:]))
        vol = recent_returns.std()

        above_ma = current_price > ma200

        if not above_ma:
            regime = BEAR
        elif vol >= VOL_HIGH_THRESH:
            regime = CAUTION
        else:
            regime = BULL

        log.info(f"[市场环境] 沪深300={current_price:.2f} MA200={ma200:.2f} "
                 f"20日波动率={vol:.4f}(阈值{VOL_HIGH_THRESH}) → {regime}")
        return regime
    except Exception as e:
        log.warning(f"市场环境判断失败: {e}，默认BULL")
        return BULL

# ========================= ETF过滤与排名（继承v3.0） =========================

def get_valid_pool(context):
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
    scores = []
    for days in M_DAYS_LIST:
        s = _single_momentum_score(etf, days)
        if s is None:
            return None
        scores.append(s)
    return sum(scores) / len(scores)


def calc_rsrs(context, etf):
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
            rs = Covxy / Varx
        rs = rs[np.isfinite(rs) & (Varx > 0)]
        if len(rs) < 2:
            g.rsrs_cache[key] = result; return result
        beta = float(np.mean(rs) - 2.0 * np.std(rs))
        result = (slope, beta)
    except Exception as e:
        log.warning(f"RSRS计算失败 {etf}: {e}")
    g.rsrs_cache[key] = result
    return result


def is_volume_abnormal(context, etf):
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

# ========================= 交易（v4.0核心：按市场环境分档执行） =========================

def _clear_etf_positions(context, keep=None):
    """清仓所有ETF池持仓，keep列表内的标的保留"""
    keep = set(keep or [])
    all_pool = set(ETF_POOL) | {DEFENSIVE_ETF}
    for security in list(context.portfolio.positions.keys()):
        if security in all_pool and security not in keep:
            if context.portfolio.positions[security].closeable_amount > 0:
                log.info(f"卖出: {security}")
                order_target_value(security, 0)


def trade(context):
    log.info(f"===== 交易决策 {context.current_dt.strftime('%Y-%m-%d %H:%M')} =====")

    regime = get_market_regime(context)

    # ---- BEAR：全部切换到防御ETF ----
    if regime == BEAR:
        log.info("🐻 熊市模式：清仓轮动持仓，买入防御ETF")
        _clear_etf_positions(context, keep=[DEFENSIVE_ETF])
        target_value = context.portfolio.total_value * 0.99
        if target_value >= MIN_ORDER_VALUE:
            _order_etf(DEFENSIVE_ETF, target_value, context)
        return

    # ---- BULL / CAUTION：正常轮动，CAUTION时仓位减半 ----
    position_ratio = 1.0 if regime == BULL else 0.5

    ranked = rank_etfs(context)

    # CAUTION时只取1只，BULL时按HOLDINGS_NUM
    n = 1 if regime == CAUTION else HOLDINGS_NUM
    targets = [etf for etf, _ in ranked[:n]]

    if ranked:
        top_str = " > ".join([f"{e[:6]}({s:.3f})" for e, s in ranked[:5]])
        log.info(f"动量排名(前5): {top_str}")
    else:
        log.info(f"{'⚠️ 谨慎' if regime == CAUTION else ''}无符合条件ETF，持有防御ETF")

    # 无目标时切换防御
    if not targets:
        _clear_etf_positions(context, keep=[DEFENSIVE_ETF])
        target_value = context.portfolio.total_value * 0.99
        if target_value >= MIN_ORDER_VALUE:
            _order_etf(DEFENSIVE_ETF, target_value, context)
        return

    # 卖出不在目标列表的ETF持仓（防御ETF也一并清掉，回归轮动）
    _clear_etf_positions(context, keep=targets)

    # 按仓位比例等权买入
    invest_value = context.portfolio.total_value * position_ratio
    target_value = invest_value / len(targets)
    if target_value < MIN_ORDER_VALUE:
        log.info("资金不足，跳过买入")
        return

    for etf in targets:
        log.info(f"买入: {etf}，目标金额: {target_value:.2f} (仓位{position_ratio*100:.0f}%)")
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
