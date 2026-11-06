# -*- coding: utf-8 -*-
"""DA 광고 실적 대시보드 v2 — 원천(DA 로데이터 xlsb · csv · xlsx) → 백업 파일(.json.gz)

사용법 (PC — make_backup.bat 을 더블클릭해도 같다)
    python build_data.py                          # raw/ 폴더의 로데이터 전부 → 백업 (raw/2024/ 안의 파일은 24년 고정 파일로)
    python build_data.py --row 0612.xlsb          # 25·26년 파일(매일) 직접 지정
    python build_data.py --y24 24년.csv           # 24년 파일(처음 한 번) — 2024-12-31 까지만 쓰고 고정
    python build_data.py --base 기존백업.json.gz --row 0613.xlsb   # 기존 백업에 이어 붙이기 (같은 날짜는 교체)

결과: backup/DA대시보드_백업_YYYYMMDD.json.gz → 대시보드에 끌어다 놓으면 저장된 데이터에 날짜 단위로 합쳐진다.
Streamlit 화면(app.py)의 '원천 파일 올리기'도 같은 함수(build)를 쓴다.

- 원천: 기존 DA 대시보드(dashboard.py)와 같은 로데이터. 첫 행 헤더(기간_일자 · 구분_* · 카테고리 · 대상여부 · 지표_*).
  xlsb · xlsx 는 '로우' 시트가 있으면 그 시트, 없으면 첫 시트.
- 일자 × 구분(채널 · 매체 · 상품 · 캠페인 · 하위캠페인 · 부서 · 카테고리 · 비용출처 · 디바이스 · 기획전 …) 단위로 합산해 담는다.
  AF코드 · AF코드이름 · 키워드(소재)는 소재 화면 단계에서 따로 담는다(이 백업에는 없음).
- 24년 파일(--y24)은 2024-12-31 까지만 담고 '고정'으로 표시한다. 이후 매일 파일에 같은 날짜가 있어도 고정 구간은 바뀌지 않는다
  (기존 대시보드에서 24년 파일이 25년 이전 날짜를 맡던 것과 같다).
- 같은 날짜가 여러 매일 파일에 있으면 뒤(수정시각이 늦은) 파일 값을 쓴다. 기존 백업보다 새 파일이 우선(고정 구간 제외).
- 읽은 결과는 data/cache/ 에 저장해 두고, 원본이 바뀌지 않았으면 다시 읽지 않는다(예: 24년 파일은 처음 한 번만 읽음).
- 지표 산식 · 기간 규칙은 docs/METRICS.md, calc.js 와 같다. 바꾸면 tests/ 도 함께 고친다.
"""
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import io
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
RAW_DIR = ROOT / 'raw'
RAW24_DIR = RAW_DIR / '2024'
CACHE_DIR = ROOT / 'data' / 'cache'
OUT_DIR = ROOT / 'backup'

FORMAT = 'da-dashboard-backup'
VERSION = 1
LOCK_UNTIL = '2024-12-31'        # 24년 파일이 맡는 마지막 날짜 (기존 대시보드 DEFAULT_START_YEAR=2025 와 같은 경계)

