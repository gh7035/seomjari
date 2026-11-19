import { useCallback, useRef } from 'react'

export default function Gutter({ side, onDrag }: {
  side: 'left' | 'right'
  // delta 는 px. 왼쪽 가터: delta>0 → 좌측 넓어짐. 우측 가터: delta>0 → 우측 **좁아짐** (중앙이 넓어짐)
  onDrag: (deltaPx: number) => void
}) {
  const startX = useRef(0)
  const dragging = useRef(false)

  const onPointerDown = useCallback((e: React.PointerEvent) => {
    e.preventDefault()
    ;(e.target as HTMLElement).setPointerCapture(e.pointerId)
    startX.current = e.clientX
    dragging.current = true
  }, [])

  const onPointerMove = useCallback((e: React.PointerEvent) => {
    if (!dragging.current) return
    const dx = e.clientX - startX.current
    startX.current = e.clientX
    onDrag(side === 'left' ? dx : -dx)
  }, [onDrag, side])

  const onPointerUp = useCallback((e: React.PointerEvent) => {
    dragging.current = false
    try { (e.target as HTMLElement).releasePointerCapture(e.pointerId) } catch {}
  }, [])

  return (
    <div
      className="gutter"
      role="separator"
      aria-orientation="vertical"
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
    >
      <div className="gutter-grip" />
    </div>
  )
}
