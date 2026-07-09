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
    return f"{v:.2f}x"

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
                  targets: dict, period_type: str = "월") -> pd.DataFrame:
    """실적요약 테이블: 실적 + 전년비 + 목표 + 목표비 한 눈에."""
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

        t_spend = targets.get("spend", 0)
        t_rev   = targets.get("rev", 0)
        t_roas  = targets.get("roas", 0)

        def _chg(c, p):
            if pd.isna(c) or pd.isna(p) or p == 0: return np.nan
            return (c - p) / abs(p)

        rows.append({
            period_type: label,
            "광고비(백만)": round(spend / 1e6, 1) if not pd.isna(spend) else np.nan,
            "거래액(백만)": round(rev / 1e6, 1) if not pd.isna(rev) else np.nan,
            "ROAS": round(roas, 2) if not pd.isna(roas) else np.nan,
            "전년비_광고비": _chg(spend, p_spend),
            "전년비_거래액": _chg(rev, p_rev),
            "전년비_ROAS": _chg(roas, p_roas),
            "목표_광고비(백만)": round(t_spend / 1e6, 1) if t_spend > 0 else np.nan,
            "목표_거래액(백만)": round(t_rev / 1e6, 1) if t_rev > 0 else np.nan,
            "목표_ROAS": t_roas if t_roas > 0 else np.nan,
            "목표비_광고비": spend / t_spend if (t_spend > 0 and not pd.isna(spend)) else np.nan,
            "목표비_거래액": rev / t_rev   if (t_rev > 0 and not pd.isna(rev)) else np.nan,
            "목표비_ROAS":  roas / t_roas  if (t_roas > 0 and not pd.isna(roas)) else np.nan,
        })
    result = pd.DataFrame(rows)

    def _fmt_chg(v):
        if pd.isna(v): return "–"
        color = "▲" if v >= 0 else "▼"
        return f"{color} {abs(v)*100:.1f}%"

    def _fmt_rate(v):
        if pd.isna(v): return "–"
        return f"{v*100:.1f}%"

    for c in ["전년비_광고비", "전년비_거래액", "전년비_ROAS"]:
        if c in result.columns:
            result[c] = result[c].apply(_fmt_chg)
    for c in ["목표비_광고비", "목표비_거래액", "목표비_ROAS"]:
        if c in result.columns:
            result[c] = result[c].apply(_fmt_rate)

    return result


# ───────────────────────────────────────────────
# 사이드바 필터
# ───────────────────────────────────────────────
def sidebar_filters(df: pd.DataFrame):
    st.sidebar.header("필터")

    years = sorted(df["연도"].unique())
    sel_year = st.sidebar.multiselect("연도", years, default=years)

    months = list(range(1, 13))
    sel_month = st.sidebar.multiselect("월", months, default=months,
                                       format_func=lambda x: f"{x}월")
    st.sidebar.divider()

    cost_mode = st.sidebar.radio("비용출처 모드",
                                 ["TOTAL", "TOTAL(서비스비용제외)", "개별 선택"], index=0)
    sel_sources = None
    if cost_mode == "개별 선택":
        all_sources = sorted(df["구분_비용출처"].dropna().unique())
        sel_sources = st.sidebar.multiselect("비용출처", all_sources, default=all_sources)

    st.sidebar.divider()

    if df["대상여부"].nunique() > 1:
        target_opts = sorted(df["대상여부"].dropna().unique())
        sel_target = st.sidebar.multiselect("대상여부", target_opts, default=["대상"])
    else:
        sel_target = list(df["대상여부"].dropna().unique())

    if df["구분_광고유형"].nunique() > 1:
        ad_types = sorted(df["구분_광고유형"].dropna().unique())
        sel_adtype = st.sidebar.multiselect("광고유형", ad_types, default=ad_types)
    else:
        sel_adtype = list(df["구분_광고유형"].dropna().unique())

    channels = sorted(df["구분_채널"].dropna().unique())
    sel_channel = st.sidebar.multiselect("채널", channels, default=channels)

    media_list = sorted(df["구분_매체명"].dropna().unique())
    sel_media = st.sidebar.multiselect("매체명", media_list, default=media_list)

    devices = sorted(df["구분_디바이스"].dropna().unique())
    sel_device = st.sidebar.multiselect("디바이스", devices, default=devices)

    st.sidebar.divider()

    depts = sorted(df["구분_부서명"].dropna().unique())
    sel_dept = st.sidebar.multiselect("부서명", depts, default=depts)

    cats = sorted(df["카테고리"].dropna().unique())
    sel_cat = st.sidebar.multiselect("카테고리", cats, default=cats)

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
    with st.sidebar.expander("📌 당월 목표 입력", expanded=False):
        t_spend  = st.number_input("목표 광고비 (원)", value=0, step=1_000_000)
        t_rev    = st.number_input("목표 거래액 (원)", value=0, step=1_000_000)
        t_roas   = st.number_input("목표 ROAS", value=0.0, step=0.1, format="%.2f")
        t_uv     = st.number_input("목표 UV", value=0, step=1_000)
        t_join   = st.number_input("목표 가입수", value=0, step=10)
        t_first  = st.number_input("목표 첫구매수", value=0, step=10)
    return dict(spend=t_spend, rev=t_rev, roas=t_roas, uv=t_uv, join=t_join, first=t_first)


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