ROW_SHEET = '로우'
ROW_DATE = '기간_일자'
# 원천 컬럼 → 백업 키 (구분). 같은 키에 후보가 여러 개면 앞의 것을 쓴다.
ROW_DIMS = {
    'at': ['구분_광고유형'],
    'tg': ['대상여부'],
    'ch': ['구분_채널'],
    'md': ['구분_매체명'],
    'pr': ['구분_상품', '구분_상품명'],
    'src': ['구분_비용출처'],
    'camp': ['구분_캠페인'],
    'sub': ['구분_하위캠페인'],
    'bpu': ['구분_부서명'],
    'cat': ['카테고리'],
    'dev': ['구분_디바이스'],
    'pno': ['구분_기획전 번호', '구분_기획전번호'],
    'bp': ['구분_브랜드/기획전'],
}
DIM_KEYS = list(ROW_DIMS)
# AF코드(소재) — 가장 잘게 쪼개진 단위라 최근 AF_DAYS 일만 따로 담는다(드릴다운의 AF코드 단계 · 소재 화면용)
AF_DIMS = {'af': ['구분_AF코드'], 'afn': ['구분_AF코드이름']}
AF_KEYS = list(AF_DIMS)
AF_ALL = DIM_KEYS + AF_KEYS
AF_DAYS = 92
# 원천 컬럼 → 백업 키 (지표). dashboard.py AGG_COLS 와 같은 목록
ROW_METRICS = {
    '지표_노출수': 'imp',
    '지표_클릭수': 'clk',
    '지표_광고비': 'cost',
    '지표_UV(전체)': 'uv',
    '지표_UV(회원)': 'uvm',
    '지표_PV(회원)': 'pvm',
    '지표_가입회원': 'join',
    '지표_순결제고객수': 'npay',
    '지표_총결제고객수': 'tpay',
    '지표_순결제거래액': 'nrev',
    '지표_총결제거래액': 'trev',
    '지표_순결제고객수(첫구매)': 'fp',
    '지표_순결제거래액(첫구매)': 'fpr',
    '지표_총결제고객수(첫구매)': 'fpt',
    '지표_총결제거래액(첫구매)': 'fprt',
    '지표_당년신규순결제고객수': 'nb',
    '지표_당년신규순결제거래액': 'nbr',
    '지표_순결제고객수(윈백)': 'wb',
    '지표_순결제거래액(윈백)': 'wbr',
    '지표_총결제고객수(윈백)': 'wbt',
    '지표_총결제거래액(윈백)': 'wbrt',
    '지표_영상조회수': 'vv',
    '지표_순결제거래액(RD)': 'rd',
    '지표_순결제거래액(PP)': 'pp',
    '지표_순결제거래액(BK)': 'bk',
    '지표_순결제거래액(SV)': 'sv',
    '지표_순결제거래액(GD)': 'gd',
    '지표_순결제거래액(PT)': 'pt',
    '지표_순결제거래액(SP)': 'sp',
}
METS = list(ROW_METRICS.values())
OPTIONAL = {'vv', 'rd', 'pp', 'bk', 'sv', 'gd', 'pt', 'sp'}   # 일부 원천에만 있는 지표 — 없어도 경고하지 않는다
# 원천에 컬럼이 없을 때 기존 대시보드와 같은 기본값 (구분)
DIM_DEFAULT = {'af': '', 'afn': '', 'at': 'DA', 'tg': '대상', 'src': '기타', 'ch': '기타', 'dev': '기타', 'bpu': '기타', 'cat': '기타',
               'camp': '기타', 'md': '기타', 'sub': '', 'pr': '', 'pno': '', 'bp': ''}
WANT_SRC = [ROW_DATE] + [c for cands in [*ROW_DIMS.values(), *AF_DIMS.values()] for c in cands] + list(ROW_METRICS)
CHUNK = 20_000
ROW_EXT = ('.xlsb', '.csv', '.xlsx', '.xlsm')


def log(*a):
    print(*a, flush=True)


# ── 정제 ───────────────────────────────────────────────────────────────
def to_num(s: pd.Series) -> pd.Series:
    """' - ' · 천단위 콤마가 섞인 숫자 컬럼 정제 (없는 값 = 0, 기존 대시보드와 같다)"""
    if s.dtype.kind in 'if':
        return s.fillna(0).astype(float)
    s = s.astype(str).str.replace(',', '', regex=False).str.strip()
    return pd.to_numeric(s, errors='coerce').fillna(0).astype(float)


def clean_dim(s: pd.Series, default: str) -> pd.Series:
    if s.isna().all():
        return pd.Series(default, index=s.index, dtype=object)
    s = s.astype(object).where(s.notna(), '').astype(str).str.strip()
    s = s.str.replace(r'^(-?\d+)\.0$', r'\1', regex=True)        # xlsb 숫자 셀 114293.0 → 114293
    return s.replace({'nan': '', 'None': ''})


