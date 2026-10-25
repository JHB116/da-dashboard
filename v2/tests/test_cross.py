# -*- coding: utf-8 -*-
"""기존 dashboard.py 와 새 calc.js 의 숫자 대조 (가짜 원본)

같은 원본을
  ① 기존 dashboard.py 함수(load_data · agg · calc_kpi · _filter_cost · _sameday_prev)로,
  ② build_data.py → 백업 → calc.js 로
계산해 월 · 주 · 일별 실적과 전년비(동요일) 비교값이 같은지 본다.
주별은 연말연초에 걸친 주만 기준이 다르다(기존: 달력 연도 × ISO 주차로 나뉨 · 새: 월~일 한 주) — 그 주는 빼고 비교한다.
"""
import io
import json
import subprocess
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

HERE = Path(__file__).resolve().parent
V2 = HERE.parent
sys.path.insert(0, str(V2))
sys.path.insert(0, str(V2.parent))
warnings.filterwarnings('ignore')

import build_data as bd  # noqa: E402
import make_sample  # noqa: E402

try:
    import dashboard as old  # 기존 대시보드 (저장소 루트)
except Exception as e:  # pragma: no cover
    pytest.skip(f'dashboard.py 를 불러오지 못함: {e}', allow_module_level=True)

# calc.js 지표 키 → dashboard.py 집계 컬럼
COLS = {
    'cost': '지표_광고비', 'nrev': '지표_순결제거래액', 'roas': '순결제ROAS', 'npr': '순결제비중', 'trev': '지표_총결제거래액',
    'troas': '총결제ROAS', 'uv': '지표_UV(전체)', 'crt': 'CR(총)', 'crct': 'CR(클릭기준·총)', 'aovt': '객단가(총)', 'cpc': 'CPC', 'ctr': 'CTR', 'cpuv': 'CPUV',
    'join': '지표_가입회원', 'jcpa': '가입CPA', 'nbr': '지표_당년신규순결제거래액', 'fp': '지표_순결제고객수(첫구매)', 'fcpa': '첫구매CPA',
    'imp': '지표_노출수', 'clk': '지표_클릭수', 'cpm': 'CPM', 'npay': '지표_순결제고객수', 'crn': 'CR(순)', 'aovn': '객단가(순)',
    'tpay': '지표_총결제고객수', 'uvc': 'UV/클릭', 'jr': '가입률', 'fpu': '첫구매율', 'fpr': '지표_순결제거래액(첫구매)', 'fps': '첫구매비중',
    'nb': '지표_당년신규순결제고객수', 'ncpa': '신규CPA', 'nbs': '신규비중', 'wb': '지표_순결제고객수(윈백)', 'wbr': '지표_순결제거래액(윈백)',
}
SUMS = {'cost', 'nrev', 'trev', 'uv', 'join', 'nbr', 'fp', 'imp', 'clk', 'npay', 'tpay', 'fpr', 'nb', 'wb', 'wbr'}


@pytest.fixture(scope='module')
def env(tmp_path_factory):
    tmp = tmp_path_factory.mktemp('cross')
    make_sample.main(tmp)
    # ① 기존: dashboard.load_dataset 과 같은 병합 (24년 파일은 2025년 이전만 + 매일 파일은 2025년 이후)
    main = old.load_data((tmp / 'sample_2526.csv').read_bytes(), 'x.csv')
    d24 = old.load_data((tmp / 'sample_24.csv').read_bytes(), 'x.csv')
    df = pd.concat([d24[d24['연도'] < 2025], main[main['연도'] >= 2025]], ignore_index=True)
    # ② 새: 백업
    bd.CACHE_DIR = tmp / 'cache'
    payload = bd.build([tmp / 'sample_2526.csv'], [tmp / 'sample_24.csv'], use_cache=False)
    bfile = tmp / 'b.json.gz'
    bfile.write_bytes(bd.backup_bytes(payload))
    return df, bfile


def js(bfile, grain, bucket, where=None):
    args = ['node', str(HERE / 'calc_dump.js'), str(bfile), grain, bucket] + ([json.dumps(where, ensure_ascii=False)] if where else [])
    return json.loads(subprocess.run(args, capture_output=True, check=True).stdout)


def close(a, b):
    if a is None or (isinstance(a, float) and np.isnan(a)):
        return b is None or (isinstance(b, float) and (np.isnan(b) or np.isinf(b)))
    if b is None or (isinstance(b, float) and np.isnan(b)):
        return False
    return abs(a - b) <= 1e-6 * max(1.0, abs(a), abs(b))


