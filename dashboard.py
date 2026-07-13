import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import io

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
TOTAL_SOURCES = ["거래액확대", "신규고객확대", "인지도제고", "E영업/광고주직접정산"]

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
    df["기간_일자"] = pd.to_datetime(df["기간_일자"], errors="coerce")
    df = df.dropna(subset=["기간_일자"])

    num_cols = [
        "지표_노출수", "지표_입찰가", "지표_클릭수", "지표_광고비",
        "지표_UV(전체)", "지표_UV(회원)", "지표_PV(회원)", "지표_가입회원",
        "지표_총결제고객수(첫구매)", "지표_순결제고객수", "지표_총결제거래액(첫구매)",
        "지표_총결제거래액", "지표_당년신규순결제고객수", "지표_당년신규순결제거래액",
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

    if df["기간_주"].isna().all():
        df["기간_주"] = (
            df["기간_일자"].dt.strftime("%Y")
            + "W"
            + df["주차번호"].astype(str).str.zfill(2)
        )

    return df


@st.cache_data(show_spinner=False)
def load_targets_from_report(file_bytes: bytes) -> dict:
    """보고서 엑셀에서 월별/주차별 목표를 파싱.
    Returns: {
      "monthly": {tab_name: {(year, month): {spend, rev, roas}}},
      "weekly":  {(year, iso_week): {spend, rev, roas}},
    }
    """
    SHEET_MAP = {
        "월별_TOTAL(서비스비용제외)": "TOTAL(서비스비용제외)",
        "월별_TOTAL": "TOTAL",
        "월별_거래액": "거래액확대",
        "월별_신규확대": "신규확대/인지도",
    }
    result = {"monthly": {}, "weekly": {}}
    try:
        xls = pd.ExcelFile(io.BytesIO(file_bytes), engine="openpyxl")

        # 월별 목표 파싱
        for sheet, tab in SHEET_MAP.items():
            if sheet not in xls.sheet_names:
                continue
            df = pd.read_excel(xls, sheet_name=sheet, header=None)
            tab_targets = {}
            for _, row in df.iterrows():
                label = str(row.iloc[1]) if pd.notna(row.iloc[1]) else ""
                if "년" not in label or "주차" in label:
                    continue
                try:
                    year = int(label[:4])
                    month = int(label[5:7])
                except Exception:
                    continue
                spend = row.iloc[41] if pd.notna(row.iloc[41]) else 0
                rev   = row.iloc[42] if pd.notna(row.iloc[42]) else 0
                roas  = row.iloc[43] if pd.notna(row.iloc[43]) else 0
                tab_targets[(year, month)] = dict(
                    spend=float(spend or 0),
                    rev=float(rev or 0),
                    roas=float(roas or 0),
                )
            result["monthly"][tab] = tab_targets

        # 주차별 목표 파싱
        if "주차별" in xls.sheet_names:
            df = pd.read_excel(xls, sheet_name="주차별", header=None)
            for _, row in df.iterrows():
                label = str(row.iloc[1]) if pd.notna(row.iloc[1]) else ""
                if "주차" not in label or len(label) < 8:
                    continue
                try:
                    date = pd.to_datetime(label[:8], format="%Y%m%d")
                    year = date.isocalendar().year
                    week = date.isocalendar().week
                except Exception:
                    continue
                spend = row.iloc[38] if pd.notna(row.iloc[38]) else 0
                rev   = row.iloc[39] if pd.notna(row.iloc[39]) else 0
                roas  = row.iloc[40] if pd.notna(row.iloc[40]) else 0
                if float(spend or 0) > 0 or float(rev or 0) > 0:
                    result["weekly"][(int(year), int(week))] = dict(
                        spend=float(spend or 0),
                        rev=float(rev or 0),
                        roas=float(roas or 0),
                    )
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
    d["순결제ROAS"]  = safe_div(d["지표_총결제거래액"],                   d["지표_광고비"])
    d["총결제ROAS"]  = safe_div(d["지표_순결제거래액(첫구매)"],            d["지표_광고비"])
    d["가입CPA"]    = safe_div(d["지표_광고비"],                        d["지표_가입회원"])
    d["첫구매CPA"]  = safe_div(d["지표_광고비"],                        d["지표_순결제고객수(첫구매)"])
    d["가입률"]     = safe_div(d["지표_가입회원"],                       d["지표_UV(전체)"])
    d["첫구매율"]   = safe_div(d["지표_순결제고객수(첫구매)"],             d["지표_UV(전체)"])
    d["CPM"]        = safe_div(d["지표_광고비"] * 1000,                 d["지표_노출수"])
    d["CPUV"]       = safe_div(d["지표_광고비"],                        d["지표_UV(전체)"])
    d["UV/클릭"]    = safe_div(d["지표_UV(전체)"],                      d["지표_클릭수"])
    d["CR(순)"]     = safe_div(d["지표_순결제고객수"],                   d["지표_UV(전체)"])
    d["CR(총)"]     = safe_div(d["지표_총결제고객수"],                   d["지표_UV(전체)"])
    d["객단가(순)"] = safe_div(d["지표_총결제거래액"],                    d["지표_순결제고객수"])
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

def fmt_num(v):
    if pd.isna(v): return "–"
    return f"{int(v):,}"

def fmt_pct(v, decimals=2):
    if pd.isna(v): return "–"
    return f"{v*100:.{decimals}f}%"

def fmt_roas(v):
    if pd.isna(v): return "–"
    return f"{v*100:.0f}%"

def week_of_month_label(year: int, week: int) -> str:
    """ISO (연도, 주차) → '26년7월1주차' 형식."""
    import datetime as _dt
    try:
        d = _dt.date.fromisocalendar(int(year), int(week), 4)  # 목요일 기준
    except Exception:
        return f"W{int(week):02d}"
    wom = (d.day - 1) // 7 + 1
    return f"{str(d.year)[2:]}년{d.month}월{wom}주차"


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
    "지표_총결제거래액(첫구매)", "지표_총결제거래액",
    "지표_당년신규순결제고객수", "지표_당년신규순결제거래액",
    "지표_총결제고객수", "지표_순결제고객수(첫구매)", "지표_순결제거래액(첫구매)",
    "지표_순결제고객수(윈백)", "지표_순결제거래액(윈백)",
    "지표_총결제고객수(윈백)", "지표_총결제거래액(윈백)", "지표_영상조회수",
]

def agg(df: pd.DataFrame, by: list) -> pd.DataFrame:
    cols = [c for c in AGG_COLS if c in df.columns]
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
                    height: int = 380, ma_window: int = 0) -> go.Figure:
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
            name=f"{yr}년", mode="lines+markers",
            line=dict(color=color, width=2),
            marker=dict(size=6),
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


def metric_trend_fig(df: pd.DataFrame, val_col: str, gran: str, title: str,
                     height: int = 380) -> go.Figure:
    """월/주/일 단위 지표 추이 (선형). 월·주는 연도별 YoY 오버레이, 일은 시계열."""
    if gran == "월":
        d = agg(df, ["연도", "월"]).sort_values(["연도", "월"])
        return yoy_overlay_fig(d, "월", val_col, title,
                               ticklabels=MONTH_LABELS, height=height)
    if gran == "주":
        d = agg(df, ["연도", "주차번호"]).sort_values(["연도", "주차번호"])
        cur_year = int(df["연도"].max())
        wk_labels = {w: week_of_month_label(cur_year, w) for w in range(1, 54)}
        return yoy_overlay_fig(d, "주차번호", val_col, title,
                               ticklabels=wk_labels, height=height)
    # 일 단위: 실제 날짜 시계열 (연도별 색상)
    d = agg(df, ["기간_일자"]).sort_values("기간_일자").dropna(subset=[val_col])
    d["연도"] = d["기간_일자"].dt.year
    fig = go.Figure()
    for i, yr in enumerate(sorted(d["연도"].unique())):
        sub = d[d["연도"] == yr]
        fig.add_trace(go.Scatter(
            x=sub["기간_일자"], y=sub[val_col], name=f"{yr}년",
            mode="lines", line=dict(color=YEAR_COLORS[i % len(YEAR_COLORS)], width=1.8),
        ))
    base_layout(fig, title, height)
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


