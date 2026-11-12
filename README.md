# postalk-cardnews

POSTALK 백엔드가 보내는 사진 6장으로 1080×1350 PNG 카드뉴스 3장을 만듭니다. 미니멀과 크리스마스 테마를 지원합니다. GPT가 사진과 요청을 바탕으로 카드 문구를 만들고, Chromium이 사진과 템플릿을 합성합니다. OpenAI 연결 없이도 기본 문구로 렌더링할 수 있습니다.

## Railway 배포

POSTALK 백엔드와 같은 Railway 프로젝트 및 환경에 Docker 서비스로 배포합니다. 내부 서비스 이름을 `postalk-cardnews`, 포트를 `8000`으로 설정한 경우 백엔드의 `CARDNEWS_API_URL`은 `http://postalk-cardnews.railway.internal:8000`입니다.

| 서비스 변수 | 설정 |
| --- | --- |
| `SUPABASE_URL` | 백엔드와 같은 Supabase 프로젝트 URL |
| `CARDNEWS_INTERNAL_API_KEY` | 백엔드와 동일한 비밀 값 |
| `OPENAI_API_KEY` | 사진 분석과 문구 생성을 위한 서버 키 |
| `PORT` | 예시 `8000` |

상태 확인은 `GET /healthz`입니다. 백엔드는 `POST /cardnews/renders`에 작업 ID, 테마, 가게 정보, 역할별 다운로드 URL 6개, PNG 업로드 URL 3개를 보냅니다. 백엔드가 서명 URL을 발급하고 최종 결과를 보관함에 등록합니다.

### 로컬 검증

```powershell
python -m pip install -r requirements.txt
python -m playwright install chromium
python -c "from cardnews.design import ensure_fonts; ensure_fonts()"
python -m unittest discover -s tests
```

테스트는 Supabase 요청을 모의 응답으로 처리합니다. 설치된 Chromium을 사용하려면 `CARDNEWS_CHROMIUM_PATH`에 실행 파일 경로를 지정합니다.
