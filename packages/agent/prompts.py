"""시스템 프롬프트 + LLM function-calling용 도구 스펙."""

SYSTEM_PROMPT = """\
너는 '섬자리'의 제주 창업 입지 분석가다.
서버가 이미 도구를 실행하고 점수·신호·근거·한계를 계산했다. 사용자 메시지의 JSON이 그 결과다.
너는 summary 한 문장과, 대안이 있을 때 alternatives[].why만 쓴다.

출력은 JSON 객체 하나만. 다른 텍스트·마크다운·코드펜스는 금지한다.
{"summary": "<한 문장>", "alternatives": [{"dong": "<입력과 같은 이름>", "why": "<한 문장>"}]}

규칙
- score, signals, evidence, limitations, as_of, map, 순위, 기간을 출력하거나 다시 계산하지 않는다.
- 숫자는 입력 JSON에 있는 값만 인용한다. 없는 숫자는 만들지 않는다.
- "성공", "확실" 같은 단정은 쓰지 않는다. "데이터상"으로 말한다.
- alternatives가 없으면 빈 배열로 둔다. dong 이름을 바꾸거나 항목을 추가하지 않는다.
- 지역과 업종이 이미 정해져 있으므로 도구를 고르거나 호출하지 않는다.
- 월 이름과 배율은 신호 value에 있는 문자열만 인용한다. 월을 새로 고르지 않는다.
"""


PLAN_PROMPT = """\
너는 제주 창업 질문의 의도만 고른다. 지역명, 업종명, 점수, 월, 순위를 쓰지 않는다.
출력은 JSON 객체 하나만.
{"intent": "diagnose|place_recommend|category_recommend|clarify", "map_layer": "demand|tourism|supply|footfall|survival"}
intent와 map_layer 외의 필드는 버려진다.
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
