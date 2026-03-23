# 克隆自聚宽文章：https://www.joinquant.com/post/4296

from jqdata import *
import numpy as np
import pandas as pd
import math, datetime
from prettytable import PrettyTable
from jqlib.technical_analysis import MACD
import requests, json, builtins
from typing import List
from collections import defaultdict

# ========================= 全局参数区 =========================
# —— 注意：以下资金比例仅用于业绩记录，不再用于实际资金分割 ——
g.global_strategy_proportion   = 0.4  # 全球选基
g.momentum_strategy_proportion = 0.4  # 安全摸狗
g.single_momentum_proportion   = 0.2  # 单动量策略

# —— 下单与风控（通用）——
MIN_ORDER_VALUE    = 2000.0   # 单笔最小金额
RESERVE_CASH_RATIO = 0.00     # 预留现金比例（0=不预留）
ROUND_LOT          = 100      # ETF最小买入单位（100份）

# —— 外部信号开关 ——
g.transdir_flag = 0

# ========================= 初始化 & 热更新 =========================

def initialize(context):
    set_benchmark('000300.XSHG')
    set_option('use_real_price', True)
    set_option('avoid_future_data', True)
    set_order_cost(OrderCost(open_tax=0, close_tax=0,
                            open_commission=0.0002, close_commission=0.0002,
                            close_today_commission=0, min_commission=5), type='fund')
    set_slippage(FixedSlippage(0.002), type="fund")


    
    _build_strategies(context)

def after_code_changed(context):
    """热更新：重挂任务 + 重建策略对象"""
    unschedule_all()
    log.set_level('order', 'error')
    log.set_level('system', 'error')
    log.set_level('strategy', 'debug')
    _build_strategies(context)

    # 统一交易时间与逻辑
    run_daily(unified_trade_logic,        time="10:30", reference_security='000300.XSHG')
    
    # 盘中风控与盘后打印
    run_daily(s1_stop_loss_by_cur_day,    time='10:00')
    run_daily(s1_volume_check,            time='13:30')
    run_daily(s2_stop_loss_by_cur_day,    time='10:00')
    run_daily(s2_volume_check,            time='13:30')
    run_daily(after_market_close,         time="15:01")



def _build_strategies(context):
    g.strategys = {}
    g.strategys['全球选基策略'] = GlobalFundSelectionStrategy(context, 0, '全球选基策略')
    g.strategys['安全摸狗']     = SafetyDogMomentumStrategy(context, 1, '安全摸狗')
    g.strategys['单动量策略']   = SingleMomentumStrategy(context, 2, '单动量策略')

# ========================= 顶层调度回调 =========================

def unified_trade_logic(context):
    """统一的交易决策与执行函数"""
    log.info(f"====== 开始执行统一交易决策 ({context.current_dt.strftime('%Y-%m-%d %H:%M')}) ======")
    
    # 1. 从每个策略获取最优候选ETF
    candidates = []
    for name, strategy_obj in g.strategys.items():
        try:
            # 调用每个策略的排名方法
            rank_list = strategy_obj._rank(context)
            if rank_list:
                top_etf = rank_list[0]
                candidates.append(top_etf)
                log.info(f"策略 '{name}' 选出候选: {top_etf} ({strategy_obj.get_stock_name(top_etf)})")
            else:
                log.info(f"策略 '{name}' 未选出有效候选。")
        except Exception as e:
            log.error(f"获取策略 '{name}' 候选失败: {e}")

    # 2. 合并候选并去重，形成最终持仓目标
    final_targets = sorted(list(set(candidates)))
    
    if not final_targets:
        log.info("所有策略均未选出有效ETF，清空所有ETF持仓。")
        for security in list(context.portfolio.positions.keys()):
            # 为安全起见，只卖出在所有策略ETF池中出现过的资产
            all_pools = g.strategys['全球选基策略'].etf_pool + g.strategys['安全摸狗'].etf_pool + g.strategys['单动量策略'].etf_pool
            if security in all_pools:
                order_target_value(security, 0)
        return

    log.info(f"最终持仓目标列表: {final_targets}")
    
    # 3. 执行调仓
    # 3.1 卖出不在最终目标列表中的现有持仓
    current_positions = list(context.portfolio.positions.keys())
    for security in current_positions:
        if security not in final_targets:
            # 同样，为安全起见，只卖出在所有策略ETF池中出现过的资产
            all_pools = g.strategys['全球选基策略'].etf_pool + g.strategys['安全摸狗'].etf_pool + g.strategys['单动量策略'].etf_pool
            if security in all_pools:
                log.info(f"卖出: {security} ({get_security_info(security).display_name})，因其不在最终目标列表中。")
                order_target_value(security, 0)

    # 3.2 均分资金，买入/调整至目标仓位
    num_targets = len(final_targets)
    portfolio_value = context.portfolio.total_value * (1 - RESERVE_CASH_RATIO)
    target_value_per_etf = portfolio_value / num_targets if num_targets > 0 else 0
    
    log.info(f"组合总价值: {context.portfolio.total_value:.2f}, 计划投入: {portfolio_value:.2f}, "
            f"目标数量: {num_targets}, 每个目标ETF价值: {target_value_per_etf:.2f}")

    if target_value_per_etf < MIN_ORDER_VALUE:
        log.warn(f"每个ETF的目标价值({target_value_per_etf:.2f})过低，小于最小下单金额({MIN_ORDER_VALUE})，本次不买入。")
        return

    for security in final_targets:
        log.info(f"调仓至目标: {security} ({get_security_info(security).display_name}), 目标价值: {target_value_per_etf:.2f}")
        order_target_value(security, target_value_per_etf)
        
    log.info("====== 统一交易决策执行完毕 ======")


