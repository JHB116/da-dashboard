# -*- coding: utf-8 -*-
"""
Drive 연동 — 서비스계정으로 주차별 최신 소재안/실적 파일을 자동으로 가져온다.

인증: 서비스계정 키(JSON). Streamlit 에선 st.secrets["gcp_service_account"],
CLI 테스트에선 파일 경로로 로드. 공유해준 폴더만 읽는다(drive.readonly).

폴더 구조 (실제):
  · 소재안 루트  = 주차 폴더들("8월 1주차" …) → 각 폴더에 매체 하위폴더(비즈보드/디스플레이/버즈빌)
                   → 매체폴더 안 엑셀 중 '가장 최근 업로드(createdTime)' = 그 주 최종 소재안
  · 실적 루트    = '●DA_로우_YYMMDD.xlsx' 들 → 가장 최근 업로드분이 최신 누적 로우

사용 흐름:
  svc = drive_service(sa_info)
  xls_bytes = fetch_latest_sojae(svc, media="비즈보드")     # 소재안 엑셀 bytes
  raw_bytes = fetch_latest_perf(svc)                        # DA로우 엑셀 bytes
"""
import io
import datetime as _dt

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

# 실제 폴더 ID (필요시 secrets/config 로 오버라이드)
SOJAE_ROOT_ID = "1q6_Gwow3UbjJ9kGEnkufywoUfD8dfkda"   # 주차별 소재안 루트
PERF_ROOT_ID  = "1XRFf_ipD_usxYZ6v34Z_lHR3QOpncEGU"   # DA 실적(로우) 루트

FOLDER_MIME = "application/vnd.google-apps.folder"
XLSX_MIME   = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


# ──────────────────────────────────────────────────────────────
# 인증
# ──────────────────────────────────────────────────────────────
def drive_service(sa_info):
    """sa_info = 서비스계정 키 dict → Drive v3 서비스."""
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build
    creds = Credentials.from_service_account_info(sa_info, scopes=SCOPES)
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _sa_from_streamlit():
    import streamlit as st
    return dict(st.secrets["gcp_service_account"])


def _sa_from_file(path):
    import json
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ──────────────────────────────────────────────────────────────
# 탐색 헬퍼
# ──────────────────────────────────────────────────────────────
def list_children(svc, folder_id, mime=None):
    """폴더 직계 자식 목록. mime 지정 시 해당 타입만."""
    q = f"'{folder_id}' in parents and trashed = false"
    if mime:
        q += f" and mimeType = '{mime}'"
    out, token = [], None
    while True:
        resp = svc.files().list(
            q=q, spaces="drive",
            fields="nextPageToken, files(id, name, mimeType, createdTime, modifiedTime)",
            pageToken=token, pageSize=100,
            supportsAllDrives=True, includeItemsFromAllDrives=True,
        ).execute()
        out.extend(resp.get("files", []))
        token = resp.get("nextPageToken")
        if not token:
            break
    return out


def _latest(files, key="createdTime"):
    """'가장 최근 업로드' = createdTime 최댓값 (사용자 기준). 없으면 None."""
    files = [f for f in files if f.get(key)]
    return max(files, key=lambda f: f[key]) if files else None


def find_subfolder(svc, parent_id, name):
    """이름이 일치(공백 무시)하는 하위 폴더 찾기."""
    target = name.replace(" ", "")
    for f in list_children(svc, parent_id, mime=FOLDER_MIME):
        if f["name"].replace(" ", "") == target:
            return f
    return None


def latest_week_folder(svc, root_id=SOJAE_ROOT_ID):
    """주차 폴더 중 가장 최근 생성분(= 최신 주차)."""
    return _latest(list_children(svc, root_id, mime=FOLDER_MIME), key="createdTime")


def download_bytes(svc, file_id, chunk_mb=5, tries=4):
    """파일 원본 bytes 다운로드. 대용량(수십 MB)·불안정 네트워크 대비 청크+재시도.
    청크 실패 시 처음부터 재시작(부분 IncompleteRead 방지)."""
    from googleapiclient.http import MediaIoBaseDownload
    last = None
    for attempt in range(tries):
        try:
            buf = io.BytesIO()
            req = svc.files().get_media(fileId=file_id)
            dl = MediaIoBaseDownload(buf, req, chunksize=chunk_mb * 1024 * 1024)
            done = False
            while not done:
                _, done = dl.next_chunk(num_retries=3)
            return buf.getvalue()
        except Exception as e:  # IncompleteRead·타임아웃 등 → 재시작
            last = e
    raise last


# ──────────────────────────────────────────────────────────────
# 상위 API
# ──────────────────────────────────────────────────────────────
def fetch_latest_sojae(svc, media="비즈보드", root_id=SOJAE_ROOT_ID, return_meta=False):
    """최신 주차 → 매체 하위폴더 → 가장 최근 업로드 엑셀 bytes."""
    wk = latest_week_folder(svc, root_id)
    if not wk:
        raise FileNotFoundError("주차 폴더를 찾지 못했습니다.")
    sub = find_subfolder(svc, wk["id"], media)
    if not sub:
        raise FileNotFoundError(f"'{wk['name']}' 안에 '{media}' 폴더가 없습니다.")
    xls = _latest(list_children(svc, sub["id"], mime=XLSX_MIME), key="createdTime")
    if not xls:
        raise FileNotFoundError(f"'{media}' 폴더에 엑셀이 없습니다.")
    data = download_bytes(svc, xls["id"])
    if return_meta:
        return data, {"week": wk["name"], "media": media, "file": xls["name"],
                      "createdTime": xls["createdTime"]}
    return data


def fetch_latest_perf(svc, root_id=PERF_ROOT_ID, name_prefix="DA_로우", return_meta=False):
    """실적 루트에서 '가장 최근 업로드'된 DA로우 엑셀 bytes."""
    cands = [f for f in list_children(svc, root_id, mime=XLSX_MIME)
             if name_prefix.replace(" ", "") in f["name"].replace(" ", "")]
    xls = _latest(cands, key="createdTime")
    if not xls:
        raise FileNotFoundError(f"실적 루트에 '{name_prefix}' 파일이 없습니다.")
    data = download_bytes(svc, xls["id"])
    if return_meta:
        return data, {"file": xls["name"], "createdTime": xls["createdTime"]}
    return data


if __name__ == "__main__":
    # 설정 검증용 드라이런: python drive_fetch.py <서비스계정키.json>
    import sys
    if len(sys.argv) < 2:
        print("usage: python drive_fetch.py <service_account_key.json>")
        raise SystemExit(1)
    svc = drive_service(_sa_from_file(sys.argv[1]))
    wk = latest_week_folder(svc)
    print("최신 주차 폴더:", wk["name"] if wk else "(없음)", "· created", wk and wk["createdTime"])
    if wk:
        for f in list_children(svc, wk["id"], mime=FOLDER_MIME):
            print("  └ 매체폴더:", f["name"])
    try:
        _, m = fetch_latest_sojae(svc, media="비즈보드", return_meta=True)
        print("소재안 최신:", m)
    except Exception as e:
        print("소재안 조회 실패:", e)
    try:
        _, m = fetch_latest_perf(svc, return_meta=True)
        print("실적 최신:", m)
    except Exception as e:
        print("실적 조회 실패:", e)