def parse_dates(s: pd.Series) -> pd.Series:
    """기간_일자 → 날짜. 문자열 · 엑셀 일련번호 · YYYYMMDD 를 모두 시도하고 '그럴듯한 연도' 비율이 가장 높은 결과를 쓴다
    (dashboard.py _parse_date_col 과 같은 방식)"""
    if pd.api.types.is_datetime64_any_dtype(s):
        return s.dt.normalize()

    def plausible(d):
        y = d.dt.year
        return float(((y >= 2015) & (y <= 2100)).mean()) if len(d) else 0.0

    txt = s.astype(str).str.strip()
    cands = [pd.to_datetime(txt.str.slice(0, 10).str.replace(r'[./]', '-', regex=True), format='%Y-%m-%d', errors='coerce')]
    num = pd.to_numeric(s, errors='coerce')
    if num.notna().mean() > 0.5:
        cands.append(pd.to_datetime(num.where(num < 1e6), unit='D', origin='1899-12-30', errors='coerce'))
    digits = txt.str.replace(r'\.0$', '', regex=True).str.replace(r'[^0-9]', '', regex=True)
    if (digits.str.len() == 8).mean() > 0.5:
        cands.append(pd.to_datetime(digits, format='%Y%m%d', errors='coerce'))
    cands.append(pd.to_datetime(txt, errors='coerce', format='mixed'))
    return max(cands, key=plausible).dt.normalize()


# ── 읽기 ───────────────────────────────────────────────────────────────
def sniff_csv(path: Path):
    """csv 인코딩(UTF-8 · CP949 · UTF-16) · 구분자(쉼표 · 탭) 판별 — 파일을 한꺼번에 메모리에 올리지 않는다"""
    import codecs
    import csv

    with open(path, 'rb') as f:
        bom = f.read(2)
    errors = 'strict'
    if bom in (b'\xff\xfe', b'\xfe\xff'):
        enc = 'utf-16'
    else:
        enc = None
        for cand in ('utf-8-sig', 'cp949'):
            dec = codecs.getincrementaldecoder(cand)('strict')
            try:
                with open(path, 'rb') as f:
                    while block := f.read(1 << 22):
                        dec.decode(block)
                dec.decode(b'', final=True)
                enc = cand
                break
            except UnicodeDecodeError:
                continue
        if enc is None:
            enc, errors = 'cp949', 'replace'
            log(f'  ! {path.name}: 인코딩이 일부 깨져 있어 cp949 로 읽고 깨진 글자를 대체했습니다')
    with open(path, 'r', encoding=enc, errors='replace', newline='') as f:
        first = f.readline()
    sep = '\t' if first.count('\t') > first.count(',') else ','
    header = [c.strip() for c in next(csv.reader([first], delimiter=sep))]
    return enc, sep, header, errors


def _check_header(header: list[str], name: str):
    if ROW_DATE not in header:
        raise ValueError(f'{name}: 첫 행에 "{ROW_DATE}" 컬럼이 없습니다 (DA 로데이터 형식인지 확인)')
    if '지표_광고비' not in header:
        raise ValueError(f'{name}: 첫 행에 "지표_광고비" 컬럼이 없습니다 (DA 로데이터 형식인지 확인)')


def _norm(df: pd.DataFrame, name: str) -> pd.DataFrame:
    df.columns = [str(c).strip() for c in df.columns]
    _check_header(list(df.columns), name)
    for c in WANT_SRC:
        if c not in df.columns:
            df[c] = None
    return df[WANT_SRC]


def iter_xlsb(path: Path):
    """pyxlsb 로 시트를 직접 순회 — 필요한 컬럼만, CHUNK 행씩"""
    from pyxlsb import open_workbook

    rows, idx = [], None
    with open_workbook(str(path)) as wb:
        sheet = ROW_SHEET if ROW_SHEET in wb.sheets else wb.sheets[0]
        with wb.get_sheet(sheet) as sh:
            for n, r in enumerate(sh.rows()):
                vals = [c.v for c in r]
                if idx is None:
                    header = [str(v).strip() if v is not None else '' for v in vals]
                    _check_header(header, path.name)
                    idx = [header.index(c) if c in header else None for c in WANT_SRC]
                    continue
                rows.append(tuple(vals[i] if i is not None and i < len(vals) else None for i in idx))
                if len(rows) >= CHUNK:
                    log(f'  … {n:,}행')
                    yield pd.DataFrame(rows, columns=WANT_SRC)
                    rows = []
    if rows or idx is None:
        yield pd.DataFrame(rows, columns=WANT_SRC)