def after_market_close(context):
    """统一的收盘后处理"""
    log.info("\n" + "="*50 + " 收盘总结 " + "="*50)
    # 打印统一的持仓
    print_unified_holdings(context)
    
    # 各策略分别打印自己的动量排名
    for st in g.strategys.values():
        st.print_top_after_close(context)
    log.info("="*112)

def print_unified_holdings(context):
    """打印统一的投资组合持仓"""
    pt = PrettyTable(["代码", "名称", "买入日", "买入价", "现价", "收益%", "数量", "市值", "仓位%"])
    positions = context.portfolio.positions
    total_value = context.portfolio.total_value
    if positions:
        for s, p in positions.items():
            position_ratio = p.value / total_value * 100 if total_value > 0 else 0
            pt.add_row([
                p.security[:6], get_security_info(p.security).display_name,
                p.init_time.date(), f"{p.avg_cost:.3f}", f"{p.price:.3f}",
                f"{(p.price / p.avg_cost - 1) * 100:.2f}%", p.total_amount,
                f"{p.value / 10000:.3f}万", f"{position_ratio:.2f}%"
            ])
        log.info("当前统一持仓:\n" + str(pt))
    else:
        log.info("当前统一持仓: 无")

# ========================= 公共基类（仅放通用“交易封装”） =========================
class BaseStrategy:
    def __init__(self, context, subportfolio_index, name, proportion):
        self.subportfolio_index = subportfolio_index # 主要用于区分日志和记录
        self.name = name
        self.start_cash = context.portfolio.starting_cash * proportion

    # --【移除】-- my_trade, my_trade_sell, my_trade_buy 等交易方法，由 unified_trade_logic 统一处理
    
    def after_market_close(self, context):
        super().after_market_close(context)
        try:
            _ = self.filter_moment_rank(self.etf_pool, self.m_days, 0, self.m_score, show_print=True)
            ts = context.current_dt.strftime('%Y-%m-%d %H:%M')
            log.info(f"【{ts} {self.name}】动量Top已输出（基类打印）")
        except Exception as e:
            log.error(f"{self.name} 收盘打印失败：{e}")

        # 收盘清空缓存，隔日必然刷新
        self._rsrs_cache.clear()
        self._ma_cache.clear()


    @staticmethod
    def get_stock_name(security):
        try:
            return get_security_info(security).display_name
        except:
            return "N/A"

