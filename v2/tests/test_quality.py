# -*- coding: utf-8 -*-
"""원천 점검 — 완전히 같은 행을 백업의 quality.dups 에 남기는지 · 이어 붙일 때 같은 날짜는 새 결과로"""
import sys
import warnings
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
warnings.filterwarnings('ignore')
import build_data as bd  # noqa: E402
import make_sample  # noqa: E402


def test_dups_found_and_replaced(tmp_path):
    df = make_sample.make('2026-10-01', '2026-10-07', seed=3)
    md = df['구분_매체명'].iloc[0]
    extra = df[(df['구분_매체명'] == md) & (df['기간_일자'].astype(str).str.contains('2026-10-03|20261003'))]
    assert len(extra)
    f1 = tmp_path / 'dup.pkl'
    pd.concat([df, extra]).to_pickle(f1)
    p = bd.build([f1], use_cache=False)
    dups = p['quality']['dups']
    assert dups and all(r[0] == '2026-10-03' and r[1] == md for r in dups)
    assert sum(r[3] for r in dups) == len(extra[(extra['지표_광고비'].astype(float) != 0) | (extra['지표_노출수'].astype(float) > 0)])
    # 같은 날짜를 깨끗한 파일로 다시 넣으면 중복 기록이 사라진다
    f2 = tmp_path / 'clean.pkl'
    df.to_pickle(f2)
    p2 = bd.build([f2], base=p, use_cache=False)
    assert p2['quality']['dups'] == []


def _shifted_csv(df, path, day, start='지표_UV(전체)', overflow=True):
    """day 의 행만 start 열부터 값을 한 칸씩 오른쪽으로 민 csv (원천 열 밀림 재현)"""
    import csv
    cols = list(df.columns)
    s = cols.index(start)
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in df.itertuples(index=False):
            r = ['' if v is None else v for v in r]
            if str(r[0]) == day:
                r = r[:s] + [''] + r[s:]
                if not overflow:
                    r = r[:-1]
            w.writerow(r)


def _by_date(p):
    df, _ = bd.decode(p['row'])
    return df.groupby('date')[['cost', 'nrev', 'uv', 'npay', 'trev']].sum()


def test_clean_has_no_shift(tmp_path):
    df = make_sample.make('2026-11-10', '2026-11-16', seed=5)
    f = tmp_path / 'clean.csv'
    df.to_csv(f, index=False, encoding='utf-8-sig')
    q = bd.build([f], use_cache=False)['quality']
    assert q['shift'] == [] and q['broken'] == []
    assert {r[0] for r in q['rows']} == {f'2026-11-{d}' for d in range(10, 17)}


def test_shift_fixed_with_overflow(tmp_path):
    df = make_sample.make('2026-11-10', '2026-11-16', seed=5)
    clean = tmp_path / 'clean.csv'
    df.to_csv(clean, index=False, encoding='utf-8-sig')
    bad = tmp_path / 'bad.csv'
    _shifted_csv(df, bad, '2026-11-16')
    want = _by_date(bd.build([clean], use_cache=False))
    p = bd.build([bad], use_cache=False)
    got = _by_date(p)
    pd.testing.assert_frame_equal(got, want)
    sh = p['quality']['shift']
    n16 = int(((df['기간_일자'] == '2026-11-16') & (df[[c for c in df.columns if c.startswith('지표_')]].astype(float).abs().sum(axis=1) > 0)).sum())
    assert {r[0] for r in sh} == {'2026-11-16'} and {r[5] for r in sh} == {'UV(전체)'}
    assert sum(r[3] for r in sh) == n16
    assert p['quality']['broken'] == []


def test_shift_fixed_without_overflow_xlsx(tmp_path):
    """마지막 칸이 잘려 헤더보다 칸이 많지 않아도 지표 관계로 찾아낸다 (xlsx)"""
    df = make_sample.make('2026-11-10', '2026-11-16', seed=6)
    clean = tmp_path / 'clean.csv'
    df.to_csv(clean, index=False, encoding='utf-8-sig')
    tmp = tmp_path / 'bad.csv'
    _shifted_csv(df, tmp, '2026-11-15', overflow=False)
    x = tmp_path / 'bad.xlsx'
    pd.read_csv(tmp, dtype=str, keep_default_na=False).replace('', None).to_excel(x, index=False, sheet_name='로우')
    want = _by_date(bd.build([clean], use_cache=False))
    p = bd.build([x], use_cache=False)
    pd.testing.assert_frame_equal(_by_date(p), want, check_dtype=False)
    assert {r[0] for r in p['quality']['shift']} == {'2026-11-15'}


def test_quality_merge_replaces_dates(tmp_path):
    df = make_sample.make('2026-11-10', '2026-11-16', seed=5)
    bad = tmp_path / 'bad.csv'
    _shifted_csv(df, bad, '2026-11-16')
    p = bd.build([bad], use_cache=False)
    assert p['quality']['shift']
    fix = tmp_path / 'fix.csv'
    df[df['기간_일자'] == '2026-11-16'].to_csv(fix, index=False, encoding='utf-8-sig')
    p2 = bd.build([fix], base=p, use_cache=False)
    assert p2['quality']['shift'] == [] and len(p2['quality']['rows']) == 7
