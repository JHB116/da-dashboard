# -*- coding: utf-8 -*-
"""
캐시 빌더 — 무거운 Drive 다운로드/파싱을 '미리 1회' 수행해 작은 캐시로 저장.
앱은 이 캐시(수백 KB)만 읽으므로, 전체 기간을 담아도 즉시 로딩된다.

산출물(cache/):
  · perf_<media>.parquet   : (기획전번호, 소재N) 소재별 성과 집계 — 전체 누적 실적에서
  · sojae_<media>.parquet  : 전 주차 소재 카탈로그(카피·브랜드·이미지유형 등)
  · meta_<media>.json      : 실적 파일명·날짜, 소재안 파일 수, 빌드시각

인증: 서비스계정 JSON을 env GCP_SA_JSON(문자열) 또는 인자 경로로.
실행: python build_cache.py [비즈보드|디스플레이|버즈빌] [service_account.json]
CI(GitHub Actions)에서 매일 돌려 cache/ 를 커밋하면 앱은 항상 최신·고속.
"""
import os
import sys
import json
import datetime as _dt

import da_copy_dashboard as C
import drive_fetch as D


def _svc(key_path=None):
    if os.getenv("GCP_SA_JSON"):
        return D.drive_service(json.loads(os.environ["GCP_SA_JSON"]))
    if key_path:
        return D.drive_service(json.load(open(key_path, encoding="utf-8")))
    raise SystemExit("서비스계정 키가 없습니다 (env GCP_SA_JSON 또는 인자 경로).")


def fetch_all_sojae(svc, media, weeks=None):
    """모든(또는 최근 weeks) 주차 폴더의 해당 매체 소재안을 모아 카탈로그로."""
    import pandas as pd
    wkf = sorted(D.list_children(svc, D.SOJAE_ROOT_ID, mime=D.FOLDER_MIME),
                 key=lambda x: x.get("createdTime", ""), reverse=True)
    if weeks:
        wkf = wkf[:weeks]
    frames, files = [], []
    for wk in wkf:
        sub = D.find_subfolder(svc, wk["id"], media)
        if not sub:
            continue
        for f in sorted(D.list_children(svc, sub["id"], mime=D.XLSX_MIME),
                        key=lambda x: x.get("createdTime", "")):
            try:
                df = C.parse_sojae_bytes(D.download_bytes(svc, f["id"]))
            except Exception as e:
                print(f"  · 파싱실패 {f['name']}: {e}")
                continue
            if len(df):
                df["_file"] = f["name"]
                frames.append(df)
                files.append(f["name"])
    if not frames:
        return pd.DataFrame(), files
    cat = pd.concat(frames, ignore_index=True)
    cat = cat[cat["메인카피"].astype(str).str.strip() != ""]
    cat = cat.drop_duplicates(["기획전번호", "소재N"], keep="last").reset_index(drop=True)
    return cat, files


def main():
    media = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].endswith(".json") else "비즈보드"
    key_path = next((a for a in sys.argv[1:] if a.endswith(".json")), None)
    svc = _svc(key_path)
    os.makedirs("cache", exist_ok=True)

    print(f"[1/2] 실적 집계 ({media}) …")
    raw, pmeta = D.fetch_latest_perf(svc, return_meta=True)
    perf = C.add_perf_kpis(C.load_da_perf_bytes(raw, media=media))
    perf.to_parquet(f"cache/perf_{media}.parquet", index=False)
    print(f"      소재별 성과 {len(perf)}행 저장")

    print(f"[2/2] 소재안 전 주차 수집 ({media}) …")
    sojae, files = fetch_all_sojae(svc, media)
    sojae.to_parquet(f"cache/sojae_{media}.parquet", index=False)
    print(f"      소재 카탈로그 {len(sojae)}행 · 파일 {len(files)}개 저장")

    meta = {
        "media": media,
        "perf_file": pmeta.get("file"),
        "perf_date": pmeta.get("createdTime", "")[:10],
        "sojae_files": len(files),
        "sojae_rows": int(len(sojae)),
        "perf_rows": int(len(perf)),
        "built_at": _dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }
    json.dump(meta, open(f"cache/meta_{media}.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print("완료:", meta)


if __name__ == "__main__":
    main()
