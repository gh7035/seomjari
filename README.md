# 섬자리 (seomjari)

> 성수기 착시를 걷어내는 제주 창업 입지 Agent
> 제주 AI·빅데이터 활용 AI Agent 개발 챌린지 출품작

제주에서 창업하려는 사람이 업종·지역·조건을 입력하면, Agent가 제주데이터허브 데이터를 스스로 조회·결합·계산해 **관광 의존도, 계절 변동성, 경쟁 밀도, 시장 트렌드**를 진단하고 **3D 지도와 근거 리포트**, **대안 지역**을 제시합니다.

## 빠른 실행 (평가 환경: Python만 필요)

```bash
cp .env.example .env        # LLM 키 설정 (없으면 LLM_PROVIDER=none으로 규칙 기반 모드)
make setup                  # Python 가상환경 + 의존성
make run                    # http://localhost:8000
```

`apps/api/static/`에 프론트 빌드 결과와 `data/processed/`에 전처리 데이터가 포함되어 있어 Node 설치나 원본 데이터 없이 실행됩니다.

## 개발 환경

```bash
make setup && make setup-web
make data                   # data/raw CSV → data/processed parquet
make dev                    # API :8000 + Web :5173
make build                  # 프론트 빌드 → apps/api/static
make test
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

| ID | 데이터 | 다운로드 |
|---|---|---|
| D1 | 주제1: 제주 예비창업자를 위한 업종별 카드 매출과 매장수 (_18, _19, _21) | https://jejudatahub.net/data/view/data/746 |
| D2 | 주제3: 상권분석을 위한 유동인구에 따른 카드 매출액 변화 (_17 ~ _21) | https://jejudatahub.net/data/view/data/748 |
| D3 | 업종별 성별 카드 이용 정보 | https://jejudatahub.net/data/view/data/1048 |
| D4 | 제주특별자치도 상가(상권) 정보 | https://jejudatahub.net/data/view/data/793 |

원본 CSV는 `data/raw/`에 넣습니다 (git 제외). 상세는 `docs/data_spec.md`.

## AI 활용 고지
- 서비스 내 사용 모델: (확정 후 기재)
- 개발 과정 AI 도구 활용 범위: (확정 후 기재)

## 오류·제약사항
- 지역별 카드 데이터는 2021년 5월까지 제공되어, 기준 기간을 2018~2019년(코로나 이전)으로 설정
- 이용금액은 특정 카드사 기준 데이터일 수 있어 화면에는 비중·배율·순위 위주로 표시
