import { useEffect, useState } from 'react'
import type { DiagnoseForm, Meta } from '../types'

const AGES = ['20대', '30대', '40대', '50대', '60대+']

export default function ContextPanel({ meta, form, disabled, onApply }: {
  meta: Meta | null
  form: DiagnoseForm | null
  disabled: boolean
  onApply: (f: DiagnoseForm) => void
}) {
  const [f, setF] = useState<DiagnoseForm | null>(form)

  // 외부 form 이 바뀌면(새 진단 시작 시) 동기화
  useEffect(() => { setF(form) }, [form])

  if (!f) {
    return (
      <div className="ctx">
        <div className="ctx-title">진단 요청</div>
        <div className="ctx-empty">아직 진단 요청이 없습니다.</div>
      </div>
    )
  }

  const dirty = JSON.stringify(f) !== JSON.stringify(form)
  const toggleAge = (a: string) =>
    setF({ ...f, ages: f.ages.includes(a) ? f.ages.filter((x) => x !== a) : [...f.ages, a] })

  const missingCount =
    (f.category ? 0 : 1) + (f.dong ? 0 : 1) + (f.customer === 'any' ? 1 : 0) + (f.ages.length === 0 ? 1 : 0)

  return (
    <div className="ctx" data-tour="ctx-form">
      <div className="ctx-head">
        <div className="ctx-title">진단 요청</div>
        {missingCount > 0 && <span className="ctx-badge">선택 {missingCount}개 남음</span>}
      </div>

      {f.question && (
        <div className="ctx-q">
          <span className="ctx-q-mark">“</span>
          <span>{f.question}</span>
        </div>
      )}

      <div className="ctx-fields">
        <Field label="업종" missing={!f.category}>
          <select
            value={f.category ?? ''}
            onChange={(e) => setF({ ...f, category: e.target.value || null })}
          >
            <option value="">선택</option>
            {meta?.categories.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </Field>

        <Field label="지역" missing={!f.dong}>
          <select
            value={f.dong ?? ''}
            onChange={(e) => setF({ ...f, dong: e.target.value || null })}
          >
            <option value="">전체 (지역 추천)</option>
            {meta?.dongs.map((d) => <option key={d.name} value={d.name}>{d.name}</option>)}
          </select>
        </Field>

        <Field label="주 고객" missing={f.customer === 'any'}>
          <select
            value={f.customer}
            onChange={(e) => setF({ ...f, customer: e.target.value as DiagnoseForm['customer'] })}
          >
            <option value="any">상관없음</option>
            <option value="tourist">관광객</option>
            <option value="local">도민</option>
          </select>
        </Field>

        <Field label="연령대" missing={f.ages.length === 0}>
          <div className="ctx-age-chips">
            {AGES.map((a) => {
              const on = f.ages.includes(a)
              return (
                <button
                  key={a}
                  type="button"
                  className={`ctx-chip ${on ? 'on' : ''}`}
                  onClick={() => toggleAge(a)}
                >{a}</button>
              )
            })}
          </div>
        </Field>

        <Field label="리스크 성향" missing={false}>
          <select
            value={f.risk}
            onChange={(e) => setF({ ...f, risk: e.target.value as DiagnoseForm['risk'] })}
          >
            <option value="safe">안정형</option>
            <option value="balanced">균형</option>
            <option value="aggressive">공격형</option>
          </select>
        </Field>
      </div>

      <button
        type="button"
        className="ctx-apply"
        onClick={() => onApply(f)}
        disabled={disabled || !dirty || !f.category}
      >{disabled ? '분석 중…' : dirty ? '변경값으로 재진단' : '값이 반영됨'}</button>
    </div>
  )
}

function Field({ label, missing, children }: {
  label: string
  missing: boolean
  children: React.ReactNode
}) {
  return (
    <div className={`ctx-field ${missing ? 'missing' : ''}`}>
      <div className="ctx-field-label">{label}{missing && <span className="warn-dot">●</span>}</div>
      <div className="ctx-field-edit">{children}</div>
    </div>
  )
}
