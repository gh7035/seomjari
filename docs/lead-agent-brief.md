# 섬자리 점수 개선 — 총괄 에이전트 지시서

이 문서는 구현 지시서다. 대화 이력 없이 이 파일만 보고 작업을 나눠 실행한다. 범위 밖 리팩터, 주제 변경, 점수 공식 재설계는 하지 않는다. 사용자가 커밋을 말하기 전에는 커밋하지 않는다.

## 목표

평가자가 `https://seomjari.duckdns.org/` 에서 보는 진단이, 서버가 계산한 수치 위에 모델이 쓴 결론 한 문장이 되게 한다. 유동인구 기간을 수요 분석 창과 맞추고, D6 근거에 실제 순증이 나오게 하며, 채팅과 화면이 그 결과를 숨기지 않게 한다.

기대 점수(내부 코드 평가 77/100 기준, 보장값 아님):

| 평가항목 | 배점 | 현재 | 목표 | 남기는 이유 |
|---|---:|---:|---:|---|
| 분석 주제의 타당성과 창의성 | 15 | 12 | 13 | 주제를 바꾸지 않는다. 결론 문장만 제주 질문과 숫자를 같이 말하게 한다. |
| 필수 데이터 활용 적절성 | 20 | 16 | 18 | D9 숫자는 키가 없으면 만들지 않는다. 카드 매출이 없는 5개 업종은 점수 null을 유지한다. |
| AI Agent 기술성 및 완성도 | 25 | 17 | 22 | 수치는 계속 서버가 계산한다. 모델의 역할은 판단 문장이다. |
| 편의성 및 실용성 | 25 | 19 | 22 | 지도와 폼 구조는 유지한다. |
| 결과 신뢰성 및 재현성 | 15 | 13 | 14 | 원본 CSV는 저장소에 넣지 않는다. |
| 합계 | 100 | 77 | 약 89 | |

동점 우선순위는 Agent, 편의성, 데이터 순이다. Phase 1이 먼저다.

## 제품 한 줄

제주에서 창업하려는 사람이 업종·지역을 입력하면, 제주데이터허브 D1–D6로 관광 의존도·계절 변동·수요·유동·경쟁·생존·최근 개폐업을 진단하고 3D 지도와 대안 지역을 보여 준다.

