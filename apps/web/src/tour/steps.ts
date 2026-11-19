import type { TourStep } from '../components/Tour'

/**
 * 투어 단계 설정. 단계 추가/수정은 이 배열만 고치면 됨.
 * target 은 CSS 셀렉터 (data-tour 속성 권장). placement 생략 시 자동.
 */

export const TOUR_A: TourStep[] = [
  {
    target: '[data-tour="entry-input"]',
    title: '업종과 지역을 한 줄로 물어보세요',
    body: '예: 애월읍에서 카페 하려는데 어때?',
    placement: 'bottom',
  },
  {
    target: '[data-tour="entry-chips"]',
    title: '처음이라면 예시를 눌러 보세요',
    body: '클릭 한 번으로 진단이 시작됩니다.',
    placement: 'bottom',
  },
  {
    target: '[data-tour="entry-features"]',
    title: '이런 걸 알려드려요',
    body: '신호등 진단, 3D 지도, 대안 지역 추천.',
    placement: 'top',
  },
]

export const TOUR_B: TourStep[] = [
  {
    target: '[data-tour="ctx-form"]',
    title: '질문에서 읽어낸 조건이에요',
    body: '고객층·연령·위험 성향을 바꿔 다시 진단할 수 있어요.',
    placement: 'right',
  },
  {
    target: '[data-tour="agent-progress"]',
    title: 'AI가 일하는 과정이에요',
    body: '숫자는 AI가 지어내지 않고 데이터 도구가 계산해요.',
    placement: 'left',
  },
  {
    target: '[data-tour="signals"]',
    title: '6가지 신호로 진단해요',
    body: '🟢 유리 🟡 보통 🔴 불리, 회색은 데이터가 없는 항목.',
    placement: 'left',
  },
  {
    target: '[data-tour="score"]',
    title: '신호를 종합한 점수예요',
    body: "계산된 신호가 적으면 점수 대신 '참고용'으로 표시돼요.",
    placement: 'left',
  },
  {
    target: '[data-tour="map-layers"]',
    title: '5개 레이어로 다르게 보세요',
    body: '수요: 월평균 매출 · 관광: 관광객 매출 비중 · 공급: 점포수 · 유동: 방문인구 · 생존: 3년 생존율. 기둥 높이와 색이 선택한 레이어 기준으로 바뀝니다.',
    placement: 'bottom',
  },
  {
    target: '[data-tour="month"]',
    title: '성수기 착시를 확인하세요',
    body: '월을 바꾸면 계절에 따라 상권이 어떻게 달라지는지 보여요.',
    placement: 'right',
  },
  {
    target: '[data-tour="alts"]',
    title: '더 나은 지역을 찾아드려요',
    body: '불리 신호가 2개 이상이면 AI가 스스로 대안을 찾아요.',
    placement: 'left',
  },
  {
    target: '[data-tour="evidence"]',
    title: '모든 수치에는 출처가 있어요',
    body: '데이터 기준 시점과 한계를 확인하세요.',
    placement: 'left',
  },
  {
    target: '[data-tour="chat-input"]',
    title: '이어서 물어보세요',
    body: '예: 그럼 한림읍은? 20대 대상이면?',
    placement: 'top',
  },
]
