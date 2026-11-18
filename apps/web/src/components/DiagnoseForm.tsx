import { useState } from 'react'
import type { DiagnoseForm } from '../types'

// TODO: /api/meta 에서 업종·행정동 목록 받아오기
const CATEGORIES = ['카페', '한식당', '양식당', '일식당', '중식당', '술집', '베이커리', '편의점', '기념품점', '소형숙박', '패스트푸드']

export default function DiagnoseFormPanel({ disabled, onSubmit }: { disabled: boolean; onSubmit: (f: DiagnoseForm) => void }) {
  const [f, setF] = useState<DiagnoseForm>({ category: '카페', dong: null, customer: 'any', ages: [], risk: 'balanced' })

  return (
    <form onSubmit={(e) => { e.preventDefault(); onSubmit(f) }}>
      <label>업종</label>
      <select value={f.category ?? ''} onChange={(e) => setF({ ...f, category: e.target.value })}>
        {CATEGORIES.map((c) => <option key={c}>{c}</option>)}
      </select>

      <label>희망 지역</label>
      <input placeholder="예: 애월읍 (비우면 지역 추천)" value={f.dong ?? ''}
        onChange={(e) => setF({ ...f, dong: e.target.value || null })} />

      <label>주 고객</label>
      <select value={f.customer} onChange={(e) => setF({ ...f, customer: e.target.value as DiagnoseForm['customer'] })}>
        <option value="any">상관없음</option>
        <option value="tourist">관광객</option>
        <option value="local">도민</option>
      </select>

      <label>리스크 성향</label>
      <select value={f.risk} onChange={(e) => setF({ ...f, risk: e.target.value as DiagnoseForm['risk'] })}>
        <option value="safe">안정형</option>
        <option value="balanced">균형</option>
        <option value="aggressive">공격형</option>
      </select>

      <button type="submit" disabled={disabled}>{disabled ? '분석 중…' : '진단 시작'}</button>
    </form>
  )
}
