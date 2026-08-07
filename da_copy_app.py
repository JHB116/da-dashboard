# -*- coding: utf-8 -*-
"""
DA 카피 분석·제안 대시보드 (Streamlit 앱)
─────────────────────────────────────────────────────────────
서비스계정으로 Drive에서 소재안(카피·소구형·이미지속성)과 실적(DA로우)을 자동 수집 →
(기획전번호, 소재순서 _N)으로 조인 → 어떤 소구형·카피·이미지유형이 성과를 만드는지 분석.

배포: Streamlit Cloud 앱의 메인 파일로 `da_copy_app.py` 지정, Secrets 에 [gcp_service_account] 키.
로컬: `.streamlit/secrets.toml` 에 키 넣고 `streamlit run da_copy_app.py`.
"""
import os
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

import da_copy_dashboard as C
import drive_fetch as D

st.set_page_config(page_title="DA 카피 분석·제안", page_icon="📝", layout="wide")

MEDIA_OPTS = ["비즈보드", "디스플레이", "버즈빌"]


@st.cache_resource(show_spinner=False)
def get_svc():
    return D.drive_service(dict(st.secrets["gcp_service_account"]))


@st.cache_data(ttl=3600, show_spinner="실적(DA로우) 불러오는 중…")
def load_perf(media):
    raw, meta = D.fetch_latest_perf(get_svc(), return_meta=True)
    perf = C.add_perf_kpis(C.load_da_perf_bytes(raw, media=media))
    return perf, meta


@st.cache_data(ttl=3600, show_spinner="소재안(카피) 수집 중…")
def load_sojae_all(media, max_weeks):
    """최근 max_weeks 주차 폴더의 해당 매체 소재안을 모아 소재 카탈로그로.
    (기획전번호, 소재N) 중복은 최신 파일 우선. 소재안은 15~40MB라 주차 수를 바운드한다."""
    svc = get_svc()
    frames, files_used = [], []
    weeks = sorted(D.list_children(svc, D.SOJAE_ROOT_ID, mime=D.FOLDER_MIME),
                   key=lambda x: x.get("createdTime", ""), reverse=True)[:max_weeks]
    for wk in weeks:
        sub = D.find_subfolder(svc, wk["id"], media)
        if not sub:
            continue
        for f in sorted(D.list_children(svc, sub["id"], mime=D.XLSX_MIME),
                        key=lambda x: x.get("createdTime", "")):
            try:
                df = C.parse_sojae_bytes(D.download_bytes(svc, f["id"]))
                if len(df):
                    df["_file"] = f["name"]
                    frames.append(df)
                    files_used.append(f["name"])
            except Exception as e:
                st.warning(f"소재안 파싱 실패({f['name']}): {e}")
    if not frames:
        return pd.DataFrame(), files_used
    cat = pd.concat(frames, ignore_index=True)
    cat = cat[cat["메인카피"].astype(str).str.strip() != ""]           # 빈 카피(미작성) 제외
    cat = cat.drop_duplicates(["기획전번호", "소재N"], keep="last")     # 최신 파일 우선
    return cat.reset_index(drop=True), files_used