def summary_table(cur_agg: pd.DataFrame, prev_agg: pd.DataFrame,
                  group_col: str, group_label_fn,
                  targets: dict = None, period_type: str = "월",
                  targets_per_period: dict = None, cur_year: int = None) -> pd.DataFrame:
    """실적요약 테이블: 실적 + 전년비 + 목표 + 목표비 한 눈에.
    targets_per_period: {(year, period_val): {spend, rev, roas}} 형태로 월별/주차별 목표 개별 지정.
    """
    if targets is None:
        targets = {}
    rows = []
    for _, r in cur_agg.iterrows():
        gval = r[group_col]
        label = group_label_fn(gval)
        spend = r.get("지표_광고비", np.nan)
        rev   = r.get("지표_총결제거래액", np.nan)
        roas  = r.get("순결제ROAS", np.nan)

        if prev_agg is not None and not prev_agg.empty:
            prow = prev_agg[prev_agg[group_col] == gval]
            p_spend = prow["지표_광고비"].values[0] if not prow.empty else np.nan
            p_rev   = prow["지표_총결제거래액"].values[0] if not prow.empty else np.nan
            p_roas  = prow["순결제ROAS"].values[0] if not prow.empty else np.nan
        else:
            p_spend = p_rev = p_roas = np.nan

        # 목표: targets_per_period[(year, period_val)] 우선, 없으면 global targets
        if targets_per_period and cur_year:
            pt = targets_per_period.get((cur_year, int(gval)), {})
        else:
            pt = {}
        t_spend = pt.get("spend", targets.get("spend", 0)) or 0
        t_rev   = pt.get("rev",   targets.get("rev",   0)) or 0
        t_roas  = pt.get("roas",  targets.get("roas",  0)) or 0

        def _chg(c, p):
            if pd.isna(c) or pd.isna(p) or p == 0: return np.nan
            return (c - p) / abs(p)

        def _chg_fmt(c, p):
            v = _chg(c, p)
            if pd.isna(v): return "–"
            return f"{'▲' if v >= 0 else '▼'} {abs(v)*100:.1f}%"

        def _rate_fmt(num, den):
            if den and den > 0 and not pd.isna(num): return f"{num/den*100:.1f}%"
            return "–"

        def _fmt_num(v, decimals=1):
            if pd.isna(v): return "–"
            return f"{round(v, decimals):,.{decimals}f}"

        rows.append({
            period_type: label,
            "광고비(백만)": _fmt_num(spend / 1e6) if not pd.isna(spend) else "–",
            "거래액(백만)": _fmt_num(rev / 1e6) if not pd.isna(rev) else "–",
            "ROAS": _fmt_num(roas, 2) if not pd.isna(roas) else "–",
            "전년비_광고비": _chg_fmt(spend, p_spend),
            "전년비_거래액": _chg_fmt(rev, p_rev),
            "전년비_ROAS": _chg_fmt(roas, p_roas),
            "목표_광고비(백만)": _fmt_num(t_spend / 1e6) if t_spend > 0 else "–",
            "목표_거래액(백만)": _fmt_num(t_rev / 1e6) if t_rev > 0 else "–",
            "목표_ROAS": _fmt_num(t_roas, 2) if t_roas > 0 else "–",
            "목표비_광고비": _rate_fmt(spend, t_spend),
            "목표비_거래액": _rate_fmt(rev, t_rev),
            "목표비_ROAS": _rate_fmt(roas, t_roas),
        })
    result = pd.DataFrame(rows)

    return result


# ───────────────────────────────────────────────
# ───────────────────────────────────────────────
# 날짜 범위 필터 (페이지 상단)
# ───────────────────────────────────────────────
def date_range_filter(df: pd.DataFrame, key_prefix: str = "dr") -> pd.DataFrame:
    """페이지 상단 날짜 범위 선택기. 프리셋 버튼 + 직접 입력.
    key_prefix로 페이지별 독립 상태를 유지한다."""
    k_start, k_end, k_preset = f"{key_prefix}_start", f"{key_prefix}_end", f"{key_prefix}_preset"

    today = pd.Timestamp.today().normalize()
    data_max = df["기간_일자"].max()
    data_min = df["기간_일자"].min()

    week_start = today - pd.Timedelta(days=today.dayofweek)
    presets = {
        "전일":   (today - pd.Timedelta(days=1), today - pd.Timedelta(days=1)),
        "이번주": (week_start, today),
        "이번달": (today.replace(day=1), today),
        "올해":   (today.replace(month=1, day=1), today),
    }

    # 초기 상태 — 기본값: 이번주
    if k_start not in st.session_state:
        ps_def = max(week_start, data_min)
        st.session_state[k_start]  = ps_def.date()
        st.session_state[k_end]    = min(today, data_max).date()
        st.session_state[k_preset] = "이번주"

    cols = st.columns([1, 1, 1, 1, 0.2, 2, 0.4, 2])
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

    with cols[5]:
        new_start = st.date_input("시작일", value=clamped_start,
                                  min_value=d_min, max_value=d_max,
                                  key=f"{key_prefix}_start_input", label_visibility="collapsed")
    with cols[6]:
        st.markdown("<div style='padding-top:8px;text-align:center;color:#64748B'>~</div>",
                    unsafe_allow_html=True)
    with cols[7]:
        new_end = st.date_input("종료일", value=clamped_end,
                                min_value=d_min, max_value=d_max,
                                key=f"{key_prefix}_end_input", label_visibility="collapsed")

    if new_start != st.session_state[k_start] or new_end != st.session_state[k_end]:
        st.session_state[k_start]  = new_start
        st.session_state[k_end]    = new_end
        st.session_state[k_preset] = "직접 지정"

    start = pd.Timestamp(st.session_state[k_start])
    end   = pd.Timestamp(st.session_state[k_end])
    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
    return df[(df["기간_일자"] >= start) & (df["기간_일자"] <= end)]


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
                         ["TOTAL", "TOTAL(서비스비용제외)", "개별 선택"], index=0)
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
    if f["cost_mode"] == "TOTAL":
        d = d[d["구분_비용출처"].isin(TOTAL_SOURCES)]
    elif f["cost_mode"] == "개별 선택" and f["sel_sources"]:
        d = d[d["구분_비용출처"].isin(f["sel_sources"])]
    return d


# ───────────────────────────────────────────────
# Plotly 공통 레이아웃
# ───────────────────────────────────────────────
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
    """잘 되는 캠페인 TOP3 / 개선 우선순위 TOP3 / 알림"""
    camp_col = next((c for c in ["구분_캠페인명", "구분_하위캠페인", "구분_매체명"] if c in df.columns), None)
    if camp_col is None:
        return
    by_camp = agg(df, [camp_col]).dropna(subset=["순결제ROAS"])
    by_camp = by_camp[by_camp["지표_광고비"] > 0]
    by_camp = by_camp[~by_camp[camp_col].astype(str).str.contains("친구추가", na=False)]
    by_camp = by_camp.rename(columns={camp_col: "구분_캠페인명"})

    t_roas = targets.get("roas", 0)

    top3 = by_camp.nlargest(3, "순결제ROAS")
    bot3 = by_camp.nsmallest(3, "순결제ROAS")

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
        st.markdown("**🏆 잘 되는 캠페인 TOP 3** <span style='font-size:11px;color:#64748B;'>ROAS 기준</span>", unsafe_allow_html=True)
        for rank, (_, row) in enumerate(top3.iterrows(), 1):
            name = str(row["구분_캠페인명"])[:35]
            roas = row["순결제ROAS"]
            spend = fmt_money(row["지표_광고비"])
            badge_color = ["#F59E0B", "#94A3B8", "#CD7F32"][rank - 1]
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
        st.markdown("**🔧 개선 우선순위 TOP 3** <span style='font-size:11px;color:#64748B;'>ROAS 낮음</span>", unsafe_allow_html=True)
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
    rev   = tot["지표_총결제거래액"]
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
        arrow = "▲" if chg >= 0 else "▼"
        color = "#16A34A" if chg >= 0 else "#EF4444"
        return f'<span style="color:{color};font-size:11px;">{arrow} {abs(chg)*100:.1f}% YoY</span>'

    # 목표 KPI 바
    render_goal_bar(targets, spend, rev, roas)

    # 10개 지표: 광고비, 거래액, ROAS, UV, CTR / 가입률, 가입CPA, CR(순), 신규거래액, CPC
    metrics = [
        ("💰 광고비",       fmt_money(spend),                        "지표_광고비",
         targets.get("spend", 0), spend),
        ("🛒 거래액(순결제)", fmt_money(rev),                         "지표_총결제거래액",
         targets.get("rev", 0), rev),
        ("📈 ROAS(순결제)",  fmt_roas(roas),                          "순결제ROAS",
         None, None),
        ("🌐 UV",            fmt_num(tot["지표_UV(전체)"]),            "지표_UV(전체)",
         None, None),
        ("📊 CTR",           fmt_pct(tot["CTR"]),                     "CTR",
         None, None),
        ("👤 가입률",        fmt_pct(tot["가입률"], 3),               "가입률",
         None, None),
        ("💸 가입CPA",       fmt_money(tot["가입CPA"]),               "가입CPA",
         None, None),
        ("🔄 CR(순)",        fmt_pct(tot["CR(순)"], 3),              "CR(순)",
         None, None),
        ("🆕 신규거래액",    fmt_money(tot["지표_당년신규순결제거래액"]), "지표_당년신규순결제거래액",
         None, None),
        ("🖱️ CPC",          fmt_money(tot["CPC"]),                   "CPC",
         None, None),
    ]

    ncol = 5
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
COST_TABS = {
    "TOTAL(서비스비용제외)": ["거래액확대", "신규고객확대", "인지도제고"],
    "TOTAL": None,  # 전체 (필터 그대로)
    "거래액확대": ["거래액확대"],
    "신규확대/인지도": ["신규고객확대", "인지도제고"],
}