def iter_raw(path: Path):
    """원천 파일 → WANT_SRC 컬럼 DataFrame 덩어리들"""
    path = Path(path)
    ext = path.suffix.lower()
    if ext == '.xlsb':
        yield from iter_xlsb(path)
    elif ext == '.pkl':                                   # 테스트용
        yield _norm(pd.read_pickle(path), path.name)
    elif ext in ('.xlsx', '.xlsm'):
        xl = pd.ExcelFile(path)
        yield _norm(xl.parse(ROW_SHEET if ROW_SHEET in xl.sheet_names else xl.sheet_names[0]), path.name)
    else:
        enc, sep, header, errors = sniff_csv(path)
        _check_header(header, path.name)
        use = [c for c in header if c in WANT_SRC]
        reader = pd.read_csv(path, encoding=enc, sep=sep, usecols=use, dtype=str, keep_default_na=False,
                             na_values=[''], chunksize=CHUNK, encoding_errors=errors)
        for k, chunk in enumerate(reader):
            if k:
                log(f'  … {k * CHUNK:,}행')
            yield _norm(chunk, path.name)


def prep(raw: pd.DataFrame) -> tuple[pd.DataFrame, set]:
    """원천 덩어리 → (date, 구분 키들, 지표 키들), 원천에 있던 지표 컬럼 키"""
    df = pd.DataFrame({'date': parse_dates(raw[ROW_DATE])})
    for k, cands in [*ROW_DIMS.items(), *AF_DIMS.items()]:
        col = next((c for c in cands if raw[c].notna().any()), cands[0])
        df[k] = clean_dim(raw[col], DIM_DEFAULT[k])
    seen = set()
    for src, k in ROW_METRICS.items():
        if raw[src].notna().any():
            seen.add(k)
        df[k] = to_num(raw[src])
    bad = int(df['date'].isna().sum())
    if bad:
        log(f'  ! 날짜를 읽지 못한 행 {bad:,}개 제외')
    return df[df['date'].notna()], seen


def load_prepped(path: Path, use_cache: bool = True, with_af: bool = False):
    """원천 → (일자 × 구분) 합산 DataFrame, 원천에 없던 지표 키[, 최근 AF_DAYS 일의 (일자 × 구분 × AF코드) 합산].
    덩어리마다 바로 합산해 메모리를 아낀다. xlsb · csv · xlsx 는 data/cache/ 에 결과를 캐시"""
    path = Path(path)
    cache = CACHE_DIR / f'{path.name}.{path.stat().st_size}.v2.pkl'
    cacheable = use_cache and path.suffix.lower() in ROW_EXT
    if cacheable and cache.exists() and cache.stat().st_mtime >= path.stat().st_mtime:
        log(f'[원천] 캐시 사용: {path.name} (이미 읽은 파일)')
        c = pd.read_pickle(cache)
        return (c['df'], c['missing'], c.get('af')) if with_af else (c['df'], c['missing'])
    log(f'[원천] {path.name} 읽는 중 (큰 파일은 몇 분)…')
    seen_all, parts, parts_af = set(), [], []
    for raw in iter_raw(path):
        p, seen = prep(raw)
        del raw
        seen_all |= seen
        for k in AF_ALL:
            p[k] = p[k].astype('category')
        parts.append(p.groupby(['date', *DIM_KEYS], sort=False, observed=True)[METS].sum().reset_index())
        parts_af.append(p.groupby(['date', *AF_ALL], sort=False, observed=True)[METS].sum().reset_index())
        del p
    df = concat_cat(parts)
    if len(parts) > 1:
        df = df.groupby(['date', *DIM_KEYS], sort=False, observed=True)[METS].sum().reset_index()
    af = concat_cat(parts_af)
    del parts_af
    if len(af):
        af = af[af['date'] > af['date'].max() - pd.Timedelta(days=AF_DAYS)]
        af = af.groupby(['date', *AF_ALL], sort=False, observed=True)[METS].sum().reset_index()
    # 순결제거래액 컬럼이 없으면 첫구매 + 윈백 (dashboard.py 와 같다)
    if 'nrev' not in seen_all and {'fpr', 'wbr'} & seen_all:
        df['nrev'] = df['fpr'] + df['wbr']
        af['nrev'] = af['fpr'] + af['wbr']
        seen_all.add('nrev')
        log('  · 순결제거래액 컬럼이 없어 순결제거래액(첫구매) + (윈백)으로 채웠습니다')
    missing = [k for k in METS if k not in seen_all]
    if cacheable:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        pd.to_pickle({'df': df, 'missing': missing, 'af': af}, cache)
    return (df, missing, af) if with_af else (df, missing)