# ========================= 通用：动量ETF基类（策略1/2共用） =========================
class ETFMomentumBase(BaseStrategy):
    def __init__(
        self,
        context,
        subportfolio_index: int,
        name: str,
        proportion: float,
        etf_pool: List[str],
        m_days: int = 25,
        m_score: float = 5.0,
        enable_stop_loss_by_cur_day: bool = True,
        stoploss_limit_by_cur_day: float = -0.03,
    ):
        BaseStrategy.__init__(self, context, subportfolio_index, name, proportion)
        self.etf_pool = list(etf_pool)
        self.m_days   = int(m_days)
        self.m_score  = float(m_score)
        self.enable_stop_loss_by_cur_day = bool(enable_stop_loss_by_cur_day)
        self.stoploss_limit_by_cur_day   = float(stoploss_limit_by_cur_day)
        self._rsrs_cache = {}
        self._ma_cache = {}

    def _minute_key(self, context):
        return context.current_dt.strftime('%Y-%m-%d %H:%M')

    def _rank(self, context):
        current_data = get_current_data()
        rank_list = []
        for etf in self.etf_pool:
            try:
                df = attribute_history(etf, self.m_days, "1d", ["close", "high"], skip_paused=False, fq='pre')
                if df is None or df.empty or len(df["close"]) < self.m_days:
                    continue
                prices = np.append(df["close"].values, current_data[etf].last_price)
                if min(prices[-1]/prices[-2], prices[-2]/prices[-3], prices[-3]/prices[-4]) < 0.95:
                    continue
                if self.enable_stop_loss_by_cur_day:
                    ratio = self.cal_cur_to_open_ratio(etf)
                    if ratio <= self.stoploss_limit_by_cur_day:
                        continue
                rank_list.append(etf)
            except Exception:
                continue
        rank_list = self.filter_moment_rank(rank_list, self.m_days, 0, self.m_score, show_print=False) # 不在内部打印
        rank_list = self.filter_volume(context, rank_list)
        rank_list = self.filter_rsrs(rank_list, context)
        return rank_list

    @staticmethod
    def cal_cur_to_open_ratio(security):
        current_data = get_current_data()
        last_price = current_data[security].last_price
        day_open = current_data[security].day_open
        return (last_price - day_open) / day_open

    def filter_moment_rank(self, stock_pool, days, ll, hh, show_print=True):
        scores_data = pd.DataFrame(index=stock_pool, columns=["score"])
        current_data = get_current_data()
        print_data = {}
        for code in stock_pool:
            try:
                hist_data = attribute_history(code, days, "1d", ["close"])
                if hist_data.empty:
                    scores_data.loc[code, "score"] = -np.inf
                    continue
                prices = np.append(hist_data["close"].values, current_data[code].last_price)
                log_prices = np.log(prices)
                x_values = np.arange(len(log_prices))
                weights = np.linspace(1, 2, len(log_prices))
                slope, _ = np.polyfit(x_values, log_prices, 1, w=weights)
                annualized_return = math.exp(slope * 250) - 1
                ss_res = np.sum(weights * (log_prices - (slope * x_values + _)) ** 2)
                ss_tot = np.sum(weights * (log_prices - np.mean(log_prices)) ** 2)
                r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0
                momentum_score = annualized_return * r2
                if min(prices[-1]/prices[-2], prices[-2]/prices[-3], prices[-3]/prices[-4]) < 0.95:
                    momentum_score = 0
                scores_data.loc[code, "score"] = momentum_score
                print_data[code] = momentum_score
            except Exception:
                scores_data.loc[code, "score"] = -np.inf
        valid_etfs = scores_data.query(f"{ll} < score < {hh}").sort_values("score", ascending=False)
        rank_list = valid_etfs.index.tolist()
        if show_print and rank_list:
            _ = [f"{i[:6]}({print_data[i]:.2f})" for i in rank_list[:4]]
            log.info(f"[{self.name}] 动量排名: {' > '.join(_)}")
        return rank_list

    def filter_volume(self, context, stock_list, days=7, volume_threshold=2, check_only=True, check_price=False):
        def _is_price_below_open(security):
            current_data = get_current_data()
            return current_data[security].last_price < current_data[security].day_open

        def _get_volume_ratio(security):
            try:
                hist_data = attribute_history(security, days, '1d', ['volume'])
                if hist_data.empty or len(hist_data) < days:
                    return
                avg_volume = hist_data['volume'].mean()

                df_vol = get_price(
                    security,
                    start_date=context.current_dt.date(),
                    end_date=context.current_dt,
                    frequency='1m',
                    fields=['volume'],
                    skip_paused=False,
                    fq='pre',
                    panel=True,
                    fill_paused=False
                )
                if df_vol is None or df_vol.empty:
                    return
                current_volume = df_vol['volume'].sum()
                _ratio = current_volume / avg_volume
                print(f"{security} 成交量较近{days}日均值 x{_ratio:.2f}")
                if _ratio > volume_threshold:
                    return _ratio
            except Exception as e:
                print(f"检查{security}成交量失败: {e}")
                return

        res = []
        for stock in stock_list:
            if check_only:
                ratio = _get_volume_ratio(stock)
                if not ratio:
                    res.append(stock)
                else:
                    print(f"👾👾👾👾👾 {stock} {self.get_stock_name(stock)} 近{days}日成交量异常, 为均值的{ratio:.4f}倍, 不纳入选择")
            else:
                position = context.portfolio.positions.get(stock)
                if position.closeable_amount == 0:
                    continue
                if position.init_time.date() == context.current_dt.date():
                    continue
                ratio = _get_volume_ratio(stock)
                if ratio:
                    if check_price and not _is_price_below_open(stock):
                        continue
                    print(f"👽👽👽👽👽 {stock} {self.get_stock_name(stock)} 近{days}日成交量异常, 较均值 x{ratio}倍, 执行卖出")
                    self.order_target_value_ex(context, stock, 0)
        return res


    def filter_rsrs(self, stock_list, context=None):
        # ====== 计算/缓存 RSRS（按交易日） ======
        def _get_slope_beta_with_cache(security, trade_date):
            key = (security, trade_date)
            if key in self._rsrs_cache:
                return self._rsrs_cache[key]

            # 1) 斜率（18天）：保持原逻辑，用一次 polyfit
            def _get_slope(security, days=18):
                try:
                    hist_data = attribute_history(security, days, '1d', ['high', 'low'])
                    if hist_data.empty or len(hist_data) < days:
                        return None
                    slope = np.polyfit(hist_data['low'].values, hist_data['high'].values, 1)[0]
                    return slope
                except Exception as e:
                    print(f"计算{security} RSRS斜率失败: {e}")
                    return None

            # 2) Beta（250天、窗口20）：向量化（与逐窗 polyfit 等价）
            def _get_beta_vectorized(security, lookback_days=250, window=20):
                try:
                    hist = attribute_history(security, lookback_days, '1d', ['high', 'low'])
                    if hist.empty or len(hist) < lookback_days:
                        return None

                    x = hist['low'].values.astype(float)
                    y = hist['high'].values.astype(float)
                    n = len(x)
                    if n < window:
                        return None

                    # 卷积核
                    k = np.ones(window, dtype=float)

                    # Rolling sums（向量化）
                    Sx  = np.convolve(x, k, mode='valid')
                    Sy  = np.convolve(y, k, mode='valid')
                    Sxx = np.convolve(x*x, k, mode='valid')
                    Sxy = np.convolve(x*y, k, mode='valid')

                    Ex = Sx / window
                    Ey = Sy / window
                    Varx = (Sxx / window) - Ex*Ex
                    Covxy = (Sxy / window) - Ex*Ey

                    with np.errstate(divide='ignore', invalid='ignore'):
                        slopes = Covxy / Varx

                    valid = np.isfinite(slopes) & (Varx > 0)
                    slopes = slopes[valid]
                    if len(slopes) < 2:
                        return None

                    beta = float(np.mean(slopes) - 2.0 * np.std(slopes))
                    return beta
                except Exception as e:
                    print(f"计算{security} RSRS Beta失败: {e}")
                    return None

            slope = _get_slope(security)
            beta  = _get_beta_vectorized(security)
            self._rsrs_cache[key] = (slope, beta)
            return slope, beta

        # ====== 均线站上判断（按分钟缓存） ======
        def _check_above_ma_with_cache(security, days=20):
            minute_key = self._minute_key(context) if context is not None else None
            key = (security, days, minute_key)
            if minute_key is not None and key in self._ma_cache:
                return self._ma_cache[key]

            res = False
            try:
                hist = attribute_history(security, days, "1d", ["close"])
                if len(hist) >= days:
                    current_price = get_current_data()[security].last_price
                    res = (current_price >= hist["close"].mean())
            except Exception as e:
                print(f"计算{security} {days}日均线失败: {e}")

            if minute_key is not None:
                self._ma_cache[key] = res
            return res

        # ====== 主流程（保持原有筛选逻辑/阈值/顺序完全一致） ======
        trade_date = context.current_dt.date() if context is not None else None
        res = []
        for stock in stock_list:
            slope, beta = _get_slope_beta_with_cache(stock, trade_date)
            if slope is None or beta is None:
                continue

            strength = (slope - beta) / abs(beta) if beta != 0 else 0
            stock_pass = (slope > beta)
            if stock_pass:
                if strength > 0.15:
                    res.append(stock)
                elif strength > 0.03 and _check_above_ma_with_cache(stock, 5):
                    res.append(stock)
                elif _check_above_ma_with_cache(stock, 10):
                    res.append(stock)
        return res


    def stop_loss_by_cur_day(self, context, ratio=-0.03):
        # 风控逻辑现在作用于统一的投资组合
        holdings = [s for s in context.portfolio.positions if s in self.etf_pool]
        for stock in holdings:
            cur_ratio = self.cal_cur_to_open_ratio(stock)
            if cur_ratio is not None and cur_ratio < ratio:
                log.warn(f"[{self.name}风控] {stock} 日内跌幅 {cur_ratio*100:.2f}% 触发止损，清仓！")
                order_target_value(stock, 0)

    def volume_check(self, context, days=7, volume_threshold=2, check_price=True):
        # 风控逻辑现在作用于统一的投资组合
        holdings = [s for s in context.portfolio.positions if s in self.etf_pool]
        pass

    def print_top_after_close(self, context, top_n: int = 5):
        try:
            self.filter_moment_rank(self.etf_pool, self.m_days, 0, self.m_score, show_print=True)
        except Exception as e:
            log.error(f"[{self.name}] 收盘打印排名失败: {e}")