# ───────────────────────────────────────────────
# KPI 카드
# ───────────────────────────────────────────────
def kpi_cards(df: pd.DataFrame, targets: dict):
    tot_raw = df[AGG_COLS].sum()
    tot_raw_df = pd.DataFrame([tot_raw])
    tot = calc_kpi(tot_raw_df).iloc[0]

    days = df["기간_일자"].nunique()

    cards = [
        ("💰 광고비",     fmt_money(tot["지표_광고비"]),        "spend",  tot["지표_광고비"]),
        ("📺 노출수",     fmt_num(tot["지표_노출수"]),           None,     None),
        ("🖱️ 클릭수",    fmt_num(tot["지표_클릭수"]),           None,     None),
        ("📈 CTR",        fmt_pct(tot["CTR"]),                  None,     None),
        ("💵 CPC",        fmt_money(tot["CPC"]),                None,     None),
        ("📡 CPM",        fmt_money(tot["CPM"]),                None,     None),
        ("🌐 UV",         fmt_num(tot["지표_UV(전체)"]),         "uv",     tot["지표_UV(전체)"]),
        ("🔗 CPUV",       fmt_money(tot["CPUV"]),               None,     None),
        ("↩️ UV/클릭",   fmt_pct(tot["UV/클릭"]),              None,     None),
        ("🔄 순결제ROAS", fmt_roas(tot["순결제ROAS"]),           "roas",   tot["순결제ROAS"]),
        ("🎯 총결제ROAS", fmt_roas(tot["총결제ROAS"]),           None,     None),
        ("📊 CR(순)",     fmt_pct(tot["CR(순)"], 3),            None,     None),
        ("💎 객단가(순)", fmt_money(tot["객단가(순)"]),          None,     None),
        ("🛒 첫구매CPA",  fmt_money(tot["첫구매CPA"]),          None,     None),
        ("👤 가입CPA",    fmt_money(tot["가입CPA"]),            None,     None),
        ("✅ 가입수",     fmt_num(tot["지표_가입회원"]),          "join",   tot["지표_가입회원"]),
        ("🛍️ 첫구매수",  fmt_num(tot["지표_순결제고객수(첫구매)"]), "first", tot["지표_순결제고객수(첫구매)"]),
        ("🔁 윈백거래액", fmt_money(tot["지표_순결제거래액(윈백)"]), None, None),
        ("🆕 신규거래액", fmt_money(tot["지표_당년신규순결제거래액"]), None, None),
        ("📅 집행일수",   fmt_num(days),                        None,     None),
    ]

    cols = st.columns(5)
    for i, (label, val, tkey, cur_val) in enumerate(cards):
        with cols[i % 5]:
            st.metric(label=label, value=val)
            if tkey and targets.get(tkey, 0) > 0 and cur_val is not None:
                progress_pill(cur_val, targets[tkey], "진도율")


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


