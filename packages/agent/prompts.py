"""시스템 프롬프트 + LLM function-calling용 도구 스펙."""

SYSTEM_PROMPT = """\
너는 '섬자리'의 제주 창업 입지 분석가다.

원칙
1. 모든 숫자는 도구 결과에서만 인용한다. 계산이 필요하면 도구를 호출한다.
2. "성공", "확실" 같은 단정 표현을 쓰지 않는다. "데이터상 유리/불리"로 표현한다.
3. 리포트에는 데이터 기간과 한계를 반드시 포함한다.
4. 업종이나 지역이 모호하면 추측하지 말고 후보를 제시해 되묻는다.
5. 신호등 중 red가 2개 이상이면 compare_places로 대안 지역을 탐색한다.
6. 지원하지 않는 업종이면 데이터가 없다고 말하고 가능한 업종을 안내한다.
7. 최종 출력은 **아래 스키마를 그대로 따른 JSON 객체만** 반환한다. 다른 텍스트/마크다운/코드펜스 금지.

진행 순서
의도 파악 → 계획 → 도구 실행 → 검증 → 리포트

도구는 서버 상한 안에서 끝내고 같은 도구를 반복하지 않는다.
지역과 업종이 있으면 get_demand, get_supply, get_footfall, get_survival, get_recent_openings, get_dong_vitality, get_trend, score_risk 순서로 한 번씩 호출한 뒤 JSON만 반환한다.
지역만 있고 업종 추천이면 find_gap_category를 호출한다. 업종만 있으면 compare_places를 호출한다.

최종 리포트 JSON 스키마 (필드 이름·타입 그대로, 7개 signal)
{
  "summary": "<한 문장 결론, 단정 금지>",
  "target": {"dong": "<행정동명 또는 null>", "category": "<업종명 또는 null>"},
  "signals": [
    {"name":"관광 의존도"|"계절 변동성"|"경쟁 밀도"|"수요 규모"|"유동 수요"|"생존 리스크"|"최근 개폐업",
     "value":"<문자열, 예: '74.5%'>",
     "level":"green"|"yellow"|"red"|"unavailable",
     "reason":"<근거 한 줄>",
     "as_of":"<데이터 시점, 예: '2018~2019' | '2025-09-02'>"}
  ],
  "score": <0~100 정수>,
  "alternatives": [{"dong":"...", "score":<정수>, "why":"..."}],
  "trend": "<없으면 null>",
  "evidence": [
    {"source":"D1"|"D2"|"D3"|"D4"|"D5"|"D6"|"D9"|"D10",
     "period":"<기간>", "detail":"<한 줄 설명>"}
  ],
  "limitations": ["<한 줄씩>"],
  "map": {"layer":"demand"|"tourism"|"supply"|"footfall"|"survival",
          "highlight":["<강조할 행정동명 목록>"]},
  "mode": "full"|"partial"
}

작성 규칙
- `score`와 `signals`는 score_risk 도구 결과를 **그대로 복사** (재계산 금지). score_risk가 7개 signal을 돌려주면 7개 다 포함한다.
- 각 signal의 `as_of` 필드를 반드시 포함 (score_risk 출력에 들어 있음).
- `evidence`는 호출한 도구들의 source/period/detail을 2개 이상 포함.
- `limitations`는 최소 2개: ①카드사 표본 비중 해석 ②2021-05 이후 지역 데이터 공백 (D5·D9로 보정).
- 생존 리스크 red면 `map.layer`="survival", 관광 의존도 red면 "tourism".
- 1개 이상 신호가 `level="unavailable"` 이면 `mode`="partial", 전부 full이면 "full".
- 지원 안 함 업종이면 signals=[], score=0, summary로 안내 (clarify는 loop가 담당하므로 LLM은 리포트만).
"""