def _filter_cost(df, tab_name):
    sources = COST_TABS.get(tab_name)
    if tab_name == "TOTAL":
        return df
    if sources:
        return df[df["구분_비용출처"].isin(sources)]
    return df


def _render_monthly_section(df_tab, targets, tab_key, sameday=False, monthly_targets=None, tab_name=None):
    """비용출처별 탭 내부: 실적요약 테이블 + 차트"""
    if df_tab.empty:
        st.info("해당 비용출처 데이터가 없습니다.")
        return

    cur_year = int(df_tab["연도"].max())
    monthly_cur = agg(df_tab[df_tab["연도"] == cur_year], ["월"]).sort_values("월")

    if sameday:
        monthly_prev = yoy_sameday_prev(df_tab, cur_year, "월")
    else:
        monthly_prev = agg(df_tab[df_tab["연도"] == cur_year - 1], ["월"])

    # 탭별 월별 목표 매핑
    tab_monthly = (monthly_targets or {}).get(tab_name, {}) if monthly_targets else {}
    tbl = summary_table(monthly_cur, monthly_prev, "월",
                        lambda m: f"{int(m)}월", targets, period_type="월",
                        targets_per_period=tab_monthly or None, cur_year=cur_year)

    # 목표/목표비 컬럼은 항상 표시 (미입력 시 –)

    st.dataframe(
        tbl.style.map(
            lambda v: "color: #16A34A" if isinstance(v, str) and v.startswith("▲")
            else ("color: #DC2626" if isinstance(v, str) and v.startswith("▼") else ""),
            subset=[c for c in tbl.columns if "전년비" in c],
        ),
        use_container_width=True, hide_index=True,
    )

    # 지표 추이 차트 (선형, 월/주/일 단위 선택, 요약 카드 지표 모두 지원)
    chart_metrics = {
        "ROAS(순결제)": "순결제ROAS", "광고비": "지표_광고비",
        "거래액(순결제)": "지표_총결제거래액", "UV": "지표_UV(전체)", "CTR": "CTR",
        "가입률": "가입률", "가입CPA": "가입CPA", "CR(순)": "CR(순)",
        "신규거래액": "지표_당년신규순결제거래액", "CPC": "CPC",
    }
    cc1, cc2 = st.columns([3, 1.4])
    with cc1:
        sel_m = st.selectbox("지표 선택", list(chart_metrics.keys()), key=f"sum_m_{tab_key}")
    with cc2:
        gran = st.radio("단위", ["월", "주", "일"], horizontal=True, key=f"sum_g_{tab_key}")
    fig = metric_trend_fig(df_tab, chart_metrics[sel_m], gran,
                           f"{sel_m} 추이 ({gran} 단위, 연도별 YoY)", height=400)
    if sel_m == "광고비" and gran == "월" and targets.get("spend", 0) > 0:
        fig.add_hline(y=targets["spend"], line_dash="dot", line_color="#EF4444",
                      annotation_text="목표")
    st.plotly_chart(fig, use_container_width=True)


def page_summary(df: pd.DataFrame, targets: dict, report_targets: dict = None, full_df: pd.DataFrame = None):
    st.header("📊 전체 요약")
    if df.empty:
        st.warning("필터 조건에 해당하는 데이터가 없습니다.")
        return

    # ── 지표별 카드 요약: 이 영역에만 날짜 범위 카드 적용
    st.markdown("##### 📇 지표별 카드 요약")
    kpi_df = date_range_filter(df, key_prefix="sum")
    kpi_cards(kpi_df, targets, full_df=df)
    st.divider()
    st.caption("아래 표·그래프는 날짜 카드와 무관하게 전체 기간(사이드바 필터 적용) 데이터를 표시합니다.")

    # ── 상단: 비용출처별 탭 (Excel 시트와 동일 구조)
    main_tabs = st.tabs(["📋 TOTAL(서비스비용제외)", "📋 TOTAL", "📋 거래액확대", "📋 신규확대/인지도",
                          "💰 예산 페이싱", "🧩 거래액 구성"])
    tab_names = ["TOTAL(서비스비용제외)", "TOTAL", "거래액확대", "신규확대/인지도"]

    sameday = st.checkbox("동요일 기준 전년비", value=True, key="sameday_toggle")

    monthly_targets = (report_targets or {}).get("monthly", {})
    for i, tname in enumerate(tab_names):
        with main_tabs[i]:
            st.caption(f"비용출처: {tname}  |  {'동요일 기준' if sameday else '동월 기준'} 전년비")
            df_tab = _filter_cost(df, tname)
            _render_monthly_section(df_tab, targets, tab_key=f"t{i}", sameday=sameday,
                                    monthly_targets=monthly_targets, tab_name=tname)

    # ── 예산 페이싱
    with main_tabs[4]:
        import calendar
        st.markdown("**당월 일별 광고비 소진 추이 & 월말 예측**")
        avail_months = sorted(df["연월"].unique(), reverse=True)
        sel_ym = st.selectbox("조회 연월", avail_months, key="pacing_ym")
        daily = df[df["연월"] == sel_ym].groupby("기간_일자")["지표_광고비"].sum().reset_index()
        daily = daily.sort_values("기간_일자")
        daily["누적광고비"] = daily["지표_광고비"].cumsum()

        year_p, month_p = int(sel_ym[:4]), int(sel_ym[5:7])
        total_days = calendar.monthrange(year_p, month_p)[1]
        last_day = (daily["기간_일자"].max() - pd.Timestamp(year_p, month_p, 1)).days + 1 if not daily.empty else 0

        fig_p = go.Figure()
        fig_p.add_trace(go.Bar(
            x=daily["기간_일자"], y=daily["지표_광고비"],
            name="일별 광고비", marker_color="#93C5FD", opacity=0.6,
        ))
        fig_p.add_trace(go.Scatter(
            x=daily["기간_일자"], y=daily["누적광고비"],
            name="누적 광고비", mode="lines+markers",
            line=dict(color="#2563EB", width=2.5), yaxis="y2",
        ))
        if last_day > 0 and targets.get("spend", 0) > 0:
            cur_cum = daily["누적광고비"].iloc[-1]
            proj_end = (cur_cum / last_day) * total_days
            fig_p.add_trace(go.Scatter(
                x=[daily["기간_일자"].max(), pd.Timestamp(year_p, month_p, total_days)],
                y=[cur_cum, proj_end],
                name=f"예측 ({fmt_money(proj_end)})",
                mode="lines", line=dict(color="#F59E0B", width=2, dash="dash"), yaxis="y2",
            ))
            fig_p.add_hline(y=targets["spend"], line_dash="dot", line_color="#EF4444",
                            annotation_text=f"목표 {fmt_money(targets['spend'])}", yref="y2")
        fig_p.update_layout(yaxis2=dict(overlaying="y", side="right", title="누적 광고비"))
        base_layout(fig_p, f"{sel_ym} 예산 페이싱", 420)
        st.plotly_chart(fig_p, use_container_width=True)
        if not daily.empty:
            cur_cum = daily["누적광고비"].iloc[-1]
            daily_avg = cur_cum / last_day if last_day > 0 else 0
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("누적 광고비", fmt_money(cur_cum))
            c2.metric("집행일", f"{last_day}일 / {total_days}일")
            c3.metric("일평균 광고비", fmt_money(daily_avg))
            if targets.get("spend", 0) > 0:
                proj = daily_avg * total_days
                c4.metric("월말 예측", fmt_money(proj),
                          delta=f"목표 대비 {fmt_delta(proj, targets['spend'])}")

    # ── 거래액 구성
    with main_tabs[5]:
        col1, col2 = st.columns(2)
        tot = df[AGG_COLS].sum()
        with col1:
            first   = tot["지표_순결제거래액(첫구매)"]
            winback = tot["지표_순결제거래액(윈백)"]
            new_rev = tot["지표_당년신규순결제거래액"]
            other   = max(0, tot["지표_총결제거래액"] - first - winback)
            bkd = pd.DataFrame({
                "구분": ["첫구매", "윈백", "신규(당년)", "기타"],
                "금액": [first, winback, new_rev, other],
            })
            bkd = bkd[bkd["금액"] > 0]
            fig4 = px.pie(bkd, names="구분", values="금액",
                          color_discrete_sequence=["#3B82F6","#10B981","#F59E0B","#94A3B8"])
            fig4.update_traces(textposition="inside", textinfo="percent+label")
            base_layout(fig4, "거래액 유형별 구성 (전체)", 400)
            st.plotly_chart(fig4, use_container_width=True)
        with col2:
            monthly_comp = agg(df, ["연도", "월"]).sort_values(["연도", "월"])
            monthly_comp["연월라벨"] = (monthly_comp["연도"].astype(str) + "-"
                                       + monthly_comp["월"].astype(str).str.zfill(2))
            fig5 = go.Figure()
            for seg, color in [
                ("지표_순결제거래액(첫구매)", "#3B82F6"),
                ("지표_순결제거래액(윈백)", "#10B981"),
                ("지표_당년신규순결제거래액", "#F59E0B"),
            ]:
                if seg in monthly_comp.columns:
                    fig5.add_trace(go.Bar(
                        x=monthly_comp["연월라벨"], y=monthly_comp[seg],
                        name=seg.replace("지표_", "").replace("순결제거래액", ""),
                        marker_color=color,
                    ))
            fig5.update_layout(barmode="stack")
            base_layout(fig5, "월별 거래액 구성 추이", 400)
            st.plotly_chart(fig5, use_container_width=True)