- 백엔드: `apps/api/main.py` (FastAPI, SSE)
- Agent: `packages/agent/loop.py`, `tools.py`, `signals.py`, `prompts.py`, `llm.py`
- 전처리: `packages/pipeline/build_data.py` (이번 작업에서 재빌드하지 않는다. parquet을 읽는 쪽만 고친다.)
- 프론트: `apps/web` → 빌드 결과가 `apps/api/static`
- 데이터: `data/processed/*.parquet`, `data/processed/registry.json`
- 실행: `make setup && make test`, 평가 실행은 `make run` (http://localhost:8000)
- 기본 LLM: `.env`의 `LLM_PROVIDER`. 로컬 기본 예시는 `none`(규칙 루프). 공개 서버는 `gemini`이며 2026-11-20 확인 시 `402 RESOURCE_EXHAUSTED`로 규칙 루프에 떨어졌다.

## 하지 말 것

- 분석 주제를 바꾸거나 업종·신호 7개의 이름을 바꾸지 않는다.
- D6 생멸을 8번째 신호나 종합 점수 가중치에 넣지 않는다. 업종과 무관한 읍면 통계다.
- D9 입도객 숫자를 추정하거나 빈 parquet을 만들어 신호가 있는 척하지 않는다. 키가 없으면 한계 문장 “D9 입도객 없음”을 유지한다.
- 모델이 계산한 점수·신호·순위를 리포트에 남기지 않는다. 모델 출력은 `summary`와 대안 `why`뿐이다.
- `openai`, `anthropic` 공급자를 이번 범위에서 구현하지 않는다. 지금은 미구현 예외 후 규칙 루프다.
- 로컬 LLM을 추가하지 않는다. 센터 PC VRAM은 3GB다.
- 원본 CSV(`data/raw`)를 커밋하지 않는다. `make data`는 돌리지 않는다.
- `.env`의 API 키를 로그, 문서, 커밋에 넣지 않는다.
- 기획서 PDF와 `docs/results.md`의 문제 정의 수치(KOSIS, 한국은행)는 이번 코드 변경의 근거로 다시 쓰지 않는다. `results.md`에서 고치는 곳은 유동 지표처럼 코드 결과가 바뀌는 칸뿐이다.

## 확인된 결함

1. Gemini 경로는 도구를 모델이 반복 호출한다. `packages/agent/prompts.py`는 진단 시 도구 8개를 호출한 뒤, 빨간 신호가 2개 이상이면 `compare_places`를 또 호출하라고 한다. `AGENT_MAX_TOOL_CALLS` 기본값은 8이다 (`packages/agent/config.py`). 애월읍 카페는 빨간 신호가 3개라 지시를 따르는 모델은 9번째에서 잘리고, `loop.py`의 `_fallback_report`가 규칙 리포트로 바꾼다.
2. `_enforce_server_fields`는 가용 신호가 부족할 때만 `score`를 null로 만든다. 정상 구간에서는 모델이 쓴 점수를 덮어쓰지 않는다.
3. 폴백 때 `rep["mode"] = "llm_fallback"`으로 리포트 모드를 덮는다 (`loop.py` `_fallback_report`). `full`/`partial`이 사라진다. `apps/web/src/components/ReportCard.tsx`는 `report.mode === 'partial'`일 때만 제한 분석 배지를, `report.mode === 'llm_fallback'`일 때만 “LLM 오류로 규칙 기반으로 재생성된 리포트입니다”를 그린다.
4. `apps/web/src/types.ts`의 `ReportMode`는 `'llm' | 'fallback' | 'partial' | 'llm_fallback'`이다. `docs/CONTRACT.md`와 서버는 `full`도 보낸다. 타입에 `full`이 없다.
5. 유동 평균은 `signals.py` `compute_footfall`과 `tools.py` `get_footfall`이 `footfall_monthly` 전기간(2017-01~2021-05, 1,934행)을 쓴다. 수요·관광·계절은 2018-01~2019-12만 쓴다. 같은 리포트에서 코로나 포함 유동과 코로나 이전 매출이 나란히 순위가 된다.
6. D6 근거는 `loop.py` `_build_report`가 `records[-1]`만 본다. 애월읍의 마지막 연도 2023년 순증이 비어 화면에 “2023년 순증 자료 없음”이 나온다. 순증이 있는 더 이른 연도는 무시된다.
7. `apps/api/main.py` `chat()`이 후속 질문 폼을 만들 때 `"ages": []`로 고정한다. 주 고객과 리스크는 이전 값을 유지한다. 연령만 사라진다. 연령은 `signals.py` `compute_demand`에서 수요 순위에만 반영되고, 유동 parquet에는 연령 열이 없다.
8. `apps/web/src/components/ContextPanel.tsx`의 “선택 N개 남음”은 업종·지역 공백에 더해 `customer === 'any'`와 `ages.length === 0`을 미선택으로 센다. 진단이 끝난 뒤에도 “선택 2개 남음”이 남는다.
9. `tests/test_grounding.py`의 수치 검사는 요약·근거·대안 문자열이 도구 요약에 있는지만 본다. 신호 값과 `score_risk` 결과를 직접 비교하지 않는다. 규칙 루프에서는 리포트와 요약이 같은 함수에서 나와, 계산식이 틀려도 이 테스트가 통과할 수 있다.
10. `docs/SPEC.md`는 규칙 루프가 `get_dong_vitality`를 호출하지 않는다고 적는다. `loop.py` `_run_fallback`은 호출한다.

기준 시나리오(규칙 루프, 유동 기간을 고치기 전 실측):

- 안정형·주 고객 상관없음·애월읍·카페: 점수 46. 관광 74.5% 빨강, 계절 1.96배 노랑, 수요 6위/41 초록, 유동 3위/43 초록, 점포 225개 빨강, 3년 생존 66.3%(n=261) 빨강, 24개월 개업 53/폐업 36 초록. 대안 일도2동 78, 화북동 75, 이도2동 72.
- 공개 사이트의 자연어 입력은 리스크가 균형이라 점수 49, 대안 77·73·70이었다. 안정형 46과 다른 것은 가중치 때문이다. 버그가 아니다.
- 네일샵·PC방은 가용 신호 2/7, 점수 null, `mode=partial`.

유동 기간을 자르면 유동 순위·인원·종합 점수가 위 숫자와 달라질 수 있다. 달라지면 테스트를 옛 숫자에 묶지 말고 새 결정론 값으로 갱신하고, `docs/results.md`의 유동 칸도 그 값으로 고친다.

## Phase 1 — 모델은 문장만, 숫자는 서버가

진단당 Gemini 호출은 1회다. 지역과 업종이 정해진 뒤에는 모델이 도구를 고르지 않는다.

1. `_run_llm`에서 도구 반복(`while used < max_calls`)을 대표 경로에서 뺀다.
2. 지역·업종 해석과 도구 실행은 기존 `_run_fallback`의 순서를 재사용한다. 순서: `get_demand`, `get_supply`, `get_footfall`, `get_survival`, `get_recent_openings`, `get_tourism_trend`, `get_dong_vitality`, `get_trend`, `score_risk`. 빨간 신호가 2개 이상이거나 지역이 없으면 지금의 조건 그대로 `compare_places`.
3. 그 도구 결과 JSON만 모델에 넘긴다. 시스템 프롬프트는 `summary`와 `alternatives[].why`만 출력하라고 제한한다. 점수·신호·증거·한계를 다시 계산하거나 지어 내지 못하게 한다.
4. 모델이 JSON을 돌려주면 문장만 채택한다. `signals`, `score`, `evidence`, `limitations`, `as_of`, `map`은 서버 리포트 값으로 덮어쓴다.
5. 모델이 예외·타임아웃·402·빈 응답이면 규칙 문장을 그대로 둔다. `report.mode`는 서버 리포트의 `full` 또는 `partial`을 유지한다. 실행 경로는 SSE 이벤트의 `mode`로만 `fallback`을 알린다. 리포트 모드를 `llm_fallback`으로 덮어 partial 배지를 지우지 않는다.
6. 크레딧 소진처럼 문장 생성만 실패한 경우, 한계 문구는 “문장은 규칙으로 작성” 한 줄이면 충분하다. “LLM 오류로 규칙 기반으로 재생성”을 리포트 본문에 넣지 않는다.
7. `AGENT_MAX_TOOL_CALLS`는 이 경로의 도구 횟수를 제한하는 데 쓰지 않는다. 함수 호출 루프 코드를 남겨 둔다면 상한 기본값을 16으로 올리되, `LLM_PROVIDER=gemini`의 대표 경로는 위의 1회 문장 호출이다.

변경 파일: `packages/agent/loop.py`, `packages/agent/prompts.py`, `packages/agent/config.py`, `.env.example`.

완료 기준:

- 가짜 `chat_with_tools`가 `summary`만 다르게 쓰고 `score: 99`를 넣어도, 애월읍·카페의 신호와 점수는 `score_risk`와 같다.
- 가짜 모델이 예외를 내도 리포트가 나온다. 네일샵은 `mode=partial`, 점수 null이다.
- 성공한 모델 호출의 HTTP 횟수는 진단 1회당 1회다. 랜드마크 해석용 기존 호출이 지역 문자열 매칭에 실패할 때만 추가될 수 있다. 애월읍·카페처럼 폼으로 확정된 입력에는 그 추가 호출이 없다.

## Phase 2 — 유동 기간과 D6

1. `compute_footfall`과 `get_footfall`의 방문인구 평균을 `BASE_START`~`BASE_END`(2018-01~2019-12)로 제한한다. 수요와 같은 `_base_slice` 기준을 쓴다. 연령 열이 없다는 사유는 유지한다.
2. 신호 `as_of`와 도구 `period`에 이 분석 창을 적는다. “2017-01~2021-05 월평균”을 유동 점수의 기간으로 남기지 않는다. 데이터셋 종료 2021-05는 기존 D2 한계 문장에 둔다.
3. D6는 신호에 넣지 않는다. `_build_report`에서 순증이 비어 있지 않은 가장 최근 연도를 고른다. 근거 `detail`은 “{동} 사업체 생멸 {연도}년 순증 {±N} (업종 무관 참고)”다. 그 연도가 없으면 지금처럼 자료 없음을 적는다.
4. 결론 문장(Phase 3)에 그 순증을 한 절로 붙일 수 있다. 점수 계산에는 더하지 않는다.
5. `docs/data_spec.md`의 유동 정의와 `docs/results.md`의 유동 칸을 새 실측으로 고친다.

변경 파일: `packages/agent/signals.py`, `packages/agent/tools.py`, `packages/agent/loop.py`, `docs/data_spec.md`, `docs/results.md`.

완료 기준:

- 애월읍 유동 신호의 `as_of`가 `2018-01~2019-12`다.
- 애월읍 D6 근거에 “2023년 순증 자료 없음”이 없고, 순증이 있는 연도와 숫자가 있다.
- `pytest`가 새 유동 값 기준으로 통과한다.

## Phase 3 — 화면에서 바로 읽히는 문장

1. 규칙 결론은 빨간 신호 개수만 말하지 않는다. 가장 심한 빨강 신호의 이름과 값을 넣는다. 애월읍 카페 예: 관광 비중 74.5% 때문에 성수기 착시 위험이 크다는 문장. 모델 문장이 채택되면 그 문장이 이 자리를 대신하고, 숫자는 서버 값을 벗어나지 않는다.
2. `apps/api/main.py` `chat()`의 `ages`에 `prev_form.get("ages") or []`를 넣는다.
3. `ContextPanel.tsx`의 남은 선택 개수에서 주 고객 상관없음과 연령 미선택을 빼거나, 연령 라벨을 “수요 순위에만 반영. 유동에는 연령이 없음”으로 바꾼다. 진단이 끝난 화면에 “선택 2개 남음”이 필수 미입력처럼 보이면 안 된다.
4. `types.ts`의 `ReportMode`에 `'full'`을 추가한다.
5. `ReportCard.tsx`의 오류 각주는 리포트 모드가 `partial`인 것과 분리한다. 문장 생성 실패는 짧은 각주 한 줄이다. partial 배지는 `report.mode === 'partial'`로 유지한다.

변경 파일: `packages/agent/loop.py`, `apps/api/main.py`, `apps/web/src/components/ContextPanel.tsx`, `apps/web/src/components/ReportCard.tsx`, `apps/web/src/types.ts`.

완료 기준:

- 20대를 고른 뒤 “한림읍은?”을 보내면 수요 사유에 20대가 남는다.
- 균형·애월읍·카페의 첫 문장에 관광 의존도 값과 종합 점수가 함께 있다.
- 네일샵 리포트에 제한 분석이 보이고 점수는 비어 있다.

## Phase 4 — 테스트를 그 숫자에 고정

1. `tests/test_grounding.py`에 안정형 애월읍 카페의 신호 `value`·`level`·`score`를 `tools.score_risk` 반환과 직접 비교하는 테스트를 추가한다. 기존 문자열 포함 검사는 삭제하지 않아도 된다.
2. 가짜 `chat_with_tools`로 Phase 1의 두 경우를 추가한다. 점수를 99로 위조해도 서버 점수가 남는다. 예외 시 네일샵 `mode`는 `partial`이다. 가짜 모델 패턴은 `tests/test_landmark_resolve.py`에 있다.
3. `/api/chat`이 연령을 유지하는 API 테스트를 추가한다.
4. `docs/SPEC.md`의 `get_dong_vitality` 서술을 실제 호출에 맞게 고친다. 규칙 루프는 호출한다. 점수에는 넣지 않는다.

완료 기준: `.venv/bin/pytest -q` 전부 통과.

## 작업 순서

Phase 1 → Phase 2 → Phase 3 → Phase 4. Phase 2가 점수를 바꾸므로 Phase 4의 기대 숫자는 Phase 2 이후에 확정한다. 프론트를 고친 뒤에는 `make build`로 `apps/api/static`을 갱신해야 공개 서버에 반영된다.

배포 전 운영 조건: Gemini 선불 크레딧이 평가 기간(2026-11-23 12:00 ~ 2026-11-27 23:59) 동안 진단 1회당 1호출을 감당해야 한다. 크레딧이 없으면 Phase 1을 배포해도 평가자는 규칙 문장만 본다. 키 값은 이 문서와 커밋에 적지 않는다.

## 검증 체크리스트

- [ ] `LLM_PROVIDER=none`에서 안정형 애월읍 카페의 신호 7개와 점수가 `score_risk`와 같다.
- [ ] 가짜 Gemini가 점수를 바꿔도 응답 점수는 서버 값이다.
- [ ] 가짜 Gemini가 죽어도 리포트가 나오고, 네일샵은 `partial`이다.
- [ ] 유동 `as_of`가 `2018-01~2019-12`이다.
- [ ] 애월읍 D6 근거에 순증 숫자가 있다. 종합 점수 가중치에는 D6가 없다.
- [ ] 연령을 고른 뒤 다른 지역을 물으면 연령이 유지된다.
- [ ] 화면 각주가 “LLM 오류로 규칙 기반으로 재생성”이 아니다.
- [ ] `pytest` 통과.
- [ ] 프론트 변경이 있으면 `make build` 후 정적 파일로 한 줄 질문 → 지도 → 점수 카드까지 확인한다.

## 완료 보고 형식

구현을 마치면 다음 다섯 가지만 보고한다.

1. 바뀐 파일과 Phase.
2. 안정형 애월읍 카페의 새 점수와 유동 값. 옛 값(점수 46, 방문인구 7,582,178명, 3위/43)과 다르면 그 차이를 적는다.
3. 모델 1회 호출 때 서버가 덮어쓰는 필드 목록.
4. `pytest` 결과.
5. 하지 않은 것: D9, D6 가중치, 원본 CSV, 다른 LLM 공급자.