# OpenAI function-calling 호환 스펙. 다른 공급자도 동일 스키마에서 변환해 쓴다.
TOOL_SPECS = [
    {
        "type": "function",
        "function": {
            "name": "resolve_place",
            "description": "자연어 지역 표현 → 표준 행정동명과 후보 목록. 모호하면 dong=null.",
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "resolve_category",
            "description": "자연어 업종 표현 → app_category. 지원 업종만 매핑된다.",
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_demand",
            "description": "행정동+업종의 월평균 매출, 관광/도민 비중, 12개월 패턴, 연령대 비중. source=D1.",
            "parameters": {
                "type": "object",
                "properties": {"dong": {"type": "string"}, "category": {"type": "string"}},
                "required": ["dong", "category"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_supply",
            "description": "행정동+업종의 점포 수와 업종 내 순위. source=D4.",
            "parameters": {
                "type": "object",
                "properties": {"dong": {"type": "string"}, "category": {"type": "string"}},
                "required": ["dong", "category"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "score_risk",
            "description": "신호 7개 값·백분위·신호등과 종합 점수. weights로 가중치 조정.",
            "parameters": {
                "type": "object",
                "properties": {
                    "dong": {"type": "string"},
                    "category": {"type": "string"},
                    "weights": {
                        "type": "object",
                        "description": "tour/season/comp/demand 가중치 (합 100 기준으로 정규화)",
                    },
                },
                "required": ["dong", "category"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare_places",
            "description": "업종 기준으로 전체 행정동에 score_risk를 돌려 Top-K 반환. exclude로 특정 동 제외.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {"type": "string"},
                    "top_k": {"type": "integer", "default": 3},
                    "exclude": {"type": "array", "items": {"type": "string"}},
                    "weights": {"type": "object"},
                },
                "required": ["category"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "parse_intent",
            "description": "자연어 발화 → 의도(diagnose|place_recommend|category_recommend|clarify)와 hints.",
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_survival",
            "description": "행정동+업종의 D5 1년·3년 생존율과 업종 평균 대비 차이 (중도절단 처리).",
            "parameters": {
                "type": "object",
                "properties": {"dong": {"type": "string"}, "category": {"type": "string"}},
                "required": ["dong", "category"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_recent_openings",
            "description": "최근 N개월(기본 24) 개업·폐업·순증. D5 인허가·폐업일 기준.",
            "parameters": {
                "type": "object",
                "properties": {
                    "dong": {"type": "string"}, "category": {"type": "string"},
                    "months": {"type": "integer", "default": 24},
                },
                "required": ["dong", "category"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_footfall",
            "description": "행정동 방문인구 월평균과 순위. 업종과 무관하다.",
            "parameters": {
                "type": "object",
                "properties": {"dong": {"type": "string"}},
                "required": ["dong"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_dong_vitality",
            "description": "행정동 사업체 생멸(D6). 업종 무관 참고.",
            "parameters": {
                "type": "object",
                "properties": {"dong": {"type": "string"}},
                "required": ["dong"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_trend",
            "description": "업종 전체의 2018년 대비 최근 연도 이용금액 증감. 지역 점수는 바꾸지 않는다.",
            "parameters": {
                "type": "object",
                "properties": {"category": {"type": "string"}},
                "required": ["category"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_gap_category",
            "description": "한 행정동에서 수요는 높고 점포는 적은 업종 후보.",
            "parameters": {
                "type": "object",
                "properties": {"dong": {"type": "string"}},
                "required": ["dong"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_tourism_trend",
            "description": "D9 입도객 최근 12개월 vs 직전 12개월 증감률 + 성수·비수 배율.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "render_map",
            "description": "UI 지도 상태만 지시. layer ∈ {demand,tourism,supply,footfall}.",
            "parameters": {
                "type": "object",
                "properties": {
                    "layer": {"type": "string",
                              "enum": ["demand", "tourism", "supply", "footfall"]},
                    "category": {"type": "string"},
                    "highlight": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["layer"],
            },
        },
    },
]
