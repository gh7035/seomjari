import { useEffect, useRef, useState } from 'react'
import type { Meta } from '../types'

const SUGGESTIONS = [
  '애월읍에서 카페 창업하려는데 어떨까요?',
  '이도2동 베이커리 괜찮나요?',
  '성산읍에 기념품점 열어도 될까?',
  '한림읍에서 한식당은 어떨까?',
]

// 8초마다 입력창에 슬라이드로 바뀌는 템플릿
const PLACEHOLDERS = [
  '애월읍에서 창업하려는데요',
  '성산읍 기념품점 어떨까요?',
  '이도2동 베이커리는 괜찮을까요?',
  '한림읍에서 한식당 열면요?',
  '노형동에 편의점 어때요?',
  '중문동 양식당 괜찮나요?',
  '구좌읍 카페 창업 생각 중이에요',
]

export default function Entry({ meta, onSubmit, busy, onHelp }: {
  meta: Meta | null
  onSubmit: (question: string) => void
  busy: boolean
  onHelp?: () => void
}) {
  const [q, setQ] = useState('')
  const [phIdx, setPhIdx] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => { inputRef.current?.focus() }, [])
  useEffect(() => {
    const t = setInterval(() => setPhIdx((i) => (i + 1) % PLACEHOLDERS.length), 5000)
    return () => clearInterval(t)
  }, [])

  function submit(text?: string) {
    const v = (text ?? q).trim()
    if (!v || busy) return
    onSubmit(v)
  }

  return (
    <div className="entry">
      <div className="entry-glow" aria-hidden />
      <nav className="entry-nav">
        <div className="brand">
          <span className="brand-dot" />
          <span>섬자리</span>
        </div>
        <div className="brand-meta">
          {meta && <span>행정동 {meta.dongs.length} · 업종 {meta.categories.length}</span>}
          {onHelp && (
            <button type="button" className="help-btn" onClick={onHelp} title="사용법 다시 보기" aria-label="사용법">?</button>
          )}
        </div>
      </nav>

      <main className="entry-main">
        <span className="entry-tag">AI Agent · 제주데이터허브 기반</span>
        <h1 className="entry-title">
          성수기 착시를 걷어내는<br />
          <span className="accent">제주 창업 입지 진단</span>
        </h1>
        <p className="entry-sub">
          업종·지역 한 줄만 적으면, Agent 가 관광 의존도·계절 변동성·경쟁 밀도·수요를 교차 분석해 신호등과 대안 지역까지 내놓습니다.
        </p>

        <form className="entry-form" data-tour="entry-input" onSubmit={(e) => { e.preventDefault(); submit() }}>
          <div className="entry-input-wrap">
            <input
              ref={inputRef}
              type="text"
              className="entry-input"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              disabled={busy}
              autoComplete="off"
            />
            {!q && (
              <div className="entry-placeholder" aria-hidden>
                <span key={phIdx} className="entry-placeholder-text">{PLACEHOLDERS[phIdx]}</span>
              </div>
            )}
          </div>
          <button type="submit" className="entry-cta" disabled={busy || !q.trim()} aria-label="진단 시작">
            {busy ? <span className="dots"><i /><i /><i /></span> : <span className="arrow">↑</span>}
          </button>
        </form>

        <div className="entry-chips" data-tour="entry-chips">
          <span className="chip-label">자주 묻는 조합</span>
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              type="button"
              className="chip"
              onClick={() => { setQ(s); submit(s) }}
              disabled={busy}
            >{s}</button>
          ))}
        </div>

        <div className="entry-features" data-tour="entry-features">
          <div className="feat">
            <div className="feat-ic">🎯</div>
            <h3>신호등 4개</h3>
            <p>관광 의존도 · 계절 변동성 · 경쟁 밀도 · 수요 규모</p>
          </div>
          <div className="feat">
            <div className="feat-ic">🗺️</div>
            <h3>3D 지도</h3>
            <p>행정동 43개 기둥 · 월 슬라이더 1~12월 · 레이어 토글</p>
          </div>
          <div className="feat">
            <div className="feat-ic">🧭</div>
            <h3>대안 지역 자동 탐색</h3>
            <p>🔴 2개 이상이면 Agent 가 Top 3 도민형 지역 제시</p>
          </div>
        </div>
      </main>

      <footer className="entry-foot">
        데이터: 제주데이터허브 (D1 카드매출 · D2 유동인구 · D3 트렌드 · D4 상가정보) · 기준 기간 {meta?.period.base ?? '2018-01~2019-12'}
      </footer>
    </div>
  )
}
