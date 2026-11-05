# -*- coding: utf-8 -*-
"""목표 파일(보고서 엑셀) → 목표 JSON — 기존 dashboard.py load_targets_from_report 와 같은 규칙

신규 양식: 'SNS/버즈빌/포탈' 3매체 목표를 합산한 값이 DA 전체 목표
  - 월별: 시트 '월TOTAL요약(누계)'   (연도, 월, {매체}_광고비 / _거래액)
  - 주차별: 시트 '통합_전체' 또는 '누계'  (연도, 월, 기간 '(9/28~…)', 광고비, 거래액)
구 양식(월별_TOTAL … / 주차별 시트)도 읽는다.

반환(JSON 으로 그대로 저장):
  {"monthly": {묶음: {"YYYY-MM": {"spend", "rev"}}},
   "weekly": {"월요일 YYYY-MM-DD": {"spend", "rev"}},
   "weekly_rows": {"YYYY-MM": [["시작일", spend, rev], …]},   # 진행 중인 달 MTD 목표용
   "file": 파일명}
"""
from __future__ import annotations

import io
import re

import pandas as pd


def _num(v) -> float:
    try:
        f = float(v)
        return 0.0 if pd.isna(f) else f
    except Exception:
        return 0.0


def _monday(year: int, week: int) -> str:
    return pd.Timestamp.fromisocalendar(int(year), int(week), 1).strftime('%Y-%m-%d')


def parse_targets(data: bytes, name: str = '') -> dict:
    out = {'monthly': {}, 'weekly': {}, 'weekly_rows': {}, 'file': name}
    xls = pd.ExcelFile(io.BytesIO(data), engine='openpyxl')
    sheets = xls.sheet_names
    if '월TOTAL요약(누계)' in sheets or '통합_전체' in sheets or '누계' in sheets:
        media = ['SNS', '버즈빌', '포탈']
        total = {}
        if '월TOTAL요약(누계)' in sheets:
            d = pd.read_excel(xls, sheet_name='월TOTAL요약(누계)', header=0)
            d.columns = [str(c).strip() for c in d.columns]
            for _, r in d.iterrows():
                try:
                    y, mo = int(r['연도']), int(r['월'])
                except Exception:
                    continue
                sp = sum(_num(r.get(f'{m}_광고비')) for m in media)
                rv = sum(_num(r.get(f'{m}_거래액')) for m in media)
                if sp or rv:
                    total[f'{y}-{mo:02d}'] = {'spend': sp, 'rev': rv}
        out['monthly']['TOTAL'] = total
        out['monthly']['TOTAL(서비스비용미반영)'] = total
        wk_sheet = next((s for s in ('통합_전체', '누계') if s in sheets), None)
        if wk_sheet:
            w = pd.read_excel(xls, sheet_name=wk_sheet, header=0)
            w.columns = [str(c).strip() for c in w.columns]
            weekly, rows = {}, {}
            for _, r in w.iterrows():
                lab = str(r.get('기간', ''))
                if 'TOTAL' in lab:
                    continue
                mt = re.search(r'\((\d{1,2})/(\d{1,2})', lab)
                if not mt:
                    continue
                try:
                    yr, mo = int(r['연도']), int(r['월'])
                    sd = pd.Timestamp(yr, int(mt.group(1)), int(mt.group(2)))
                except Exception:
                    continue
                iso = sd.isocalendar()
                key = _monday(iso[0], iso[1])
                sp, rv = _num(r.get('광고비')), _num(r.get('거래액'))
                cur = weekly.setdefault(key, {'spend': 0.0, 'rev': 0.0})
                cur['spend'] += sp
                cur['rev'] += rv
                acc = rows.setdefault(f'{yr}-{mo:02d}', {}).setdefault(sd.strftime('%Y-%m-%d'), [0.0, 0.0])
                acc[0] += sp
                acc[1] += rv
            out['weekly'] = {k: v for k, v in weekly.items() if v['spend'] or v['rev']}
            out['weekly_rows'] = {ym: [[d, v[0], v[1]] for d, v in sorted(wk.items())] for ym, wk in rows.items()}
        return out
    # 구 양식 (하위 호환)
    sheet_map = {'월별_TOTAL(서비스비용제외)': 'TOTAL', '월별_TOTAL': 'TOTAL(서비스비용미반영)',
                 '월별_거래액': '거래액확대', '월별_신규확대': '신규고객확대'}
    for sheet, tab in sheet_map.items():
        if sheet not in sheets:
            continue
        df = pd.read_excel(xls, sheet_name=sheet, header=None)
        tt = {}
        for _, row in df.iterrows():
            label = str(row.iloc[1]) if pd.notna(row.iloc[1]) else ''
            if '년' not in label or '주차' in label:
                continue
            try:
                y, mo = int(label[:4]), int(label[5:7])
            except Exception:
                continue
            tt[f'{y}-{mo:02d}'] = {'spend': _num(row.iloc[41]), 'rev': _num(row.iloc[42])}
        out['monthly'][tab] = tt
    if '주차별' in sheets:
        df = pd.read_excel(xls, sheet_name='주차별', header=None)
        for _, row in df.iterrows():
            label = str(row.iloc[1]) if pd.notna(row.iloc[1]) else ''
            if '주차' not in label or len(label) < 8:
                continue
            try:
                date = pd.to_datetime(label[:8], format='%Y%m%d')
            except Exception:
                continue
            iso = date.isocalendar()
            sp, rv = _num(row.iloc[38]), _num(row.iloc[39])
            if sp > 0 or rv > 0:
                out['weekly'][_monday(iso[0], iso[1])] = {'spend': sp, 'rev': rv}
    return out


def count(t: dict) -> tuple[int, int]:
    """(월 목표 수, 주 목표 수)"""
    return sum(len(v) for v in t.get('monthly', {}).values()), len(t.get('weekly', {}))