# ───────────────────────────────────────────────
# 페이지 2: 매체별 성과
# ───────────────────────────────────────────────
def page_media(df: pd.DataFrame):
    st.header("📡 매체별 성과")
    if df.empty:
        st.warning("필터 조건에 해당하는 데이터가 없습니다.")
        return

    metric_options = {
        "순결제ROAS": "순결제ROAS", "광고비": "지표_광고비", "거래액": "지표_총결제거래액",
        "노출수": "지표_노출수", "클릭수": "지표_클릭수",
        "UV": "지표_UV(전체)", "CTR": "CTR", "CPC": "CPC", "CPM": "CPM", "CPUV": "CPUV",
        "총결제ROAS": "총결제ROAS", "CR(순)": "CR(순)", "CR(총)": "CR(총)",
        "객단가(순)": "객단가(순)", "첫구매CPA": "첫구매CPA", "가입CPA": "가입CPA",
        "가입률": "가입률", "첫구매율": "첫구매율",
    }

    by_media = agg(df, ["구분_매체명"]).sort_values("지표_광고비", ascending=False)

    # 매체별 광고비 · 순결제ROAS · 거래액 (고정 3종 그래프)
    fixed = [("광고비", "지표_광고비", False), ("순결제ROAS", "순결제ROAS", True),
             ("거래액", "지표_총결제거래액", False)]
    fcols = st.columns(3)
    for (flabel, fcol, is_ratio), fc in zip(fixed, fcols):
        with fc:
            top = by_media.dropna(subset=[fcol]).sort_values(fcol, ascending=True).tail(12)
            fig = px.bar(top, x=fcol, y="구분_매체명", orientation="h",
                         color="구분_매체명", color_discrete_map=MEDIA_COLORS)
            if is_ratio:
                fig.update_xaxes(tickformat=".0%")
            base_layout(fig, f"매체별 {flabel}", 380)
            fig.update_layout(showlegend=False)
            st.plotly_chart(fig, use_container_width=True)

    st.divider()
    sel_label = st.selectbox("비교 지표 (아래 상세)", list(metric_options.keys()))
    sel_col   = metric_options[sel_label]

    col1, col2 = st.columns(2)
    with col1:
        top = by_media.dropna(subset=[sel_col]).sort_values(sel_col, ascending=True).tail(12)
        fig = px.bar(top, x=sel_col, y="구분_매체명", orientation="h",
                     color="구분_매체명", color_discrete_map=MEDIA_COLORS)
        if sel_col in ("순결제ROAS", "총결제ROAS", "CTR", "CR(순)", "CR(총)", "가입률", "첫구매율"):
            fig.update_xaxes(tickformat=".0%")
        base_layout(fig, f"매체별 {sel_label}", 420)
        fig.update_layout(showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        valid = by_media[by_media["지표_광고비"] > 0].dropna(subset=["순결제ROAS"])
        fig2 = px.scatter(valid, x="지표_광고비", y="순결제ROAS", size="지표_클릭수",
                          color="구분_매체명", color_discrete_map=MEDIA_COLORS,
                          hover_name="구분_매체명", text="구분_매체명")
        fig2.update_traces(textposition="top center")
        fig2.update_yaxes(tickformat=".0%")
        base_layout(fig2, "광고비 vs 순결제ROAS (버블=클릭수)", 420)
        st.plotly_chart(fig2, use_container_width=True)

    # 매체별 요약 테이블
    st.subheader("매체별 지표 요약")
    disp_cols = [
        "구분_매체명", "집행일수", "지표_광고비", "지표_노출수", "지표_클릭수",
        "지표_UV(전체)", "CTR", "CPC", "CPM", "CPUV", "UV/클릭",
        "순결제ROAS", "총결제ROAS", "CR(순)", "CR(총)",
        "객단가(순)", "객단가(총)", "순결제비중",
        "첫구매CPA", "가입CPA", "가입률", "첫구매율",
        "신규비중", "윈백비중", "첫구매비중",
    ]
    tbl = by_media[[c for c in disp_cols if c in by_media.columns]].copy()
    fmt_map = {
        "지표_광고비": fmt_money, "지표_노출수": fmt_num, "지표_클릭수": fmt_num,
        "지표_UV(전체)": fmt_num, "CTR": fmt_pct, "CPC": fmt_money, "CPM": fmt_money,
        "CPUV": fmt_money, "UV/클릭": lambda v: fmt_pct(v),
        "순결제ROAS": fmt_roas, "총결제ROAS": fmt_roas,
        "CR(순)": lambda v: fmt_pct(v, 3), "CR(총)": lambda v: fmt_pct(v, 3),
        "객단가(순)": fmt_money, "객단가(총)": fmt_money,
        "순결제비중": fmt_pct, "첫구매CPA": fmt_money, "가입CPA": fmt_money,
        "가입률": lambda v: fmt_pct(v, 3), "첫구매율": lambda v: fmt_pct(v, 3),
        "신규비중": fmt_pct, "윈백비중": fmt_pct, "첫구매비중": fmt_pct,
    }
    tbl_fmt = tbl.copy()
    for c, fn in fmt_map.items():
        if c in tbl_fmt.columns:
            tbl_fmt[c] = tbl_fmt[c].apply(fn)
    st.dataframe(tbl_fmt, use_container_width=True, hide_index=True)

    # 매체별 월별 추이 (동기간 YoY 오버레이)
    st.subheader("매체별 월별 추이 (동기간 YoY)")
    sel_media_list = st.multiselect("매체 선택", sorted(df["구분_매체명"].unique()),
                                    default=sorted(df["구분_매체명"].unique())[:5])
    by_mm = agg(df[df["구분_매체명"].isin(sel_media_list)],
                ["구분_매체명", "연도", "월"]).sort_values(["연도", "월"])

    fig3 = go.Figure()
    years = sorted(by_mm["연도"].unique())
    for med in sel_media_list:
        for i, yr in enumerate(years):
            sub = by_mm[(by_mm["구분_매체명"] == med) & (by_mm["연도"] == yr)]
            fig3.add_trace(go.Scatter(
                x=sub["월"], y=sub[sel_col],
                name=f"{med} {yr}년",
                mode="lines+markers",
                line=dict(dash="solid" if i == 0 else "dash"),
            ))
    fig3.update_xaxes(tickvals=list(range(1, 13)),
                      ticktext=[f"{m}월" for m in range(1, 13)])
    base_layout(fig3, f"매체별 월별 {sel_label} (동기간 YoY)", 420)
    st.plotly_chart(fig3, use_container_width=True)


# ───────────────────────────────────────────────
# 페이지 3: 캠페인별 성과
# ───────────────────────────────────────────────
def page_campaign(df: pd.DataFrame, targets: dict = None):
    if targets is None:
        targets = {}
    st.header("🎯 캠페인별 성과")
    if df.empty:
        st.warning("필터 조건에 해당하는 데이터가 없습니다.")
        return

    # ── 날짜 범위 카드 (이 페이지 전용)
    df = date_range_filter(df, key_prefix="camp")
    if df.empty:
        st.warning("선택한 날짜 범위에 데이터가 없습니다.")
        return

    # ── 잘 되는 캠페인 / 개선 우선순위 / 알림 (전체 요약에서 이동)
    render_top3_section(df, targets)
    st.divider()

    tab_rank, tab_quad = st.tabs(["📋 캠페인 랭킹", "🔲 효율 사분면"])

    with tab_rank:
        # 그래프: 부서별 · 카테고리(상품)별 순결제ROAS
        g1, g2 = st.columns(2)
        with g1:
            by_dept = agg(df, ["구분_부서명"])
            by_dept = by_dept[(by_dept["지표_광고비"] > 0) & by_dept["순결제ROAS"].notna()]
            by_dept = by_dept.sort_values("순결제ROAS")
            fig = px.bar(by_dept, x="순결제ROAS", y="구분_부서명", orientation="h",
                         color_discrete_sequence=["#2563EB"])
            fig.update_xaxes(tickformat=".0%")
            base_layout(fig, "부서별 순결제ROAS", 350)
            fig.update_layout(showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
        with g2:
            by_cat = agg(df, ["카테고리"])
            by_cat = by_cat[(by_cat["지표_광고비"] > 0) & by_cat["순결제ROAS"].notna()]
            by_cat = by_cat.sort_values("순결제ROAS").tail(15)
            fig2 = px.bar(by_cat, x="순결제ROAS", y="카테고리", orientation="h",
                          color_discrete_sequence=["#16A34A"])
            fig2.update_xaxes(tickformat=".0%")
            base_layout(fig2, "카테고리(상품)별 순결제ROAS", 350)
            fig2.update_layout(showlegend=False)
            st.plotly_chart(fig2, use_container_width=True)

        # 필터: 매체 · 상품(카테고리) — 다중 선택
        f1, f2 = st.columns(2)
        with f1:
            sel_media = st.multiselect("매체 필터", sorted(df["구분_매체명"].dropna().unique()),
                                       key="camp_media")
        with f2:
            sel_cat = st.multiselect("상품(카테고리) 필터", sorted(df["카테고리"].dropna().unique()),
                                     key="camp_cat")
        dff = df
        if sel_media:
            dff = dff[dff["구분_매체명"].isin(sel_media)]
        if sel_cat:
            dff = dff[dff["카테고리"].isin(sel_cat)]

        fmt_map = {
            "지표_광고비": fmt_money, "지표_총결제거래액": fmt_money,
            "지표_노출수": fmt_num, "지표_클릭수": fmt_num,
            "CTR": fmt_pct, "CPC": fmt_money, "CPM": fmt_money, "CPUV": fmt_money,
            "UV/클릭": fmt_pct, "순결제ROAS": fmt_roas, "총결제ROAS": fmt_roas,
            "CR(순)": lambda v: fmt_pct(v, 3), "객단가(순)": fmt_money,
            "첫구매CPA": fmt_money, "가입CPA": fmt_money,
            "가입률": lambda v: fmt_pct(v, 3), "첫구매율": lambda v: fmt_pct(v, 3),
            "신규비중": fmt_pct, "윈백비중": fmt_pct,
        }
        disp = [
            "구분_캠페인", "구분_매체명", "카테고리",
            "집행일수", "지표_광고비", "지표_총결제거래액", "지표_노출수", "지표_클릭수",
            "CTR", "CPC", "CPM", "CPUV", "UV/클릭",
            "순결제ROAS", "총결제ROAS", "CR(순)", "객단가(순)",
            "첫구매CPA", "가입CPA", "가입률", "첫구매율",
            "신규비중", "윈백비중",
        ]

        def render_camp_table(src_name, sort_label, sort_col):
            st.markdown(f"##### 캠페인별 실적 상위 50개 ({src_name}) · {sort_label} 정렬")
            sub = dff[dff["구분_비용출처"] == src_name]
            if sub.empty:
                st.info(f"{src_name} 데이터가 없습니다.")
                return
            cdf = agg(sub, ["구분_캠페인"])
            cdf = cdf.sort_values(sort_col, ascending=False, na_position="last").head(50)
            tbl = cdf[[c for c in disp if c in cdf.columns]].copy()
            for c, fn in fmt_map.items():
                if c in tbl.columns:
                    tbl[c] = tbl[c].apply(fn)
            tbl.columns = [c.replace("구분_", "").replace("지표_", "") for c in tbl.columns]
            st.dataframe(tbl, use_container_width=True, hide_index=True)

        render_camp_table("거래액확대", "순결제ROAS", "순결제ROAS")
        st.divider()
        render_camp_table("신규고객확대", "가입률", "가입률")
        st.divider()
        render_camp_table("인지도제고", "가입률", "가입률")

    # ── 효율 사분면 분석 (BCG Matrix 스타일)
    with tab_quad:
        st.markdown("""
        **광고비 × ROAS 사분면** — 캠페인을 4가지 유형으로 분류합니다.
        - 🌟 **스타** (고ROAS + 고광고비): 핵심 성과 캠페인, 예산 유지/확대
        - 💰 **캐시카우** (고ROAS + 저광고비): 효율 좋음, 예산 증액 검토
        - ❓ **물음표** (저ROAS + 고광고비): 비효율 대형 캠페인, 구조 개선 필요
        - 🐕 **개** (저ROAS + 저광고비): 효율·규모 모두 낮음, 재검토
        """)

        quad_df = agg(df, ["구분_캠페인", "구분_매체명"]).dropna(subset=["순결제ROAS"])
        quad_df = quad_df[quad_df["지표_광고비"] > 0]

        if quad_df.empty:
            st.info("사분면 분석에 필요한 데이터가 없습니다.")
        else:
            med_spend = quad_df["지표_광고비"].median()
            med_roas  = quad_df["순결제ROAS"].median()

            def quadrant(row):
                hi_spend = row["지표_광고비"] >= med_spend
                hi_roas  = row["순결제ROAS"] >= med_roas
                if hi_roas and hi_spend:   return "🌟 스타"
                if hi_roas and not hi_spend: return "💰 캐시카우"
                if not hi_roas and hi_spend: return "❓ 물음표"
                return "🐕 개"

            quad_df["사분면"] = quad_df.apply(quadrant, axis=1)
            quad_colors = {"🌟 스타": "#16A34A", "💰 캐시카우": "#2563EB",
                           "❓ 물음표": "#EA580C", "🐕 개": "#94A3B8"}

            fig_q = px.scatter(
                quad_df, x="지표_광고비", y="순결제ROAS",
                color="사분면", color_discrete_map=quad_colors,
                size="지표_클릭수", hover_name="구분_캠페인",
                hover_data={"구분_매체명": True, "지표_광고비": True, "순결제ROAS": ":.2f"},
                size_max=40,
            )
            # 사분면 구분선
            fig_q.add_vline(x=med_spend, line_dash="dash", line_color="#CBD5E1")
            fig_q.add_hline(y=med_roas,  line_dash="dash", line_color="#CBD5E1")
            fig_q.add_annotation(x=med_spend * 0.02, y=med_roas * 1.02,
                                  text=f"중앙값 광고비 {fmt_money(med_spend)}<br>중앙값 ROAS {med_roas:.2f}x",
                                  showarrow=False, font=dict(size=10, color="#64748B"))
            base_layout(fig_q, "캠페인 효율 사분면 (버블=클릭수)", 520)
            st.plotly_chart(fig_q, use_container_width=True)

            # 사분면별 요약
            quad_summary = quad_df.groupby("사분면").agg(
                캠페인수=("구분_캠페인", "count"),
                총광고비=("지표_광고비", "sum"),
                평균ROAS=("순결제ROAS", "mean"),
            ).reset_index().sort_values("총광고비", ascending=False)
            quad_summary["총광고비"] = quad_summary["총광고비"].apply(fmt_money)
            quad_summary["평균ROAS"] = quad_summary["평균ROAS"].apply(fmt_roas)
            st.dataframe(quad_summary, use_container_width=True, hide_index=True)


# ───────────────────────────────────────────────
# 페이지 4: 퍼널 & 전환 분석
# ───────────────────────────────────────────────
def page_funnel(df: pd.DataFrame):
    st.header("🔍 퍼널 & 전환 분석")
    if df.empty:
        st.warning("필터 조건에 해당하는 데이터가 없습니다.")
        return

    tot = df[AGG_COLS].sum()
    c1, c2 = st.columns(2)

    with c1:
        fig = go.Figure(go.Funnel(
            y=["노출", "클릭", "UV(전체)", "가입회원", "순결제고객", "첫구매 결제"],
            x=[tot["지표_노출수"], tot["지표_클릭수"], tot["지표_UV(전체)"],
               tot["지표_가입회원"], tot["지표_순결제고객수"], tot["지표_순결제고객수(첫구매)"]],
            textinfo="value+percent initial",
            marker_color=["#1E40AF","#2563EB","#3B82F6","#60A5FA","#93C5FD","#BAE6FD"],
        ))
        base_layout(fig, "광고 퍼널 (전체 합산)", 430)
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        bkd = pd.DataFrame({
            "구분": ["첫구매", "윈백", "신규(당년)", "기타"],
            "금액": [
                tot["지표_순결제거래액(첫구매)"], tot["지표_순결제거래액(윈백)"],
                tot["지표_당년신규순결제거래액"],
                max(0, tot["지표_총결제거래액"]
                    - tot["지표_순결제거래액(첫구매)"]
                    - tot["지표_순결제거래액(윈백)"]),
            ],
        })
        bkd = bkd[bkd["금액"] > 0]
        fig2 = px.pie(bkd, names="구분", values="금액",
                      color_discrete_sequence=["#3B82F6","#10B981","#F59E0B","#94A3B8"])
        fig2.update_traces(textposition="inside", textinfo="percent+label")
        base_layout(fig2, "거래액 유형별 구성", 430)
        st.plotly_chart(fig2, use_container_width=True)

    # 카테고리별 성과
    st.subheader("카테고리별 성과")
    by_cat = agg(df, ["카테고리"]).sort_values("지표_광고비", ascending=False).head(15)
    c3, c4 = st.columns(2)
    with c3:
        fig3 = px.bar(by_cat.sort_values("지표_광고비"), x="지표_광고비", y="카테고리",
                      orientation="h")
        base_layout(fig3, "카테고리별 광고비", 420)
        st.plotly_chart(fig3, use_container_width=True)
    with c4:
        cat_r = by_cat[by_cat["순결제ROAS"].notna() & (by_cat["지표_광고비"] > 0)]
        fig4 = px.bar(cat_r.sort_values("순결제ROAS"), x="순결제ROAS", y="카테고리",
                      orientation="h", color_discrete_sequence=["#10B981"])
        base_layout(fig4, "카테고리별 순결제ROAS", 420)
        st.plotly_chart(fig4, use_container_width=True)

    # 월별 CR·객단가 추이 (동기간 YoY)
    st.subheader("월별 전환 지표 추이 (동기간 YoY)")
    monthly = agg(df, ["연도", "월"]).sort_values(["연도", "월"])
    tab1, tab2 = st.tabs(["CR & 가입률", "객단가"])
    with tab1:
        fig5 = go.Figure()
        years = sorted(monthly["연도"].unique())
        for i, yr in enumerate(years):
            sub = monthly[monthly["연도"] == yr]
            color = YEAR_COLORS[i % len(YEAR_COLORS)]
            fig5.add_trace(go.Scatter(x=sub["월"], y=sub["CR(순)"],
                                      name=f"{yr}년 CR(순)", mode="lines+markers",
                                      line=dict(color=color)))
            fig5.add_trace(go.Scatter(x=sub["월"], y=sub["가입률"],
                                      name=f"{yr}년 가입률", mode="lines+markers",
                                      line=dict(color=color, dash="dash")))
        fig5.update_xaxes(tickvals=list(range(1, 13)),
                          ticktext=[f"{m}월" for m in range(1, 13)])
        base_layout(fig5, "월별 CR(순) & 가입률 (동기간 YoY)", 380)
        st.plotly_chart(fig5, use_container_width=True)
    with tab2:
        fig6 = yoy_overlay_fig(monthly, "월", "객단가(순)",
                               "월별 객단가(순) (동기간 YoY)",
                               ticklabels=MONTH_LABELS, height=380)
        st.plotly_chart(fig6, use_container_width=True)


# ───────────────────────────────────────────────
# 페이지 5: 주차별 성과
# ───────────────────────────────────────────────
def page_weekly(df: pd.DataFrame, targets: dict = None, report_targets: dict = None):
    if targets is None:
        targets = {}
    st.header("📅 주차별 성과")
    if df.empty:
        st.warning("필터 조건에 해당하는 데이터가 없습니다.")
        return

    tab_weekly, tab_heatmap = st.tabs(["📈 주차별 추이", "🗓️ 요일별 히트맵"])

    with tab_weekly:
        cur_year = int(df["연도"].max())
        weekly = agg(df, ["연도", "주차번호"]).sort_values(["연도", "주차번호"])

        metric_options = {
            "순결제ROAS": "순결제ROAS", "광고비": "지표_광고비", "거래액": "지표_총결제거래액",
            "CTR": "CTR", "CPM": "CPM",
            "CR(순)": "CR(순)", "객단가(순)": "객단가(순)",
            "가입수": "지표_가입회원", "첫구매수": "지표_순결제고객수(첫구매)",
        }
        col_a, col_b, col_c = st.columns([3, 1, 1])
        with col_a:
            sel_label = st.selectbox("비교 지표", list(metric_options.keys()), key="wk_metric")
        with col_b:
            use_ma = st.checkbox("4주 이동평균", value=True, key="wk_ma",
                                 help="최근 4주(당주+직전 3주)의 평균을 이어 그린 점선. "
                                      "주 단위 등락을 완만하게 만들어 추세를 보기 쉽게 합니다.")
        with col_c:
            wk_sameday = st.checkbox("동요일 전년비", value=True, key="wk_sameday")

        sel_col = metric_options[sel_label]

        week_labels = {w: week_of_month_label(cur_year, w) for w in range(1, 54)}
        fig = yoy_overlay_fig(
            weekly, "주차번호", sel_col,
            f"주차별 {sel_label} (YoY — W01~W53)",
            ticklabels=week_labels, height=440,
            ma_window=4 if use_ma else 0,
        )
        st.plotly_chart(fig, use_container_width=True)

        # 주차별 실적요약 테이블 (전년비 + 목표 + 목표비)
        st.subheader("주차별 실적요약")
        weekly_cur = agg(df[df["연도"] == cur_year], ["주차번호"]).sort_values("주차번호")
        if wk_sameday:
            weekly_prev = yoy_sameday_prev(df, cur_year, "주차번호")
        else:
            weekly_prev = agg(df[df["연도"] == cur_year - 1], ["주차번호"])

        weekly_targets = (report_targets or {}).get("weekly", {})
        wk_tbl = summary_table(weekly_cur, weekly_prev, "주차번호",
                               lambda w: week_of_month_label(cur_year, w), targets, period_type="주차",
                               targets_per_period=weekly_targets or None, cur_year=cur_year)
        # 목표/목표비 컬럼은 항상 표시 (미입력 시 –)
        st.dataframe(
            wk_tbl.style.map(
                lambda v: "color: #16A34A" if isinstance(v, str) and v.startswith("▲")
                else ("color: #DC2626" if isinstance(v, str) and v.startswith("▼") else ""),
                subset=[c for c in wk_tbl.columns if "전년비" in c],
            ),
            use_container_width=True, hide_index=True,
        )

        # 이상치 감지
        st.subheader("⚠️ 이상치 감지 (전주 대비 ±30% 이상 변화)")
        anomaly_rows = []
        for yr in sorted(weekly["연도"].unique()):
            sub = weekly[weekly["연도"] == yr].sort_values("주차번호").dropna(subset=[sel_col])
            if len(sub) < 2:
                continue
            sub = sub.copy()
            sub["전주"] = sub[sel_col].shift(1)
            sub["변화율"] = (sub[sel_col] - sub["전주"]) / sub["전주"].abs()
            anomalies = sub[sub["변화율"].abs() >= 0.3].copy()
            anomalies["연도"] = yr
            anomaly_rows.append(anomalies[["연도", "주차번호", sel_col, "전주", "변화율"]])

        if anomaly_rows:
            anom_df = pd.concat(anomaly_rows)
            anom_df["주차"] = anom_df.apply(
                lambda r: week_of_month_label(r["연도"], r["주차번호"]), axis=1)
            anom_df["변화율"] = anom_df["변화율"].apply(lambda v: fmt_pct(v, 1) if not pd.isna(v) else "–")
            fmt_fn = fmt_roas if "ROAS" in sel_label else (
                fmt_pct if sel_label in ("CTR", "CR(순)") else
                fmt_num if "수" in sel_label else fmt_money
            )
            anom_df[sel_col] = anom_df[sel_col].apply(fmt_fn)
            anom_df["전주"] = anom_df["전주"].apply(fmt_fn)
            st.dataframe(anom_df[["연도", "주차", sel_col, "전주", "변화율"]],
                         use_container_width=True, hide_index=True)
        else:
            st.info("±30% 이상 변화 주차가 없습니다.")

    # ── 요일별 히트맵
    with tab_heatmap:
        st.markdown("**요일 × 월별 성과 히트맵** — 어느 요일/월에 성과가 집중되는지 파악합니다.")

        hm_metric_opts = {
            "순결제ROAS": "순결제ROAS", "광고비": "지표_광고비",
            "CTR": "CTR", "CPM": "CPM", "CR(순)": "CR(순)",
            "UV": "지표_UV(전체)", "거래액": "지표_총결제거래액",
        }
        col_x, col_y = st.columns([2, 1])
        with col_x:
            hm_sel = st.selectbox("히트맵 지표", list(hm_metric_opts.keys()), key="hm_metric")
        with col_y:
            hm_norm = st.radio("정규화", ["없음", "요일 내 상대값"], key="hm_norm", horizontal=True)

        hm_col = hm_metric_opts[hm_sel]
        hm_data = agg(df, ["요일", "월"])[["요일", "월", hm_col]].dropna()

        pivot = hm_data.pivot_table(index="요일", columns="월", values=hm_col, aggfunc="mean")
        pivot = pivot.reindex(index=list(range(7)))

        if hm_norm == "요일 내 상대값":
            pivot = pivot.div(pivot.max(axis=1), axis=0)

        y_labels = [WEEKDAY_LABELS[i] for i in pivot.index if i in pivot.index]
        x_labels = [f"{m}월" for m in pivot.columns]

        fig_hm = px.imshow(
            pivot.values,
            x=x_labels, y=y_labels,
            color_continuous_scale="Blues",
            aspect="auto",
            text_auto=False,
        )
        fig_hm.update_traces(
            hovertemplate="요일: %{y}<br>월: %{x}<br>값: %{z:.3g}<extra></extra>"
        )
        base_layout(fig_hm, f"요일 × 월별 {hm_sel} 히트맵", 420)
        st.plotly_chart(fig_hm, use_container_width=True)

        # 요일별 요약
        st.subheader("요일별 평균 성과")
        day_agg = agg(df, ["요일"])
        day_agg["요일명"] = day_agg["요일"].map(dict(enumerate(WEEKDAY_LABELS)))
        day_disp = ["요일명", "지표_광고비", "지표_클릭수", "CTR", "CPM",
                    "순결제ROAS", "CR(순)", "객단가(순)"]
        day_tbl = day_agg[[c for c in day_disp if c in day_agg.columns]].copy()
        for c, fn in [("지표_광고비", fmt_money), ("지표_클릭수", fmt_num),
                      ("CTR", fmt_pct), ("CPM", fmt_money),
                      ("순결제ROAS", fmt_roas), ("CR(순)", lambda v: fmt_pct(v, 3)),
                      ("객단가(순)", fmt_money)]:
            if c in day_tbl.columns:
                day_tbl[c] = day_tbl[c].apply(fn)
        st.dataframe(day_tbl, use_container_width=True, hide_index=True)


# ───────────────────────────────────────────────
# 페이지 6: 일별 성과 (신규)
# ───────────────────────────────────────────────
def page_daily(df: pd.DataFrame, targets: dict):
    st.header("📆 일별 성과")
    if df.empty:
        st.warning("필터 조건에 해당하는 데이터가 없습니다.")
        return

    import calendar

    cur_year = int(df["연도"].max())
    avail_months = sorted(df[df["연도"] == cur_year]["연월"].unique(), reverse=True)
    sel_ym = st.selectbox("조회 연월", avail_months, key="daily_ym")

    df_month = df[df["연월"] == sel_ym]
    daily_cur = agg(df_month, ["기간_일자"]).sort_values("기간_일자")

    # 동요일 전년 비교
    daily_cur["비교일자"] = daily_cur["기간_일자"] - pd.Timedelta(days=364)
    prev_dates = daily_cur["비교일자"].tolist()
    df_prev = df[df["기간_일자"].isin(prev_dates)].copy()
    df_prev = df_prev.rename(columns={"기간_일자": "비교일자_orig"})
    daily_prev_raw = agg(df[df["기간_일자"].isin(prev_dates)], ["기간_일자"])
    date_to_cur = {row["비교일자"]: row["기간_일자"] for _, row in daily_cur.iterrows()}

    # 일별 라벨 (날짜 + 요일)
    daily_cur["일자라벨"] = daily_cur["기간_일자"].dt.strftime("%m/%d") + " (" + \
        daily_cur["기간_일자"].dt.dayofweek.map(dict(enumerate(WEEKDAY_LABELS))) + ")"

    # 지표 선택
    metric_options = {
        "순결제ROAS": "순결제ROAS", "광고비": "지표_광고비", "거래액": "지표_총결제거래액",
        "CTR": "CTR", "CPM": "CPM",
        "UV": "지표_UV(전체)", "CR(순)": "CR(순)", "객단가(순)": "객단가(순)",
        "가입수": "지표_가입회원", "첫구매수": "지표_순결제고객수(첫구매)",
    }
    col_a, col_b = st.columns([3, 1])
    with col_a:
        sel_label = st.selectbox("비교 지표", list(metric_options.keys()), key="daily_metric")
    with col_b:
        show_prev = st.checkbox("동요일 전년 비교", value=True, key="daily_prev")

    sel_col = metric_options[sel_label]

    # 차트
    fig = go.Figure()

    if sel_label == "광고비":
        fig.add_trace(go.Bar(
            x=daily_cur["일자라벨"], y=daily_cur[sel_col],
            name=f"{cur_year}년", marker_color=YEAR_COLORS[0], opacity=0.8,
        ))
    else:
        fig.add_trace(go.Scatter(
            x=daily_cur["일자라벨"], y=daily_cur[sel_col],
            name=f"{cur_year}년", mode="lines+markers",
            line=dict(color=YEAR_COLORS[0], width=2), marker=dict(size=5),
        ))

    if show_prev and not daily_prev_raw.empty:
        daily_prev_raw["일자라벨"] = daily_prev_raw["기간_일자"].apply(
            lambda d: date_to_cur.get(d, d)
        )
        daily_prev_raw["일자라벨"] = daily_prev_raw["일자라벨"].dt.strftime("%m/%d") + " (" + \
            daily_prev_raw["일자라벨"].dt.dayofweek.map(dict(enumerate(WEEKDAY_LABELS))) + ")"
        fig.add_trace(go.Scatter(
            x=daily_prev_raw["일자라벨"], y=daily_prev_raw[sel_col],
            name=f"{cur_year-1}년 동요일", mode="lines+markers",
            line=dict(color=YEAR_COLORS[1], width=1.5, dash="dash"), marker=dict(size=4),
        ))

    if sel_label == "광고비" and targets.get("spend", 0) > 0:
        year_p, month_p = int(sel_ym[:4]), int(sel_ym[5:7])
        total_days = calendar.monthrange(year_p, month_p)[1]
        daily_target = targets["spend"] / total_days
        fig.add_hline(y=daily_target, line_dash="dot", line_color="#EF4444",
                      annotation_text=f"일 목표 {fmt_money(daily_target)}")

    base_layout(fig, f"{sel_ym} 일별 {sel_label} (동요일 전년 비교)", 420)
    fig.update_layout(xaxis_tickangle=-45)
    st.plotly_chart(fig, use_container_width=True)

    # 요일별 집계 요약
    col1, col2 = st.columns(2)
    with col1:
        dow_agg = daily_cur.copy()
        dow_agg["요일"] = daily_cur["기간_일자"].dt.dayofweek
        dow_summary = dow_agg.groupby("요일").agg(
            일수=("기간_일자", "count"),
            **{sel_col: (sel_col, "mean")},
        ).reset_index()
        dow_summary["요일명"] = dow_summary["요일"].map(dict(enumerate(WEEKDAY_LABELS)))
        fig2 = px.bar(dow_summary, x="요일명", y=sel_col,
                      color="요일명", color_discrete_sequence=px.colors.qualitative.Set2)
        base_layout(fig2, f"요일별 평균 {sel_label}", 320)
        fig2.update_layout(showlegend=False)
        st.plotly_chart(fig2, use_container_width=True)

    with col2:
        # 전년비 테이블 (동요일 기준)
        if show_prev and not daily_prev_raw.empty:
            merge_df = daily_cur[["기간_일자", "비교일자", sel_col]].copy()
            merge_df = merge_df.merge(
                daily_prev_raw[["기간_일자", sel_col]].rename(
                    columns={"기간_일자": "비교일자", sel_col: "전년_동요일"}),
                on="비교일자", how="left",
            )
            merge_df["전년비"] = (merge_df[sel_col] - merge_df["전년_동요일"]) / merge_df["전년_동요일"].abs()
            merge_df["일자"] = merge_df["기간_일자"].dt.strftime("%m/%d") + " (" + \
                merge_df["기간_일자"].dt.dayofweek.map(dict(enumerate(WEEKDAY_LABELS))) + ")"
            merge_df["비교(전년)"] = merge_df["비교일자"].dt.strftime("%m/%d") + " (" + \
                merge_df["비교일자"].dt.dayofweek.map(dict(enumerate(WEEKDAY_LABELS))) + ")"

            fmt_fn = fmt_roas if "ROAS" in sel_label else (
                fmt_pct if sel_label in ("CTR", "CR(순)") else
                fmt_num if "수" in sel_label else fmt_money
            )
            disp = merge_df[["일자", sel_col, "비교(전년)", "전년_동요일", "전년비"]].copy()
            disp[sel_col] = disp[sel_col].apply(fmt_fn)
            disp["전년_동요일"] = disp["전년_동요일"].apply(fmt_fn)
            disp["전년비"] = disp["전년비"].apply(
                lambda v: ("▲ " if v >= 0 else "▼ ") + f"{abs(v)*100:.1f}%"
                if not pd.isna(v) else "–"
            )
            st.dataframe(disp, use_container_width=True, hide_index=True)

    # 상세 지표 테이블
    st.subheader("일별 상세 지표")
    disp_cols = [
        "일자라벨", "지표_광고비", "지표_노출수", "지표_클릭수",
        "지표_UV(전체)", "CTR", "CPC", "CPM", "CPUV",
        "순결제ROAS", "CR(순)", "객단가(순)",
        "지표_가입회원", "지표_순결제고객수(첫구매)",
    ]
    tbl = daily_cur[[c for c in disp_cols if c in daily_cur.columns]].copy()
    fmt_map = {
        "지표_광고비": fmt_money, "지표_노출수": fmt_num, "지표_클릭수": fmt_num,
        "지표_UV(전체)": fmt_num, "CTR": fmt_pct, "CPC": fmt_money, "CPM": fmt_money,
        "CPUV": fmt_money, "순결제ROAS": fmt_roas,
        "CR(순)": lambda v: fmt_pct(v, 3), "객단가(순)": fmt_money,
        "지표_가입회원": fmt_num, "지표_순결제고객수(첫구매)": fmt_num,
    }
    tbl_fmt = tbl.copy()
    for c, fn in fmt_map.items():
        if c in tbl_fmt.columns:
            tbl_fmt[c] = tbl_fmt[c].apply(fn)
    st.dataframe(tbl_fmt.rename(columns={"일자라벨": "일자"}),
                 use_container_width=True, hide_index=True)


# ───────────────────────────────────────────────
# 페이지 7: 소재(AF코드) 상세
# ───────────────────────────────────────────────
def page_creative(df: pd.DataFrame):
    st.header("🎨 소재(AF코드) 상세")
    if df.empty:
        st.warning("필터 조건에 해당하는 데이터가 없습니다.")
        return

    c1, c2, c3 = st.columns(3)
    with c1:
        camp_search = st.text_input("캠페인 검색", key="cr_camp")
    with c2:
        af_search = st.text_input("AF코드 / 소재명 검색", key="cr_af")
    with c3:
        top_n = st.selectbox("상위 N개", [30, 50, 100, 200], index=1)

    cr_df = agg(df, ["구분_AF코드", "구분_AF코드이름", "구분_캠페인",
                     "구분_하위캠페인", "구분_매체명", "구분_비용출처"])
    if camp_search:
        cr_df = cr_df[cr_df["구분_캠페인"].str.contains(camp_search, na=False)]
    if af_search:
        mask = (cr_df["구분_AF코드"].str.contains(af_search, na=False) |
                cr_df["구분_AF코드이름"].str.contains(af_search, na=False))
        cr_df = cr_df[mask]

    sort_col = st.selectbox("정렬 기준",
                            ["지표_광고비", "CTR", "CPM", "순결제ROAS", "CR(순)",
                             "객단가(순)", "첫구매CPA", "가입CPA"])
    asc = sort_col in ("첫구매CPA", "가입CPA")
    cr_df = cr_df.sort_values(sort_col, ascending=asc, na_position="last").head(top_n)

    ca, cb = st.columns(2)
    with ca:
        top_ctr = cr_df[cr_df["지표_노출수"] > 1000].nlargest(10, "CTR")
        fig = px.bar(top_ctr, x="CTR", y="구분_AF코드이름", orientation="h",
                     color_discrete_sequence=["#3B82F6"])
        fig.update_xaxes(tickformat=".2%")
        base_layout(fig, "CTR 상위 10 소재 (노출 1,000+)", 380)
        fig.update_layout(showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
    with cb:
        top_roas = cr_df[cr_df["지표_광고비"] > 0].nlargest(10, "순결제ROAS")
        fig2 = px.bar(top_roas, x="순결제ROAS", y="구분_AF코드이름", orientation="h",
                      color_discrete_sequence=["#10B981"])
        base_layout(fig2, "순결제ROAS 상위 10 소재", 380)
        fig2.update_layout(showlegend=False)
        st.plotly_chart(fig2, use_container_width=True)

    st.subheader(f"소재 테이블 (상위 {top_n}개)")
    disp = [
        "구분_AF코드", "구분_AF코드이름", "구분_캠페인", "구분_매체명",
        "집행일수", "지표_광고비", "지표_노출수", "지표_클릭수",
        "CTR", "CPC", "CPM", "CPUV", "UV/클릭",
        "순결제ROAS", "CR(순)", "객단가(순)", "순결제비중",
        "첫구매CPA", "가입CPA", "가입률", "첫구매율",
    ]
    tbl = cr_df[[c for c in disp if c in cr_df.columns]].copy()
    fmt_map = {
        "지표_광고비": fmt_money, "지표_노출수": fmt_num, "지표_클릭수": fmt_num,
        "CTR": fmt_pct, "CPC": fmt_money, "CPM": fmt_money, "CPUV": fmt_money,
        "UV/클릭": fmt_pct, "순결제ROAS": fmt_roas,
        "CR(순)": lambda v: fmt_pct(v, 3), "객단가(순)": fmt_money, "순결제비중": fmt_pct,
        "첫구매CPA": fmt_money, "가입CPA": fmt_money,
        "가입률": lambda v: fmt_pct(v, 3), "첫구매율": lambda v: fmt_pct(v, 3),
    }
    tbl_fmt = tbl.copy()
    for c, fn in fmt_map.items():
        if c in tbl_fmt.columns:
            tbl_fmt[c] = tbl_fmt[c].apply(fn)
    st.dataframe(tbl_fmt, use_container_width=True, hide_index=True)

    st.download_button(
        "📥 현재 필터 데이터 CSV 다운로드",
        data=df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"),
        file_name="da_filtered_data.csv", mime="text/csv",
    )


# ───────────────────────────────────────────────
# 메인
# ───────────────────────────────────────────────
def main():
    st.title("📊 DA 광고 실적 대시보드")

    # 사이드바 순서: ① 페이지  ② 필터  ③ 파일 업로드
    page_box   = st.sidebar.container()
    filter_box = st.sidebar.container()
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

    # ── ② 필터
    with filter_box:
        filters = sidebar_filters(df)

    pre_date_filtered = filter_df(df, filters)  # 날짜 범위 필터 전 (전년비/타 페이지용)

    targets = get_targets()

    # ── ① 페이지 선택 (맨 위)
    with page_box:
        st.subheader("📄 페이지")
        page = st.radio("페이지", [
            "📊 전체 요약", "📆 일별 성과", "📡 매체별 성과", "🎯 캠페인별 성과",
            "📅 주차별 성과", "🔍 퍼널 & 전환 분석", "🎨 소재 상세",
        ], label_visibility="collapsed")

    if page == "📊 전체 요약":
        page_summary(pre_date_filtered, targets, report_targets)
    elif page == "📆 일별 성과":
        page_daily(pre_date_filtered, targets)
    elif page == "📡 매체별 성과":
        page_media(pre_date_filtered)
    elif page == "🎯 캠페인별 성과":
        page_campaign(pre_date_filtered, targets)
    elif page == "📅 주차별 성과":
        page_weekly(pre_date_filtered, targets, report_targets)
    elif page == "🔍 퍼널 & 전환 분석":
        page_funnel(pre_date_filtered)
    elif page == "🎨 소재 상세":
        page_creative(pre_date_filtered)


if st.runtime.exists():
    main()