def _render_monthly_section(df_tab, targets, tab_key, sameday=False):
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

    tbl = summary_table(monthly_cur, monthly_prev, "월",
                        lambda m: f"{int(m)}월", targets, period_type="월")

    # 목표/목표비 컬럼 유무에 따라 표시 여부 결정
    has_target = targets.get("spend", 0) > 0 or targets.get("rev", 0) > 0
    drop_cols = []
    if not has_target:
        drop_cols = [c for c in tbl.columns if "목표" in c]
    if drop_cols:
        tbl = tbl.drop(columns=drop_cols)

    st.dataframe(
        tbl.style.map(
            lambda v: "color: #16A34A" if isinstance(v, str) and v.startswith("▲")
            else ("color: #DC2626" if isinstance(v, str) and v.startswith("▼") else ""),
            subset=[c for c in tbl.columns if "전년비" in c],
        ),
        use_container_width=True, hide_index=True,
    )

    # 광고비 + ROAS 차트
    col1, col2 = st.columns(2)
    with col1:
        monthly_all = agg(df_tab, ["연도", "월"]).sort_values(["연도", "월"])
        fig = go.Figure()
        for i, yr in enumerate(sorted(monthly_all["연도"].unique())):
            sub = monthly_all[monthly_all["연도"] == yr]
            fig.add_trace(go.Bar(
                x=sub["월"], y=sub["지표_광고비"],
                name=f"{yr}년", marker_color=YEAR_COLORS[i % len(YEAR_COLORS)], opacity=0.8,
            ))
        if targets.get("spend", 0) > 0:
            fig.add_hline(y=targets["spend"], line_dash="dot", line_color="#EF4444",
                          annotation_text="목표")
        fig.update_xaxes(tickvals=list(range(1, 13)),
                         ticktext=[f"{m}월" for m in range(1, 13)])
        base_layout(fig, "월별 광고비 (YoY)", 360)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        metric_opts = {
            "순결제ROAS": "순결제ROAS", "거래액": "지표_총결제거래액",
            "CTR": "CTR", "CPM": "CPM", "CR(순)": "CR(순)", "객단가(순)": "객단가(순)",
        }
        sel_m = st.selectbox("지표 선택", list(metric_opts.keys()), key=f"sum_m_{tab_key}")
        fig2 = yoy_overlay_fig(
            monthly_all, "월", metric_opts[sel_m],
            f"월별 {sel_m} (YoY)", ticklabels=MONTH_LABELS, height=360,
        )
        if sel_m == "순결제ROAS" and targets.get("roas", 0) > 0:
            fig2.add_hline(y=targets["roas"], line_dash="dot", line_color="#EF4444",
                           annotation_text=f"목표 {targets['roas']:.1f}x")
        st.plotly_chart(fig2, use_container_width=True)