def compare(df_tab, rows, gran):
    cols = old.PERIOD_COLS[gran]
    cur = old.agg(df_tab, cols)
    prev = old._sameday_prev(df_tab, gran)
    mixed = set()
    if gran == '주':   # 기존 집계는 (달력 연도, ISO 주차) — ISO 연도가 다른 날짜(연말연초)가 섞인 주는 기준이 다르다
        iy = df_tab['기간_일자'].dt.isocalendar().year.astype(int)
        mixed = set(map(tuple, df_tab.loc[iy != df_tab['연도'], ['연도', '주차번호']].drop_duplicates().astype(int).to_numpy()))
    by = {}
    for _, r in cur.iterrows():
        if gran == '월':
            key = f"{int(r['연도'])}-{int(r['월']):02d}"
        elif gran == '주':
            if (int(r['연도']), int(r['주차번호'])) in mixed:
                continue
            mon = pd.Timestamp.fromisocalendar(int(r['연도']), int(r['주차번호']), 1)
            if mon.year != int(r['연도']):
                continue
            key = mon.strftime('%Y-%m-%d')
        else:
            key = pd.Timestamp(r['기간_일자']).strftime('%Y-%m-%d')
        by[key] = (r, prev.get(old._period_key(gran, r)))
    n = 0
    for row in rows:
        if row['key'] not in by:
            continue
        r, p = by[row['key']]
        days = int(r['집행일수']) if '집행일수' in r else 1
        assert row['days'] == days, (row['key'], 'days')
        for k, col in COLS.items():
            assert close(row[k], float(r[col]) if pd.notna(r[col]) else None), (gran, row['key'], k, row[k], r[col])
            if k in SUMS:
                assert close(row[k + '_avg'], float(r[col]) / days), (gran, row['key'], k, 'avg')
            pv = float(p[col]) if p is not None and pd.notna(p[col]) else None
            assert close(row[k + '_yoy'], pv), (gran, row['key'], k, 'yoy', row[k + '_yoy'], pv)
        n += 1
    assert n >= len(by) * 0.9 and n > 0, (n, len(by))
    return n


@pytest.mark.parametrize('gran,grain', [('월', 'month'), ('주', 'week'), ('일', 'day')])
@pytest.mark.parametrize('bucket', ['TOTAL', 'TOTAL(서비스비용미반영)', '신규고객확대'])
def test_period_matches_old(env, gran, grain, bucket):
    df, bfile = env
    compare(old._filter_cost(df, bucket), js(bfile, grain, bucket), gran)


def test_filter_matches_old(env):
    df, bfile = env
    sub = old._filter_cost(df, 'TOTAL')
    sub = sub[sub['구분_매체명'].isin(['카카오 비즈보드', '네이버 GFA']) & (sub['구분_디바이스'] == 'MO')]
    compare(sub, js(bfile, 'month', 'TOTAL', {'md': ['카카오 비즈보드', '네이버 GFA'], 'dev': ['MO']}), '월')


def test_lock_and_merge(tmp_path):
    """24년 고정 구간 · 매일 파일 이어 붙이기 — Python(build --base)과 JS(mergeBackup)가 같은 결과"""
    make_sample.main(tmp_path)
    bd.CACHE_DIR = tmp_path / 'cache'
    full = bd.build([tmp_path / 'sample_2526.csv', tmp_path / 'sample_1011.csv'], [tmp_path / 'sample_24.csv'], use_cache=False)
    # 순서를 바꿔 넣어도(매일 파일 먼저 → 24년 → 다음 날) 결과가 같아야 한다
    a = bd.build([tmp_path / 'sample_2526.csv'], use_cache=False)
    b = bd.build(y24_paths=[tmp_path / 'sample_24.csv'], use_cache=False)
    c = bd.build([tmp_path / 'sample_1011.csv'], use_cache=False)
    step = bd.build(y24_paths=[tmp_path / 'sample_24.csv'], base=a, use_cache=False)
    step = bd.build([tmp_path / 'sample_1011.csv'], base=step, use_cache=False)
    for name, p in [('full', full), ('a', a), ('b', b), ('c', c), ('step', step)]:
        (tmp_path / f'{name}.json.gz').write_bytes(bd.backup_bytes(p))
    merged = subprocess.run(['node', '-e', '''
      const fs=require('fs'),zlib=require('zlib'),C=require(process.argv[1]);
      const rd=f=>JSON.parse(zlib.gunzipSync(fs.readFileSync(f)).toString());
      let m=C.mergeBackup(rd(process.argv[2]),rd(process.argv[3])); m=C.mergeBackup(m,rd(process.argv[4]));
      fs.writeFileSync(process.argv[5], JSON.stringify(m));''', str(V2 / 'calc.js'),
        str(tmp_path / 'a.json.gz'), str(tmp_path / 'b.json.gz'), str(tmp_path / 'c.json.gz'), str(tmp_path / 'm.json')], check=True)
    m = json.loads((tmp_path / 'm.json').read_text())

    def table(p):
        df, _ = bd.decode(p['row'])
        g = df.groupby(['date', 'md', 'src', 'dev'])[['cost', 'nrev', 'join']].sum().round(2)
        return g.sort_index()

    t_full = table(full)
    pd.testing.assert_frame_equal(t_full, table(step))
    pd.testing.assert_frame_equal(t_full, table(m))
    assert m['source']['lock'] == bd.LOCK_UNTIL and step['source']['lock'] == bd.LOCK_UNTIL
    # 고정 구간(2024-12)은 24년 파일 값, 2025-01은 매일 파일 값
    raw24 = pd.read_csv(tmp_path / 'sample_24.csv')
    raw25 = pd.read_csv(tmp_path / 'sample_2526.csv')
    dfm, _ = bd.decode(m['row'])
    assert abs(dfm[dfm['date'] == '2024-12-15']['cost'].sum() - raw24[raw24['기간_일자'] == '2024-12-15']['지표_광고비'].sum()) < 1
    assert abs(dfm[dfm['date'] == '2025-01-15']['cost'].sum() - raw25[raw25['기간_일자'] == '2025-01-15']['지표_광고비'].sum()) < 1