# ========================= 策略1：全球选基（继承通用基类） =========================
class GlobalFundSelectionStrategy(ETFMomentumBase):
    def __init__(self, context, subportfolio_index: int = 0, name: str = '全球选基策略'):
        super().__init__(
            context=context,
            subportfolio_index=subportfolio_index,
            name=name,
            proportion=g.global_strategy_proportion,
            etf_pool=getattr(g, 'etf_pool_1', [
                "510180.XSHG", "159915.XSHE", "588190.XSHG", "510410.XSHG", 
                "512290.XSHG", "512480.XSHG", "512710.XSHG", "515650.XSHG", 
                "515070.XSHG", "516160.XSHG", "159851.XSHE", "159637.XSHE", 
                "512880.XSHG", "518880.XSHG", "501018.XSHG", "159985.XSHE", 
                "159980.XSHE", "513100.XSHG", "159509.XSHE", "513030.XSHG", 
                "513520.XSHG", "513690.XSHG", "513130.XSHG", "159550.XSHE", 
                "511220.XSHG"
            ]),
            m_days=getattr(g, 'm_days_s1', 25),
            m_score=getattr(g, 'm_score_s1', 6),
            enable_stop_loss_by_cur_day=getattr(g, 'enable_stop_loss_by_cur_day_s1', True),
            stoploss_limit_by_cur_day=getattr(g, 'stoploss_limit_by_cur_day_s1', -0.03),
        )

