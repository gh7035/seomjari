import { useCallback, useEffect, useLayoutEffect, useState } from 'react'

export interface TourStep {
  target: string
  title: string
  body: string
  placement?: 'top' | 'bottom' | 'left' | 'right' | 'auto'
}

interface Props {
  steps: TourStep[]
  open: boolean
  onClose: () => void
}

const PAD = 8
const TOOLTIP_W = 320
const TOOLTIP_H_EST = 160
const MOBILE_BREAKPOINT = 900

function clamp(v: number, lo: number, hi: number) { return Math.max(lo, Math.min(hi, v)) }

export default function Tour({ steps, open, onClose }: Props) {
  const [i, setI] = useState(0)
  const [rect, setRect] = useState<DOMRect | null>(null)
  const [isMobile, setIsMobile] = useState<boolean>(
    typeof window !== 'undefined' ? window.innerWidth < MOBILE_BREAKPOINT : false,
  )
  const [visible, setVisible] = useState(false)

  const current = steps[i]

  const updateRect = useCallback(() => {
    if (!current) return
    const el = document.querySelector(current.target) as HTMLElement | null
    if (!el) { setRect(null); return }
    try { el.scrollIntoView({ block: 'center', behavior: 'smooth' }) } catch {}
    // scrollIntoView 가 끝나기를 짧게 기다렸다가 측정
    const measure = () => setRect(el.getBoundingClientRect())
    measure()
    requestAnimationFrame(measure)
    setTimeout(measure, 260)
  }, [current])

  // open 토글 시 첫 단계로
  useEffect(() => {
    if (!open) { setVisible(false); return }
    setI(0)
    requestAnimationFrame(() => setVisible(true)) // 다음 틱에 켜서 fade-in
  }, [open])

  useLayoutEffect(() => {
    if (!open) return
    updateRect()
  }, [open, i, updateRect])

  useEffect(() => {
    if (!open) return
    const onResize = () => {
      setIsMobile(window.innerWidth < MOBILE_BREAKPOINT)
      updateRect()
    }
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [open, updateRect])

  const prev = useCallback(() => setI((v) => Math.max(0, v - 1)), [])
  const next = useCallback(() => setI((v) => {
    if (v >= steps.length - 1) { onClose(); return v }
    return v + 1
  }), [steps.length, onClose])

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { e.preventDefault(); onClose() }
      else if (e.key === 'ArrowRight') { e.preventDefault(); next() }
      else if (e.key === 'ArrowLeft') { e.preventDefault(); prev() }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose, next, prev])

  if (!open || !current) return null

  const spotStyle: React.CSSProperties | undefined = rect ? {
    position: 'fixed',
    left: rect.left - PAD,
    top: rect.top - PAD,
    width: rect.width + PAD * 2,
    height: rect.height + PAD * 2,
  } : undefined

  // 말풍선 위치 계산
  let tooltipStyle: React.CSSProperties = {}
  if (!isMobile) {
    if (rect) {
      const w = TOOLTIP_W
      const h = TOOLTIP_H_EST
      const vw = window.innerWidth
      const vh = window.innerHeight
      const placement = resolvePlacement(current.placement, rect, w, h, vw, vh)
      if (placement === 'bottom') {
        tooltipStyle = { left: clamp(rect.left + rect.width / 2 - w / 2, 12, vw - w - 12), top: Math.min(rect.bottom + 16, vh - h - 12) }
      } else if (placement === 'top') {
        tooltipStyle = { left: clamp(rect.left + rect.width / 2 - w / 2, 12, vw - w - 12), top: Math.max(12, rect.top - h - 16) }
      } else if (placement === 'right') {
        tooltipStyle = { left: Math.min(rect.right + 16, vw - w - 12), top: clamp(rect.top + rect.height / 2 - h / 2, 12, vh - h - 12) }
      } else {
        tooltipStyle = { left: Math.max(12, rect.left - w - 16), top: clamp(rect.top + rect.height / 2 - h / 2, 12, vh - h - 12) }
      }
      tooltipStyle.width = w
      tooltipStyle.position = 'fixed'
    } else {
      // 대상 없음 → 화면 중앙
      tooltipStyle = { position: 'fixed', left: '50%', top: '50%', transform: 'translate(-50%, -50%)', width: TOOLTIP_W }
    }
  }

  const isLast = i === steps.length - 1

  return (
    <>
      {/* 클릭·입력 차단 (투명 전면 레이어) */}
      <div
        className={`tour-blocker ${visible ? 'in' : ''}`}
        onClick={(e) => { e.preventDefault(); e.stopPropagation() }}
      />
      {/* 스포트라이트 (box-shadow 로 외곽 어둡게) */}
      {rect && <div className={`tour-spot ${visible ? 'in' : ''}`} style={spotStyle} />}
      {!rect && <div className={`tour-dim ${visible ? 'in' : ''}`} />}
      {/* 말풍선 */}
      <div
        className={`tour-tooltip ${isMobile ? 'tour-sheet' : ''} ${visible ? 'in' : ''}`}
        style={isMobile ? undefined : tooltipStyle}
        role="dialog"
        aria-live="polite"
        aria-label={`온보딩 ${i + 1}/${steps.length}`}
      >
        <div className="tour-title">{current.title}</div>
        <div className="tour-body">{current.body}</div>
        <div className="tour-actions">
          <button type="button" className="tour-skip" onClick={onClose}>건너뛰기</button>
          <div className="tour-nav">
            <button type="button" className="tour-btn" onClick={prev} disabled={i === 0}>이전</button>
            <span className="tour-count">{i + 1} / {steps.length}</span>
            <button type="button" className="tour-btn tour-primary" onClick={next}>{isLast ? '완료' : '다음'}</button>
          </div>
        </div>
      </div>
    </>
  )
}

function resolvePlacement(
  hint: TourStep['placement'],
  rect: DOMRect, w: number, h: number, vw: number, vh: number,
): 'top' | 'bottom' | 'left' | 'right' {
  if (hint && hint !== 'auto') return hint
  const below = vh - rect.bottom
  const above = rect.top
  const right = vw - rect.right
  const left = rect.left
  const slack = 24
  if (below >= h + slack) return 'bottom'
  if (above >= h + slack) return 'top'
  if (right >= w + slack) return 'right'
  if (left >= w + slack) return 'left'
  return 'bottom'
}