def concat_cat(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """범주형 구분을 유지한 채 이어 붙인다"""
    frames = [f for f in frames if len(f)] or frames[:1]
    if len(frames) == 1:
        return frames[0].reset_index(drop=True)
    for c in [c for c in frames[0].columns if isinstance(frames[0][c].dtype, pd.CategoricalDtype)]:
        cats = pd.api.types.union_categoricals([f[c] for f in frames]).categories
        for f in frames:
            f[c] = f[c].cat.set_categories(cats)
    return pd.concat(frames, ignore_index=True)


def unpack_upload(name: str, src, out_dir: Path) -> list[Path]:
    """올린 파일 → 디스크의 원천 파일들. zip 은 안의 xlsb · csv · xlsx 를, gz 는 풀어서. 조금씩 복사해 메모리를 아낀다"""
    import shutil
    import zipfile

    out_dir = Path(out_dir)
    lower = name.lower()
    if lower.endswith('.zip'):
        paths = []
        with zipfile.ZipFile(src) as z:
            for i, info in enumerate(m for m in z.infolist() if not m.is_dir()):
                fname = info.filename
                if not info.flag_bits & 0x800:          # 윈도우 압축(CP949 파일명) 깨짐 복구
                    try:
                        fname = fname.encode('cp437').decode('cp949')
                    except (UnicodeEncodeError, UnicodeDecodeError):
                        pass
                base = Path(fname).name
                if base.startswith('.') or Path(base).suffix.lower() not in ROW_EXT:
                    continue
                p = out_dir / f'{i:03d}_{base}'
                with z.open(info) as r, open(p, 'wb') as w:
                    shutil.copyfileobj(r, w, 1 << 20)
                paths.append(p)
        if not paths:
            raise ValueError(f'{name}: 압축 안에 xlsb · csv · xlsx 파일이 없습니다')
        return sorted(paths)
    if lower.endswith('.gz'):
        p = out_dir / name[:-3]
        with gzip.open(src) as r, open(p, 'wb') as w:
            shutil.copyfileobj(r, w, 1 << 20)
        return [p]
    p = out_dir / name
    with open(p, 'wb') as w:
        if hasattr(src, 'getbuffer'):
            w.write(src.getbuffer())
        else:
            shutil.copyfileobj(src, w, 1 << 20)
    return [p]


def latest_wins(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """같은 날짜가 여러 프레임에 있으면 뒤 프레임 것만 남긴다"""
    seen: set = set()
    keep = []
    for f in reversed(frames):
        part = f[~f['date'].isin(seen)]
        if len(part):
            keep.append(part)
        seen |= set(f['date'].unique())
    return concat_cat(keep[::-1]) if keep else frames[0].iloc[0:0]


# ── 인코딩 · 디코딩 ────────────────────────────────────────────────────
def encode(g: pd.DataFrame, dates, dims=None) -> dict:
    """열 단위 + 값 목록 인덱스로 압축: dims[k] = 값 목록(광고비 큰 순), f[k] = 인덱스 배열, f[지표] = 값 배열.
    전부 0인 지표는 빼고 zero 목록에 적는다"""
    dates = sorted(pd.Timestamp(d) for d in dates)
    dcodes = pd.Categorical(g['date'], categories=dates).codes
    out = {'dates': [d.strftime('%Y-%m-%d') for d in dates], 'dims': {}, 'f': {'d': dcodes.astype(np.int32)}, 'zero': []}
    weight = np.abs(g['cost'].to_numpy(dtype=float)) + 1e-9
    for k in dims or DIM_KEYS:
        c = g[k] if isinstance(g[k].dtype, pd.CategoricalDtype) else g[k].astype('category')
        codes = c.cat.codes.to_numpy()
        cats = [str(v) for v in c.cat.categories]
        present = np.bincount(codes, minlength=len(cats)) > 0
        sums = np.bincount(codes, weights=weight, minlength=len(cats))
        order = [i for i in np.argsort(-sums, kind='stable') if present[i]]
        newix = np.full(len(cats), -1, dtype=np.int32)
        newix[order] = np.arange(len(order), dtype=np.int32)
        out['dims'][k] = [cats[i] for i in order]
        out['f'][k] = newix[codes]
    for m in METS:
        v = g[m].to_numpy(dtype=float)
        if not np.any(np.abs(v) > 1e-12):
            out['zero'].append(m)
            continue
        out['f'][m] = np.round(v, 4)
    out['n'] = int(len(g))
    return out


def _arr_json(a: np.ndarray) -> str:
    a = np.asarray(a)
    if a.dtype.kind in 'iu' or (a.dtype.kind == 'f' and np.array_equal(a, np.round(a))):
        return '[' + ','.join(map(str, a.astype(np.int64).tolist())) + ']'
    return '[' + ','.join(str(int(x)) if float(x).is_integer() else repr(float(x)) for x in a.tolist()) + ']'


def to_json(payload: dict) -> str:
    def enc(o):
        if isinstance(o, np.ndarray):
            return _arr_json(o)
        if isinstance(o, dict):
            return '{' + ','.join(json.dumps(str(k), ensure_ascii=False) + ':' + enc(v) for k, v in o.items()) + '}'
        if isinstance(o, (list, tuple)):
            return '[' + ','.join(enc(v) for v in o) + ']'
        if isinstance(o, np.integer):
            return str(int(o))
        if isinstance(o, np.floating):
            return repr(float(o))
        return json.dumps(o, ensure_ascii=False)
    return enc(payload)


def decode(sec: dict, dims=None) -> tuple[pd.DataFrame, list]:
    """백업 섹션 → (집계 DataFrame, 날짜 목록)"""
    dates = [pd.Timestamp(d) for d in sec['dates']]
    n = len(sec['f']['d'])
    df = pd.DataFrame({'date': pd.Series(dates, dtype='datetime64[ns]').iloc[np.asarray(sec['f']['d'], dtype=int)].to_numpy()})
    for k in dims or DIM_KEYS:
        vals = sec['dims'].get(k)
        if vals is None:
            df[k] = DIM_DEFAULT[k]
        else:
            df[k] = np.array(vals, dtype=object)[np.asarray(sec['f'][k], dtype=int)] if n else []
    for m in METS:
        df[m] = np.asarray(sec['f'][m], dtype=float) if m in sec['f'] else 0.0
    return df, dates


def read_backup(src) -> dict:
    raw = src.read() if hasattr(src, 'read') else Path(src).read_bytes()
    if raw[:2] == b'\x1f\x8b':
        raw = gzip.decompress(raw)
    p = json.loads(raw.decode('utf-8'))
    if p.get('format') != FORMAT:
        raise ValueError('DA 대시보드 백업이 아닙니다')
    return p


# ── 빌드 ───────────────────────────────────────────────────────────────
def _read_group(paths: list, use_cache: bool, until: str | None = None, af_out: list | None = None):
    """파일 묶음 → (같은 날짜는 뒤 파일 우선으로 합친 DataFrame, 파일명들, 없는 지표). af_out 을 주면 AF 집계도 모은다"""
    frames, files, missing = [], [], set()
    for p in paths:
        df, ms, af = load_prepped(p, use_cache=use_cache, with_af=True)
        if af_out is not None and af is not None and len(af):
            af_out.append(af)
        if until is not None:
            n0 = df['date'].nunique()
            df = df[df['date'] <= pd.Timestamp(until)]
            cut = n0 - df['date'].nunique()
            if cut:
                log(f'  · {Path(p).name}: {until} 이후 {cut}일은 24년 파일에서 쓰지 않음(매일 파일이 맡음)')
        frames.append(df)
        files.append(Path(p).name)
        core = [m for m in ms if m not in OPTIONAL]
        if core:
            log(f'  ! {Path(p).name}: 원천에 없는 지표 → 0 으로 둠: {core}')
        missing |= set(core)
    if not frames:
        return None, files, missing
    return latest_wins(frames), files, missing


def build(row_paths=(), y24_paths=(), base: dict | None = None, use_cache: bool = True) -> dict:
    """원천 파일들(+기존 백업) → 백업 payload.
    - y24_paths: 24년 파일 — LOCK_UNTIL 까지만 쓰고 그 구간을 '고정'으로 표시
    - row_paths: 매일 파일 — 고정 구간이 있으면 그 구간의 날짜는 버린다
    - base: 기존 백업 — 새 파일에 있는 날짜는 교체, 나머지 날짜는 유지"""
    row_paths, y24_paths = list(row_paths or []), list(y24_paths or [])
    base_row = (base or {}).get('row')
    prev = (base or {}).get('source', {})
    lock = prev.get('lock') if base_row else None
    y24, y24_files, miss24 = _read_group(y24_paths, use_cache, until=LOCK_UNTIL)
    if y24 is not None and len(y24):
        lock = LOCK_UNTIL
    af_new = []
    new, files, miss = _read_group(row_paths, use_cache, af_out=af_new)
    if new is not None and lock:
        n0 = new['date'].nunique()
        new = new[new['date'] > pd.Timestamp(lock)]
        if n0 - new['date'].nunique():
            log(f'  · 매일 파일의 {lock} 이전 {n0 - new["date"].nunique()}일은 24년 파일 값을 유지')
    parts, dates = [], set()
    replace = set()
    for f in (y24, new):
        if f is not None and len(f):
            replace |= set(f['date'].unique())
    if y24 is not None and len(y24):          # 24년 파일을 새로 넣으면 고정 구간 전체를 그 파일로 바꾼다
        replace |= {d for d in (decode(base_row)[1] if base_row else []) if d <= pd.Timestamp(LOCK_UNTIL)}
    if base_row:
        old, old_dates = decode(base_row)
        old = old[~old['date'].isin(replace)]
        parts.append(old)
        dates |= {d for d in old_dates if d not in replace}
        log(f'[백업] 기존 {len(old_dates)}일 중 {len([d for d in old_dates if d not in replace])}일 유지')
    for f in (y24, new):
        if f is not None and len(f):
            parts.append(f)
            dates |= set(f['date'].unique())
    if not parts or not dates:
        raise ValueError('읽은 데이터가 없습니다')
    for p in parts:
        for k in DIM_KEYS:
            p[k] = p[k].astype(str)
    g = pd.concat(parts, ignore_index=True)
    g = g.groupby(['date', *DIM_KEYS], sort=False)[METS].sum().reset_index()
    g = g[(g[METS].abs() > 1e-12).any(axis=1)]
    dates = sorted(dates)
    sec = encode(g, dates)
    src = {
        'files': (prev.get('files', []) if base_row else []) + files,
        'files24': y24_files or (prev.get('files24', []) if base_row else []),
        'lock': lock,
        'missing': sorted((set(prev.get('missing', [])) if base_row else set()) | miss | miss24),
        'from': sec['dates'][0], 'to': sec['dates'][-1], 'days': len(dates), 'rows': int(len(g)),
    }
    log(f'[백업] 집계 {len(g):,}행 · {len(dates)}일 ({src["from"]} ~ {src["to"]})' + (f' · 고정 ~{lock}' if lock else ''))
    af_sec = build_af(af_new, (base or {}).get('af'), dates[-1])
    if af_sec:
        log(f'[백업] AF코드 {af_sec["n"]:,}행 · 최근 {len(af_sec["dates"])}일 ({af_sec["dates"][0]} ~ {af_sec["dates"][-1]})')
    return {'format': FORMAT, 'version': VERSION, 'created': dt.datetime.now().isoformat(timespec='seconds'),
            'lastDate': src['to'], 'source': src, 'row': sec, 'af': af_sec,
            'targets': (base or {}).get('targets'), 'memos': (base or {}).get('memos') or {}}


def build_af(new_frames: list, base_af: dict | None, last_date) -> dict | None:
    """AF코드 섹션 — 새 파일(같은 날짜는 뒤 파일 우선) + 기존 백업의 나머지 날짜, 전체 마지막 날 기준 최근 AF_DAYS 일만"""
    parts = []
    new = latest_wins(new_frames) if new_frames else None
    new_dates = set(new['date'].unique()) if new is not None else set()
    if base_af:
        old, _ = decode(base_af, AF_ALL)
        parts.append(old[~old['date'].isin(new_dates)])
    if new is not None and len(new):
        parts.append(new)
    if not parts:
        return None
    for p in parts:
        for k in AF_ALL:
            p[k] = p[k].astype(str)
    g = pd.concat(parts, ignore_index=True)
    g = g[g['date'] > pd.Timestamp(last_date) - pd.Timedelta(days=AF_DAYS)]
    if not len(g):
        return None
    g = g.groupby(['date', *AF_ALL], sort=False)[METS].sum().reset_index()
    g = g[(g[METS].abs() > 1e-12).any(axis=1)]
    return encode(g, sorted(g['date'].unique()), AF_ALL)


def targets_payload(targets: dict) -> dict:
    """목표만 담은 백업 — 대시보드가 저장된 데이터에 목표만 바꿔 넣는다"""
    return {'format': FORMAT, 'version': VERSION, 'created': dt.datetime.now().isoformat(timespec='seconds'),
            'source': {}, 'targets': targets}


def backup_bytes(payload: dict) -> bytes:
    raw = to_json(payload).encode('utf-8')
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode='wb', compresslevel=6, mtime=0) as f:
        f.write(raw)
    return buf.getvalue()


def backup_name(payload: dict) -> str:
    if not payload.get('row'):
        return f'DA대시보드_목표_{dt.date.today().strftime("%Y%m%d")}.json.gz'
    return f'DA대시보드_백업_{(payload.get("lastDate") or dt.date.today().isoformat()).replace("-", "")}.json.gz'


def write_backup(payload: dict) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / backup_name(payload)
    data = backup_bytes(payload)
    out.write_bytes(data)
    log(f'[저장] {out}  ({len(data) / 1e6:.1f}MB)')
    return out


def by_mtime(paths):
    return sorted(paths, key=lambda p: Path(p).stat().st_mtime)


def _raw_files(d: Path):
    return [p for p in d.glob('*') if p.is_file() and p.suffix.lower() in ROW_EXT and not p.name.startswith(('~$', '.'))]


def main(argv=None):
    ap = argparse.ArgumentParser(description='DA 대시보드 백업 만들기')
    ap.add_argument('--row', type=Path, nargs='*', help='25·26년 로데이터(매일) 파일들 (기본: raw 폴더 전부, 수정시각 순)')
    ap.add_argument('--y24', type=Path, nargs='*', help='24년 로데이터 파일 (기본: raw/2024 폴더) — 2024-12-31 까지만 쓰고 고정')
    ap.add_argument('--base', type=Path, help='이어 붙일 기존 백업(.json.gz)')
    ap.add_argument('--targets', type=Path, help='목표 파일(보고서 엑셀 .xlsx) — 실적 요약표 목표 · 목표비')
    a = ap.parse_args(argv)
    tg = None
    if a.targets:
        import targets as tgm
        tg = tgm.parse_targets(a.targets.read_bytes(), a.targets.name)
        log(f'[목표] {a.targets.name}: 월 {tgm.count(tg)[0]}건 · 주 {tgm.count(tg)[1]}건')

    use_folder = a.row is None and a.y24 is None and not a.targets
    rows = by_mtime(_raw_files(RAW_DIR)) if use_folder else list(a.row or [])
    y24 = by_mtime(_raw_files(RAW24_DIR)) if use_folder and RAW24_DIR.exists() else list(a.y24 or [])
    base = read_backup(a.base) if a.base else None
    if tg and not rows and not y24 and not base:
        write_backup(targets_payload(tg))
        return
    if not rows and not y24 and not base:
        sys.exit(f'원천 파일이 없습니다. {RAW_DIR} 에 로데이터(xlsb · csv · xlsx)를, 24년 파일은 {RAW24_DIR} 에 넣거나 --row / --y24 로 지정하세요.')
    log(f'매일 파일: {[Path(p).name for p in rows] or "(없음)"} / 24년 파일: {[Path(p).name for p in y24] or "(없음)"}'
        + (f' / 기존 백업: {a.base.name}' if base else ''))
    try:
        payload = build(rows, y24, base=base)
    except ValueError as e:
        sys.exit(str(e))
    if tg:
        payload['targets'] = tg
    write_backup(payload)


if __name__ == '__main__':
    main()