# ========================= 策略2：安全摸狗（继承通用基类） =========================
class SafetyDogMomentumStrategy(ETFMomentumBase):
    def __init__(self, context, subportfolio_index: int = 1, name: str = '安全摸狗'):
        super().__init__(
            context=context,
            subportfolio_index=subportfolio_index,
            name=name,
            proportion=g.momentum_strategy_proportion,
            etf_pool=getattr(g, 'etf_pool_2', [
                "159915.XSHE", "588000.XSHG", "518880.XSHG", "501018.XSHG", 
                "159985.XSHE", "159980.XSHE", "513100.XSHG", "513030.XSHG", 
                "513520.XSHG", "513690.XSHG", "513130.XSHG", "159509.XSHE", 
                "511220.XSHG"
            ]),
            m_days=getattr(g, 'm_days_s2', 25),
            m_score=getattr(g, 'm_score_s2', 5),
            enable_stop_loss_by_cur_day=getattr(g, 'enable_stop_loss_by_cur_day_s2', True),
            stoploss_limit_by_cur_day=getattr(g, 'stoploss_limit_by_cur_day_s2', -0.03),
        )

# ========================= 策略3：单动量策略（新整合） =========================
class SingleMomentumStrategy(BaseStrategy):
    def __init__(self, context, subportfolio_index: int = 2, name: str = '单动量策略'):
        BaseStrategy.__init__(self, context, subportfolio_index, name, g.single_momentum_proportion)
        self.stock_sum = 1
        self.etf_pool = [
            "513100.XSHG", "159509.XSHE", "513520.XSHG", "513030.XSHG", "518880.XSHG", 
            "159980.XSHE", "159985.XSHE", "159981.XSHE", "501018.XSHG", "511090.XSHG", 
            "513130.XSHG", "513690.XSHG", "510180.XSHG", "159915.XSHE", "510410.XSHG", 
            "515650.XSHG", "512290.XSHG", "588120.XSHG", "515070.XSHG", "159851.XSHE", 
            "159637.XSHE", "516160.XSHG", "159550.XSHE", "512710.XSHG", "159692.XSHE", 
            "512480.XSHG", "515250.XSHG", "159378.XSHE", "516510.XSHG", "515050.XSHG", 
            "159995.XSHE", "515790.XSHG", "515000.XSHG"
        ]
        self.m_days = 25
        self.enable_volume_check = True
        self.volume_lookback = 5
        self.volume_threshold = 2.0
        self.ma_filter_days = 20
        self.enable_ma_filter = True

    def _rank(self, context):
        """实现原单动量策略的排名逻辑"""
        filtered_pool = self.etf_pool
        if self.enable_ma_filter:
            filtered_pool = self._filter_below_ma(filtered_pool, self.ma_filter_days)
        
        data = pd.DataFrame(index=filtered_pool, columns=["score"])
        current_data = get_current_data()
        for etf in filtered_pool:
            try:
                df = attribute_history(etf, self.m_days, "1d", ["close"])
                prices = np.append(df["close"].values, current_data[etf].last_price)
                y = np.log(prices)
                x = np.arange(len(y))
                weights = np.linspace(1, 2, len(y))
                slope, intercept = np.polyfit(x, y, 1, w=weights)
                annualized_return = math.exp(slope * 250) - 1
                ss_res = np.sum(weights * (y - (slope * x + intercept))**2)
                ss_tot = np.sum(weights * (y - np.mean(y))**2)
                r2 = 1 - ss_res / ss_tot if ss_tot else 0
                score = annualized_return * r2
                if len(prices) >= 4 and min(prices[-1]/prices[-2], prices[-2]/prices[-3], prices[-3]/prices[-4]) < 0.95:
                    score = 0
                data.loc[etf, "score"] = score
            except Exception:
                data.loc[etf, "score"] = -np.inf
        
        # 增加成交量过滤
        if self.enable_volume_check:
            data = data[data.index.isin(self._filter_volume(context, data.index.tolist()))]

        data = data.query("0 < score < 5").sort_values(by="score", ascending=False)
        return data.index.tolist()

    def print_top_after_close(self, context, top_n: int = 5):
        try:
            rank_list = self._rank(context)
            if rank_list:
                top_str = " > ".join([f"{etf[:6]}" for etf in rank_list[:top_n]])
                log.info(f"[{self.name}] 收盘动量排名: {top_str}")
        except Exception as e:
            log.error(f"[{self.name}] 收盘打印排名失败: {e}")

    def _get_volume_ratio(self, context, security, lookback_days, threshold):
        try:
            hist_data = attribute_history(security, lookback_days, '1d', ['volume'])
            if hist_data.empty or len(hist_data) < lookback_days: return None
            avg_volume = hist_data['volume'].mean()
            df_vol = get_price(security, start_date=context.current_dt.date(), end_date=context.current_dt,
                            frequency='1m', fields=['volume'], fq='pre')
            if df_vol is None or df_vol.empty: return None
            current_volume = df_vol['volume'].sum()
            volume_ratio = current_volume / avg_volume
            return volume_ratio if volume_ratio > threshold else None
        except:
            return None

    def _filter_volume(self, context, stock_list):
        if not self.enable_volume_check:
            return stock_list
        
        final_list = []
        for etf in stock_list:
            vol_ratio = self._get_volume_ratio(context, etf, self.volume_lookback, self.volume_threshold)
            if vol_ratio is None:
                final_list.append(etf)
            else:
                log.info(f"[{self.name}] 候选 {etf} 因放量(x{vol_ratio:.2f})被过滤")
        return final_list

    def _filter_below_ma(self, stocks, days=20):
        if not stocks: return []
        current_data = get_current_data()
        filtered = []
        for stock in stocks:
            try:
                hist = attribute_history(stock, days, "1d", ["close"])
                if len(hist) < days: continue
                ma_n = hist["close"].mean()
                current_price = current_data[stock].last_price
                if current_price >= ma_n:
                    filtered.append(stock)
            except:
                continue
        return filtered

# ========================= 调度包装函数（部分保留用于风控） =========================
def s1_stop_loss_by_cur_day(context):
    g.strategys['全球选基策略'].stop_loss_by_cur_day(context)

def s1_volume_check(context):
    g.strategys['全球选基策略'].volume_check(context)

def s2_stop_loss_by_cur_day(context):
    g.strategys['安全摸狗'].stop_loss_by_cur_day(context)

def s2_volume_check(context):
    g.strategys['安全摸狗'].volume_check(context)