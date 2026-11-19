# postalk-cardnews

POSTALK 백엔드가 보내는 사진 6장으로 1080×1350 PNG 카드뉴스 4장(표지 1장과 본문 3장)을 만듭니다. 미니멀과 크리스마스 테마를 지원합니다. GPT가 사진과 요청을 바탕으로 카드 문구를 만들고, Chromium이 사진과 템플릿을 합성합니다. OpenAI 연결 없이도 기본 문구로 렌더링할 수 있습니다.

## Railway 배포

POSTALK 백엔드와 같은 Railway 프로젝트 및 환경에 Docker 서비스로 배포합니다. 내부 서비스 이름을 `postalk-cardnews`, 포트를 `8000`으로 설정한 경우 백엔드의 `CARDNEWS_API_URL`은 `http://postalk-cardnews.railway.internal:8000`입니다.

| 서비스 변수 | 설정 |
| --- | --- |
| `SUPABASE_URL` | 백엔드와 같은 Supabase 프로젝트 URL |
| `CARDNEWS_INTERNAL_API_KEY` | 백엔드와 동일한 비밀 값 |
| `OPENAI_API_KEY` | 선택. 사진 분석과 문구 생성을 위한 서버 키 |
| `PORT` | 예시 `8000` |

상태 확인은 `GET /healthz`입니다. 응답에는 서비스 이름과 현재 미디어 저장소(`supabase`)가 포함됩니다. 백엔드는 `POST /cardnews/renders`에 작업 ID, 테마, 가게·메뉴 정보, 역할별 다운로드 URL 6개, PNG 업로드 URL 4개를 보냅니다. 백엔드가 서명 URL을 발급하고 최종 결과를 보관함에 등록합니다.

백엔드와 이 서비스 사이의 전체 요청 흐름과 배포 점검 순서는 [POSTALK 백엔드 연동 안내](docs/backend-integration.md)에 정리했습니다.

## 내부 API

이 서비스는 프론트엔드가 직접 호출하지 않습니다. POSTALK 백엔드만 `x-cardnews-api-key` 헤더로 호출합니다.

| 메서드·경로 | 인증 | 설명 |
| --- | --- | --- |
| `GET /healthz` | 없음 | Railway 상태 확인. `{ "status": "ok" }`를 반환합니다. |
| `POST /cardnews/renders` | `x-cardnews-api-key` | 사진 6장으로 카드뉴스 PNG 4장을 생성합니다. |

### `POST /cardnews/renders`

```json
{
  "job_id": "생성 작업 UUID",
  "theme": "christmas",
  "store_name": "가게 이름",
  "area": "시장 또는 지역",
  "menu_name": "대표 메뉴",
  "store_description": "가게 소개",
  "store_address": "가게 주소",
  "menus": ["대표 메뉴", "두 번째 메뉴"],
  "menu_details": [
    { "name": "대표 메뉴", "description": "메뉴 설명" },
    { "name": "두 번째 메뉴" }
  ],
  "direction": "따뜻한 겨울 조명과 빨간 포인트",
  "photos": [
    { "role": "bowl", "download_url": "Supabase 서명 다운로드 URL" },
    { "role": "zoom", "download_url": "..." },
    { "role": "food1", "download_url": "..." },
    { "role": "food2", "download_url": "..." },
    { "role": "store1", "download_url": "..." },
    { "role": "store2", "download_url": "..." }
  ],
  "uploads": ["PNG 1 업로드 URL", "PNG 2 업로드 URL", "PNG 3 업로드 URL", "PNG 4 업로드 URL"]
}
```

- `theme`: `minimal` 또는 `christmas`
- 사진 역할 6개는 빠짐없이 한 번씩만 있어야 하며, 같은 파일을 재사용할 수 없습니다.
- 입력과 출력 URL은 같은 Supabase `uploads` 버킷의 유효한 서명 URL만 허용합니다.
- 생성 결과는 1080×1350 PNG 4장입니다.

성공하면 카드별 Storage 경로와 바이트 수, 템플릿 키, 인스타그램 캡션과 해시태그를 반환합니다. 첫 출력은 표지입니다. 이전 백엔드가 업로드 URL 3개를 보내면 본문 3장만 반환합니다.

운영 백엔드는 `Accept: application/x-ndjson`으로 진행 단계와 최종 결과를 받습니다. 아래는 단일 JSON 응답 본문이며 스트리밍에서는 `result` 이벤트 안에 들어갑니다.

```json
{
  "cards": [{ "key": "stores/.../generated/job-1.png", "bytes": 123456 }],
  "template": "x1",
  "fallback": false,
  "caption": "대표 메뉴를 만나보세요.",
  "hashtags": ["#대표메뉴"]
}
```

`401`은 내부 키 불일치, `400`은 입력 URL·사진 역할·출력 경로 오류, `422`는 요청 필드 검증 오류, `503`은 서비스 내부 키 미설정입니다. 렌더링 또는 Storage 전송에 실패하면 단일 JSON 모드는 `502`, 스트리밍 모드는 `RENDER_FAILED` 이벤트를 반환합니다. 서명 URL과 내부 키는 로그나 클라이언트에 노출하지 않습니다.

### 로컬 검증

```powershell
python -m pip install -r requirements.txt
python -m playwright install chromium
python -c "from cardnews.design import ensure_fonts; ensure_fonts()"
python -m unittest discover -s tests
```

테스트는 Supabase 요청을 모의 응답으로 처리합니다. 설치된 Chromium을 사용하려면 `CARDNEWS_CHROMIUM_PATH`에 실행 파일 경로를 지정합니다.

## 운영 검증 기록

PNG 생성부터 JPEG 게시 사본 변환, 캐러셀 4장 실제 게시와 중복 방지까지 확인한 결과는 [백엔드의 게시 검증 기록](https://github.com/Superkid0714/Postalk_backend/blob/main/docs/incidents/20261118-instagram-publication.md)에 정리했습니다.

## 사진 라벨과 입력 메뉴 우선순위

사진 분석보다 사용자가 입력한 메뉴를 우선합니다. `menus`가 없으면 `menu_details[].name`, 그다음 기존 `menu_name`을 사용합니다.

| 사진 역할 | 라벨 기준 |
| --- | --- |
| bowl · zoom | 첫 번째 메뉴 |
| food1 | 두 번째 메뉴 |
| food2 | 세 번째 메뉴 |
| store1 · store2 | 가게·공간 문구. 음식 이름 사용 안 함 |

입력 메뉴에 맞게 사진을 제출해야 이 대응이 정확합니다. 입력하지 않은 메뉴 역할은 확인된 사진 분석 결과가 있을 때만 음식 이름을 사용하고, 없으면 중립적인 기본 라벨을 사용합니다. OpenAI 미설정·호출 실패 시에도 입력 메뉴 순서는 유지합니다.

사진 분석과 메뉴 입력 근거가 모두 없으면 광고 문구 생성 호출을 건너뛰고 기본 카드 문구·캡션을 사용합니다(`fallback=true`). 사진 분석과 문구 생성은 운영 기본 모델에서 단계별 1회, OpenAI 타임아웃 60초·SDK 자동 재시도 0회로 호출합니다. 백엔드의 180초 요청 제한을 고려해 SDK와 대체 모델의 연쇄 재시도를 사용하지 않습니다.