def bar(df, ycol, xcol, title, higher_better=True, pct=True):
    diff = df[xcol]
    colors = ["#48bb78" if (v >= 0) == higher_better else "#f56565" for v in diff.fillna(0)]
    fig = go.Figure(go.Bar(y=df[ycol], x=diff * (100 if pct else 1), orientation="h",
                           marker_color=colors))
    fig.update_layout(height=max(300, 32 * len(df)), margin=dict(l=8, r=8, t=36, b=8),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", title=title)
    return fig


def fmt_metric(v, metric):
    if pd.isna(v):
        return "–"
    if metric in ("CTR", "CR(순)"):
        return f"{v*100:.2f}%"
    if metric == "ROAS":
        return f"{v*100:.0f}%"
    if metric.startswith("CPC"):
        return f"{v:,.0f}원"
    return f"{v:,.0f}"


def main():
    st.title("📝 DA 카피 분석·제안")

    if "gcp_service_account" not in st.secrets:
        st.error("서비스계정 키가 없습니다. Streamlit Secrets(또는 .streamlit/secrets.toml)에 "
                 "`[gcp_service_account]` 를 넣어주세요.")
        st.stop()

    media = st.sidebar.selectbox("매체", MEDIA_OPTS, index=0)
    metric = st.sidebar.selectbox("성과 주지표", list(C.METRICS), index=0)
    min_n = st.sidebar.number_input("최소 표본(소재 수)", 3, 100, 5)
    max_weeks = st.sidebar.number_input("소재안 수집 주차 수", 1, 30,
                                        int(os.getenv("DA_COPY_MAX_WEEKS", "6")),
                                        help="최근 N개 주차 폴더의 소재안을 수집(파일이 커서 바운드)")
    if st.sidebar.button("🔄 새로 불러오기"):
        st.cache_data.clear()

    perf, pmeta = load_perf(media)
    sojae, files_used = load_sojae_all(media, int(max_weeks))
    if sojae.empty or perf.empty:
        st.info("소재안 또는 실적 데이터가 비어 있어요."); st.stop()

    tagged = C.add_tags(sojae)
    joined = C.join_sojae_perf(tagged, perf)

    c1, c2, c3 = st.columns(3)
    c1.metric("조인된 소재", f"{len(joined):,}")
    c2.metric("소재 카탈로그", f"{len(sojae):,}")
    c3.metric("실적 파일", pmeta["file"].replace("●", ""))
    st.caption(f"매체 {media} · 소재안 {len(files_used)}개 파일 수집 · 실적 {pmeta['createdTime'][:10]} 기준 · "
               "성과는 기획전 전체 집행기간 누적")

    if joined.empty:
        st.warning("조인된 소재가 없어요. (아직 집행 전 주차이거나 매체 불일치일 수 있어요)"); st.stop()

    # 필터
    with st.expander("필터", expanded=False):
        brands = st.multiselect("브랜드", sorted(joined["브랜드"].dropna().unique()))
        if brands:
            joined = joined[joined["브랜드"].isin(brands)]

    tab1, tab2, tab3, tab4 = st.tabs(["🏷 소구형별 성과", "🖼 이미지유형별", "🥇 소재 리더보드", "💡 제안"])

    with tab1:
        st.subheader(f"소구형(카피 자동분류)별 {metric}")
        ap = C.appeal_perf(joined, metric, min_n=int(min_n))
        if ap.empty:
            st.info("표본이 부족해요.")
        else:
            hb = C.METRICS[metric][2]
            st.plotly_chart(bar(ap, "태그", "차이", f"{metric} 보유−미보유", hb,
                                pct=(metric != "ROAS")), use_container_width=True)
            show = ap.copy()
            for c in ["보유가중", "미보유가중"]:
                show[c] = ap[c].map(lambda v: fmt_metric(v, metric))
            show["차이"] = ap["차이"].map(lambda v: fmt_metric(v, metric) if metric == "ROAS"
                                        else f"{v*100:+.2f}%p")
            show["효과크기"] = ap["효과크기"].map(lambda v: "–" if pd.isna(v) else f"{v:+.2f}")
            show["유의성"] = ap["q"].map(C.sig_label)
            st.dataframe(show[["태그", "보유가중", "보유n", "미보유가중", "미보유n", "차이", "효과크기", "유의성"]],
                         use_container_width=True, hide_index=True)
            st.caption("차이 = 해당 소구형 소재의 가중 성과 − 안 쓴 소재. 효과크기·유의성(FDR 보정)으로 우연 여부 판단.")

    with tab2:
        st.subheader(f"이미지유형별 {metric}")
        cp = C.cat_perf(joined, "이미지유형", metric, min_n=int(min_n))
        if cp.empty:
            st.info("표본이 부족해요.")
        else:
            cp2 = cp.copy(); cp2[metric] = cp[metric].map(lambda v: fmt_metric(v, metric))
            cp2["노출"] = cp["노출"].map(lambda v: f"{v:,.0f}")
            st.dataframe(cp2, use_container_width=True, hide_index=True)

    with tab3:
        st.subheader("소재 리더보드 (조인된 개별 소재)")
        lb = joined.copy()
        lb["CTR"] = lb["CTR"].map(lambda v: fmt_metric(v, "CTR"))
        lb["ROAS"] = lb["ROAS"].map(lambda v: fmt_metric(v, "ROAS"))
        lb["노출"] = pd.to_numeric(lb["지표_노출수"], errors="coerce")
        st.dataframe(
            lb.sort_values("노출", ascending=False)[
                ["기획전번호", "소재N", "브랜드", "이미지유형", "소구형_수동",
                 "메인카피", "서브카피", "노출", "CTR", "ROAS"]],
            use_container_width=True, hide_index=True)

    with tab4:
        st.subheader("💡 제안 — 밀어볼 소구형")
        ap = C.appeal_perf(joined, metric, min_n=int(min_n))
        hb = C.METRICS[metric][2]
        good = ap[(ap["q"].notna()) & (ap["q"] < 0.10) & ((ap["차이"] > 0) == hb)] if len(ap) else ap
        if len(good):
            for _, r in good.head(5).iterrows():
                st.markdown(f"- **{r['태그']}** — {metric} 우위 ({C.sig_label(r['q'])}, 소재 {int(r['보유n'])}건)")
        else:
            st.info("아직 통계적으로 뚜렷하게 이기는 소구형이 없어요(표본 누적 필요). "
                    "아래는 방향성 상위입니다:")
            if len(ap):
                topk = ap.head(3)
                for _, r in topk.iterrows():
                    d = fmt_metric(r["차이"], metric) if metric == "ROAS" else f"{r['차이']*100:+.2f}%p"
                    st.markdown(f"- {r['태그']} — {metric} {d} (소재 {int(r['보유n'])}건)")


if __name__ == "__main__":
    main()