def page_summary(df: pd.DataFrame, targets: dict):
    st.header("📊 전체 요약")
    if df.empty:
        st.warning("필터 조건에 해당하는 데이터가 없습니다.")
        return

    kpi_cards(df, targets)
    st.divider()

    # ── 상단: 비용출처별 탭 (Excel 시트와 동일 구조)
    main_tabs = st.tabs(["📋 TOTAL(서비스비용제외)", "📋 TOTAL", "📋 거래액확대", "📋 신규확대/인지도",
                          "💰 예산 페이싱", "🧩 거래액 구성"])
    tab_names = ["TOTAL(서비스비용제외)", "TOTAL", "거래액확대", "신규확대/인지도"]

    sameday = st.sidebar.checkbox("동요일 기준 전년비", value=False, key="sameday_toggle")

    for i, tname in enumerate(tab_names):
        with main_tabs[i]:
            st.caption(f"비용출처: {tname}  |  {'동요일 기준' if sameday else '동월 기준'} 전년비")
            df_tab = _filter_cost(df, tname)
            _render_monthly_section(df_tab, targets, tab_key=f"t{i}", sameday=sameday)

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
        "광고비": "지표_광고비", "노출수": "지표_노출수", "클릭수": "지표_클릭수",
        "UV": "지표_UV(전체)", "CTR": "CTR", "CPC": "CPC", "CPM": "CPM", "CPUV": "CPUV",
        "순결제ROAS": "순결제ROAS", "총결제ROAS": "총결제ROAS",
        "CR(순)": "CR(순)", "CR(총)": "CR(총)",
        "객단가(순)": "객단가(순)", "첫구매CPA": "첫구매CPA", "가입CPA": "가입CPA",
        "가입률": "가입률", "첫구매율": "첫구매율", "거래액": "지표_총결제거래액",
    }
    sel_label = st.selectbox("비교 지표", list(metric_options.keys()))
    sel_col   = metric_options[sel_label]

    by_media = agg(df, ["구분_매체명"]).sort_values("지표_광고비", ascending=False)

    col1, col2 = st.columns(2)
    with col1:
        top = by_media.dropna(subset=[sel_col]).sort_values(sel_col, ascending=True).tail(12)
        fig = px.bar(top, x=sel_col, y="구분_매체명", orientation="h",
                     color="구분_매체명", color_discrete_map=MEDIA_COLORS)
        base_layout(fig, f"매체별 {sel_label}", 420)
        fig.update_layout(showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        valid = by_media[by_media["지표_광고비"] > 0].dropna(subset=["순결제ROAS"])
        fig2 = px.scatter(valid, x="지표_광고비", y="순결제ROAS", size="지표_클릭수",
                          color="구분_매체명", color_discrete_map=MEDIA_COLORS,
                          hover_name="구분_매체명", text="구분_매체명")
        fig2.update_traces(textposition="top center")
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
def page_campaign(df: pd.DataFrame):
    st.header("🎯 캠페인별 성과")
    if df.empty:
        st.warning("필터 조건에 해당하는 데이터가 없습니다.")
        return

    tab_rank, tab_quad = st.tabs(["📋 캠페인 랭킹", "🔲 효율 사분면"])

    with tab_rank:
        c1, c2 = st.columns([2, 1])
        with c1:
            search = st.text_input("캠페인명 검색", placeholder="키워드 입력...")
        with c2:
            sort_opt = st.selectbox("정렬 기준",
                                    ["광고비", "노출수", "클릭수", "CTR", "CPM",
                                     "순결제ROAS", "CR(순)", "첫구매CPA", "객단가(순)"])

        sort_map = {
            "광고비": "지표_광고비", "노출수": "지표_노출수", "클릭수": "지표_클릭수",
            "CTR": "CTR", "CPM": "CPM", "순결제ROAS": "순결제ROAS",
            "CR(순)": "CR(순)", "첫구매CPA": "첫구매CPA", "객단가(순)": "객단가(순)",
        }
        sort_col = sort_map[sort_opt]

        camp_df = agg(df, ["구분_캠페인", "구분_비용출처", "구분_매체명"])
        if search:
            camp_df = camp_df[camp_df["구분_캠페인"].str.contains(search, na=False)]
        camp_df = camp_df.sort_values(sort_col, ascending=False, na_position="last").head(50)

        c3, c4 = st.columns(2)
        with c3:
            by_src = agg(df, ["구분_비용출처"]).sort_values("지표_광고비", ascending=False)
            by_src = by_src[by_src["지표_광고비"] > 0]
            fig = px.bar(by_src, x="구분_비용출처", y="지표_광고비",
                         color="구분_비용출처", color_discrete_map=PURPOSE_COLORS)
            base_layout(fig, "비용출처별 광고비", 350)
            fig.update_layout(showlegend=False, xaxis_tickangle=-20)
            st.plotly_chart(fig, use_container_width=True)

        with c4:
            by_dept = agg(df, ["구분_부서명"]).sort_values("지표_광고비", ascending=False)
            by_dept = by_dept[by_dept["지표_광고비"] > 0]
            fig2 = px.bar(by_dept, x="구분_부서명", y="지표_광고비")
            base_layout(fig2, "부서별 광고비", 350)
            fig2.update_layout(xaxis_tickangle=-20)
            st.plotly_chart(fig2, use_container_width=True)

        st.subheader(f"캠페인별 실적 상위 50개 (정렬: {sort_opt})")
        disp = [
            "구분_캠페인", "구분_비용출처", "구분_매체명",
            "집행일수", "지표_광고비", "지표_노출수", "지표_클릭수",
            "CTR", "CPC", "CPM", "CPUV", "UV/클릭",
            "순결제ROAS", "총결제ROAS", "CR(순)", "객단가(순)",
            "첫구매CPA", "가입CPA", "가입률", "첫구매율",
            "신규비중", "윈백비중",
        ]
        tbl = camp_df[[c for c in disp if c in camp_df.columns]].copy()
        fmt_map = {
            "지표_광고비": fmt_money, "지표_노출수": fmt_num, "지표_클릭수": fmt_num,
            "CTR": fmt_pct, "CPC": fmt_money, "CPM": fmt_money, "CPUV": fmt_money,
            "UV/클릭": fmt_pct, "순결제ROAS": fmt_roas, "총결제ROAS": fmt_roas,
            "CR(순)": lambda v: fmt_pct(v, 3), "객단가(순)": fmt_money,
            "첫구매CPA": fmt_money, "가입CPA": fmt_money,
            "가입률": lambda v: fmt_pct(v, 3), "첫구매율": lambda v: fmt_pct(v, 3),
            "신규비중": fmt_pct, "윈백비중": fmt_pct,
        }
        tbl_fmt = tbl.copy()
        for c, fn in fmt_map.items():
            if c in tbl_fmt.columns:
                tbl_fmt[c] = tbl_fmt[c].apply(fn)
        st.dataframe(tbl_fmt, use_container_width=True, hide_index=True)

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
def page_weekly(df: pd.DataFrame):
    st.header("📅 주차별 성과")
    if df.empty:
        st.warning("필터 조건에 해당하는 데이터가 없습니다.")
        return

    tab_weekly, tab_heatmap = st.tabs(["📈 주차별 추이", "🗓️ 요일별 히트맵"])

    with tab_weekly:
        cur_year = int(df["연도"].max())
        weekly = agg(df, ["연도", "주차번호"]).sort_values(["연도", "주차번호"])

        metric_options = {
            "광고비": "지표_광고비", "거래액": "지표_총결제거래액",
            "순결제ROAS": "순결제ROAS", "CTR": "CTR", "CPM": "CPM",
            "CR(순)": "CR(순)", "객단가(순)": "객단가(순)",
            "가입수": "지표_가입회원", "첫구매수": "지표_순결제고객수(첫구매)",
        }
        col_a, col_b, col_c = st.columns([3, 1, 1])
        with col_a:
            sel_label = st.selectbox("비교 지표", list(metric_options.keys()), key="wk_metric")
        with col_b:
            use_ma = st.checkbox("4주 이동평균", value=True, key="wk_ma")
        with col_c:
            wk_sameday = st.checkbox("동요일 전년비", value=False, key="wk_sameday")

        sel_col = metric_options[sel_label]

        week_labels = {w: f"W{w:02d}" for w in range(1, 54)}
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

        wk_tbl = summary_table(weekly_cur, weekly_prev, "주차번호",
                               lambda w: f"W{int(w):02d}", targets, period_type="주차")
        has_target = targets.get("spend", 0) > 0 or targets.get("rev", 0) > 0
        if not has_target:
            wk_tbl = wk_tbl.drop(columns=[c for c in wk_tbl.columns if "목표" in c])
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
            anom_df["주차"] = anom_df["주차번호"].apply(lambda w: f"W{w:02d}")
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
            "광고비": "지표_광고비", "순결제ROAS": "순결제ROAS",
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
        "광고비": "지표_광고비", "거래액": "지표_총결제거래액",
        "순결제ROAS": "순결제ROAS", "CTR": "CTR", "CPM": "CPM",
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

    uploaded = st.sidebar.file_uploader(
        "데이터 파일 업로드", type=["csv", "xlsx", "xlsb"],
        help="DA 광고 로데이터 파일을 업로드하세요. (CSV / Excel)",
    )

    if uploaded is None:
        st.info("👈 사이드바에서 데이터 파일을 업로드해주세요.")
        st.markdown("""
        **지원 파일 형식**
        - CSV (UTF-8, UTF-8-BOM, CP949, EUC-KR)
        - Excel (.xlsx, .xlsb)

        **필수 컬럼**: `기간_일자`, `구분_*`, `지표_*`
        """)
        return

    with st.spinner("데이터 로딩 중..."):
        df = load_data(uploaded.read(), uploaded.name)

    st.sidebar.caption(
        f"총 {len(df):,}행 | {df['기간_일자'].min().date()} ~ {df['기간_일자'].max().date()}"
    )

    filters = sidebar_filters(df)
    filtered = filter_df(df, filters)
    st.sidebar.caption(f"필터 적용 후: {len(filtered):,}행")

    targets = get_targets()

    st.sidebar.divider()
    page = st.sidebar.radio("페이지", [
        "📊 전체 요약", "📆 일별 성과", "📡 매체별 성과", "🎯 캠페인별 성과",
        "📅 주차별 성과", "🔍 퍼널 & 전환 분석", "🎨 소재 상세",
    ])

    if page == "📊 전체 요약":
        page_summary(filtered, targets)
    elif page == "📆 일별 성과":
        page_daily(filtered, targets)
    elif page == "📡 매체별 성과":
        page_media(filtered)
    elif page == "🎯 캠페인별 성과":
        page_campaign(filtered)
    elif page == "📅 주차별 성과":
        page_weekly(filtered)
    elif page == "🔍 퍼널 & 전환 분석":
        page_funnel(filtered)
    elif page == "🎨 소재 상세":
        page_creative(filtered)


if st.runtime.exists():
    main()
