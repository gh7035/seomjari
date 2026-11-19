import type { DongMeta } from '../types'

// 제주 행정동 43개 (제주시 26 + 서귀포시 17).
// 좌표는 D4(상가 정보) 좌표 중앙값을 가정한 근사치로, 제주 범위 안에 있다.
export const DONGS: DongMeta[] = [
  // 제주시 읍면
  { name: '한경면', city: '제주시', type: '읍면', lon: 126.207, lat: 33.335 },
  { name: '한림읍', city: '제주시', type: '읍면', lon: 126.268, lat: 33.412 },
  { name: '애월읍', city: '제주시', type: '읍면', lon: 126.331, lat: 33.463 },
  { name: '조천읍', city: '제주시', type: '읍면', lon: 126.643, lat: 33.541 },
  { name: '구좌읍', city: '제주시', type: '읍면', lon: 126.789, lat: 33.526 },
  { name: '추자면', city: '제주시', type: '읍면', lon: 126.302, lat: 33.962 },
  { name: '우도면', city: '제주시', type: '읍면', lon: 126.953, lat: 33.504 },
  // 제주시 동
  { name: '일도1동', city: '제주시', type: '도심', lon: 126.531, lat: 33.513 },
  { name: '일도2동', city: '제주시', type: '도심', lon: 126.543, lat: 33.504 },
  { name: '이도1동', city: '제주시', type: '도심', lon: 126.527, lat: 33.506 },
  { name: '이도2동', city: '제주시', type: '도심', lon: 126.541, lat: 33.496 },
  { name: '삼도1동', city: '제주시', type: '도심', lon: 126.518, lat: 33.512 },
  { name: '삼도2동', city: '제주시', type: '도심', lon: 126.516, lat: 33.504 },
  { name: '용담1동', city: '제주시', type: '도심', lon: 126.507, lat: 33.514 },
  { name: '용담2동', city: '제주시', type: '도심', lon: 126.493, lat: 33.513 },
  { name: '건입동', city: '제주시', type: '도심', lon: 126.533, lat: 33.519 },
  { name: '화북동', city: '제주시', type: '도심', lon: 126.571, lat: 33.517 },
  { name: '삼양동', city: '제주시', type: '도심', lon: 126.597, lat: 33.527 },
  { name: '봉개동', city: '제주시', type: '도심', lon: 126.610, lat: 33.473 },
  { name: '아라동', city: '제주시', type: '도심', lon: 126.546, lat: 33.471 },
  { name: '오라동', city: '제주시', type: '도심', lon: 126.515, lat: 33.472 },
  { name: '연동', city: '제주시', type: '도심', lon: 126.493, lat: 33.489 },
  { name: '노형동', city: '제주시', type: '도심', lon: 126.472, lat: 33.479 },
  { name: '외도동', city: '제주시', type: '도심', lon: 126.434, lat: 33.488 },
  { name: '이호동', city: '제주시', type: '도심', lon: 126.457, lat: 33.498 },
  { name: '도두동', city: '제주시', type: '도심', lon: 126.472, lat: 33.503 },
  // 서귀포시 읍면
  { name: '대정읍', city: '서귀포시', type: '읍면', lon: 126.253, lat: 33.226 },
  { name: '남원읍', city: '서귀포시', type: '읍면', lon: 126.713, lat: 33.284 },
  { name: '성산읍', city: '서귀포시', type: '읍면', lon: 126.908, lat: 33.428 },
  { name: '안덕면', city: '서귀포시', type: '읍면', lon: 126.351, lat: 33.258 },
  { name: '표선면', city: '서귀포시', type: '읍면', lon: 126.834, lat: 33.325 },
  // 서귀포시 동
  { name: '송산동', city: '서귀포시', type: '도심', lon: 126.573, lat: 33.246 },
  { name: '정방동', city: '서귀포시', type: '도심', lon: 126.572, lat: 33.246 },
  { name: '중앙동', city: '서귀포시', type: '도심', lon: 126.561, lat: 33.248 },
  { name: '천지동', city: '서귀포시', type: '도심', lon: 126.558, lat: 33.246 },
  { name: '효돈동', city: '서귀포시', type: '도심', lon: 126.611, lat: 33.273 },
  { name: '영천동', city: '서귀포시', type: '도심', lon: 126.597, lat: 33.293 },
  { name: '동홍동', city: '서귀포시', type: '도심', lon: 126.574, lat: 33.263 },
  { name: '서홍동', city: '서귀포시', type: '도심', lon: 126.548, lat: 33.262 },
  { name: '대륜동', city: '서귀포시', type: '도심', lon: 126.513, lat: 33.244 },
  { name: '대천동', city: '서귀포시', type: '도심', lon: 126.491, lat: 33.253 },
  { name: '중문동', city: '서귀포시', type: '도심', lon: 126.418, lat: 33.254 },
  { name: '예래동', city: '서귀포시', type: '도심', lon: 126.388, lat: 33.258 },
]
