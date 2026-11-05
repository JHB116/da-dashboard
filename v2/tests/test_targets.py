# -*- coding: utf-8 -*-
"""목표 파일(보고서 엑셀) 읽기 · 진행 중인 달 MTD 목표 — 기존 dashboard.py 와 같은 값인지"""
import json
import subprocess
import sys
import warnings
from pathlib import Path

import pandas as pd
import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent.parent))
warnings.filterwarnings('ignore')
import make_sample  # noqa: E402
import targets as tgm  # noqa: E402

try:
    import dashboard as old
except Exception as e:  # pragma: no cover
    pytest.skip(f'dashboard.py 를 불러오지 못함: {e}', allow_module_level=True)


def test_targets_match_old(tmp_path):
    f = make_sample.make_targets(tmp_path)
    data = f.read_bytes()
    o, n = old.load_targets_from_report(data), tgm.parse_targets(data, f.name)
    assert n['monthly']['TOTAL']
    for k, v in n['monthly']['TOTAL'].items():
        ov = o['monthly']['TOTAL'][(int(k[:4]), int(k[5:]))]
        assert abs(ov['spend'] - v['spend']) < 1 and abs(ov['rev'] - v['rev']) < 1
    for k, v in n['weekly'].items():
        iso = pd.Timestamp(k).isocalendar()
        assert abs(o['weekly'][(int(iso[0]), int(iso[1]))]['spend'] - v['spend']) < 1
    (tmp_path / 't.json').write_text(json.dumps(n))
    for last in ['2026-10-11', '2026-10-01', '2026-10-31', '2026-11-04']:
        dm = pd.Timestamp(last)
        om = old.mtd_target_from_weekly(o['weekly_rows'], dm.year, dm.month, dm)
        js = subprocess.run(['node', '-e', '''
          const C=require(process.argv[1]),T=require(process.argv[2]),d=process.argv[3];
          const y=+d.slice(0,4),m=+d.slice(5,7),s=C.dnum(`${d.slice(0,7)}-01`),e=s+C.monthDays(y,m)-1;
          console.log(JSON.stringify(C.periodTarget(T,'TOTAL','month',{key:d.slice(0,7),start:s,end:e,partial:C.dnum(d)<e},d)));''',
            str(HERE.parent / 'calc.js'), str(tmp_path / 't.json'), last], capture_output=True, check=True, text=True).stdout
        nm = json.loads(js)
        if dm.day < pd.Timestamp(last).days_in_month:
            assert abs(nm['spend'] - om['spend']) < 1 and abs(nm['rev'] - om['rev']) < 1, (last, nm, om)
        else:   # 끝난 달은 월 목표 그대로
            mt = n['monthly']['TOTAL'][last[:7]]
            assert abs(nm['spend'] - mt['spend']) < 1
