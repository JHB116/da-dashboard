# da-dashboard
lf da dashboard

## 업로드 파일 영구 보관 (구글 드라이브)

마지막에 올린 로데이터·목표 파일은 서버에 보관되어 재업로드 없이 조회됩니다.
앱 재부팅 후에도 유지하려면 Streamlit Cloud → 앱 Settings → Secrets 에 아래를 넣고,
드라이브 폴더 `DA 대시보드 보관`을 서비스계정 이메일(`client_email`)에 **편집자**로 공유하세요.

```toml
[gdrive]
folder_id = "1fRGaReqs68Q959C_eL8Hii9Iptt73kuz"

[gcp_service_account]
# 서비스계정 JSON 키 파일의 내용을 그대로 옮겨 적기
type = "service_account"
project_id = "..."
private_key_id = "..."
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email = "...@....iam.gserviceaccount.com"
client_id = "..."
token_uri = "https://oauth2.googleapis.com/token"
```

폴더 안의 `da_dashboard_raw.bin`, `da_dashboard_report.bin` 파일은 지우지 마세요
(서비스계정은 개인 드라이브에 새 파일을 만들 수 없어, 이 파일을 덮어쓰는 방식으로 보관합니다).
