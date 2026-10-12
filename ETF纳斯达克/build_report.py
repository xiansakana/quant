"""从已保存的聚宽页面回执生成可复核的报告和收益曲线。"""
from pathlib import Path
import json
import re
from datetime import datetime, timezone
import hashlib

BASE = Path(__file__).parent


def load_receipt(path):
    receipt = json.loads(path.read_text(encoding='utf-8'))
    assert receipt['status'] == 'succeeded', path
    return receipt['result']['value']


def metric(text, name):
    section = text.split('收益概述\n策略收益\n', 1)
    if len(section) < 2:
        return None
    section = '策略收益\n' + section[1]
    match = re.search(r'(?:^|\n)' + re.escape(name) + r'\s*\n([^\n]+)', section)
    return match.group(1).strip() if match else None


def summarize(item):
    result = {key: item.get(key) for key in ['name', 'url']}
    result.update({key: metric(item['text'], key) for key in
                   ['策略收益', '策略年化收益', '基准收益', '最大回撤', '夏普比率', '超额收益']})
    assert '回测完成' in item['text'], item['name']
    for series in item.get('series', []):
        if series['name'] in ['orders', 'fills', 'switches', 'exposure']:
            result[series['name']] = series['last']['y']
    return result


def main():
    train = load_receipt(BASE/'train_results_receipt.json')
    curves = [load_receipt(path) for path in sorted(BASE.glob('curve_*_receipt.json'))]
    rows = [summarize(item) for item in train]
    extra = [summarize(item) for item in curves if item['name'] != 'train_rolling_010']
    source = (BASE/'nasdaq_etf_rotation.py').read_bytes()
    payload = {'capital': 100000, 'selected_mode': 'rolling', 'threshold_log': 0.01,
               'source_sha256': hashlib.sha256(source).hexdigest(), 'training': rows,
               'validation': extra, 'curves': curves,
               'stress_assumptions': {'commission_each_side': 0.0005, 'min_commission': 10,
                                      'fixed_slippage_roundtrip_yuan': 0.008,
                                      'limit_offset_yuan': 0.005}}
    (BASE/'backtest_results.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    names = {'train_daily_005': '昨日涨跌幅 / 0.5%', 'train_daily_010': '昨日涨跌幅 / 1%',
             'train_rolling_005': '20日相对价格 / 0.5%', 'train_rolling_010': '2024训练期：20日相对价格 / 1%',
             'train_nav_005': '滞后同日净值 / 0.5%', 'holdout_2025': '2025 独立留出期',
             'latest_2026': '2026-01-01至10-09 独立留出期', 'stress_2025': '2025 双倍费用及滑点',
             'revalidate_2024': '2024 最终代码复核', 'bear_2022_2023': '2022—2023 历史压力回放'}
    lines = ['# 纳斯达克100 ETF相对价差轮动：聚宽分钟回测', '',
             '资金10万元；参考ETF300和ETF创业板的同指数价差换仓逻辑。所有数字来自本次实际运行的聚宽回测，原始页面回执和链接保留在同目录。', '',
             '## 策略与选择方法', '',
             '最终选择20日相对价格基线、1%换仓门槛。在2024年五个候选中按净收益选择，随后锁定参数检验2025年、2026年。有限候选的最好结果不等于全局最优。2022—2023如有结果，仅为回溯压力检验，不是时间上位于训练期之后的独立留出期。', '',
             '设b_i为过去20个交易日[log(ETF_i收盘价)-当日ETF池log价格中位数]的中位数，当前评分s_i=log(已完成分钟收盘价)-b_i。买入评分最低的合格ETF；持仓评分比目标高出至少0.01，且超过预计换仓成本的1.5倍时才换仓。此处0.01为对数价差，约等于1.005%的简单价差。', '',
             '净值版本是一个未入选的对照：用至少滞后5个A股交易日的共同净值日期比较P/NAV。不把它标作实时绝对溢价，净值公告时点没有逐条重建。', '',
             '## 2024训练期候选', '',
             '| 候选 | 收益 | 基准 | 最大回撤 | 夏普 | 换仓信号数 |',
             '|---|---:|---:|---:|---:|---:|']
    for row in rows:
        lines.append('| %s | %s | %s | %s | %s | %s |' % (names[row['name']], row['策略收益'], row['基准收益'], row['最大回撤'], row['夏普比率'], row.get('switches')))
    lines += ['', '## 最终策略验证', '', '| 区间 | 收益 | 基准 | 最大回撤 | 夏普 |', '|---|---:|---:|---:|---:|']
    for row in extra:
        lines.append('| %s | %s | %s | %s | %s |' % (names.get(row['name'], row['name']), row['策略收益'], row['基准收益'], row['最大回撤'], row['夏普比率']))
    lines += ['', '每个区间从独立的10万元账户起跑，不能直接把各区间收益相加或当成连续账户实测。聚宽“超额收益”采用相对净值口径，收益率相减得到的是百分点差，二者不能混称。', '',
              '成本压力测试保持滚动20日与1%门槛：单边佣金提高至万5、每笔最低10元、双边总滑点0.008元，预计成本门槛同步更新，限价容忍范围提高至5个价位以容纳压力滑点。并非根据留出期收益重新选择参数。', '',
              '独立留出期标准成本下均跑赢基准；但2025双倍成本下收益15.20%，仅比基准14.78%高0.42个百分点，且回撤25.07%。成本敏感性明显，不能据此保证实盘超额收益。', '',
              '## 实际交易约束', '',
              '- 仅交易代码中明确列出的11只境内上市纳斯达克100 ETF；不混入纳斯达克科技、生物科技、标普500、LOF或美股。',
              '- 回测时按上市至少60天、过去20日平均成交额至少1000万元过滤；基金池为事先列出的固定池，没有重建全市场历史存续ETF集合。',
              '- 每边佣金万2.5，每笔最低5元，基金印花税设为0；这些是回测假设，并非已核实的用户券商费率。',
              '- FixedSlippage(0.004)表示聚宽双边总价差0.004元，单边0.002元，即2个最小价格单位。',
              '- 成交参与率5%，另外按上一已完成分钟成交量与近3分钟均量较小者的5%限制单笔数量。候选需要该数量对应至少1万元，不等于每笔实际成交都一定超过1万元；撮合仍可能部分成交。',
              '- 使用限价单、100份买入单位、1%现金预留；零股全额卖出有单独处理。成交价格、手续费和分批次数由聚宽撮合记录确认。',
              '- 先卖后买，并以实际可卖余额、持仓、可用资金检查。每分钟撤销未完成订单；撤单后跳过当分钟，避免重复占用资金。最长30分钟转换任务可能留下部分仓位或现金。',
              '- 每5分钟检查新信号，09:40—14:50交易，午间至13:05暂停；每天最多6次换仓信号，换仓信号至少间隔15分钟。',
              '- 对停牌、零成交、涨跌停附近价格进行过滤。盘口深度、真实排队与撤单网络延迟并未由分钟K线重建。', '',
              '## 结果的适用边界', '',
              '这是纯多头的统计价差轮动，不是锁定现金流的无风险套利。收益包含纳指上涨、汇率变化、国内溢价变化和换仓影响。没有做空腿或期货对冲，隔夜可能发生跳空亏损。即使相对便宜，各基金也可能共同处于高溢价状态。', '',
              '最终版本没有把实时IOPV、基金申购额度、申赎开放状态、公告公布时间和纳指期货价差加入历史回测。正式交易前应接入这些实时数据并核验券商订单状态；不能把此次分钟回测直接标为已验证的实盘套利。', '',
              '基金管理人的高溢价停复牌公告显示，该风险是真实存在的：[159941溢价及停复牌公告](https://disc.static.szse.cn/disc/disk03/finalpage/2026-09-14/0a48f444-1e6f-4fac-a78b-cae2bcaaf97e.PDF)。', '',
              '跨境ETF二级市场可T+0交易：[上交所规则说明](https://www.sse.com.cn/assortment/fund/etf/question/c/c_20240118_5734755.shtml)。申赎另有确认和交收安排，此策略未使用申赎。聚宽滑点与净值接口口径：[聚宽API文档](https://cdn.joinquant.com/help/img/JoinQuantAPI.pdf)。', '',
              '## 回测链接', '']
    for row in rows+extra:
        lines.append('- [%s](%s)' % (names.get(row['name'], row['name']), row['url']))
    lines += ['', '最终源码：nasdaq_etf_rotation.py；执行安全测试：test_execution.py；结构化结果：backtest_results.json。', '',
              '源码SHA256：`%s`。' % payload['source_sha256'], '']
    (BASE/'回测报告.md').write_text('\n'.join(lines), encoding='utf-8')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.font_manager import FontProperties
    font = FontProperties(fname=r'C:\Windows\Fonts\msyh.ttc')
    chosen = [c for c in curves if c['name'] in ['train_rolling_010', 'holdout_2025', 'latest_2026']]
    chosen.sort(key=lambda c: ['train_rolling_010', 'holdout_2025', 'latest_2026'].index(c['name']))
    fig, axes = plt.subplots(len(chosen), 1, figsize=(12, 3.8*len(chosen)), squeeze=False)
    for ax, item in zip(axes[:, 0], chosen):
        for series in item['series']:
            if series['name'] not in ['策略收益', '基准收益'] or 'data' not in series:
                continue
            points = [(datetime.fromtimestamp(x/1000, timezone.utc), y) for x, y in series['data'] if y is not None]
            ax.plot([p[0] for p in points], [p[1] for p in points], label=series['name'], linewidth=1.5)
        ax.set_title(names.get(item['name'], '2024 训练期选择'), fontproperties=font)
        ax.set_ylabel('累计收益 (%)', fontproperties=font)
        ax.grid(alpha=0.2)
        ax.legend(prop=font)
    fig.tight_layout()
    fig.savefig(BASE/'收益曲线.png', dpi=160)
    print(json.dumps({'training': rows, 'validation': extra}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
