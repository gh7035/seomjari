# 섬자리 (seomjari)

> 성수기 착시를 걷어내는 제주 창업 입지 Agent
> 제주 AI·빅데이터 활용 AI Agent 개발 챌린지 출품작

제주에서 창업하려는 사람이 업종·지역·조건을 입력하면, Agent가 제주데이터허브 데이터를 조회·결합·계산해 **관광 의존도, 계절 변동성, 경쟁 밀도, 수요, 유동, 생존, 최근 개폐업**을 진단하고 **3D 지도와 근거 리포트**, **대안 지역**을 제시합니다.

## 빠른 실행 (평가 환경: Python만 필요)

```bash
cp .env.example .env        # LLM 키 설정 (없으면 LLM_PROVIDER=none으로 규칙 기반 fallback)
make setup                  # Python 가상환경 + 의존성
make run                    # http://localhost:8000
```

`apps/api/static/`에 프론트 빌드 결과와 `data/processed/`에 전처리 parquet이 포함되어 있어 Node 설치나 원본 CSV 없이 실행됩니다.

## 개발 환경

```bash
make setup && make setup-web
make data                   # data/raw CSV → data/processed parquet
make dev                    # API :8000 + Web :5173
make build                  # 프론트 빌드 → apps/api/static
make test                   # pytest (grounding + 재현성)
```

## 구조

| 경로 | 언어 | 역할 |
|---|---|---|
| `apps/api` | Python | FastAPI, SSE 진행 스트림, 정적 파일 서빙 |
| `apps/web` | TypeScript | React + deck.gl 3D 지도 UI |
| `packages/agent` | Python | Agent 루프, 도구, 프롬프트, LLM 어댑터 |
| `packages/pipeline` | Python | 원본 데이터 전처리, 업종 매핑표 |
| `packages/schema` | JSON | 리포트 계약 (Python·TS 공용) |

## 데이터 (모두 제주데이터허브)

| ID | 데이터 | 다운로드 | 파일명 |
|---|---|---|---|
| D1 | 주제1: 업종별 카드 매출과 매장수 (_18, _19, _21) | https://jejudatahub.net/data/view/data/746 | `data/raw/d1_card_{18,19,21}.csv` |
| D2 | 주제3: 유동인구에 따른 카드 매출액 변화 (_17~_21) | https://jejudatahub.net/data/view/data/748 | `data/raw/d2_footfall_{17..21}.csv` |
| D3 | 업종별 성별 카드 이용 정보 | https://jejudatahub.net/data/view/data/1048 | `data/raw/d3_industry_gender.csv` |
| D4 | 제주특별자치도 상가(상권) 정보 | https://jejudatahub.net/data/view/data/793 | `data/raw/d4_stores.csv` |
| D5 | 제주특별자치도 음식점 목록(통합) | https://jejudatahub.net/data/view/data/780 | `data/raw/d5_restaurants.csv` |

D3는 `trend_yearly.parquet`까지 만들어지지만 `get_trend`는 아직 리포트에 연결되지 않습니다. D6·D9 원본이 없으면 그 단계만 건너뛰고, 제출된 `data/processed/`에는 해당 parquet이 없습니다.

원본 CSV는 `data/raw/`에 넣습니다(git 제외). 상세 전처리 흐름과 지표 정의는 `docs/data_spec.md`, 실행 결과는 `docs/results.md`.

## 사용자 매뉴얼

1. 브라우저에서 `http://localhost:8000` 접속.
2. 사이드바에서 **업종**(16종), **희망 지역**(43개 행정동, 비우면 지역 추천 모드), **주 고객**(관광객/도민/상관없음), **타깃 연령**, **리스크 성향**(안정/균형/공격)을 설정.
3. **진단 시작** → 상단에 Agent 진행 단계가 실시간으로 표시되고, 3D 지도와 진단 카드가 그려짐.
4. 지도 상단의 레이어 토글(수요/관광/공급/유동/생존)로 보고 싶은 지표 전환, 하단 월 슬라이더로 1~12월 패턴 비교.
5. 리포트 하단 "근거와 한계" 펼치면 데이터 출처(D1·D2·D4·D5)·기간·주의사항 확인 가능.
6. 아래 채팅 입력에 "그럼 한림은 어때?"처럼 묻면 직전 업종을 유지하고 그 지역으로 다시 진단한다. 업종만 바꾸면 지역은 비워져 지역 추천으로 넘어간다.

## 오류·제약사항

- 지역별 카드 데이터는 **2021-05**까지 제공 → 기준 기간을 2018~2019년(코로나 이전)으로 설정.
- 이용금액은 특정 카드사 기준 표본일 수 있어 UI는 **비중·배율·순위** 위주로 표시.
- 업종 매핑은 16종(`packages/pipeline/category_map.csv`)이다. 카드 매출(D1)이 있는 11종만 수요·관광·계절 신호가 나오고, PC방·미용실·네일샵·헬스장·노래방은 점포·유동만 있어 점수를 보류한다. 매핑 밖 업종은 업종 선택지를 되묻는다.
- 타깃 연령은 폼에 저장되지만, 유동 데이터에 연령 열이 없고 연령 비중은 점수에 들어가지 않는다.
- LLM 공급자가 없거나(`LLM_PROVIDER=none`) Gemini 리포트 검증에 실패하면 규칙 기반 루프가 동작한다. 규칙 루프의 수치는 결정론적이다.

## API 키 발급 방법 (선택)

### 제주데이터허브 — D9 방문목적별 입도객
1. https://open.jejudatahub.net 로그인
2. 데이터 상세(예: 580번 "방문목적별 입도객")에서 "프로젝트 담기"
3. 내 프로젝트 → projectKey 복사 → `.env` 의 `JEJU_HUB_PROJECT_KEY` 에 설정
4. `make data` 시 2018-01 ~ 현재까지 자동 수집, `data/raw/d9_visitors_purpose.csv` 에 캐시됨
5. 다음 실행부터는 **키가 없어도** 캐시만 있으면 동일하게 동작

### 공공데이터포털 — D10 지역별 관광 수요 강도 (선택, 미구현)
1. https://data.go.kr 에서 "한국관광공사_지역별 관광 수요 강도" 활용신청 (자동 승인)
2. 일반 인증키 발급 → `.env` 의 `TOUR_API_KEY` 설정

**키가 없어도** 동봉된 `data/processed/`만으로 진단은 동작한다. D9 parquet은 제출물에 없으므로 입도객 신호는 나오지 않는다.

## AI 활용 고지

- **서비스 내 AI 모델**: 기본은 LLM 없음(규칙 기반 fallback). 구현된 외부 공급자는 Gemini(`LLM_PROVIDER=gemini`, `packages/agent/llm.py`)뿐이다. `openai`와 `anthropic`은 호출 시 미구현 예외가 나고 규칙 루프로 떨어진다. 센터 PC VRAM 제약(3GB)으로 로컬 LLM은 쓰지 않는다.
- **개발 과정 AI 활용**: Anthropic Claude 코드 어시스턴트로 파이프라인/루프 초안 작성, 모든 수치는 `tests/test_grounding.py`로 검증.
