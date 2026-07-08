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

    # 없는 컬럼에 기본값 채우기
    defaults = {
        "기간_주": None,  # 아래에서 별도 처리
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
            df["기간_일자"].dt.strftime("%Y%m")
            + df["기간_일자"].dt.isocalendar().week.astype(str).str.zfill(2)
            + "주차"
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
    if "기간_일자" in df.columns and "집행일수" not in by:
        days = df.groupby(by, dropna=False)["기간_일자"].nunique().reset_index()
        days.columns = list(days.columns[:-1]) + ["집행일수"]
        grouped = grouped.merge(days, on=by, how="left")
    return calc_kpi(grouped)


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
# 목표 입력 UI (사이드바 하단)
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
# KPI 카드 (목표 진도율 포함)
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
# 전년비 계산 헬퍼
# ───────────────────────────────────────────────
def yoy_compare(df: pd.DataFrame, cur_year: int, by_col: str, val_col: str):
    prev_year = cur_year - 1
    sub = df[df["연도"].isin([cur_year, prev_year])]
    piv = agg(sub, ["연도", by_col])
    cur  = piv[piv["연도"] == cur_year][[by_col, val_col]].rename(columns={val_col: "당년"})
    prev = piv[piv["연도"] == prev_year][[by_col, val_col]].rename(columns={val_col: "전년"})
    merged = cur.merge(prev, on=by_col, how="outer").sort_values(by_col)
    merged["전년비"] = (merged["당년"] - merged["전년"]) / merged["전년"].abs()
    return merged


# ───────────────────────────────────────────────
# 페이지 1: 전체 요약
# ───────────────────────────────────────────────
def page_summary(df: pd.DataFrame, targets: dict):
    st.header("📊 전체 요약")
    if df.empty:
        st.warning("필터 조건에 해당하는 데이터가 없습니다.")
        return

    kpi_cards(df, targets)
    st.divider()

    col1, col2 = st.columns(2)
    with col1:
        monthly = agg(df, ["연도", "월", "연월"]).sort_values(["연도", "월"])
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        for yr in sorted(monthly["연도"].unique()):
            sub = monthly[monthly["연도"] == yr]
            fig.add_trace(go.Bar(x=sub["연월"], y=sub["지표_광고비"],
                                 name=f"{yr} 광고비", opacity=0.75), secondary_y=False)
            fig.add_trace(go.Scatter(x=sub["연월"], y=sub["지표_총결제거래액"],
                                     name=f"{yr} 거래액", mode="lines+markers"), secondary_y=True)
        if targets["spend"] > 0:
            fig.add_hline(y=targets["spend"], line_dash="dot", line_color="#EF4444",
                          annotation_text="목표 광고비", secondary_y=False)
        if targets["rev"] > 0:
            fig.add_hline(y=targets["rev"], line_dash="dot", line_color="#10B981",
                          annotation_text="목표 거래액", secondary_y=True)
        fig.update_yaxes(title_text="광고비", secondary_y=False)
        fig.update_yaxes(title_text="거래액", secondary_y=True)
        base_layout(fig, "월별 광고비 & 거래액 추이", 400)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        by_media = agg(df, ["구분_매체명"]).nlargest(10, "지표_광고비")
        fig2 = px.pie(by_media, names="구분_매체명", values="지표_광고비",
                      color="구분_매체명", color_discrete_map=MEDIA_COLORS)
        fig2.update_traces(textposition="inside", textinfo="percent+label")
        base_layout(fig2, "매체별 광고비 비중", 400)
        st.plotly_chart(fig2, use_container_width=True)

    col3, col4 = st.columns(2)
    with col3:
        monthly2 = agg(df, ["연도", "월", "연월"]).sort_values(["연도", "월"])
        fig3 = go.Figure()
        for yr in sorted(monthly2["연도"].unique()):
            sub = monthly2[monthly2["연도"] == yr]
            fig3.add_trace(go.Scatter(x=sub["연월"], y=sub["순결제ROAS"],
                                      name=f"{yr} 순결제ROAS", mode="lines+markers"))
        if targets["roas"] > 0:
            fig3.add_hline(y=targets["roas"], line_dash="dot", line_color="#EF4444",
                           annotation_text=f"목표 ROAS {targets['roas']:.1f}x")
        base_layout(fig3, "월별 순결제ROAS 추이", 380)
        st.plotly_chart(fig3, use_container_width=True)

    with col4:
        tot = df[AGG_COLS].sum()
        first  = tot["지표_순결제거래액(첫구매)"]
        winback = tot["지표_순결제거래액(윈백)"]
        new_rev = tot["지표_당년신규순결제거래액"]
        other  = max(0, tot["지표_총결제거래액"] - first - winback)
        bkd = pd.DataFrame({
            "구분": ["첫구매", "윈백", "신규(당년)", "기타"],
            "금액": [first, winback, new_rev, other],
        })
        bkd = bkd[bkd["금액"] > 0]
        fig4 = px.pie(bkd, names="구분", values="금액",
                      color_discrete_sequence=["#3B82F6","#10B981","#F59E0B","#94A3B8"])
        fig4.update_traces(textposition="inside", textinfo="percent+label")
        base_layout(fig4, "거래액 유형별 구성", 380)
        st.plotly_chart(fig4, use_container_width=True)

    st.subheader("월별 전년비 요약")
    cur_year = max(df["연도"].unique())
    yoy_metrics = {
        "광고비": "지표_광고비", "거래액": "지표_총결제거래액",
        "순결제ROAS": "순결제ROAS", "UV": "지표_UV(전체)",
        "CTR": "CTR", "CPM": "CPM",
    }
    sel_yoy = st.selectbox("비교 지표", list(yoy_metrics.keys()), key="yoy_sel")
    yoy_df = yoy_compare(df, cur_year, "연월", yoy_metrics[sel_yoy])

    fmt_fn = fmt_roas if "ROAS" in sel_yoy else (fmt_pct if sel_yoy == "CTR" else fmt_money if "비" not in sel_yoy else fmt_pct)
    yoy_disp = yoy_df.copy()
    yoy_disp["당년"]  = yoy_disp["당년"].apply(fmt_fn)
    yoy_disp["전년"]  = yoy_disp["전년"].apply(fmt_fn)
    yoy_disp["전년비"] = yoy_disp["전년비"].apply(lambda v: fmt_pct(v, 1) if not pd.isna(v) else "–")
    st.dataframe(yoy_disp, use_container_width=True, hide_index=True)


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

    st.subheader("매체별 월별 추이")
    sel_media_list = st.multiselect("매체 선택", sorted(df["구분_매체명"].unique()),
                                    default=sorted(df["구분_매체명"].unique())[:5])
    by_mm = agg(df[df["구분_매체명"].isin(sel_media_list)],
                ["구분_매체명", "연도", "월", "연월"]).sort_values(["연도", "월"])
    fig3 = px.line(by_mm, x="연월", y=sel_col, color="구분_매체명",
                   color_discrete_map=MEDIA_COLORS, markers=True)
    base_layout(fig3, f"매체별 월별 {sel_label} 추이", 380)
    st.plotly_chart(fig3, use_container_width=True)


# ───────────────────────────────────────────────
# 페이지 3: 캠페인별 성과
# ───────────────────────────────────────────────
def page_campaign(df: pd.DataFrame):
    st.header("🎯 캠페인별 성과")
    if df.empty:
        st.warning("필터 조건에 해당하는 데이터가 없습니다.")
        return

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

    st.subheader("월별 전환 지표 추이")
    monthly = agg(df, ["연도", "월", "연월"]).sort_values(["연도", "월"])
    tab1, tab2 = st.tabs(["CR & 가입률", "객단가"])
    with tab1:
        fig5 = go.Figure()
        for yr in sorted(monthly["연도"].unique()):
            sub = monthly[monthly["연도"] == yr]
            fig5.add_trace(go.Scatter(x=sub["연월"], y=sub["CR(순)"],
                                      name=f"{yr} CR(순)", mode="lines+markers"))
            fig5.add_trace(go.Scatter(x=sub["연월"], y=sub["가입률"],
                                      name=f"{yr} 가입률", mode="lines+markers",
                                      line=dict(dash="dash")))
        base_layout(fig5, "월별 CR(순) & 가입률", 380)
        st.plotly_chart(fig5, use_container_width=True)
    with tab2:
        fig6 = go.Figure()
        for yr in sorted(monthly["연도"].unique()):
            sub = monthly[monthly["연도"] == yr]
            fig6.add_trace(go.Scatter(x=sub["연월"], y=sub["객단가(순)"],
                                      name=f"{yr} 객단가(순)", mode="lines+markers"))
        base_layout(fig6, "월별 객단가(순) 추이", 380)
        st.plotly_chart(fig6, use_container_width=True)


# ───────────────────────────────────────────────
# 페이지 5: 주차별 성과
# ───────────────────────────────────────────────
def page_weekly(df: pd.DataFrame):
    st.header("📅 주차별 성과")
    if df.empty:
        st.warning("필터 조건에 해당하는 데이터가 없습니다.")
        return

    weekly = agg(df, ["연도", "기간_주"]).sort_values(["연도", "기간_주"])

    metric_options = {
        "광고비": "지표_광고비", "거래액": "지표_총결제거래액",
        "순결제ROAS": "순결제ROAS", "CTR": "CTR", "CPM": "CPM",
        "CR(순)": "CR(순)", "객단가(순)": "객단가(순)",
        "가입수": "지표_가입회원", "첫구매수": "지표_순결제고객수(첫구매)",
    }
    sel_label = st.selectbox("비교 지표", list(metric_options.keys()), key="wk_metric")
    sel_col   = metric_options[sel_label]

    fig = go.Figure()
    for yr in sorted(weekly["연도"].unique()):
        sub = weekly[weekly["연도"] == yr].dropna(subset=[sel_col])
        fig.add_trace(go.Scatter(x=sub["기간_주"], y=sub[sel_col],
                                 name=str(yr), mode="lines+markers"))
    base_layout(fig, f"주차별 {sel_label} 추이 (연도 오버레이)", 420)
    fig.update_xaxes(tickangle=-45)
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("주차별 전년비 비교표")
    cur_year = max(df["연도"].unique())
    yoy = yoy_compare(df, cur_year, "기간_주", sel_col)
    fmt_fn = fmt_roas if "ROAS" in sel_label else (fmt_pct if sel_label in ("CTR","CR(순)") else fmt_money if "수" not in sel_label else fmt_num)
    yoy_disp = yoy.copy()
    yoy_disp["당년"]  = yoy_disp["당년"].apply(fmt_fn)
    yoy_disp["전년"]  = yoy_disp["전년"].apply(fmt_fn)
    yoy_disp["전년비"] = yoy_disp["전년비"].apply(lambda v: fmt_pct(v, 1) if not pd.isna(v) else "–")
    st.dataframe(yoy_disp, use_container_width=True, hide_index=True)

    st.subheader("주차별 전체 지표")
    disp_cols = [
        "기간_주", "집행일수", "지표_광고비", "지표_노출수", "지표_클릭수",
        "CTR", "CPM", "CPC", "CPUV", "순결제ROAS",
        "CR(순)", "객단가(순)", "순결제비중",
        "지표_가입회원", "가입CPA", "지표_순결제고객수(첫구매)", "첫구매CPA",
        "신규비중", "윈백비중",
    ]
    tbl = weekly[[c for c in disp_cols if c in weekly.columns]].copy()
    fmt_map = {
        "지표_광고비": fmt_money, "지표_노출수": fmt_num, "지표_클릭수": fmt_num,
        "CTR": fmt_pct, "CPM": fmt_money, "CPC": fmt_money, "CPUV": fmt_money,
        "순결제ROAS": fmt_roas, "CR(순)": lambda v: fmt_pct(v, 3),
        "객단가(순)": fmt_money, "순결제비중": fmt_pct,
        "지표_가입회원": fmt_num, "가입CPA": fmt_money,
        "지표_순결제고객수(첫구매)": fmt_num, "첫구매CPA": fmt_money,
        "신규비중": fmt_pct, "윈백비중": fmt_pct,
    }
    tbl_fmt = tbl.copy()
    for c, fn in fmt_map.items():
        if c in tbl_fmt.columns:
            tbl_fmt[c] = tbl_fmt[c].apply(fn)
    st.dataframe(tbl_fmt, use_container_width=True, hide_index=True)


# ───────────────────────────────────────────────
# 페이지 6: 소재(AF코드) 상세
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
        st.info("👈 사이드바에서 파일을 업로드해주세요.")
        st.markdown("""
        **지원 파일 형식**
        - CSV (UTF-8, UTF-8-BOM, CP949)
        - Excel (xlsx, xlsb)
        - 필수 컬럼: `기간_일자`, `구분_*`, `지표_*`

        **주차별 페이지 활용 시** `기간_주` 컬럼이 있으면 자동 인식합니다.
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
        "📊 전체 요약", "📡 매체별 성과", "🎯 캠페인별 성과",
        "📅 주차별 성과", "🔍 퍼널 & 전환 분석", "🎨 소재 상세",
    ])

    if page == "📊 전체 요약":
        page_summary(filtered, targets)
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
