"""
sx_kpi.py - SX指数の成績KPIを集計する（株式会社サクシス 全社員共通の道具）

使い方:
  python3 tools/sx_kpi.py                       # 全体 + グレード別
  python3 tools/sx_kpi.py --by place            # 切り口を指定
  python3 tools/sx_kpi.py --by conf_band --from 2026-05-01 --to 2026-05-31
  python3 tools/sx_kpi.py --json                # 機械可読で出力

切り口(--by): grade, place, class_code, field_size, conf_band, model, date

回収率の扱い:
  ◎の単勝オッズ(ai_top1_odds)が記録されたレースだけで計算する。
  オッズが「当たったレースにだけ」記録されていると回収率が大きく上振れするため、
  記録率が ODDS_COVERAGE_MIN 未満の区分は回収率を出さない（'-' / null）。
"""
import argparse
import json
import sys
from collections import OrderedDict
from pathlib import Path

LOG_FILE = Path(__file__).resolve().parent.parent / 'daily_results_log.json'
MIN_SAMPLE = 100
ODDS_COVERAGE_MIN = 0.9
GRADE_ORDER = {'S': 0, 'A': 1, 'B': 2, 'C': 3}


def load_races(path, date_from=None, date_to=None):
    with open(path, encoding='utf-8') as f:
        log = json.load(f)
    races = []
    for day in log.get('days', []):
        for r in day.get('races', []):
            r = dict(r)
            r['date'] = day.get('date', r.get('date'))
            r['model'] = day.get('model', r.get('model', 'unknown'))
            if date_from and r['date'] < date_from:
                continue
            if date_to and r['date'] > date_to:
                continue
            races.append(r)
    return races


def top1_odds(r):
    """◎の単勝オッズ。勝ち馬オッズでの補完はしない（的中分だけ埋まり上振れするため）。"""
    return r.get('ai_top1_odds')


def conf_band(r):
    c = r.get('ai_top1_conf')
    if c is None:
        return '不明'
    lo = min(int(c * 10), 9) * 10
    return f'{lo:02d}-{lo + 10}%'


def segment_key(r, by):
    if by == 'conf_band':
        return conf_band(r)
    v = r.get(by)
    return '不明' if v is None else v


def summarize(races):
    n = len(races)
    if n == 0:
        return {'races': 0}
    win = sum(bool(r.get('hit_win')) for r in races)
    plc = sum(bool(r.get('hit_place')) for r in races)
    qui = sum(bool(r.get('hit_quinella')) for r in races)
    trio = sum(bool(r.get('hit_trio_box')) for r in races)
    priced = [r for r in races if top1_odds(r) is not None]
    payout = sum(top1_odds(r) * 100 for r in priced if r.get('hit_win'))
    coverage = len(priced) / n
    roi_ok = bool(priced) and coverage >= ODDS_COVERAGE_MIN
    confs = [r['ai_top1_conf'] for r in races if r.get('ai_top1_conf') is not None]
    return OrderedDict([
        ('races', n),
        ('win_rate', round(win / n * 100, 1)),
        ('place_rate', round(plc / n * 100, 1)),
        ('quinella_rate', round(qui / n * 100, 1)),
        ('trio_box_rate', round(trio / n * 100, 1)),
        ('avg_conf', round(sum(confs) / len(confs) * 100, 1) if confs else None),
        ('roi_races', len(priced)),
        ('win_roi', round(payout / (len(priced) * 100) * 100, 1) if roi_ok else None),
        ('odds_coverage', round(coverage * 100, 1)),
        ('odds_missing', n - len(priced)),
        ('sample_ok', n >= MIN_SAMPLE),
    ])


def by_segment(races, by):
    groups = {}
    for r in races:
        groups.setdefault(segment_key(r, by), []).append(r)

    def sort_key(k):
        if by == 'grade':
            return (GRADE_ORDER.get(k, 99), str(k))
        return (0, k) if isinstance(k, (int, float)) else (1, str(k))

    return OrderedDict((str(k), summarize(groups[k])) for k in sorted(groups, key=sort_key))


def data_quality(races):
    return OrderedDict([
        ('races', len(races)),
        ('days', len({r['date'] for r in races})),
        ('top1_odds_missing', sum(r.get('ai_top1_odds') is None for r in races)),
        ('top1_odds_missing_on_hit', sum(r.get('ai_top1_odds') is None and bool(r.get('hit_win')) for r in races)),
        ('top1_odds_missing_on_miss', sum(r.get('ai_top1_odds') is None and not r.get('hit_win') for r in races)),
        ('winner_name_unknown', sum(r.get('win_name') in (None, '', '不明') for r in races)),
    ])


def fmt(v, suffix=''):
    return '-' if v is None else f'{v}{suffix}'


def print_table(title, rows):
    print(f'\n## {title}')
    head = ['区分', 'R数', '単勝%', '複勝%', '馬連%', '3複BOX%', '平均自信%', '回収率%', 'オッズ記録率%', '判定']
    print(' | '.join(head))
    print(' | '.join(['---'] * len(head)))
    for name, s in rows.items():
        if s['races'] == 0:
            continue
        print(' | '.join([
            str(name), str(s['races']), fmt(s['win_rate']), fmt(s['place_rate']),
            fmt(s['quinella_rate']), fmt(s['trio_box_rate']), fmt(s['avg_conf']),
            fmt(s['win_roi']), fmt(s['odds_coverage']),
            '' if s['sample_ok'] else '参考値',
        ]))


def main(argv=None):
    p = argparse.ArgumentParser(description='SX指数の成績KPI集計')
    p.add_argument('--log', default=str(LOG_FILE))
    p.add_argument('--by', default='grade',
                   choices=['grade', 'place', 'class_code', 'field_size', 'conf_band', 'model', 'date'])
    p.add_argument('--from', dest='date_from')
    p.add_argument('--to', dest='date_to')
    p.add_argument('--json', action='store_true')
    a = p.parse_args(argv)

    races = load_races(a.log, a.date_from, a.date_to)
    result = OrderedDict([
        ('period', [a.date_from or (min(r['date'] for r in races) if races else None),
                    a.date_to or (max(r['date'] for r in races) if races else None)]),
        ('data_quality', data_quality(races)),
        ('overall', summarize(races)),
        ('by', a.by),
        ('segments', by_segment(races, a.by)),
    ])

    if a.json:
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        print()
        return 0

    q = result['data_quality']
    print(f"# SX KPI  期間: {result['period'][0]} 〜 {result['period'][1]}  "
          f"({q['days']}日 / {q['races']}レース)")
    print(f"データ品質: ◎オッズ欠損 {q['top1_odds_missing']}件"
          f"（◎的中 {q['top1_odds_missing_on_hit']}件 / ◎不的中 {q['top1_odds_missing_on_miss']}件）"
          f" / 勝ち馬名不明 {q['winner_name_unknown']}件")
    if result['overall'].get('races') and result['overall']['win_roi'] is None:
        print(f'※ ◎オッズの記録率が{int(ODDS_COVERAGE_MIN * 100)}%未満のため回収率は計算できません。'
              '外れたレースの◎オッズも記録してください。')
    if q['races'] == 0:
        print('対象レースがありません。')
        return 0
    if q['races'] < MIN_SAMPLE:
        print(f'※ {MIN_SAMPLE}レース未満のため、すべて参考値です。')
    print_table('全体', OrderedDict([('全体', result['overall'])]))
    print_table(f'{a.by} 別', result['segments'])
    print('\n回収率は ◎単勝100円均等買い。オッズ記録率90%未満の区分は「-」。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
