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
