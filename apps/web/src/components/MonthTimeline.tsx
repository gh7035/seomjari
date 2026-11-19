import { useEffect, useMemo, useRef, useState } from 'react'
import { getMapLayer } from '../api'
import type { MapLayer } from '../types'

interface Props {
  month: number
  onChange: (m: number) => void
  layer: MapLayer
  category: string | null
  highlightDong: string | null
}

const PLAY_INTERVAL_MS = 800

export default function MonthTimeline({ month, onChange, layer, category, highlightDong }: Props) {
  const [values, setValues] = useState<number[] | null>(null)
  const [playing, setPlaying] = useState(false)
  const barRef = useRef<HTMLDivElement>(null)
  const draggingRef = useRef(false)

  // 강조 지역의 12개월 값 (현재 레이어 기준). 12번 요청 대신 /api/map 월별 호출.
  useEffect(() => {
    let cancelled = false
    if (!category || !highlightDong) { setValues(null); return }
    // 순차 로드 (서버 부담/429 완전 회피). 각 요청 사이 작은 틈.
    async function load() {
      const out = new Array<number>(12).fill(0)
      for (let m = 1; m <= 12; m++) {
        if (cancelled) return
        try {
          const r = await getMapLayer(layer, category!, m)
          const p = r.points.find((x) => x.dong === highlightDong)
          out[m - 1] = p ? p.value : 0
        } catch { /* 429 등은 api.ts 가 재시도. 실패 시 0 유지 */ }
        // 부분 결과를 바로 반영해 UX 개선
        if (!cancelled) setValues([...out])
        await new Promise((r2) => setTimeout(r2, 40))
      }
    }
    load()
    return () => { cancelled = true }
  }, [layer, category, highlightDong])

  // 성수/비수 분류 (상위 3 / 하위 3)
  const classify = useMemo(() => {
    if (!values) return null
    const idx = values.map((v, i) => ({ i, v }))
    const sorted = [...idx].sort((a, b) => b.v - a.v)
    const peak = new Set(sorted.slice(0, 3).map((x) => x.i))
    const trough = new Set(sorted.slice(-3).map((x) => x.i))
    return { peak, trough }
  }, [values])

  const maxV = useMemo(() => Math.max(1, ...(values ?? [1])), [values])

  // 재생
  useEffect(() => {
    if (!playing) return
    const id = window.setInterval(() => {
      onChange(((month === 0 ? 0 : month) % 12) + 1)
    }, PLAY_INTERVAL_MS)
    return () => window.clearInterval(id)
  }, [playing, month, onChange])

  // ← → 키
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return
      if (e.key === 'ArrowRight') { e.preventDefault(); onChange(month >= 12 ? 1 : (month === 0 ? 1 : month + 1)) }
      else if (e.key === 'ArrowLeft') { e.preventDefault(); onChange(month <= 1 ? 12 : month - 1) }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [month, onChange])

  // 드래그 처리
  function monthFromClientX(clientX: number): number {
    const bar = barRef.current
    if (!bar) return month
    const r = bar.getBoundingClientRect()
    const x = Math.max(0, Math.min(r.width, clientX - r.left))
    const idx = Math.floor((x / r.width) * 12)
    return Math.max(1, Math.min(12, idx + 1))
  }

  function onPointerDown(e: React.PointerEvent) {
    draggingRef.current = true
    ;(e.target as HTMLElement).setPointerCapture?.(e.pointerId)
    onChange(monthFromClientX(e.clientX))
  }
  function onPointerMove(e: React.PointerEvent) {
    if (!draggingRef.current) return
    onChange(monthFromClientX(e.clientX))
  }
  function onPointerUp(e: React.PointerEvent) {
    draggingRef.current = false
    try { (e.target as HTMLElement).releasePointerCapture?.(e.pointerId) } catch {}
  }

  return (
    <div className="mtl">
      <button
        type="button"
        className="mtl-play"
        onClick={() => setPlaying((p) => !p)}
        aria-label={playing ? '일시정지' : '재생'}
        title={playing ? '일시정지' : '1월부터 12월까지 재생'}
      >
        {playing ? '⏸' : '▶'}
      </button>

      <button
        type="button"
        className={`mtl-avg ${month === 0 ? 'active' : ''}`}
        onClick={() => { setPlaying(false); onChange(0) }}
        title="월평균"
      >월평균</button>

      <div
        className="mtl-bar"
        ref={barRef}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
      >
        {Array.from({ length: 12 }, (_, i) => {
          const m = i + 1
          const v = values?.[i] ?? 0
          const heightPct = values ? Math.round((v / maxV) * 100) : 0
          const isPeak = classify?.peak.has(i)
          const isTrough = classify?.trough.has(i)
          const barClass = isPeak ? 'peak' : isTrough ? 'trough' : 'mid'
          const active = month === m
          return (
            <div key={m} className={`mtl-cell ${active ? 'active' : ''}`}>
              {active && <span className="mtl-cursor-label">{m}월</span>}
              {values && (
                <div
                  className={`mtl-bar-fill ${barClass}`}
                  style={{ height: `${Math.max(4, heightPct)}%` }}
                  title={`${m}월 · ${Math.round(v).toLocaleString()}`}
                />
              )}
              <span className="mtl-cell-label">{m}</span>
            </div>
          )
        })}
      </div>

      {values && classify && (
        <div className="mtl-legend" aria-label="성수기/비수기 범례">
          <span className="mtl-legend-item"><span className="mtl-swatch peak" />성수기</span>
          <span className="mtl-legend-item"><span className="mtl-swatch trough" />비수기</span>
        </div>
      )}
    </div>
  )
}
