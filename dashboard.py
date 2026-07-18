import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import io
import re
import calendar

st.set_page_config(
    page_title="DA 광고 실적 대시보드",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""<style>
/* 전체 배경 */
.main .block-container { padding-top: 1.5rem; max-width: 1400px; }
/* 헤더 */
h1 { font-size: 1.6rem !important; font-weight: 700 !important; color: #0F172A !important; }
h2 { font-size: 1.2rem !important; font-weight: 600 !important; color: #1E293B !important; }
h3 { font-size: 1rem !important; font-weight: 600 !important; }
/* 기본 st.metric 숨김 (커스텀 카드로 대체) */
[data-testid="metric-container"] > div:first-child { font-size: 12px !important; color: #64748B !important; }
[data-testid="metric-container"] > div:nth-child(2) > div { font-size: 1.5rem !important; font-weight: 700 !important; color: #0F172A !important; }
/* 탭 스타일 */
.stTabs [data-baseweb="tab"] { font-size: 13px; font-weight: 500; }
/* 구분선 */
hr { margin: 0.8rem 0 !important; border-color: #E2E8F0 !important; }
/* 데이터프레임 */
[data-testid="stDataFrameResizable"] { border-radius: 8px !important; }
</style>""", unsafe_allow_html=True)

# ───────────────────────────────────────────────
# 상수
# ───────────────────────────────────────────────
# 비용출처 버킷 정의 (사용자 지정). 값이 목록에 있으면 해당 탭에 합산된다.
# 'e영업'/'E영업' 대소문자 변형까지 함께 포함해 매칭 누락을 방지한다.
COST_BUCKETS = {
    "TOTAL": [
        "거래액확대", "신규고객확대", "인지도제고", "E영업/광고주직접정산",
        "신규고객확대-실적구분", "브랜드비용", "거래액확대-실적구분", "서비스비용-정산제외",
        "브랜드/정산제외", "인지도제고/브랜딩", "서비스비용-e영업", "서비스비용-E영업",
        "서비스비용-거래액확대", "서비스비용-인지도제고", "E영업/정산제외",
    ],
    "TOTAL(서비스비용미반영)": [
        "거래액확대", "신규고객확대", "인지도제고", "E영업/광고주직접정산",
        "신규고객확대-실적구분", "브랜드비용", "거래액확대-실적구분",
        "브랜드/정산제외", "인지도제고/브랜딩", "E영업/정산제외",
    ],
    "거래액확대": [
        "거래액확대", "거래액확대-실적구분", "E영업/광고주직접정산", "E영업/정산제외",
        "서비스비용-거래액확대", "서비스비용-e영업", "서비스비용-E영업",
    ],
    "신규고객확대": [
        "신규고객확대", "신규고객확대-실적구분",
    ],
    "인지도제고": [
        "인지도제고", "서비스비용-인지도제고", "인지도제고/브랜딩",
    ],
}
TOTAL_SOURCES = COST_BUCKETS["TOTAL"]  # 사이드바 'TOTAL' 모드용

MEDIA_COLORS = {
    "카카오": "#FFCD00", "네이버": "#03C75A", "버즈빌": "#FF6B35",
    "토스": "#0064FF", "페이스북": "#1877F2", "FB/IG": "#E1306C",
    "인스타그램": "#C13584", "구글": "#4285F4", "유튜브": "#FF0000",
    "당근마켓": "#FF7640", "캐시슬라이드": "#FFB800", "오케이캐시백": "#E60026",
}

PURPOSE_COLORS = {
    "거래액확대": "#2563EB", "신규고객확대": "#16A34A",
    "인지도제고": "#9333EA", "E영업/광고주직접정산": "#EA580C",
}

YEAR_COLORS = ["#2563EB", "#F59E0B", "#10B981", "#EF4444"]

MONTH_LABELS = {i: f"{i}월" for i in range(1, 13)}
WEEKDAY_LABELS = ["월", "화", "수", "목", "금", "토", "일"]


# ───────────────────────────────────────────────
# 데이터 로드
# ───────────────────────────────────────────────
# 원본('금주누적' 스타일, 접두어 없는) 컬럼 → 대시보드 스키마 매핑
WEEKLY_COL_MAP = {
    "노출수": "지표_노출수", "클릭수": "지표_클릭수", "비용": "지표_광고비",
    "UV": "지표_UV(전체)", "결제고객수": "지표_순결제고객수", "결제고객수(총)": "지표_총결제고객수",
    "순결제매출": "지표_순결제거래액", "총결제매출": "지표_총결제거래액",
    "가입수": "지표_가입회원", "첫구매수": "지표_순결제고객수(첫구매)", "첫구매": "지표_순결제거래액(첫구매)",
    "신규고객수": "지표_당년신규순결제고객수", "신규거래액": "지표_당년신규순결제거래액",
    "윈백고객수": "지표_순결제고객수(윈백)", "윈백거래액": "지표_순결제거래액(윈백)",
    "비용출처": "구분_비용출처", "캠페인": "구분_캠페인", "하위캠페인": "구분_하위캠페인",
    "AF코드": "구분_AF코드", "AF코드명": "구분_AF코드이름",
}


def _map_weekly_format(df: pd.DataFrame) -> pd.DataFrame:
    """접두어 없는 원본 포맷을 대시보드 스키마로 변환."""
    # 문자열 컬럼 앞뒤 공백 정리 (' 총합계 ', ' - ' 등)
    for c in df.select_dtypes(include="object").columns:
        df[c] = df[c].astype(str).str.strip()

    # 매체 = 매체명 + 상품명 (예: '카카오 비즈보드'), 상품명은 별도 보존
    if "매체명" in df.columns:
        media = df["매체명"].fillna("").astype(str).str.strip()
        if "상품명" in df.columns:
            prod = df["상품명"].fillna("").astype(str).str.strip()
            df["구분_상품"] = prod
            # 상품명이 비었거나 매체명과 같으면 매체명만 사용 (예: '구글 구글' 방지)
            df["구분_매체명"] = [
                m if (not p or p == m) else f"{m} {p}"
                for m, p in zip(media, prod)
            ]
        else:
            df["구분_매체명"] = media

    df = df.rename(columns=WEEKLY_COL_MAP)

    # '총합계' 합계행 및 빈 비용출처 제외
    if "구분_비용출처" in df.columns:
        df = df[~df["구분_비용출처"].astype(str).str.strip().isin(["총합계", "", "nan"])]
    return df


@st.cache_data(show_spinner=False)
def load_data(file_bytes: bytes, filename: str) -> pd.DataFrame:
    ext = filename.rsplit(".", 1)[-1].lower()
    if ext == "csv":
        enc_list = ["utf-8-sig", "utf-8", "cp949", "euc-kr"]
        df = None
        for enc in enc_list:
            try:
                df = pd.read_csv(io.BytesIO(file_bytes), encoding=enc)
                break
            except Exception:
                continue
        if df is None:
            raise ValueError("파일 인코딩을 인식할 수 없습니다.")
    elif ext == "xlsx":
        df = pd.read_excel(io.BytesIO(file_bytes), engine="openpyxl")
    elif ext == "xlsb":
        df = pd.read_excel(io.BytesIO(file_bytes), engine="pyxlsb")
    else:
        raise ValueError(f"지원하지 않는 파일 형식입니다: {ext}")

    df.columns = df.columns.str.strip()

    # 접두어 없는 원본('금주누적') 포맷 자동 감지 → 매핑
    if "지표_광고비" not in df.columns and ("비용" in df.columns or "순결제매출" in df.columns):
        df = _map_weekly_format(df)

    df["기간_일자"] = pd.to_datetime(df["기간_일자"], errors="coerce")
    df = df.dropna(subset=["기간_일자"])

    num_cols = [
        "지표_노출수", "지표_입찰가", "지표_클릭수", "지표_광고비",
        "지표_UV(전체)", "지표_UV(회원)", "지표_PV(회원)", "지표_가입회원",
        "지표_총결제고객수(첫구매)", "지표_순결제고객수", "지표_총결제거래액(첫구매)",
        "지표_총결제거래액", "지표_순결제거래액", "지표_당년신규순결제고객수", "지표_당년신규순결제거래액",
        "지표_총결제고객수", "지표_순결제고객수(첫구매)", "지표_순결제거래액(첫구매)",
        "지표_순결제고객수(윈백)", "지표_순결제거래액(윈백)",
        "지표_총결제고객수(윈백)", "지표_총결제거래액(윈백)", "지표_영상조회수",
    ]
    for c in num_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

    df["연도"] = df["기간_일자"].dt.year
    df["월"] = df["기간_일자"].dt.month
    df["연월"] = df["기간_일자"].dt.to_period("M").astype(str)
    df["요일"] = df["기간_일자"].dt.dayofweek   # 0=월 ~ 6=일
    df["주차번호"] = df["기간_일자"].dt.isocalendar().week.astype(int)  # ISO 주차 1~53

    # 선택 컬럼 기본값 채우기
    defaults = {
        "기간_주": None,
        "대상여부": "대상",
        "구분_광고유형": "DA",
        "구분_비용출처": "기타",
        "구분_채널": "기타",
        "구분_디바이스": "기타",
        "구분_부서명": "기타",
        "카테고리": "기타",
        "구분_캠페인": "기타",
        "구분_매체명": "기타",
        "구분_AF코드": "",
        "구분_AF코드이름": "",
        "구분_하위캠페인": "",
    }
    for col, val in defaults.items():
        if col not in df.columns:
            df[col] = val

    # 상품명 컬럼 정규화: 로데이터가 '구분_상품명'이면 '구분_상품'으로도 사용(필터/소재 공용)
    if "구분_상품명" in df.columns:
        prod = df["구분_상품명"].astype(str)
        if "구분_상품" not in df.columns or df["구분_상품"].astype(str).str.strip().eq("").all():
            df["구분_상품"] = prod
    if "구분_상품" not in df.columns:
        df["구분_상품"] = ""

    if df["기간_주"].isna().all():
        df["기간_주"] = (
            df["기간_일자"].dt.strftime("%Y")
            + "W"
            + df["주차번호"].astype(str).str.zfill(2)
        )

    # 순결제거래액 = 순결제거래액(첫구매) + 순결제거래액(윈백) (직접 컬럼이 없으면 파생)
    if "지표_순결제거래액" not in df.columns:
        df["지표_순결제거래액"] = (
            df.get("지표_순결제거래액(첫구매)", 0) + df.get("지표_순결제거래액(윈백)", 0)
        )

    # 집계 대상 지표 중 원본에 없는 컬럼은 0으로 채워 KeyError 방지
    for c in AGG_COLS:
        if c not in df.columns:
            df[c] = 0

    return df


def _tnum(v):
    """엑셀 셀 → 숫자 (실패 시 0)."""
    try:
        f = float(v)
        return 0.0 if pd.isna(f) else f
    except Exception:
        return 0.0


@st.cache_data(show_spinner=False)
def load_targets_from_report(file_bytes: bytes) -> dict:
    """목표 엑셀 파싱.
    신규 양식: 'SNS/버즈빌/포탈' 3매체 목표를 합산한 값이 DA 전체 목표.
      - 월별: 시트 '월TOTAL요약(누계)'  (연도,월, {매체}_광고비/거래액/ROAS)
      - 주차별: 시트 '통합_전체'         (연도,월,기간,광고유형,UV,광고비,거래액,ROAS)
    Returns: {
      "monthly": {tab_name: {(year, month): {spend, rev, roas}}},
      "weekly":  {(year, iso_week): {spend, rev, roas}},
      "monthly_media": {media: {(year, month): {...}}},   # 매체별(SNS/버즈빌/포탈)
    }
    DA 전체 목표는 요약의 'TOTAL' 및 'TOTAL(서비스비용미반영)' 탭에 매핑한다.
    """
    result = {"monthly": {}, "weekly": {}, "monthly_media": {}, "weekly_rows": {}}
    try:
        xls = pd.ExcelFile(io.BytesIO(file_bytes), engine="openpyxl")
        sheets = xls.sheet_names

        # ── 신규 양식
        if "월TOTAL요약(누계)" in sheets or "통합_전체" in sheets or "누계" in sheets:
            MEDIA = ["SNS", "버즈빌", "포탈"]
            total_monthly, media_monthly = {}, {mm: {} for mm in MEDIA}

            if "월TOTAL요약(누계)" in sheets:
                d = pd.read_excel(xls, sheet_name="월TOTAL요약(누계)", header=0)
                d.columns = [str(c).strip() for c in d.columns]
                for _, r in d.iterrows():
                    try:
                        y, mo = int(r["연도"]), int(r["월"])
                    except Exception:
                        continue
                    tspend = trev = 0.0
                    for mm in MEDIA:
                        s = _tnum(r.get(f"{mm}_광고비")); rv = _tnum(r.get(f"{mm}_거래액"))
                        if s or rv:
                            media_monthly[mm][(y, mo)] = dict(
                                spend=s, rev=rv, roas=(rv / s if s else 0.0))
                        tspend += s; trev += rv
                    if tspend or trev:
                        total_monthly[(y, mo)] = dict(
                            spend=tspend, rev=trev, roas=(trev / tspend if tspend else 0.0))

            # DA 전체 목표를 전체 요약 탭에 매핑
            result["monthly"]["TOTAL"] = total_monthly
            result["monthly"]["TOTAL(서비스비용미반영)"] = total_monthly
            result["monthly_media"] = media_monthly

            # 주차별. 시트명은 '통합_전체' 또는 '누계'.
            # - result["weekly"]: ISO 주차 키(주차별 시트 목표 매칭용)
            # - result["weekly_rows"]: (연도,월)별 주차 목록[시작일, spend, rev] (월 MTD 목표 계산용)
            wk_sheet = next((s for s in ("통합_전체", "누계") if s in sheets), None)
            if wk_sheet:
                w = pd.read_excel(xls, sheet_name=wk_sheet, header=0)
                w.columns = [str(c).strip() for c in w.columns]
                agg_wk = {}          # ISO 주차 키
                rows_by_ym = {}      # (연,월) -> {시작일: [spend,rev]}
                for _, r in w.iterrows():
                    lab = str(r.get("기간", ""))
                    if "TOTAL" in lab:
                        continue
                    mt = re.search(r"\((\d{1,2})/(\d{1,2})", lab)
                    if not mt:
                        continue
                    try:
                        yr = int(r["연도"]); mo = int(r["월"])
                        sd = pd.Timestamp(yr, int(mt.group(1)), int(mt.group(2)))
                        iso = sd.isocalendar()
                        key = (int(iso[0]), int(iso[1]))
                    except Exception:
                        continue
                    sp = _tnum(r.get("광고비")); rv = _tnum(r.get("거래액"))
                    cur = agg_wk.get(key, dict(spend=0.0, rev=0.0))
                    cur["spend"] += sp; cur["rev"] += rv
                    agg_wk[key] = cur
                    ym = rows_by_ym.setdefault((yr, mo), {})
                    acc = ym.setdefault(sd, [0.0, 0.0])
                    acc[0] += sp; acc[1] += rv
                for k, v in agg_wk.items():
                    if v["spend"] or v["rev"]:
                        v["roas"] = v["rev"] / v["spend"] if v["spend"] else 0.0
                        result["weekly"][k] = v
                for ym, wk in rows_by_ym.items():
                    result["weekly_rows"][ym] = sorted(
                        [(sd, sv[0], sv[1]) for sd, sv in wk.items()], key=lambda x: x[0])
            return result

        # ── 구 양식 (하위 호환)
        SHEET_MAP = {
            "월별_TOTAL(서비스비용제외)": "TOTAL",
            "월별_TOTAL": "TOTAL(서비스비용미반영)",
            "월별_거래액": "거래액확대",
            "월별_신규확대": "신규고객확대",
        }
        for sheet, tab in SHEET_MAP.items():
            if sheet not in sheets:
                continue
            df = pd.read_excel(xls, sheet_name=sheet, header=None)
            tab_targets = {}
            for _, row in df.iterrows():
                label = str(row.iloc[1]) if pd.notna(row.iloc[1]) else ""
                if "년" not in label or "주차" in label:
                    continue
                try:
                    year = int(label[:4]); month = int(label[5:7])
                except Exception:
                    continue
                tab_targets[(year, month)] = dict(
                    spend=_tnum(row.iloc[41]), rev=_tnum(row.iloc[42]), roas=_tnum(row.iloc[43]))
            result["monthly"][tab] = tab_targets
        if "주차별" in sheets:
            df = pd.read_excel(xls, sheet_name="주차별", header=None)
            for _, row in df.iterrows():
                label = str(row.iloc[1]) if pd.notna(row.iloc[1]) else ""
                if "주차" not in label or len(label) < 8:
                    continue
                try:
                    date = pd.to_datetime(label[:8], format="%Y%m%d")
                    year = date.isocalendar().year; week = date.isocalendar().week
                except Exception:
                    continue
                spend, rev, roas = _tnum(row.iloc[38]), _tnum(row.iloc[39]), _tnum(row.iloc[40])
                if spend > 0 or rev > 0:
                    result["weekly"][(int(year), int(week))] = dict(spend=spend, rev=rev, roas=roas)
    except Exception as e:
        st.warning(f"목표 파일 파싱 오류: {e}")
    return result


# ───────────────────────────────────────────────
# 파생지표 계산
# ───────────────────────────────────────────────
def calc_kpi(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d["CTR"]        = safe_div(d["지표_클릭수"],                        d["지표_노출수"])
    d["CPC"]        = safe_div(d["지표_광고비"],                        d["지표_클릭수"])
    d["순결제ROAS"]  = safe_div(d["지표_순결제거래액"],                   d["지표_광고비"])
    d["총결제ROAS"]  = safe_div(d["지표_총결제거래액"],                   d["지표_광고비"])
    d["가입CPA"]    = safe_div(d["지표_광고비"],                        d["지표_가입회원"])
    d["첫구매CPA"]  = safe_div(d["지표_광고비"],                        d["지표_순결제고객수(첫구매)"])
    d["가입률"]     = safe_div(d["지표_가입회원"],                       d["지표_UV(전체)"])
    d["첫구매율"]   = safe_div(d["지표_순결제고객수(첫구매)"],             d["지표_UV(전체)"])
    d["CPM"]        = safe_div(d["지표_광고비"] * 1000,                 d["지표_노출수"])
    d["CPUV"]       = safe_div(d["지표_광고비"],                        d["지표_UV(전체)"])
    d["UV/클릭"]    = safe_div(d["지표_UV(전체)"],                      d["지표_클릭수"])
    d["CR(순)"]     = safe_div(d["지표_순결제고객수"],                   d["지표_UV(전체)"])
    d["CR(총)"]     = safe_div(d["지표_총결제고객수"],                   d["지표_UV(전체)"])
    d["객단가(순)"] = safe_div(d["지표_순결제거래액"],                    d["지표_순결제고객수"])
    d["객단가(총)"] = safe_div(d["지표_총결제거래액"],                    d["지표_총결제고객수"])
    d["순결제비중"]  = safe_div(d["지표_순결제고객수"],                   d["지표_총결제고객수"])
    d["신규비중"]   = safe_div(d["지표_당년신규순결제거래액"],              d["지표_총결제거래액"])
    d["윈백비중"]   = safe_div(d["지표_순결제거래액(윈백)"],               d["지표_총결제거래액"])
    d["첫구매비중"] = safe_div(d["지표_순결제거래액(첫구매)"],             d["지표_총결제거래액"])
    return d


def safe_div(num, den):
    return np.where((den == 0) | pd.isna(den), np.nan, num / den)


# ───────────────────────────────────────────────
# 포맷 헬퍼
# ───────────────────────────────────────────────
def fmt_money(v):
    if pd.isna(v): return "–"
    if abs(v) >= 1e8: return f"{v/1e8:.1f}억원"
    if abs(v) >= 1e6: return f"{v/1e6:.1f}백만원"
    return f"{int(v):,}원"

def fmt_won(v):
    """항상 원 단위로만 표기 (억/백만 단위 변환 없음)."""
    if pd.isna(v): return "–"
    return f"{int(round(v)):,}원"

def fmt_num(v):
    if pd.isna(v): return "–"
    return f"{int(v):,}"

def fmt_pct(v, decimals=2):
    if pd.isna(v): return "–"
    return f"{v*100:.{decimals}f}%"

def fmt_roas(v):
    if pd.isna(v): return "–"
    return f"{v*100:.0f}%"

# 증감률 통일 표기: 증가 → +초록, 감소 → △빨강
def signed_pct(v, decimals=1):
    """증감률 문자열: 증가는 '+', 감소는 '△'. (색상은 Styler chg_style로)"""
    if pd.isna(v):
        return "–"
    if v >= 0:
        return f"+{v*100:.{decimals}f}%"
    return f"△{abs(v)*100:.{decimals}f}%"


def chg_style(v):
    """Styler용: '+' 시작 초록, '△' 시작 빨강."""
    if isinstance(v, str):
        if v.startswith("+"):
            return "color: #16A34A"
        if v.startswith("△"):
            return "color: #DC2626"
    return ""


# 전체요약/일별 공통 그래프 지표 (표기 순서)
SUMMARY_CHART_METRICS = {
    "광고비": "지표_광고비", "거래액(순결제)": "지표_순결제거래액",
    "ROAS(순결제)": "순결제ROAS", "순결제비중": "순결제비중",
    "UV": "지표_UV(전체)", "CR(총)": "CR(총)",
    "CTR": "CTR", "CPC": "CPC", "가입률": "가입률", "가입CPA": "가입CPA",
    "첫구매CPA": "첫구매CPA", "신규거래액": "지표_당년신규순결제거래액",
}
RATIO_TICKFMT = {"순결제ROAS": ".0%", "순결제비중": ".1%",
                 "CR(총)": ".2%", "CTR": ".2%", "가입률": ".2%"}

# 일별 상세 지표 표 (요청 순서): (표기명, 원본컬럼, 종류)
DAILY_DETAIL_SPEC = [
    ("노출수", "지표_노출수", "num"), ("클릭수", "지표_클릭수", "num"),
    ("CTR", "CTR", "pct"), ("CR", "CR(순)", "pct3"),
    ("객단가", "객단가(순)", "money"), ("결제고객수", "지표_순결제고객수", "num"),
    ("CPM", "CPM", "money"), ("CPC", "CPC", "money"), ("CPUV", "CPUV", "money"),
    ("UV", "지표_UV(전체)", "num"), ("광고비", "지표_광고비", "money"),
    ("순결제거래액", "지표_순결제거래액", "money"), ("순결제ROAS", "순결제ROAS", "roas"),
    ("순결제비중(%)", "순결제비중", "pct"),
    ("총결제거래액", "지표_총결제거래액", "money"), ("총결제ROAS", "총결제ROAS", "roas"),
    ("UV/클릭(%)", "UV/클릭", "pct"), ("CR(총)", "CR(총)", "pct3"),
    ("객단가(총)", "객단가(총)", "money"), ("총결제고객수", "지표_총결제고객수", "num"),
    ("가입률", "가입률", "pct3"), ("가입수", "지표_가입회원", "num"),
    ("가입CPA", "가입CPA", "money"), ("첫구매율", "첫구매율", "pct3"),
    ("첫구매수", "지표_순결제고객수(첫구매)", "num"), ("첫구매CPA", "첫구매CPA", "money"),
    ("첫구매거래액", "지표_순결제거래액(첫구매)", "money"), ("첫구매비중", "첫구매비중", "pct"),
    ("신규고객수", "지표_당년신규순결제고객수", "num"), ("신규거래액", "지표_당년신규순결제거래액", "money"),
    ("신규비중", "신규비중", "pct"), ("윈백고객수", "지표_순결제고객수(윈백)", "num"),
    ("윈백거래액", "지표_순결제거래액(윈백)", "money"),
]

_DETAIL_FMT = {
    "money": fmt_money, "num": fmt_num,
    "pct": lambda v: fmt_pct(v, 2), "pct3": lambda v: fmt_pct(v, 3), "roas": fmt_roas,
}

# 소재 상세 첨부(Excel) 컬럼 양식 (업로드 예시 파일 순서). col=None → 빈 컬럼
CREATIVE_EXPORT_SPEC = [
    ("비용출처", "구분_비용출처"), ("카테고리", "카테고리"), ("기획전번호", None),
    ("AF코드", "구분_AF코드"), ("AF코드명", "구분_AF코드이름"), ("상세내역", None),
    ("캠페인", "구분_캠페인"), ("하위캠페인", "구분_하위캠페인"),
    ("매체명", "구분_매체명"), ("상품명", "구분_상품"),
    ("노출수", "지표_노출수"), ("클릭수", "지표_클릭수"), ("CTR", "CTR"), ("CR", "CR(순)"),
    ("객단가", "객단가(순)"), ("결제고객수", "지표_순결제고객수"),
    ("CPM", "CPM"), ("CPC", "CPC"), ("CPUV", "CPUV"), ("UV", "지표_UV(전체)"),
    ("비용", "지표_광고비"), ("순결제거래액", "지표_순결제거래액"), ("순결제ROAS", "순결제ROAS"),
    ("순결제비중(%)", "순결제비중"), ("총결제거래액", "지표_총결제거래액"), ("총결제ROAS", "총결제ROAS"),
    ("UV/클릭(%)", "UV/클릭"), ("CR총", "CR(총)"), ("객단가(총)", "객단가(총)"),
    ("결제고객수(총)", "지표_총결제고객수"), ("가입률", "가입률"), ("가입수", "지표_가입회원"),
    ("가입CPA", "가입CPA"), ("첫구매율", "첫구매율"), ("첫구매수", "지표_순결제고객수(첫구매)"),
    ("첫구매CPA", "첫구매CPA"), ("첫구매", "지표_순결제거래액(첫구매)"), ("첫구매비중", "첫구매비중"),
    ("신규고객수", "지표_당년신규순결제고객수"), ("신규거래액", "지표_당년신규순결제거래액"),
    ("신규비중", "신규비중"), ("윈백고객수", "지표_순결제고객수(윈백)"), ("윈백거래액", "지표_순결제거래액(윈백)"),
]


def week_of_month_label(year: int, week: int) -> str:
    """ISO (연도, 주차) → '26년7월1주차' 형식."""
    import datetime as _dt
    try:
        d = _dt.date.fromisocalendar(int(year), int(week), 4)  # 목요일 기준
    except Exception:
        return f"W{int(week):02d}"
    wom = (d.day - 1) // 7 + 1
    return f"{str(d.year)[2:]}년 {d.month}월 {wom}주차"


def fmt_delta(cur, prev, is_pct=False):
    if pd.isna(cur) or pd.isna(prev) or prev == 0:
        return "–"
    ratio = (cur - prev) / abs(prev)
    if is_pct:
        diff = (cur - prev) * 100
        sign = "+" if diff >= 0 else "△"
        return f"{sign}{abs(diff):.2f}%p"
    sign = "+" if ratio >= 0 else "△"
    return f"{sign}{abs(ratio)*100:.1f}%"


# ───────────────────────────────────────────────
# 집계 헬퍼
# ───────────────────────────────────────────────
AGG_COLS = [
    "지표_노출수", "지표_클릭수", "지표_광고비",
    "지표_UV(전체)", "지표_UV(회원)", "지표_PV(회원)", "지표_가입회원",
    "지표_총결제고객수(첫구매)", "지표_순결제고객수",
    "지표_총결제거래액(첫구매)", "지표_총결제거래액", "지표_순결제거래액",
    "지표_당년신규순결제고객수", "지표_당년신규순결제거래액",
    "지표_총결제고객수", "지표_순결제고객수(첫구매)", "지표_순결제거래액(첫구매)",
    "지표_순결제고객수(윈백)", "지표_순결제거래액(윈백)",
    "지표_총결제고객수(윈백)", "지표_총결제거래액(윈백)", "지표_영상조회수",
]

def agg(df: pd.DataFrame, by: list) -> pd.DataFrame:
    cols = [c for c in AGG_COLS if c in df.columns]
    # 방어적: 집계 대상 컬럼에 문자열(' - ' 등)이 섞여 있으면 groupby.sum()이
    # 'int + str' TypeError를 낸다. 항상 숫자로 강제 변환한다.
    non_numeric = [c for c in cols if not pd.api.types.is_numeric_dtype(df[c])]
    if non_numeric:
        df = df.copy()
        for c in non_numeric:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
    grouped = df.groupby(by, dropna=False)[cols].sum().reset_index()
    if "기간_일자" in df.columns and "집행일수" not in by and "기간_일자" not in by:
        days = df.groupby(by, dropna=False)["기간_일자"].nunique().reset_index()
        days.columns = list(days.columns[:-1]) + ["집행일수"]
        grouped = grouped.merge(days, on=by, how="left")
    return calc_kpi(grouped)


# ───────────────────────────────────────────────
# YoY 동기간 오버레이 헬퍼
# ───────────────────────────────────────────────
def yoy_overlay_fig(df: pd.DataFrame, period_col: str, val_col: str,
                    title: str, ticklabels: dict | None = None,
                    height: int = 380, ma_window: int = 0,
                    textfmt: str | None = None) -> go.Figure:
    """
    연도별 라인을 동일 x축(period_col)에 겹쳐 그린다.
    period_col: 月(1~12) 또는 주차번호(1~53) 같은 숫자형 기간 컬럼
    ticklabels: {값: "라벨"} 딕셔너리 (없으면 그대로)
    ma_window: 이동평균 창 크기 (0=사용안함)
    """
    years = sorted(df["연도"].unique())
    fig = go.Figure()
    for i, yr in enumerate(years):
        sub = df[df["연도"] == yr].sort_values(period_col).dropna(subset=[val_col])
        color = YEAR_COLORS[i % len(YEAR_COLORS)]
        fig.add_trace(go.Scatter(
            x=sub[period_col], y=sub[val_col],
            name=f"{yr}년",
            mode="lines+markers+text" if textfmt else "lines+markers",
            line=dict(color=color, width=2),
            marker=dict(size=6),
            texttemplate=(f"%{{y:{textfmt}}}" if textfmt else None),
            textposition="top center", textfont=dict(size=9),
        ))
        if ma_window > 1 and len(sub) >= ma_window:
            ma = sub[val_col].rolling(ma_window, min_periods=1).mean()
            fig.add_trace(go.Scatter(
                x=sub[period_col], y=ma,
                name=f"{yr}년 {ma_window}주MA",
                mode="lines",
                line=dict(color=color, width=1.5, dash="dot"),
                showlegend=True,
            ))
    if ticklabels:
        vals = sorted(ticklabels.keys())
        fig.update_xaxes(tickvals=vals, ticktext=[ticklabels[v] for v in vals])
    base_layout(fig, title, height)
    return fig


# 일평균으로 환산할 볼륨(합산) 지표 — 비율지표(ROAS/CPA/CR 등)는 그대로 둔다.
VOLUME_COLS = {
    "지표_광고비", "지표_순결제거래액", "지표_총결제거래액", "지표_UV(전체)",
    "지표_당년신규순결제거래액", "지표_클릭수", "지표_노출수", "지표_가입회원",
    "지표_순결제고객수", "지표_총결제고객수", "지표_순결제고객수(첫구매)",
}


def metric_trend_fig(df: pd.DataFrame, val_col: str, gran: str, title: str,
                     height: int = 380, tickfmt: str = None) -> go.Figure:
    """월/주/주(최근10주) 단위 지표 추이 (선형, 연도별 YoY 오버레이).
    볼륨 지표는 '일평균'(해당 기간 합계 / 집행일수)으로 환산해 표시한다."""
    lbl_fmt = tickfmt if tickfmt else ",.0f"
    is_vol = val_col in VOLUME_COLS
    if gran == "월":
        d = agg(df, ["연도", "월"]).sort_values(["연도", "월"])
        if is_vol and "집행일수" in d.columns:
            d[val_col] = d[val_col] / d["집행일수"].replace(0, np.nan)
        # 당월(부분월)은 전년도 동일월 포인트를 MTD(동요일 -364일 창)로 맞춤.
        data_max = df["기간_일자"].max()
        cy, cm = int(data_max.year), int(data_max.month)
        if data_max.day < calendar.monthrange(cy, cm)[1]:
            cur_dates = df[(df["연도"] == cy) & (df["월"] == cm)]["기간_일자"].drop_duplicates()
            prev_dates = cur_dates - pd.Timedelta(days=364)
            sub = df[df["기간_일자"].isin(prev_dates)]
            if not sub.empty:
                pa = agg(sub, ["연도"])
                v = pa[val_col].iloc[0]
                if is_vol:
                    ndays = sub["기간_일자"].nunique()
                    v = v / ndays if ndays else np.nan
                mask = (d["연도"] == cy - 1) & (d["월"] == cm)
                if mask.any():
                    d.loc[mask, val_col] = v
                elif not pd.isna(v):
                    d = pd.concat([d, pd.DataFrame([{"연도": cy - 1, "월": cm, val_col: v}])],
                                  ignore_index=True).sort_values(["연도", "월"])
        fig = yoy_overlay_fig(d, "월", val_col, title,
                              ticklabels=MONTH_LABELS, height=height, textfmt=lbl_fmt)
    elif gran == "일":
        # 일 단위: 실제 날짜 시계열 (연도별 색상) + 데이터값 라벨
        d = agg(df, ["기간_일자"]).sort_values("기간_일자").dropna(subset=[val_col])
        d["_yr"] = d["기간_일자"].dt.year
        fig = go.Figure()
        # 점이 너무 많으면 라벨이 겹치므로 40개 이하일 때만 값 표시
        show_text = d["기간_일자"].nunique() <= 40
        for i, yr in enumerate(sorted(d["_yr"].unique())):
            sub = d[d["_yr"] == yr]
            fig.add_trace(go.Scatter(
                x=sub["기간_일자"], y=sub[val_col], name=f"{yr}년",
                mode="lines+markers+text" if show_text else "lines+markers",
                line=dict(color=YEAR_COLORS[i % len(YEAR_COLORS)], width=1.8),
                marker=dict(size=4),
                texttemplate=(f"%{{y:{lbl_fmt}}}" if show_text else None),
                textposition="top center", textfont=dict(size=8),
            ))
        base_layout(fig, title, height)
    else:
        # 주 / 주(최근10주): 주 단위 일평균
        d = agg(df, ["연도", "주차번호"]).sort_values(["연도", "주차번호"])
        if is_vol and "집행일수" in d.columns:
            d[val_col] = d[val_col] / d["집행일수"].replace(0, np.nan)
        # 당주(부분주)는 전년도 동일 주차 포인트를 MTD(동요일 -364일 창)로 맞춤.
        data_max = df["기간_일자"].max()
        iso = data_max.isocalendar()
        cwy, cw = int(iso[0]), int(iso[1])
        import datetime as _dt
        try:
            sunday = pd.Timestamp(_dt.date.fromisocalendar(cwy, cw, 7))
        except Exception:
            sunday = data_max
        if data_max.normalize() < sunday:
            cur_dates = df[df["기간_일자"] > (data_max - pd.Timedelta(days=data_max.weekday()))]["기간_일자"].drop_duplicates()
            prev_dates = cur_dates - pd.Timedelta(days=364)
            sub = df[df["기간_일자"].isin(prev_dates)]
            if not sub.empty:
                pa = agg(sub, ["연도"])
                v = pa[val_col].iloc[0]
                if is_vol:
                    nd = sub["기간_일자"].nunique()
                    v = v / nd if nd else np.nan
                mask = (d["연도"] == cwy - 1) & (d["주차번호"] == cw)
                if mask.any() and not pd.isna(v):
                    d.loc[mask, val_col] = v
        if gran == "주(최근10주)":
            d = d.copy()
            d["_ord"] = d["연도"].astype(int) * 100 + d["주차번호"].astype(int)
            recent = sorted(d["_ord"].unique())[-10:]
            d = d[d["_ord"].isin(recent)]
        cur_year = int(df["연도"].max())
        wk_labels = {w: week_of_month_label(cur_year, w) for w in range(1, 54)}
        fig = yoy_overlay_fig(d, "주차번호", val_col, title,
                              ticklabels=wk_labels, height=height)
    if tickfmt:
        fig.update_yaxes(tickformat=tickfmt)
    return fig


def yoy_compare(df: pd.DataFrame, cur_year: int, by_col: str, val_col: str):
    prev_year = cur_year - 1
    sub = df[df["연도"].isin([cur_year, prev_year])]
    piv = agg(sub, ["연도", by_col])
    cur  = piv[piv["연도"] == cur_year][[by_col, val_col]].rename(columns={val_col: "당년"})
    prev = piv[piv["연도"] == prev_year][[by_col, val_col]].rename(columns={val_col: "전년"})
    merged = cur.merge(prev, on=by_col, how="outer").sort_values(by_col)
    merged["전년비"] = (merged["당년"] - merged["전년"]) / merged["전년"].abs()
    return merged


def yoy_sameday_prev(df: pd.DataFrame, cur_year: int, group_col: str) -> pd.DataFrame:
    """동요일 기준 전년 집계: 현재년도 각 날짜의 -364일(52주) 전 날짜로 전년 데이터 매핑."""
    cur = df[df["연도"] == cur_year][["기간_일자", group_col]].drop_duplicates()
    cur["비교일자"] = cur["기간_일자"] - pd.Timedelta(days=364)
    date_to_group = cur.set_index("비교일자")[group_col].to_dict()

    prev = df[df["연도"] == cur_year - 1].copy()
    prev[group_col + "_cur"] = prev["기간_일자"].map(date_to_group)
    prev_valid = prev.dropna(subset=[group_col + "_cur"])
    if prev_valid.empty:
        return pd.DataFrame()
    prev_agg = agg(prev_valid, [group_col + "_cur"])
    prev_agg = prev_agg.rename(columns={group_col + "_cur": group_col})
    return prev_agg


def _fmt_mil(v):
    """백만원 단위 소수1자리."""
    if pd.isna(v): return "–"
    return f"{round(v / 1e6, 1):,.1f}"

# 요약 테이블 지표 정의: 표기라벨 -> (원본컬럼, 표기포맷 함수)
_METRIC_SRC = {
    "광고비(백만)":     ("지표_광고비",              _fmt_mil),
    "거래액(백만)":     ("지표_순결제거래액",         _fmt_mil),
    "ROAS":            ("순결제ROAS",              fmt_roas),
    "가입수":           ("지표_가입회원",            fmt_num),
    "가입CPA":          ("가입CPA",                fmt_won),
    "첫구매수":         ("지표_순결제고객수(첫구매)",   fmt_num),
    "첫구매CPA":        ("첫구매CPA",              fmt_won),
    "신규거래액(백만)":   ("지표_당년신규순결제거래액",   _fmt_mil),
}
# 목표가 존재하는 지표 -> 목표 dict 키
_TGT_KEY = {"광고비(백만)": "spend", "거래액(백만)": "rev", "ROAS": "roas"}

DEFAULT_METRICS = ["광고비(백만)", "거래액(백만)", "ROAS"]
ACQ_METRICS = ["광고비(백만)", "거래액(백만)", "ROAS", "가입수", "가입CPA",
               "첫구매수", "첫구매CPA", "신규거래액(백만)"]


def summary_table(rows, metric_labels, groups, period_type: str = "월") -> pd.DataFrame:
    """실적요약 테이블(2줄 헤더/MultiIndex 컬럼).
    rows: [(라벨, cur_series, prev_series|None, target_dict), ...]
    metric_labels: 표기할 지표 라벨 목록(_METRIC_SRC 키)
    groups: ("실적","전년비","목표","목표비") 중 포함할 그룹
    반환: 상단=그룹, 하단=지표 인 2단 컬럼 DataFrame
    """
    def _get(s, col):
        if s is None: return np.nan
        try:
            v = s.get(col, np.nan)
        except AttributeError:
            v = np.nan
        return v

    def _chg(c, p):
        if pd.isna(c) or pd.isna(p) or p == 0: return np.nan
        return (c - p) / abs(p)

    tuples = [(period_type, "")]
    for g in groups:
        for m in metric_labels:
            tuples.append((g, m))

    data = []
    for row in rows:
        # row: (라벨, cur, prev, tgt[, block]) — block=True면 전년비/목표비 차단
        label, cur, prev, tgt = row[0], row[1], row[2], row[3]
        block = row[4] if len(row) > 4 else False
        tgt = tgt or {}
        rec = {(period_type, ""): label}
        for m in metric_labels:
            src, fmt = _METRIC_SRC[m]
            cval = _get(cur, src)
            pval = _get(prev, src)
            tk = _TGT_KEY.get(m)
            tv = (tgt.get(tk) if tk else None) or 0
            if "실적" in groups:
                rec[("실적", m)] = fmt(cval) if not pd.isna(cval) else "–"
            if "전년비" in groups:
                rec[("전년비", m)] = "–" if block else signed_pct(_chg(cval, pval))
            if "목표" in groups:
                rec[("목표", m)] = fmt(tv) if tv > 0 else "–"
            if "목표비" in groups:
                # 목표비도 증감률 형식(+초록/△빨강)으로 통일: 실적/목표 - 1
                rec[("목표비", m)] = ("–" if (block or not tk or tv <= 0 or pd.isna(cval))
                                     else signed_pct(cval / tv - 1))
        data.append(rec)

    return pd.DataFrame(data, columns=pd.MultiIndex.from_tuples(tuples))


# ───────────────────────────────────────────────
# 상세 실적 표 (기간별 전지표) — 전체요약/주차별/일별 공용
# ───────────────────────────────────────────────
def _fmt_kind(v, kind):
    if pd.isna(v): return "–"
    if kind == "money": return fmt_money(v)
    if kind == "won":   return fmt_won(v)
    if kind == "roas":  return fmt_roas(v)
    if kind == "num":   return fmt_num(v)
    if kind == "pct1":  return fmt_pct(v, 1)
    if kind == "pct2":  return fmt_pct(v, 2)
    return str(v)

# (표기명, 원본컬럼, 종류)
DETAIL_SPEC = [
    ("광고비",        "지표_광고비",              "money"),
    ("순결제매출",     "지표_순결제거래액",         "money"),
    ("순결제ROAS",    "순결제ROAS",              "roas"),
    ("순결제비중(%)",  "순결제비중",              "pct1"),
    ("총결제매출",     "지표_총결제거래액",         "money"),
    ("총매출ROAS",    "총결제ROAS",              "roas"),
    ("UV/클릭(%)",    "UV/클릭",                "pct2"),
    ("CR(총)",       "CR(총)",                 "pct2"),
    ("객단가(총)",     "객단가(총)",              "won"),
    ("총결제고객수",   "지표_총결제고객수",         "num"),
    ("가입률",        "가입률",                  "pct2"),
    ("가입수",        "지표_가입회원",            "num"),
    ("가입CPA",       "가입CPA",                "won"),
    ("첫구매율",       "첫구매율",                "pct2"),
    ("첫구매수",       "지표_순결제고객수(첫구매)",   "num"),
    ("첫구매CPA",      "첫구매CPA",              "won"),
    ("첫구매거래액",    "지표_순결제거래액(첫구매)",   "money"),
    ("첫구매비중",     "첫구매비중",              "pct1"),
    ("신규고객수",     "지표_당년신규순결제고객수",   "num"),
    ("신규거래액",     "지표_당년신규순결제거래액",   "money"),
    ("신규비중",       "신규비중",                "pct1"),
    ("윈백고객수",     "지표_순결제고객수(윈백)",     "num"),
    ("윈백거래액",     "지표_순결제거래액(윈백)",     "money"),
]
DETAIL_COLS = [d[0] for d in DETAIL_SPEC]


def detail_table(rows, period_label="기간") -> pd.DataFrame:
    """실적 상세표. rows: [(라벨, cur_series)]"""
    data = []
    for label, s in rows:
        rec = {period_label: label}
        for disp, col, kind in DETAIL_SPEC:
            v = (s.get(col, np.nan) if s is not None else np.nan)
            rec[disp] = _fmt_kind(v, kind)
        data.append(rec)
    return pd.DataFrame(data, columns=[period_label] + DETAIL_COLS)


def detail_table_yoy(rows, period_label="기간") -> pd.DataFrame:
    """전년비 상세표(모든 셀이 증감률). rows: [(라벨, cur_series, prev_series[, block])]"""
    data = []
    for row in rows:
        label, cur, prev = row[0], row[1], row[2]
        block = row[3] if len(row) > 3 else False
        rec = {period_label: label}
        for disp, col, kind in DETAIL_SPEC:
            c = (cur.get(col, np.nan) if cur is not None else np.nan)
            p = (prev.get(col, np.nan) if prev is not None else np.nan)
            if block or pd.isna(c) or pd.isna(p) or p == 0:
                rec[disp] = "–"
            else:
                rec[disp] = signed_pct((c - p) / abs(p))
        data.append(rec)
    return pd.DataFrame(data, columns=[period_label] + DETAIL_COLS)


def mtd_target_from_weekly(weekly_rows: dict, year: int, month: int, data_max) -> dict:
    """당월 MTD 목표(목표파일 주차 기준):
    - 완결된 주(다음 주가 이미 시작): 목표 전액
    - 진행 중인 주(data_max 포함): 목표 × (진행일수 ÷ 7)
    - 아직 시작 안 한 주: 제외
    weekly_rows: {(연,월): [(시작일, spend, rev), ...]} (시작일 오름차순)
    """
    rows = (weekly_rows or {}).get((int(year), int(month)))
    if not rows:
        return {}
    dmax = pd.Timestamp(data_max).normalize()
    spend = rev = 0.0
    for i, (sd, sp, rv) in enumerate(rows):
        sd = pd.Timestamp(sd).normalize()
        if sd > dmax:
            break
        nxt = pd.Timestamp(rows[i + 1][0]).normalize() if i + 1 < len(rows) else None
        if nxt is not None and nxt <= dmax:
            # 다음 주가 이미 시작 → 이 주는 완결
            spend += sp; rev += rv
        else:
            # 진행 중인 주
            elapsed = (dmax - sd).days + 1
            f = min(max(elapsed, 0), 7) / 7.0
            spend += sp * f; rev += rv * f
    if spend <= 0 and rev <= 0:
        return {}
    return dict(spend=spend, rev=rev, roas=(rev / spend if spend else 0.0))


# ───────────────────────────────────────────────
# 날짜 범위 필터 (페이지 상단)
# ───────────────────────────────────────────────
def date_range_filter(df: pd.DataFrame, key_prefix: str = "dr",
                      default_preset: str = "이번달") -> pd.DataFrame:
    """페이지 상단 날짜 범위 선택기. 프리셋 버튼 + 직접 입력.
    key_prefix로 페이지별 독립 상태를 유지한다."""
    k_start, k_end, k_preset = f"{key_prefix}_start", f"{key_prefix}_end", f"{key_prefix}_preset"

    today = pd.Timestamp.today().normalize()
    data_max = df["기간_일자"].max()
    data_min = df["기간_일자"].min()

    week_start = today - pd.Timedelta(days=today.dayofweek)
    last_week_start = week_start - pd.Timedelta(days=7)
    presets = {
        "전일":   (today - pd.Timedelta(days=1), today - pd.Timedelta(days=1)),
        "이번주": (week_start, today),
        "지난주": (last_week_start, week_start - pd.Timedelta(days=1)),
        "이번달": (today.replace(day=1), today),
        "올해":   (today.replace(month=1, day=1), today),
    }

    # 초기 상태
    if k_start not in st.session_state:
        ps_def, pe_def = presets.get(default_preset, presets["이번주"])
        st.session_state[k_start]  = max(ps_def, data_min).date()
        st.session_state[k_end]    = min(pe_def, data_max).date()
        st.session_state[k_preset] = default_preset

    cols = st.columns([1, 1, 1, 1, 1, 0.2, 2, 0.4, 2])
    for i, (label, (ps, pe)) in enumerate(presets.items()):
        with cols[i]:
            ps_clamped = max(ps, data_min).date()
            pe_clamped = min(pe, data_max).date()
            is_active = st.session_state.get(k_preset) == label
            if st.button(label, key=f"{key_prefix}_btn_{label}",
                         type="primary" if is_active else "secondary",
                         use_container_width=True):
                st.session_state[k_start]  = ps_clamped
                st.session_state[k_end]    = pe_clamped
                st.session_state[k_preset] = label
                st.rerun()

    d_min = data_min.date()
    d_max = data_max.date()
    # clamp session state values to valid data range before passing to date_input
    clamped_start = max(d_min, min(d_max, st.session_state[k_start]))
    clamped_end   = max(d_min, min(d_max, st.session_state[k_end]))

    # NOTE: date_input에 key를 주면 위젯 상태가 value=를 덮어써서 프리셋 버튼이
    # 되돌려지는 버그가 생긴다. key 없이 value=로만 제어한다.
    with cols[6]:
        new_start = st.date_input("시작일", value=clamped_start,
                                  min_value=d_min, max_value=d_max,
                                  label_visibility="collapsed")
    with cols[7]:
        st.markdown("<div style='padding-top:8px;text-align:center;color:#64748B'>~</div>",
                    unsafe_allow_html=True)
    with cols[8]:
        new_end = st.date_input("종료일", value=clamped_end,
                                min_value=d_min, max_value=d_max,
                                label_visibility="collapsed")

    if new_start != st.session_state[k_start] or new_end != st.session_state[k_end]:
        st.session_state[k_start]  = new_start
        st.session_state[k_end]    = new_end
        st.session_state[k_preset] = "직접 지정"

    start = pd.Timestamp(st.session_state[k_start])
    end   = pd.Timestamp(st.session_state[k_end])
    out = df[(df["기간_일자"] >= start) & (df["기간_일자"] <= end)]
    st.caption(f"📅 적용 기간: **{start.date()} ~ {end.date()}** · {len(out):,}행")
    return out


# 사이드바 필터
# ───────────────────────────────────────────────
def sidebar_filters(df: pd.DataFrame):
    """호출자가 st.sidebar 컨테이너 컨텍스트 안에서 호출한다고 가정 (st.* 사용)."""
    st.header("필터")

    years = sorted(df["연도"].unique())
    sel_year = st.multiselect("연도", years, default=years)

    months = list(range(1, 13))
    sel_month = st.multiselect("월", months, default=months,
                               format_func=lambda x: f"{x}월")
    st.divider()

    cost_mode = st.radio("비용출처 모드",
                         ["TOTAL", "TOTAL(서비스비용미반영)", "개별 선택"], index=0)
    sel_sources = None
    if cost_mode == "개별 선택":
        all_sources = sorted(df["구분_비용출처"].dropna().unique())
        sel_sources = st.multiselect("비용출처", all_sources, default=all_sources)

    st.divider()

    if df["대상여부"].nunique() > 1:
        target_opts = sorted(df["대상여부"].dropna().unique())
        sel_target = st.multiselect("대상여부", target_opts, default=["대상"])
    else:
        sel_target = list(df["대상여부"].dropna().unique())

    if df["구분_광고유형"].nunique() > 1:
        ad_types = sorted(df["구분_광고유형"].dropna().unique())
        sel_adtype = st.multiselect("광고유형", ad_types, default=ad_types)
    else:
        sel_adtype = list(df["구분_광고유형"].dropna().unique())

    channels = sorted(df["구분_채널"].dropna().unique())
    sel_channel = st.multiselect("채널", channels, default=channels)

    media_list = sorted(df["구분_매체명"].dropna().unique())
    sel_media = st.multiselect("매체명", media_list, default=media_list)

    devices = sorted(df["구분_디바이스"].dropna().unique())
    sel_device = st.multiselect("디바이스", devices, default=devices)

    st.divider()

    depts = sorted(df["구분_부서명"].dropna().unique())
    sel_dept = st.multiselect("부서명", depts, default=depts)

    cats = sorted(df["카테고리"].dropna().unique())
    sel_cat = st.multiselect("카테고리", cats, default=cats)

    return dict(
        years=sel_year, months=sel_month,
        cost_mode=cost_mode, sel_sources=sel_sources,
        target=sel_target, adtype=sel_adtype,
        channels=sel_channel, media=sel_media,
        devices=sel_device, depts=sel_dept, cats=sel_cat,
    )


def filter_df(df: pd.DataFrame, f: dict) -> pd.DataFrame:
    mask = (
        df["연도"].isin(f["years"]) &
        df["월"].isin(f["months"]) &
        df["대상여부"].isin(f["target"]) &
        df["구분_광고유형"].isin(f["adtype"]) &
        df["구분_채널"].isin(f["channels"]) &
        df["구분_매체명"].isin(f["media"]) &
        df["구분_디바이스"].isin(f["devices"]) &
        df["구분_부서명"].isin(f["depts"]) &
        df["카테고리"].isin(f["cats"])
    )
    d = df[mask]
    if f["cost_mode"] in ("TOTAL", "TOTAL(서비스비용미반영)"):
        d = d[d["구분_비용출처"].isin(COST_BUCKETS[f["cost_mode"]])]
    elif f["cost_mode"] == "개별 선택" and f["sel_sources"]:
        d = d[d["구분_비용출처"].isin(f["sel_sources"])]
    return d


# ───────────────────────────────────────────────
# Plotly 공통 레이아웃
# ───────────────────────────────────────────────
def label_traces(fig, fmt=",.0f", size=9):
    """모든 trace에 데이터값 라벨 표시. fmt은 d3 포맷(예: ',.0f', '.0%')."""
    for tr in fig.data:
        ttype = getattr(tr, "type", "")
        if ttype == "bar":
            axis = "x" if getattr(tr, "orientation", "v") == "h" else "y"
            tr.texttemplate = f"%{{{axis}:{fmt}}}"
            tr.textposition = "outside"
            tr.textfont = dict(size=size)
            tr.cliponaxis = False
        elif ttype == "scatter":
            m = getattr(tr, "mode", "") or "lines"
            if "text" not in m:
                tr.mode = (m + "+text") if "markers" in m else (m + "+markers+text")
            tr.texttemplate = f"%{{y:{fmt}}}"
            tr.textposition = "top center"
            tr.textfont = dict(size=size)
    return fig


def base_layout(fig, title="", height=400):
    fig.update_layout(
        title=dict(text=title, font=dict(size=14, color="#1E293B")),
        height=height,
        paper_bgcolor="white", plot_bgcolor="#F8FAFC",
        font=dict(family="Pretendard, Apple SD Gothic Neo, sans-serif", size=12),
        margin=dict(l=10, r=10, t=50, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis=dict(gridcolor="#E2E8F0", linecolor="#CBD5E1"),
        yaxis=dict(gridcolor="#E2E8F0", linecolor="#CBD5E1"),
    )
    return fig


# ───────────────────────────────────────────────
# 목표 입력 UI
# ───────────────────────────────────────────────
def get_targets():
    return dict(spend=0, rev=0, roas=0, uv=0, join=0, first=0)


def progress_pill(cur, target, label):
    if target <= 0:
        return
    rate = cur / target
    color = "#16A34A" if rate >= 1.0 else ("#EA580C" if rate < 0.7 else "#D97706")
    st.markdown(
        f'<span style="background:{color};color:white;padding:2px 8px;'
        f'border-radius:12px;font-size:12px;">{label} {rate*100:.1f}%</span>',
        unsafe_allow_html=True,
    )


def render_kpi_card(label: str, value: str, sub_label: str = "", sub_value: str = "",
                    accent: str = "#2563EB", progress: float = None):
    """레퍼런스 디자인 스타일의 KPI 카드."""
    progress_html = ""
    if progress is not None:
        pct = min(progress * 100, 100)
        bar_color = "#16A34A" if progress >= 1.0 else ("#D97706" if progress >= 0.7 else "#EF4444")
        progress_html = f"""
        <div style="margin-top:8px;">
          <div style="display:flex;justify-content:space-between;margin-bottom:3px;">
            <span style="font-size:11px;color:#64748B;">목표 달성률</span>
            <span style="font-size:11px;font-weight:600;color:{bar_color};">{progress*100:.1f}%</span>
          </div>
          <div style="background:#E2E8F0;border-radius:4px;height:4px;">
            <div style="background:{bar_color};width:{pct}%;height:4px;border-radius:4px;"></div>
          </div>
        </div>"""
    sub_html = ""
    if sub_label:
        sub_html = f'<div style="margin-top:2px;font-size:11px;color:#64748B;">{sub_label} <b style="color:#334155;">{sub_value}</b></div>'
    elif sub_value:
        # sub_value only (e.g. YoY HTML span)
        sub_html = f'<div style="margin-top:2px;">{sub_value}</div>'
    st.markdown(f"""
    <div style="background:white;border:1px solid #E2E8F0;border-radius:10px;padding:9px 12px;
                box-shadow:0 1px 3px rgba(0,0,0,.05);min-height:62px;">
      <div style="font-size:11px;color:#64748B;font-weight:500;margin-bottom:2px;">{label}</div>
      <div style="font-size:17px;font-weight:700;color:#0F172A;line-height:1.15;">{value}</div>
      {sub_html}
      {progress_html}
    </div>""", unsafe_allow_html=True)


def render_goal_bar(targets: dict, cur_spend: float, cur_rev: float, cur_roas: float):
    """목표 KPI 한줄 요약 바."""
    items = []
    if targets.get("spend", 0) > 0:
        items.append(("월 광고비 목표", fmt_money(targets["spend"]),
                       cur_spend / targets["spend"] if cur_spend else None))
    if targets.get("roas", 0) > 0:
        items.append(("ROAS 목표", fmt_roas(targets["roas"]),
                       cur_roas / targets["roas"] if cur_roas else None))
    if targets.get("rev", 0) > 0:
        items.append(("월 거래액 목표", fmt_money(targets["rev"]),
                       cur_rev / targets["rev"] if cur_rev else None))
    if not items:
        return
    parts = []
    for name, val, rate in items:
        badge = ""
        if rate is not None:
            bc = "#16A34A" if rate >= 1.0 else ("#D97706" if rate >= 0.7 else "#EF4444")
            badge = f' <span style="background:{bc};color:white;border-radius:8px;padding:1px 7px;font-size:11px;">{rate*100:.1f}%</span>'
        parts.append(f'<span style="margin-right:24px;"><span style="color:#64748B;">{name}</span> <b style="color:#0F172A;">{val}</b>{badge}</span>')
    st.markdown(
        f'<div style="background:#F1F5F9;border-radius:10px;padding:10px 18px;margin-bottom:12px;font-size:13px;">{"".join(parts)}</div>',
        unsafe_allow_html=True,
    )


def render_top3_section(df: pd.DataFrame, targets: dict):
    """잘 되는 캠페인 TOP5 / 개선 우선순위 TOP5 / 알림 (친구추가 캠페인 제외)"""
    camp_col = next((c for c in ["구분_캠페인", "구분_캠페인명", "구분_하위캠페인", "구분_매체명"]
                     if c in df.columns and df[c].astype(str).str.strip().ne("").any()), None)
    if camp_col is None:
        return
    # 친구추가 캠페인은 집계 전에 원천 제거
    base = df[~df[camp_col].astype(str).str.contains("친구추가", na=False)]
    by_camp = agg(base, [camp_col]).dropna(subset=["순결제ROAS"])
    by_camp = by_camp[by_camp["지표_광고비"] > 0]
    by_camp = by_camp[by_camp[camp_col].astype(str).str.strip().ne("")]
    by_camp = by_camp.rename(columns={camp_col: "구분_캠페인명"})

    t_roas = targets.get("roas", 0)
    N = 5

    top3 = by_camp.nlargest(N, "순결제ROAS")
    bot3 = by_camp.nsmallest(N, "순결제ROAS")

    # 알림 자동 생성
    alerts = []
    tot = calc_kpi(pd.DataFrame([df[AGG_COLS].sum()])).iloc[0]
    cur_roas = tot["순결제ROAS"]
    if t_roas > 0 and cur_roas < t_roas:
        gap = t_roas - cur_roas
        alerts.append(("⚠️", "ROAS 목표 미달", f"현재 {fmt_roas(cur_roas)} | 목표 {fmt_roas(t_roas)} | 부족 {gap*100:.0f}%p"))
    # 전월 대비 급변 캠페인
    years = sorted(df["연도"].unique())
    if len(years) >= 1:
        cur_year = int(df["연도"].max())
        cur_month = int(df[df["연도"] == cur_year]["월"].max())
        prev_month_df = df[(df["연도"] == cur_year) & (df["월"] == cur_month - 1)] if cur_month > 1 else pd.DataFrame()
        cur_month_df = df[(df["연도"] == cur_year) & (df["월"] == cur_month)]
        if not prev_month_df.empty and not cur_month_df.empty and camp_col in df.columns:
            prev_month_df = prev_month_df[~prev_month_df[camp_col].astype(str).str.contains("친구추가", na=False)]
            cur_month_df = cur_month_df[~cur_month_df[camp_col].astype(str).str.contains("친구추가", na=False)]
            pm = agg(prev_month_df, [camp_col]).set_index(camp_col)
            cm = agg(cur_month_df, [camp_col]).set_index(camp_col)
            common = pm.index.intersection(cm.index)
            for c in common:
                p, n = pm.loc[c, "지표_광고비"], cm.loc[c, "지표_광고비"]
                if p > 0 and abs(n - p) / p > 0.5:
                    direction = "급증" if n > p else "급감"
                    alerts.append(("📊", f"캠페인 광고비 {direction}", f"{c[:30]} ({(n-p)/p*100:+.0f}%)"))
    if not alerts:
        alerts.append(("✅", "이상 없음", "모든 주요 지표가 정상 범위입니다."))

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("**🏆 잘 되는 캠페인 TOP 5** <span style='font-size:11px;color:#64748B;'>ROAS 기준</span>", unsafe_allow_html=True)
        for rank, (_, row) in enumerate(top3.iterrows(), 1):
            name = str(row["구분_캠페인명"])[:35]
            roas = row["순결제ROAS"]
            spend = fmt_money(row["지표_광고비"])
            badge_color = ["#F59E0B", "#94A3B8", "#CD7F32", "#64748B", "#94A3B8"][rank - 1]
            st.markdown(f"""
            <div style="background:white;border:1px solid #E2E8F0;border-radius:10px;padding:12px 14px;margin-bottom:8px;">
              <div style="display:flex;justify-content:space-between;align-items:center;">
                <span style="font-size:11px;font-weight:700;color:{badge_color};">#{rank}</span>
                <span style="font-size:13px;font-weight:700;color:#16A34A;">{fmt_roas(roas)}</span>
              </div>
              <div style="font-size:12px;color:#334155;margin-top:4px;word-break:break-all;">{name}</div>
              <div style="font-size:11px;color:#94A3B8;margin-top:2px;">광고비 {spend}</div>
            </div>""", unsafe_allow_html=True)

    with col2:
        st.markdown("**🔧 개선 우선순위 TOP 5** <span style='font-size:11px;color:#64748B;'>ROAS 낮음</span>", unsafe_allow_html=True)
        for rank, (_, row) in enumerate(bot3.iterrows(), 1):
            name = str(row["구분_캠페인명"])[:35]
            roas = row["순결제ROAS"]
            spend = fmt_money(row["지표_광고비"])
            gap_html = ""
            if t_roas > 0:
                gap = roas - t_roas
                gc = "#EF4444" if gap < 0 else "#16A34A"
                gap_html = f'<span style="color:{gc};font-size:11px;">목표 대비 {gap*100:+.0f}%p</span>'
            st.markdown(f"""
            <div style="background:white;border:1px solid #FEE2E2;border-radius:10px;padding:12px 14px;margin-bottom:8px;">
              <div style="display:flex;justify-content:space-between;align-items:center;">
                <span style="font-size:11px;font-weight:700;color:#EF4444;">#{rank}</span>
                <span style="font-size:13px;font-weight:700;color:#EF4444;">{fmt_roas(roas)}</span>
              </div>
              <div style="font-size:12px;color:#334155;margin-top:4px;word-break:break-all;">{name}</div>
              <div style="font-size:11px;color:#94A3B8;margin-top:2px;">광고비 {spend} &nbsp; {gap_html}</div>
            </div>""", unsafe_allow_html=True)

    with col3:
        st.markdown("**🔔 알림 & 인사이트**", unsafe_allow_html=True)
        for icon, title, desc in alerts[:5]:
            bg = "#FFF7ED" if icon == "⚠️" else ("#F0FDF4" if icon == "✅" else "#EFF6FF")
            bd = "#FED7AA" if icon == "⚠️" else ("#BBF7D0" if icon == "✅" else "#BFDBFE")
            st.markdown(f"""
            <div style="background:{bg};border:1px solid {bd};border-radius:10px;padding:10px 13px;margin-bottom:8px;">
              <div style="font-size:12px;font-weight:600;color:#1E293B;">{icon} {title}</div>
              <div style="font-size:11px;color:#475569;margin-top:2px;">{desc}</div>
            </div>""", unsafe_allow_html=True)


# ───────────────────────────────────────────────
# KPI 카드
# ───────────────────────────────────────────────
def kpi_cards(df: pd.DataFrame, targets: dict, full_df: pd.DataFrame = None):
    """full_df: 필터 전 전체 데이터 (동요일 전년비 계산용)"""
    tot_raw = df[AGG_COLS].sum()
    tot = calc_kpi(pd.DataFrame([tot_raw])).iloc[0]

    spend = tot["지표_광고비"]
    rev   = tot["지표_순결제거래액"]
    roas  = tot["순결제ROAS"]

    # 동요일 전년비 계산
    def yoy_delta(col):
        if full_df is None or df.empty: return ""
        cur_dates = df["기간_일자"].dropna()
        if cur_dates.empty: return ""
        prev_dates = cur_dates - pd.Timedelta(days=364)
        prev_df = full_df[full_df["기간_일자"].isin(prev_dates)]
        if prev_df.empty: return ""
        p = calc_kpi(pd.DataFrame([prev_df[AGG_COLS].sum()])).iloc[0]
        c_val, p_val = tot.get(col, np.nan), p.get(col, np.nan)
        if pd.isna(c_val) or pd.isna(p_val) or p_val == 0: return ""
        chg = (c_val - p_val) / abs(p_val)
        sym = "+" if chg >= 0 else "△"
        color = "#16A34A" if chg >= 0 else "#DC2626"
        return f'<span style="color:{color};font-size:11px;">{sym}{abs(chg)*100:.1f}% YoY</span>'

    # 목표 KPI 바
    render_goal_bar(targets, spend, rev, roas)

    # 11개 지표 (요청 순서): 광고비, 거래액, ROAS, UV, CR(총), CTR, CPC, 가입률, 가입CPA, 첫구매CPA, 신규거래액
    metrics = [
        ("💰 광고비",       fmt_money(spend),                        "지표_광고비",
         targets.get("spend", 0), spend),
        ("🛒 거래액(순결제)", fmt_money(rev),                         "지표_순결제거래액",
         targets.get("rev", 0), rev),
        ("📈 ROAS(순결제)",  fmt_roas(roas),                          "순결제ROAS",
         None, None),
        ("🧮 순결제비중",     fmt_pct(tot["순결제비중"], 1),            "순결제비중",
         None, None),
        ("🌐 UV",            fmt_num(tot["지표_UV(전체)"]),            "지표_UV(전체)",
         None, None),
        ("🔁 CR(총)",        fmt_pct(tot["CR(총)"], 3),              "CR(총)",
         None, None),
        ("📊 CTR",           fmt_pct(tot["CTR"]),                     "CTR",
         None, None),
        ("🖱️ CPC",          fmt_money(tot["CPC"]),                   "CPC",
         None, None),
        ("👤 가입률",        fmt_pct(tot["가입률"], 3),               "가입률",
         None, None),
        ("💸 가입CPA",       fmt_money(tot["가입CPA"]),               "가입CPA",
         None, None),
        ("🧾 첫구매CPA",     fmt_money(tot["첫구매CPA"]),             "첫구매CPA",
         None, None),
        ("🆕 신규거래액",    fmt_money(tot["지표_당년신규순결제거래액"]), "지표_당년신규순결제거래액",
         None, None),
    ]

    ncol = 6
    cols = st.columns(ncol)
    for i, (label, val, col_key, t_val, c_val) in enumerate(metrics):
        prog = None
        if t_val and t_val > 0 and c_val:
            prog = c_val / t_val
        with cols[i % ncol]:
            yoy = yoy_delta(col_key)
            render_kpi_card(label, val, sub_label="", sub_value=yoy, progress=prog)
        if (i + 1) % ncol == 0 and i < len(metrics) - 1:
            st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)


# ───────────────────────────────────────────────
# 페이지 1: 전체 요약
# ───────────────────────────────────────────────

# 비용출처 탭 정의 (Excel 시트와 동일)
COST_TABS = COST_BUCKETS  # 요약 탭 = 사용자 지정 버킷


def _filter_cost(df, tab_name):
    sources = COST_TABS.get(tab_name)
    if sources:
        return df[df["구분_비용출처"].isin(sources)]
    return df


START_YEAR = 2025  # 표에 노출할 최소 연도


def _sameday_prev_by_ym(df_tab: pd.DataFrame) -> dict:
    """동요일(-364일) 기준, 현재 각 (연도,월)에 대응하는 전년 집계를 반환.
    반환: {(연도, 월): Series} — 키는 '현재' 기간의 (연도,월)."""
    cur = df_tab[["기간_일자", "연도", "월"]].drop_duplicates().copy()
    cur["비교일자"] = cur["기간_일자"] - pd.Timedelta(days=364)
    joined = df_tab.merge(
        cur[["비교일자", "연도", "월"]].rename(columns={"연도": "_cy", "월": "_cm"}),
        left_on="기간_일자", right_on="비교일자", how="inner",
    )
    if joined.empty:
        return {}
    pa = agg(joined, ["_cy", "_cm"])
    return {(int(r["_cy"]), int(r["_cm"])): r for _, r in pa.iterrows()}


def _style_summary(tbl, metric_labels, groups):
    """전년비·목표비 컬럼에 +초록/△빨강 색상 적용."""
    subset = [(g, m) for g in ("전년비", "목표비") if g in groups for m in metric_labels]
    if subset:
        return tbl.style.map(chg_style, subset=subset)
    return tbl.style


def _split_render(rows_new, rows_old, show_fn, key, latest_first=False):
    """한 표에 26년(기본)만 표시하고, 체크박스로 25년 행을 같은 표에 접었다 폈다.
    latest_first=True면 최근 기간이 위로 오도록 역순 정렬."""
    include = False
    if rows_old:
        include = st.checkbox(f"📁 {START_YEAR}년 포함", value=False, key=key)
    rows = (list(rows_old) + list(rows_new)) if include else list(rows_new)
    if latest_first:
        rows = rows[::-1]
    if rows:
        show_fn(rows)
    else:
        st.info("표시할 데이터가 없습니다.")


def _render_monthly_section(df_tab, targets, tab_key, sameday=False, monthly_targets=None,
                            tab_name=None, weekly_targets=None, weekly_rows=None):
    """비용출처별 탭 내부: 실적요약 테이블 (2줄 헤더).
    - 25년(START_YEAR) 행은 전년비/목표비 블락 + 한 표 접이식(체크박스)
    - 당월(부분월)은 MTD 목표(주차별 목표 기준) 사용"""
    if df_tab.empty:
        st.info("해당 비용출처 데이터가 없습니다.")
        return

    cur = agg(df_tab[df_tab["연도"] >= START_YEAR], ["연도", "월"]).sort_values(["연도", "월"])
    if cur.empty:
        st.info("해당 기간 데이터가 없습니다.")
        return

    if sameday:
        prev_map = _sameday_prev_by_ym(df_tab)
    else:
        pa = agg(df_tab, ["연도", "월"])
        prev_map = {(int(r["연도"]), int(r["월"])): r for _, r in pa.iterrows()}

    if tab_name in ("신규고객확대", "인지도제고"):
        metric_labels, groups = ACQ_METRICS, ("실적", "전년비")
    elif tab_name == "거래액확대":
        metric_labels, groups = DEFAULT_METRICS, ("실적", "전년비")
    else:  # TOTAL, TOTAL(서비스비용미반영)
        metric_labels, groups = DEFAULT_METRICS, ("실적", "전년비", "목표", "목표비")

    tab_monthly = (monthly_targets or {}).get(tab_name, {}) if monthly_targets else {}

    # 당월(부분월) 판정
    data_max = df_tab["기간_일자"].max()
    cy, cm = int(data_max.year), int(data_max.month)
    last_day = calendar.monthrange(cy, cm)[1]
    partial = data_max.day < last_day

    rows_new, rows_old = [], []
    for _, r in cur.iterrows():
        yr, mo = int(r["연도"]), int(r["월"])
        label = f"{yr % 100:02d}년 {mo}월"
        prev = prev_map.get((yr, mo)) if sameday else prev_map.get((yr - 1, mo))
        tgt = dict(tab_monthly.get((yr, mo), {}) or {})
        # 당월 MTD 목표 (TOTAL 탭만 weekly 목표 사용)
        if partial and yr == cy and mo == cm and weekly_rows:
            mtd = mtd_target_from_weekly(weekly_rows, yr, mo, data_max)
            if mtd:
                tgt = mtd
        block = (yr <= START_YEAR)  # 25년 전년비/목표비 블락(24년 데이터 혼입 방지)
        (rows_old if yr <= START_YEAR else rows_new).append((label, r, prev, tgt, block))

    def _show(rows):
        tbl = summary_table(rows, metric_labels, groups, period_type="월")
        st.dataframe(_style_summary(tbl, metric_labels, groups),
                     use_container_width=True, hide_index=True)

    _split_render(rows_new, rows_old, _show, key=f"{tab_key}_yr")


def _render_trend_grid(df, targets):
    """지표별 추이 그리드 — 월 단위 일평균만 표시. 비용출처는 선택식."""
    st.markdown("#### 📈 지표별 추이 (월 · 일평균)")
    src = st.radio("비용출처", ["TOTAL", "TOTAL(서비스비용미반영)", "거래액확대", "신규고객확대", "인지도제고"],
                   horizontal=True, key="sum_trend_src")
    st.caption("월별 **일평균**(합계 지표 ÷ 집행일수). 당월은 전년도 **MTD**(동요일 -364일) 창으로 비교합니다.")
    df_tab = _filter_cost(df, src)
    if df_tab.empty:
        st.info("해당 비용출처 데이터가 없습니다.")
        return
    mlist = list(SUMMARY_CHART_METRICS.items())
    for i in range(0, len(mlist), 2):
        ccols = st.columns(2)
        for (lbl, col), cc in zip(mlist[i:i + 2], ccols):
            with cc:
                fig = metric_trend_fig(df_tab, col, "월", f"{lbl} (월 일평균)",
                                       height=300, tickfmt=RATIO_TICKFMT.get(col))
                st.plotly_chart(fig, use_container_width=True, key=f"sum_chart_{col}")


# 전체요약/주차별/일별 공용 필터 스펙
_PAGE_FILTER_SPECS = [
    ("비용출처", "구분_비용출처"), ("채널명", "구분_채널"), ("매체명", "구분_매체명"),
    ("상품명", "구분_상품"), ("부서명", "구분_부서명"), ("디바이스명", "구분_디바이스"),
]


def page_filters(df: pd.DataFrame, key_prefix: str, expanded: bool = False,
                 media_default=None, extra_specs=None) -> pd.DataFrame:
    """접이식 필터 행(비용출처/채널명/매체명/상품명/부서명/디바이스명). 선택값을 df에 적용해 반환.
    media_default: 매체명 기본 선택값(list, 부분일치) — 없으면 전체.
    extra_specs: 추가 (라벨, 컬럼) 목록(예: 캠페인명/하위캠페인명)."""
    specs = _PAGE_FILTER_SPECS + list(extra_specs or [])
    with st.expander("🔎 필터", expanded=expanded):
        out = df
        for i in range(0, len(specs), 6):
            chunk = specs[i:i + 6]
            cols = st.columns(len(chunk))
            for (label, col), c in zip(chunk, cols):
                if col not in df.columns:
                    continue
                opts = sorted(df[col].dropna().unique().tolist())
                default = opts
                if label == "매체명" and media_default:
                    d = [m for m in opts if any(x in str(m) for x in media_default)]
                    if d:
                        default = d
                with c:
                    sel = st.multiselect(label, opts, default=default, key=f"{key_prefix}_{col}")
                if sel and set(sel) != set(opts):
                    out = out[out[col].isin(sel)]
        return out


def summary_filters(df: pd.DataFrame) -> pd.DataFrame:
    return page_filters(df, "sumf", expanded=False)


def _render_detail_tables(df):
    """월별 상세 실적표. TOTAL 기준. (MTD 전년비 표는 25년 전년비 산출 불가로 제거)"""
    df_tot = _filter_cost(df, "TOTAL")
    if df_tot.empty:
        return
    cur = agg(df_tot[df_tot["연도"] >= START_YEAR], ["연도", "월"]).sort_values(["연도", "월"])
    if cur.empty:
        return
    rows_new, rows_old = [], []
    for _, r in cur.iterrows():
        yr, mo = int(r["연도"]), int(r["월"])
        label = f"{yr % 100:02d}년 {mo}월"
        (rows_old if yr <= START_YEAR else rows_new).append((label, r))

    def _actual(rows):
        st.dataframe(detail_table(rows), use_container_width=True, hide_index=True)

    st.markdown("##### 📄 월별 상세 실적")
    _split_render(rows_new, rows_old, _actual, key="sum_detA")


def page_summary(df: pd.DataFrame, targets: dict, report_targets: dict = None, full_df: pd.DataFrame = None):
    st.header("📊 전체 요약")
    if df.empty:
        st.warning("데이터가 없습니다.")
        return

    # ── 지표별 카드 요약: 이 영역에만 날짜 범위 카드 적용
    st.markdown("##### 📇 지표별 카드 요약")
    kpi_df = date_range_filter(df, key_prefix="sum")

    # ── 날짜 카드 하단 필터 (페이지 전체에 적용)
    df = summary_filters(df)
    # 위젯은 위에서 한 번만 렌더되므로, 선택값을 kpi_df에도 동일 적용
    for _, col in [("비용출처", "구분_비용출처"), ("채널명", "구분_채널"), ("매체명", "구분_매체명"),
                   ("상품명", "구분_상품"), ("부서명", "구분_부서명"), ("디바이스명", "구분_디바이스")]:
        sel = st.session_state.get(f"sumf_{col}")
        if sel and col in kpi_df.columns:
            kpi_df = kpi_df[kpi_df[col].isin(sel)]

    kpi_cards(kpi_df, targets, full_df=df)
    st.divider()
    st.caption("아래 표·그래프는 날짜 카드와 무관하게 전체 기간 데이터를 표시합니다.")

    # ── 상단: 비용출처별 탭 (Excel 시트와 동일 구조)
    main_tabs = st.tabs(["📋 TOTAL", "📋 TOTAL(서비스비용미반영)", "📋 거래액확대",
                         "📋 신규고객확대", "📋 인지도제고"])
    tab_names = ["TOTAL", "TOTAL(서비스비용미반영)", "거래액확대", "신규고객확대", "인지도제고"]

    st.caption("ℹ️ 전년비는 **동요일 기준**(전년 동일 요일, -364일)으로 비교합니다.")
    sameday = True

    monthly_targets = (report_targets or {}).get("monthly", {})
    weekly_rows = (report_targets or {}).get("weekly_rows", {})
    for i, tname in enumerate(tab_names):
        with main_tabs[i]:
            st.caption(f"비용출처: {tname}  |  {'동요일 기준' if sameday else '동월 기준'} 전년비")
            df_tab = _filter_cost(df, tname)
            wr = weekly_rows if tname in ("TOTAL", "TOTAL(서비스비용미반영)") else None
            _render_monthly_section(df_tab, targets, tab_key=f"t{i}", sameday=sameday,
                                    monthly_targets=monthly_targets, tab_name=tname,
                                    weekly_rows=wr)

    # ── 실적요약표(탭) → 그래프 → 상세표 순
    st.divider()
    _render_trend_grid(df, targets)
    st.divider()
    _render_detail_tables(df)


# ───────────────────────────────────────────────
# 주차별/일별 공용 기간(period) 프레임워크
# ───────────────────────────────────────────────
PERIOD_COLS = {"월": ["연도", "월"], "주": ["연도", "주차번호"], "일": ["기간_일자"]}
PERIOD_TYPE = {"월": "월", "주": "주차", "일": "일"}


def _row_year(gran, r):
    return pd.Timestamp(r["기간_일자"]).year if gran == "일" else int(r["연도"])


def _period_key(gran, r):
    if gran == "월": return (int(r["연도"]), int(r["월"]))
    if gran == "주": return (int(r["연도"]), int(r["주차번호"]))
    return (pd.Timestamp(r["기간_일자"]).normalize(),)


def _period_label(gran, r):
    if gran == "월": return f"{int(r['연도']) % 100:02d}년 {int(r['월'])}월"
    if gran == "주": return week_of_month_label(int(r["연도"]), int(r["주차번호"]))
    return pd.Timestamp(r["기간_일자"]).strftime("%y년 %m월 %d일")


def _sameday_prev(df, gran):
    """동요일(-364일) 전년 집계를 현재 기간키로 매핑. {기간키: Series}"""
    cols = PERIOD_COLS[gran]
    base_cols = list(dict.fromkeys(["기간_일자"] + cols))  # 중복 제거(일 단위 대응)
    cur = df[base_cols].drop_duplicates().copy()
    cur["비교일자"] = cur["기간_일자"] - pd.Timedelta(days=364)
    ren = {c: f"_c{i}" for i, c in enumerate(cols)}
    joined = df.merge(cur[["비교일자"] + cols].rename(columns=ren),
                      left_on="기간_일자", right_on="비교일자", how="inner")
    if joined.empty:
        return {}
    gb = list(ren.values())
    pa = agg(joined, gb)
    out = {}
    for _, r in pa.iterrows():
        if gran == "일":
            key = (pd.Timestamp(r["_c0"]).normalize(),)
        else:
            key = (int(r["_c0"]), int(r["_c1"]))
        out[key] = r
    return out


def mtd_target_week(weekly, year, iso_week, data_max) -> dict:
    """당주 MTD 목표: 주차 목표 ÷7 × 진행일수(월~data_max)."""
    wt = (weekly or {}).get((int(year), int(iso_week)))
    if not wt:
        return {}
    import datetime as _dt
    try:
        monday = pd.Timestamp(_dt.date.fromisocalendar(int(year), int(iso_week), 1))
    except Exception:
        return dict(wt)
    days = (pd.Timestamp(data_max).normalize() - monday).days + 1
    days = min(max(days, 0), 7)
    f = days / 7.0
    return dict(spend=(wt.get("spend", 0) or 0) * f, rev=(wt.get("rev", 0) or 0) * f,
                roas=wt.get("roas", 0) or 0)


def _period_target(gran, tab_name, tab_monthly, weekly, key, data_max, weekly_rows=None):
    if tab_name not in ("TOTAL", "TOTAL(서비스비용미반영)"):
        return {}
    if gran == "월":
        yr, mo = key
        base = dict(tab_monthly.get((yr, mo), {}) or {})
        last = calendar.monthrange(yr, mo)[1]
        if (yr == data_max.year and mo == data_max.month
                and data_max.day < last and weekly_rows):
            m = mtd_target_from_weekly(weekly_rows, yr, mo, data_max)
            if m:
                return m
        return base
    if gran == "주":
        yr, wk = key
        wt = (weekly or {}).get((yr, wk))
        if not wt:
            return {}
        import datetime as _dt
        try:
            sunday = pd.Timestamp(_dt.date.fromisocalendar(yr, wk, 7))
        except Exception:
            return dict(wt)
        if pd.Timestamp(data_max).normalize() < sunday:
            return mtd_target_week(weekly, yr, wk, data_max)
        return dict(wt)
    return {}


def _render_period_section(df_tab, gran, tab_name, weekly_targets=None, monthly_targets=None,
                           weekly_rows=None, key="", prev_tab=None):
    """기간별 실적요약표(2줄 헤더) — 주/일 공용. 25년 접이식(한 표) + 당기간 MTD 목표.
    주=최신 주차가 위, 일=최근 날짜가 아래. prev_tab=전년비 계산용(기간 미필터) 소스."""
    if df_tab.empty:
        st.info("해당 비용출처 데이터가 없습니다.")
        return
    cols = PERIOD_COLS[gran]
    d_all = agg(df_tab, cols)
    yr_ser = (d_all["기간_일자"].dt.year if gran == "일" else d_all["연도"])
    cur = d_all[yr_ser >= START_YEAR].sort_values(cols)
    if cur.empty:
        st.info("해당 기간 데이터가 없습니다.")
        return
    prev_map = _sameday_prev(prev_tab if prev_tab is not None else df_tab, gran)

    if tab_name in ("신규고객확대", "인지도제고"):
        metric_labels, groups = ACQ_METRICS, ("실적", "전년비")
    elif tab_name == "거래액확대":
        metric_labels, groups = DEFAULT_METRICS, ("실적", "전년비")
    else:
        metric_labels = DEFAULT_METRICS
        groups = ("실적", "전년비", "목표", "목표비") if gran in ("월", "주") else ("실적", "전년비")

    tab_monthly = (monthly_targets or {}).get(tab_name, {}) if monthly_targets else {}
    data_max = df_tab["기간_일자"].max()
    ptype = PERIOD_TYPE[gran]

    rows_new, rows_old = [], []
    for _, r in cur.iterrows():
        pk = _period_key(gran, r)
        label = _period_label(gran, r)
        yr = _row_year(gran, r)
        prev = prev_map.get(pk)
        tgt = _period_target(gran, tab_name, tab_monthly, weekly_targets, pk, data_max,
                             weekly_rows=weekly_rows)
        block = (yr <= START_YEAR)
        (rows_old if yr <= START_YEAR else rows_new).append((label, r, prev, tgt, block))

    def _show(rows):
        tbl = summary_table(rows, metric_labels, groups, period_type=ptype)
        st.dataframe(_style_summary(tbl, metric_labels, groups),
                     use_container_width=True, hide_index=True)

    # 최근 기간이 맨 아래(오름차순)로 표시
    _split_render(rows_new, rows_old, _show, key=f"{key}_yr", latest_first=False)


def _render_period_tabs(df, gran, report_targets, targets, prev_df=None):
    tab_names = ["TOTAL", "TOTAL(서비스비용미반영)", "거래액확대", "신규고객확대", "인지도제고"]
    tabs = st.tabs(["📋 " + t for t in tab_names])
    monthly_targets = (report_targets or {}).get("monthly", {})
    weekly_targets = (report_targets or {}).get("weekly", {})
    weekly_rows = (report_targets or {}).get("weekly_rows", {})
    st.caption("ℹ️ 전년비는 **동요일 기준**(전년 동일 요일, -364일)으로 비교합니다.")
    for i, tname in enumerate(tab_names):
        with tabs[i]:
            st.caption(f"비용출처: {tname}")
            df_tab = _filter_cost(df, tname)
            prev_tab = _filter_cost(prev_df, tname) if prev_df is not None else None
            is_total = tname in ("TOTAL", "TOTAL(서비스비용미반영)")
            _render_period_section(df_tab, gran, tname,
                                   weekly_targets=(weekly_targets if is_total else None),
                                   monthly_targets=monthly_targets,
                                   weekly_rows=(weekly_rows if is_total else None),
                                   key=f"{gran}_{i}", prev_tab=prev_tab)


def _render_period_graph(df, gran, key_prefix):
    """기간별 지표 추이 그리드(전 지표 노출). 주/월은 일평균, 일은 일자값. 당기간은 전년 MTD 비교."""
    avg_note = "" if gran == "일" else " · 일평균"
    st.markdown(f"#### 📈 지표별 추이 ({gran}{avg_note})")
    src = st.radio("비용출처", ["TOTAL", "TOTAL(서비스비용미반영)", "거래액확대", "신규고객확대", "인지도제고"],
                   horizontal=True, key=f"{key_prefix}_gsrc")
    df_tab = _filter_cost(df, src)
    if df_tab.empty:
        st.info("해당 비용출처 데이터가 없습니다.")
        return
    suffix = "" if gran == "일" else f" ({gran} 일평균)"
    mlist = list(SUMMARY_CHART_METRICS.items())
    for i in range(0, len(mlist), 2):
        ccols = st.columns(2)
        for (lbl, col), cc in zip(mlist[i:i + 2], ccols):
            with cc:
                fig = metric_trend_fig(df_tab, col, gran, f"{lbl}{suffix}",
                                       height=300, tickfmt=RATIO_TICKFMT.get(col))
                st.plotly_chart(fig, use_container_width=True, key=f"{key_prefix}_chart_{col}")


def _render_period_detail(df, gran, key_prefix="", prev_df=None):
    """기간별 상세 실적표 + 상세 실적표(전년비). TOTAL 기준, 25년 한 표 접이식."""
    df_tot = _filter_cost(df, "TOTAL")
    if df_tot.empty:
        return
    prev_tot = _filter_cost(prev_df, "TOTAL") if prev_df is not None else df_tot
    cols = PERIOD_COLS[gran]
    d_all = agg(df_tot, cols)
    yr_ser = (d_all["기간_일자"].dt.year if gran == "일" else d_all["연도"])
    cur = d_all[yr_ser >= START_YEAR].sort_values(cols)
    if cur.empty:
        return
    prev_map = _sameday_prev(prev_tot, gran)
    ptype = PERIOD_TYPE[gran]
    rows_new, rows_old = [], []
    for _, r in cur.iterrows():
        pk = _period_key(gran, r)
        label = _period_label(gran, r)
        yr = _row_year(gran, r)
        prev = prev_map.get(pk)
        block = (yr <= START_YEAR)
        (rows_old if yr <= START_YEAR else rows_new).append((label, r, prev, block))

    lf = False  # 최근 기간이 맨 아래(오름차순)

    def _actual(rows):
        st.dataframe(detail_table([(l, s) for l, s, _, _ in rows], period_label=ptype),
                     use_container_width=True, hide_index=True)

    def _yoy(rows):
        t = detail_table_yoy([(l, s, p, b) for l, s, p, b in rows], period_label=ptype)
        st.dataframe(t.style.map(chg_style, subset=DETAIL_COLS),
                     use_container_width=True, hide_index=True)

    st.markdown(f"##### 📄 {gran}별 상세 실적")
    _split_render(rows_new, rows_old, _actual, key=f"{key_prefix}_detA", latest_first=lf)
    st.markdown(f"##### 📄 {gran}별 실적 (전년비)")
    _split_render(rows_new, rows_old, _yoy, key=f"{key_prefix}_detB", latest_first=lf)


def render_period_sheet(df, gran, header, report_targets=None, targets=None,
                        key_prefix=None, month_picker=False, recent_default=None):
    """주차별/일별 시트: 필터 → 실적요약탭 → 그래프 → 상세표 → 상세표(전년비).
    month_picker=True(일별): 기본은 최신 연월만 표시.
    recent_default=N(주차별): 기본은 최근 N주만, '전체 기간 보기'로 전체 표시."""
    st.header(header)
    if df.empty:
        st.warning("데이터가 없습니다.")
        return
    key_prefix = key_prefix or gran
    base = page_filters(df, f"{key_prefix}f", expanded=False)
    df = base
    prev_df = None
    if month_picker and "연월" in base.columns and not base.empty:
        months = sorted(base["연월"].dropna().unique(), reverse=True)
        opts = ["전체 기간"] + months
        sel = st.selectbox("조회 기간", opts, index=(1 if len(opts) > 1 else 0),
                           key=f"{key_prefix}_month")
        if sel != "전체 기간":
            df = base[base["연월"] == sel]
            prev_df = base  # 전년비는 전체 기간에서 동요일 비교
        if df.empty:
            st.info("해당 기간 데이터가 없습니다.")
            return
    elif recent_default and not base.empty:
        full = st.checkbox(f"전체 기간 보기 (기본: 최근 {recent_default}주)",
                           value=False, key=f"{key_prefix}_full")
        if not full:
            ordv = base["연도"].astype(int) * 100 + base["주차번호"].astype(int)
            recent = sorted(ordv.unique())[-recent_default:]
            df = base[ordv.isin(recent)]
            prev_df = base  # 전년비는 전체 기간에서 동요일 비교
            if df.empty:
                st.info("최근 데이터가 없습니다.")
                return
    _render_period_tabs(df, gran, report_targets, targets or {}, prev_df=prev_df)
    st.divider()
    _render_period_graph(df, gran, key_prefix)
    st.divider()
    _render_period_detail(df, gran, key_prefix=key_prefix, prev_df=prev_df)


# ───────────────────────────────────────────────
# 그룹(매체/BPU)별 실적 공용 렌더
# ───────────────────────────────────────────────
def _sameday_prev_window(prev_source, col, cur_dates):
    """동요일(-364일) 창의 전년 집계를 그룹값 기준으로 매핑. {그룹값: Series}
    prev_source: 전년 데이터를 포함한(날짜 미필터) 소스 df."""
    prev = prev_source[prev_source["기간_일자"].isin(
        pd.Series(cur_dates.unique()) - pd.Timedelta(days=364))]
    if prev.empty:
        return {}
    pa = agg(prev, [col])
    return {r[col]: r for _, r in pa.iterrows()}


def render_group_sheet_body(df, group_col, order=None, ptype=None, prev_source=None):
    """그룹(매체/BPU)별 실적요약표 + 상세표 + 상세표(전년비).
    prev_source: 전년비 계산용(날짜 미필터, 동일 필터) 소스. 없으면 df 사용."""
    ptype = ptype or group_col.replace("구분_", "")
    if prev_source is None:
        prev_source = df
    cur = agg(df, [group_col])
    cur = cur[cur["지표_광고비"].fillna(0) > 0]
    if cur.empty:
        st.info("데이터가 없습니다.")
        return
    if order:
        cur["_ord"] = cur[group_col].apply(lambda v: order.index(v) if v in order else 999)
        cur = cur.sort_values(["_ord", "지표_광고비"], ascending=[True, False])
    else:
        cur = cur.sort_values("지표_광고비", ascending=False)
    prev_map = _sameday_prev_window(prev_source, group_col, df["기간_일자"])

    rows = [(str(r[group_col]), r, prev_map.get(r[group_col]), {}, False)
            for _, r in cur.iterrows()]
    st.markdown("##### 📇 실적 요약")
    tbl = summary_table(rows, DEFAULT_METRICS, ("실적", "전년비"), period_type=ptype)
    st.dataframe(_style_summary(tbl, DEFAULT_METRICS, ("실적", "전년비")),
                 use_container_width=True, hide_index=True)
    st.caption("ℹ️ 전년비는 동요일 기준(-364일) 동기간 비교입니다.")

    st.markdown("##### 📄 상세 실적")
    st.dataframe(detail_table([(str(r[group_col]), r) for _, r in cur.iterrows()],
                              period_label=ptype),
                 use_container_width=True, hide_index=True)

    st.markdown("##### 📄 상세 실적 (전년비)")
    dyt = detail_table_yoy([(str(r[group_col]), r, prev_map.get(r[group_col]), False)
                            for _, r in cur.iterrows()], period_label=ptype)
    st.dataframe(dyt.style.map(chg_style, subset=DETAIL_COLS),
                 use_container_width=True, hide_index=True)


# 캠페인/하위캠페인 랭킹 표 지표 순서 (표기명, 원본컬럼, 종류)
CAMP_METRIC_SPEC = [
    ("집행일수", "집행일수", "num"), ("노출수", "지표_노출수", "num"),
    ("클릭수", "지표_클릭수", "num"), ("CTR", "CTR", "pct2"),
    ("CR", "CR(순)", "pct2"), ("객단가", "객단가(순)", "won"),
    ("결제고객수", "지표_순결제고객수", "num"), ("CPM", "CPM", "won"),
    ("CPC", "CPC", "won"), ("CPUV", "CPUV", "won"), ("UV", "지표_UV(전체)", "num"),
    ("광고비", "지표_광고비", "won"), ("순결제매출", "지표_순결제거래액", "won"),
    ("순결제ROAS", "순결제ROAS", "roas"), ("순결제비중(%)", "순결제비중", "pct1"),
    ("총결제매출", "지표_총결제거래액", "won"), ("총매출ROAS", "총결제ROAS", "roas"),
    ("UV/클릭(%)", "UV/클릭", "pct2"), ("CR(총)", "CR(총)", "pct2"),
    ("객단가(총)", "객단가(총)", "won"), ("총결제고객수", "지표_총결제고객수", "num"),
    ("가입률", "가입률", "pct2"), ("가입수", "지표_가입회원", "num"),
    ("가입CPA", "가입CPA", "won"), ("첫구매율", "첫구매율", "pct2"),
    ("첫구매수", "지표_순결제고객수(첫구매)", "num"), ("첫구매CPA", "첫구매CPA", "won"),
    ("첫구매거래액", "지표_순결제거래액(첫구매)", "won"), ("첫구매비중", "첫구매비중", "pct1"),
    ("신규고객수", "지표_당년신규순결제고객수", "num"), ("신규거래액", "지표_당년신규순결제거래액", "won"),
    ("신규비중", "신규비중", "pct1"), ("윈백고객수", "지표_순결제고객수(윈백)", "num"),
    ("윈백거래액", "지표_순결제거래액(윈백)", "won"),
]

# 부서(BPU) 고정 표기 순서
BPU_ORDER = ["e-영업1 BPU", "e-영업2 BPU", "e-영업3 BPU", "e-영업4 BPU",
             "편성 BSU", "e-마케팅 BSU"]


def render_ranking_table(df, group_col, src_name, sort_label, sort_col,
                         ascending=False, top_n=50, id_cols=None, group_cols=None):
    """비용출처(src_name)별 상위 N 랭킹 표. CAMP_METRIC_SPEC 순서로 표기.
    group_cols: 집계 기준(예: [캠페인, 매체명]). 없으면 [group_col]."""
    label = group_col.replace("구분_", "")
    group_cols = group_cols or [group_col]
    st.markdown(f"##### {label}×매체별 실적 상위 {top_n}개 ({src_name}) · {sort_label} 정렬"
                if len(group_cols) > 1 else
                f"##### {label}별 실적 상위 {top_n}개 ({src_name}) · {sort_label} 정렬")
    sub = df[df["구분_비용출처"] == src_name]
    if sub.empty:
        st.info(f"{src_name} 데이터가 없습니다.")
        return
    cdf = agg(sub, group_cols)
    cdf = cdf[cdf["지표_광고비"].fillna(0) > 0]
    if sort_col in cdf.columns:
        cdf = cdf.sort_values(sort_col, ascending=ascending, na_position="last")
    cdf = cdf.head(top_n)
    id_cols = id_cols or [group_col]
    out = {}
    for c in id_cols:
        if c in cdf.columns:
            out[c.replace("구분_", "")] = cdf[c].astype(str).values
    for disp, col, kind in CAMP_METRIC_SPEC:
        if col == "집행일수":
            out[disp] = (cdf["집행일수"].apply(lambda v: _fmt_kind(v, "num")).values
                         if "집행일수" in cdf.columns else "–")
        elif col in cdf.columns:
            out[disp] = cdf[col].apply(lambda v, k=kind: _fmt_kind(v, k)).values
    st.dataframe(pd.DataFrame(out), use_container_width=True, hide_index=True)


# 비용출처별 정렬 규칙: (정렬라벨, 정렬컬럼, 오름차순)
RANK_SORT = {
    "거래액확대": ("순결제ROAS 높은 순", "순결제ROAS", False),
    "신규고객확대": ("가입CPA 낮은 순", "가입CPA", True),
    "인지도제고": ("CPM 낮은 순", "CPM", True),
}


# ───────────────────────────────────────────────
# 페이지 2: 매체별 성과
# ───────────────────────────────────────────────
def page_media(df: pd.DataFrame):
    st.header("📡 매체별 실적")
    if df.empty:
        st.warning("데이터가 없습니다.")
        return

    # 접이식 필터(날짜 미적용, 전년비 소스) → 날짜 카드
    base = page_filters(df, "medf", expanded=False)
    df = date_range_filter(base, key_prefix="med", default_preset="이번달")
    if df.empty:
        st.warning("선택한 날짜 범위에 데이터가 없습니다.")
        return

    # ── 상단: 매체별 광고비·거래액·순결제ROAS 비교 (유지)
    by_media = agg(df, ["구분_매체명"]).sort_values("지표_광고비", ascending=False)
    mc = by_media.dropna(subset=["순결제ROAS"]).head(15)
    figc = make_subplots(specs=[[{"secondary_y": True}]])
    figc.add_trace(go.Bar(x=mc["구분_매체명"], y=mc["지표_광고비"], name="광고비",
                          marker_color="#2563EB", texttemplate="%{y:,.0f}",
                          textposition="outside", textfont=dict(size=9)), secondary_y=False)
    figc.add_trace(go.Bar(x=mc["구분_매체명"], y=mc["지표_순결제거래액"], name="거래액",
                          marker_color="#93C5FD", texttemplate="%{y:,.0f}",
                          textposition="outside", textfont=dict(size=9)), secondary_y=False)
    figc.add_trace(go.Scatter(x=mc["구분_매체명"], y=mc["순결제ROAS"], name="순결제ROAS",
                              mode="lines+markers+text", line=dict(color="#16A34A", width=2),
                              texttemplate="%{y:.0%}", textposition="top center",
                              textfont=dict(size=9)), secondary_y=True)
    figc.update_yaxes(tickformat=".0%", secondary_y=True)
    base_layout(figc, "매체별 광고비·거래액·순결제ROAS", 430)
    figc.update_layout(barmode="group", xaxis_tickangle=-20)
    st.plotly_chart(figc, use_container_width=True, key="media_compare")

    st.divider()
    # ── 주차별/일별과 통일된 매체별 실적요약·상세표 (전년비는 base에서 동요일 비교)
    render_group_sheet_body(df, "구분_매체명", prev_source=base)


# ───────────────────────────────────────────────
# 페이지 3: 캠페인별 성과
# ───────────────────────────────────────────────
def page_campaign(df: pd.DataFrame, targets: dict = None):
    if targets is None:
        targets = {}
    st.header("🎯 캠페인별 실적")
    if df.empty:
        st.warning("데이터가 없습니다.")
        return

    # 친구추가 캠페인은 전체 제외
    if "구분_캠페인" in df.columns:
        df = df[~df["구분_캠페인"].astype(str).str.contains("친구추가", na=False)]

    # 날짜 카드 (지난주 포함) + 접이식 필터 (매체명 기본: 네이버·카카오)
    df = date_range_filter(df, key_prefix="camp", default_preset="이번달")
    if df.empty:
        st.warning("선택한 날짜 범위에 데이터가 없습니다.")
        return
    extra = [("캠페인명", "구분_캠페인"), ("하위캠페인명", "구분_하위캠페인")]
    df = page_filters(df, "campf", expanded=False,
                      media_default=["네이버", "카카오"], extra_specs=extra)
    if df.empty:
        st.info("필터 결과 데이터가 없습니다.")
        return

    tab_rank, tab_quad = st.tabs(["📋 캠페인 랭킹", "🔲 효율 사분면"])

    with tab_rank:
        split_media = st.checkbox("매체명·상품명 분리 보기", value=False, key="camp_split",
                                  help="켜면 캠페인을 매체명·상품명 단위로 나눠서 표시합니다.")
        extra_cols = ["구분_매체명", "구분_상품"] if split_media else []
        extra_ids = ["구분_매체명", "구분_상품"] if split_media else []

        # 캠페인별 실적 상위 50개 (비용출처별 정렬 규칙)
        for src in ["거래액확대", "신규고객확대", "인지도제고"]:
            slabel, scol, asc = RANK_SORT[src]
            render_ranking_table(df, "구분_캠페인", src, slabel, scol, ascending=asc,
                                 group_cols=["구분_캠페인"] + extra_cols,
                                 id_cols=["구분_캠페인"] + extra_ids)
            st.divider()

        # 하위캠페인별 실적 상위 50개
        st.markdown("### 하위캠페인별 실적")
        for src in ["거래액확대", "신규고객확대", "인지도제고"]:
            slabel, scol, asc = RANK_SORT[src]
            render_ranking_table(df, "구분_하위캠페인", src, slabel, scol, ascending=asc,
                                 group_cols=["구분_하위캠페인"] + extra_cols,
                                 id_cols=["구분_하위캠페인"] + extra_ids)
            st.divider()

    # ── 효율 사분면
    with tab_quad:
        st.markdown("""
        **광고비 × ROAS 사분면** — 캠페인을 4가지 유형으로 분류합니다.
        - 🌟 **스타** (고ROAS + 고광고비) / 💰 **캐시카우** (고ROAS + 저광고비)
        - ❓ **물음표** (저ROAS + 고광고비) / 🐕 **개** (저ROAS + 저광고비)
        """)
        quad_src = df[df["구분_매체명"].astype(str).str.contains("카카오|네이버", na=False)]
        st.caption("포함 매체: **카카오 · 네이버** 계열만 · 광고비 하위 5% 소액 캠페인 제외(ROAS 왜곡 방지)")
        quad_df = agg(quad_src, ["구분_캠페인", "구분_매체명"]).dropna(subset=["순결제ROAS"])
        quad_df = quad_df[quad_df["지표_광고비"] > 0]
        # 소액·극단 ROAS 아웃라이어 제거(원이 일렬로 서는 현상 방지)
        if len(quad_df) >= 5:
            spend_floor = quad_df["지표_광고비"].quantile(0.05)
            quad_df = quad_df[quad_df["지표_광고비"] >= spend_floor]
        if quad_df.empty:
            st.info("카카오·네이버 매체 데이터가 없습니다.")
        else:
            med_spend = quad_df["지표_광고비"].median()
            med_roas = quad_df["순결제ROAS"].median()

            def quadrant(row):
                hs = row["지표_광고비"] >= med_spend
                hr = row["순결제ROAS"] >= med_roas
                if hr and hs: return "🌟 스타"
                if hr and not hs: return "💰 캐시카우"
                if not hr and hs: return "❓ 물음표"
                return "🐕 개"

            quad_df["사분면"] = quad_df.apply(quadrant, axis=1)
            quad_colors = {"🌟 스타": "#16A34A", "💰 캐시카우": "#2563EB",
                           "❓ 물음표": "#EA580C", "🐕 개": "#94A3B8"}
            fig_q = px.scatter(quad_df, x="지표_광고비", y="순결제ROAS",
                               color="사분면", color_discrete_map=quad_colors,
                               size="지표_클릭수", hover_name="구분_캠페인", size_max=40)
            fig_q.add_vline(x=med_spend, line_dash="dash", line_color="#CBD5E1")
            fig_q.add_hline(y=med_roas, line_dash="dash", line_color="#CBD5E1")
            base_layout(fig_q, "캠페인 효율 사분면 (버블=클릭수)", 520)
            # y축을 합리적 범위로 고정(극단 ROAS로 원이 일렬로 서는 현상 방지)
            y_hi = float(quad_df["순결제ROAS"].quantile(0.95))
            fig_q.update_yaxes(tickformat=".0%", range=[0, max(y_hi * 1.15, med_roas * 1.5, 0.01)])
            st.plotly_chart(fig_q, use_container_width=True, key="camp_quad")


def _render_bpu_charts(df):
    """부서(BPU)별 광고비·거래액·순결제ROAS — 고정 순서 막대 그래프."""
    by_dept = agg(df, ["구분_부서명"])
    by_dept = by_dept[by_dept["지표_광고비"].fillna(0) > 0].copy()
    if by_dept.empty:
        return
    by_dept["_ord"] = by_dept["구분_부서명"].apply(
        lambda v: BPU_ORDER.index(v) if v in BPU_ORDER else 999)
    by_dept = by_dept.sort_values("_ord")
    order_present = [b for b in BPU_ORDER if b in set(by_dept["구분_부서명"])]
    dept_charts = [
        ("BPU별 광고비", "지표_광고비", "#2563EB", ",.0f"),
        ("BPU별 거래액(순결제)", "지표_순결제거래액", "#0EA5E9", ",.0f"),
        ("BPU별 순결제ROAS", "순결제ROAS", "#16A34A", ".0%"),
    ]
    gcols = st.columns(3)
    for (dlabel, dcol, dcolor, dfmt), gc in zip(dept_charts, gcols):
        with gc:
            sub = by_dept.dropna(subset=[dcol])
            fig = px.bar(sub, x="구분_부서명", y=dcol, color_discrete_sequence=[dcolor])
            fig.update_xaxes(categoryorder="array", categoryarray=order_present)
            if dfmt == ".0%":
                fig.update_yaxes(tickformat=".0%")
            base_layout(fig, dlabel, 350)
            fig.update_layout(showlegend=False, xaxis_tickangle=-20)
            label_traces(fig, dfmt)
            st.plotly_chart(fig, use_container_width=True, key=f"bpu_dept_{dcol}")


def page_bpu(df: pd.DataFrame, targets: dict = None, report_targets: dict = None):
    st.header("🏢 BPU별 실적")
    if df.empty:
        st.warning("데이터가 없습니다.")
        return
    base = page_filters(df, "bpuf", expanded=False)
    df = date_range_filter(base, key_prefix="bpu", default_preset="이번달")
    if df.empty:
        st.warning("선택한 날짜 범위에 데이터가 없습니다.")
        return
    _render_bpu_charts(df)
    st.divider()
    render_group_sheet_body(df, "구분_부서명", order=BPU_ORDER, ptype="BPU", prev_source=base)


# 페이지: 주차별 실적 / 일별 실적 (공용 프레임워크)
# ───────────────────────────────────────────────
def page_weekly(df: pd.DataFrame, targets: dict = None, report_targets: dict = None):
    render_period_sheet(df, "주", "📅 주차별 실적", report_targets=report_targets,
                        targets=targets or {}, key_prefix="wk", recent_default=12)


def page_daily(df: pd.DataFrame, targets: dict = None, report_targets: dict = None):
    render_period_sheet(df, "일", "📆 일별 실적", report_targets=report_targets,
                        targets=targets or {}, key_prefix="dy", month_picker=True)


# ───────────────────────────────────────────────
# 페이지 7: 소재(AF코드) 상세
# ───────────────────────────────────────────────
def page_creative(df: pd.DataFrame):
    st.header("🎨 소재(AF코드) 상세")
    if df.empty:
        st.warning("필터 조건에 해당하는 데이터가 없습니다.")
        return

    # ── 날짜 범위 카드 (이 페이지 전용, 기본값: 올해)
    df = date_range_filter(df, key_prefix="cr", default_preset="이번달")
    if df.empty:
        st.warning("선택한 날짜 범위에 데이터가 없습니다.")
        return

    c1, c2, c3 = st.columns(3)
    with c1:
        camp_search = st.text_input("캠페인 검색", key="cr_camp")
    with c2:
        af_search = st.text_input("AF코드 / 소재명 검색", key="cr_af")
    with c3:
        top_n = st.selectbox("상위 N개", ["ALL", 30, 50, 100, 200], index=2)

    gb = ["구분_AF코드", "구분_AF코드이름", "구분_캠페인",
          "구분_하위캠페인", "구분_매체명", "구분_비용출처", "카테고리"]
    if "구분_상품" in df.columns:
        gb.append("구분_상품")
    # 기획전번호·상세내역 등 빈칸으로 나오던 식별 컬럼을 실제 데이터에서 찾아 포함
    CR_ID_CANDIDATES = {
        "기획전번호": ["구분_기획전 번호", "구분_기획전번호", "기획전번호", "구분_기획전"],
        "상세내역": ["구분_키워드(소재)", "구분_상세내역", "상세내역", "구분_소재상세"],
        "상품명": ["구분_상품명", "구분_상품"],
    }
    cr_id_resolved = {}
    for label, cands in CR_ID_CANDIDATES.items():
        found = next((c for c in cands if c in df.columns), None)
        if found:
            cr_id_resolved[label] = found
            if found not in gb:
                gb.append(found)
    cr_full = agg(df, gb)
    if camp_search:
        cr_full = cr_full[cr_full["구분_캠페인"].str.contains(camp_search, na=False)]
    if af_search:
        mask = (cr_full["구분_AF코드"].str.contains(af_search, na=False) |
                cr_full["구분_AF코드이름"].str.contains(af_search, na=False))
        cr_full = cr_full[mask]

    # ── 매체별 CTR / 순결제ROAS 상위 10 소재
    avail_media = sorted(cr_full["구분_매체명"].dropna().unique())
    # 디폴트 선택 매체: 네이버·카카오 계열 (단, 카카오페이지 제외)
    default_media = [m for m in avail_media
                     if ("네이버" in str(m) or "카카오" in str(m)) and "카카오페이지" not in str(m)] \
        or avail_media[:5]
    sel_media_cr = st.multiselect("소재 그래프 매체 선택", avail_media,
                                  default=default_media, key="cr_media_sel")

    def media_top10(metric, tickfmt, color, header, impr_filter=False):
        st.subheader(header)
        media_list = sel_media_cr or default_media
        for r in range(0, len(media_list), 2):
            mcols = st.columns(2)
            for media, mc in zip(media_list[r:r + 2], mcols):
                with mc:
                    sub = cr_full[cr_full["구분_매체명"] == media]
                    if impr_filter:
                        sub = sub[sub["지표_노출수"] > 1000]
                    sub = sub.dropna(subset=[metric])
                    sub = sub[sub["지표_광고비"] > 0] if metric == "순결제ROAS" else sub
                    sub = sub.nlargest(10, metric)
                    if sub.empty:
                        st.caption(f"🔹 {media}: 데이터 없음")
                        continue
                    fig = px.bar(sub, x=metric, y="구분_AF코드이름", orientation="h",
                                 color_discrete_sequence=[color])
                    fig.update_xaxes(tickformat=tickfmt)
                    base_layout(fig, media, 320)
                    fig.update_layout(showlegend=False)
                    label_traces(fig, tickfmt)
                    st.plotly_chart(fig, use_container_width=True,
                                    key=f"cr_{metric}_{media}")

    media_top10("CTR", ".2%", "#3B82F6", "📊 CTR 상위 10 소재 (매체별, 노출 1,000+)", impr_filter=True)
    media_top10("순결제ROAS", ".0%", "#10B981", "📈 순결제ROAS 상위 10 소재 (매체별)")

    # ── 소재 테이블 (정렬 + 상위 N). 기본 정렬: 순결제ROAS
    sort_opts = ["순결제ROAS", "지표_광고비", "CTR", "CPM", "CR(순)",
                 "객단가(순)", "첫구매CPA", "가입CPA"]
    sort_col = st.selectbox("정렬 기준", sort_opts, index=0)
    asc = sort_col in ("첫구매CPA", "가입CPA")
    cr_df = cr_full.sort_values(sort_col, ascending=asc, na_position="last")
    if top_n != "ALL":
        cr_df = cr_df.head(int(top_n))

    n_label = "전체" if top_n == "ALL" else f"상위 {top_n}개"
    st.subheader(f"소재 테이블 ({n_label}) · {sort_col} {'오름차순' if asc else '내림차순'}")
    if cr_df.empty:
        st.info("표시할 소재 데이터가 없습니다.")
        return
    # 정렬 기준에 따른 소재 표를 화면에 직접 표시 (다운로드 버튼 제거)
    exp = {}
    for label, col in CREATIVE_EXPORT_SPEC:
        c = cr_id_resolved.get(label, col)  # 기획전번호/상세내역 등 실제 컬럼 해석
        exp[label] = cr_df[c].values if (c and c in cr_df.columns) else ""
    export_tbl = pd.DataFrame(exp)
    st.dataframe(export_tbl, use_container_width=True, hide_index=True)


def build_html_report(df: pd.DataFrame) -> str:
    """현재 필터 데이터를 단독 실행 가능한 HTML 문서로 변환."""
    period = ""
    if not df.empty and "기간_일자" in df.columns:
        period = f"{df['기간_일자'].min().date()} ~ {df['기간_일자'].max().date()}"
    table_html = df.to_html(index=False, border=0, na_rep="", justify="center")
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<title>DA 광고 실적 데이터</title>
<style>
  body {{ font-family: 'Pretendard','Apple SD Gothic Neo',sans-serif; margin:24px; color:#0F172A; }}
  h1 {{ font-size:20px; }}
  .meta {{ color:#64748B; font-size:13px; margin-bottom:16px; }}
  table {{ border-collapse:collapse; font-size:12px; width:100%; }}
  th, td {{ border:1px solid #E2E8F0; padding:4px 8px; white-space:nowrap; }}
  th {{ background:#F1F5F9; position:sticky; top:0; }}
  tr:nth-child(even) td {{ background:#F8FAFC; }}
  .wrap {{ overflow-x:auto; }}
</style></head><body>
<h1>📊 DA 광고 실적 데이터</h1>
<div class="meta">기간: {period} · 총 {len(df):,}행 · 생성 {pd.Timestamp.now():%Y-%m-%d %H:%M}</div>
<div class="wrap">{table_html}</div>
</body></html>"""


# ───────────────────────────────────────────────
# 메인
# ───────────────────────────────────────────────
def main():
    st.title("📊 DA 광고 실적 대시보드")

    # 사이드바 순서: ① 페이지  ② 내보내기  ③ 파일 업로드 (필터는 제거됨)
    page_box   = st.sidebar.container()
    export_box = st.sidebar.container()
    upload_box = st.sidebar.container()

    # ── ③ 파일 업로드 (맨 아래)
    with upload_box:
        st.divider()
        st.subheader("📁 파일 업로드")
        uploaded = st.file_uploader(
            "데이터 파일", type=["csv", "xlsx", "xlsb"],
            help="DA 광고 로데이터 파일을 업로드하세요. (CSV / Excel)",
            key="data_uploader",
        )
        report_file = st.file_uploader(
            "목표 파일 (보고서 엑셀)", type=["xlsx"],
            help="월별/주차별 목표가 있는 보고서 엑셀을 업로드하면 자동으로 목표비를 계산합니다.",
            key="report_uploader",
        )

    if uploaded is None:
        st.info("👈 사이드바 하단 '파일 업로드'에서 데이터 파일을 업로드해주세요.")
        st.markdown("""
        **지원 파일 형식**
        - CSV (UTF-8, UTF-8-BOM, CP949, EUC-KR)
        - Excel (.xlsx, .xlsb)

        **필수 컬럼**: `기간_일자`, `구분_*`, `지표_*`
        """)
        return

    with st.spinner("데이터 로딩 중..."):
        df = load_data(uploaded.read(), uploaded.name)

    report_targets = {}
    if report_file is not None:
        with st.spinner("목표 파일 로딩 중..."):
            report_targets = load_targets_from_report(report_file.read())

    # 업로드 박스 하단에 로드 상태 표시
    with upload_box:
        st.caption(
            f"총 {len(df):,}행 | {df['기간_일자'].min().date()} ~ {df['기간_일자'].max().date()}"
        )
        if report_file is not None:
            n_m = sum(len(v) for v in report_targets.get("monthly", {}).values())
            n_w = len(report_targets.get("weekly", {}))
            if n_m or n_w:
                st.success(f"✅ 목표 로드: 월별 {n_m}건 · 주차별 {n_w}건")
            else:
                st.warning("⚠️ 목표 파일에서 목표를 찾지 못했습니다. 시트/열 구조를 확인해주세요.")

    # 필터는 사이드바에서 제거됨 — 전체요약 페이지 내부 필터로 대체.
    pre_date_filtered = df  # 전체 데이터 (날짜 범위 필터 전)

    targets = get_targets()

    # ── ① 페이지 선택 (맨 위)
    with page_box:
        st.subheader("📄 페이지")
        page = st.radio("페이지", [
            "📊 전체 요약", "📅 주차별 실적", "📆 일별 실적", "📡 매체별 실적",
            "🎯 캠페인별 실적", "🎨 소재 상세", "🏢 BPU별 실적",
        ], label_visibility="collapsed")

    # 현재 페이지의 날짜 카드 범위를 내보내기에 반영
    DATE_PREFIX = {"📊 전체 요약": "sum", "🎯 캠페인별 실적": "camp", "🎨 소재 상세": "cr"}
    prefix = DATE_PREFIX.get(page)
    export_df = pre_date_filtered
    rng_note = "전체 기간(날짜 카드 없음)"
    if prefix and f"{prefix}_start" in st.session_state:
        s = pd.Timestamp(st.session_state[f"{prefix}_start"])
        e = pd.Timestamp(st.session_state[f"{prefix}_end"])
        export_df = pre_date_filtered[(pre_date_filtered["기간_일자"] >= s)
                                      & (pre_date_filtered["기간_일자"] <= e)]
        rng_note = f"{s.date()} ~ {e.date()}"

    # ── ③ 내보내기 (사이드바 필터 + 현재 페이지 날짜 카드 반영)
    # 매 rerun마다 대용량 파일을 만들지 않도록, 체크했을 때만 생성한다.
    with export_box:
        st.divider()
        st.subheader("📤 내보내기")
        st.caption(f"기간: {rng_note} · {len(export_df):,}행")
        if st.checkbox("내보내기 파일 준비", key="export_prepare"):
            try:
                # CSV (Excel/클로드 분석용) — 한글 깨짐 방지 utf-8-sig
                csv_bytes = export_df.to_csv(index=False).encode("utf-8-sig")
                st.download_button(
                    "📄 CSV 출력 (분석용)", data=csv_bytes,
                    file_name="da_filtered.csv", mime="text/csv",
                    use_container_width=True, key="export_csv",
                )
                json_bytes = export_df.to_json(
                    orient="records", force_ascii=False, date_format="iso", indent=2
                ).encode("utf-8")
                st.download_button(
                    "🧾 JSON 출력", data=json_bytes,
                    file_name="da_filtered.json", mime="application/json",
                    use_container_width=True, key="export_json",
                )
                HTML_MAX = 5000
                html_doc = build_html_report(export_df.head(HTML_MAX))
                if len(export_df) > HTML_MAX:
                    st.caption(f"※ HTML은 상위 {HTML_MAX:,}행만 포함(용량 보호). JSON은 전체 포함.")
                st.download_button(
                    "🌐 HTML 출력", data=html_doc.encode("utf-8"),
                    file_name="da_filtered.html", mime="text/html",
                    use_container_width=True, key="export_html",
                )
            except Exception as e:
                st.warning(f"내보내기 생성 중 오류: {e}")

    if page == "📊 전체 요약":
        page_summary(pre_date_filtered, targets, report_targets)
    elif page == "📅 주차별 실적":
        page_weekly(pre_date_filtered, targets, report_targets)
    elif page == "📆 일별 실적":
        page_daily(pre_date_filtered, targets, report_targets)
    elif page == "🎯 캠페인별 실적":
        page_campaign(pre_date_filtered, targets)
    elif page == "🏢 BPU별 실적":
        page_bpu(pre_date_filtered, targets, report_targets)
    elif page == "📡 매체별 실적":
        page_media(pre_date_filtered)
    elif page == "🎨 소재 상세":
        page_creative(pre_date_filtered)


if st.runtime.exists():
    main()
