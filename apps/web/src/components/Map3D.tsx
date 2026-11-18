import { useEffect, useState } from 'react'
import DeckGL from '@deck.gl/react'
import { ColumnLayer } from '@deck.gl/layers'
import type { MapLayer } from '../types'

interface Point { dong: string; lon: number; lat: number; value: number; tourism: number }

const VIEW = { longitude: 126.55, latitude: 33.38, zoom: 9.2, pitch: 50, bearing: -10 }

// 관광 의존도 0(도민형, 파랑) → 1(관광형, 빨강)
const color = (t: number): [number, number, number] => [Math.round(60 + 195 * t), 120, Math.round(230 - 180 * t)]

export default function Map3D({ layer, highlight }: { layer: MapLayer; highlight: string[] }) {
  const [points, setPoints] = useState<Point[]>([])

  useEffect(() => {
    fetch(`/api/map/${layer}`).then((r) => r.json()).then((d) => setPoints(d.points ?? []))
  }, [layer])

  const max = Math.max(1, ...points.map((p) => p.value))
  const layers = [
    new ColumnLayer<Point>({
      id: 'columns',
      data: points,
      diskResolution: 12,
      radius: 900,
      extruded: true,
      pickable: true,
      getPosition: (p) => [p.lon, p.lat],
      getElevation: (p) => (p.value / max) * 30000,
      getFillColor: (p) => (highlight.includes(p.dong) ? [255, 210, 60] : color(p.tourism)),
      updateTriggers: { getFillColor: [highlight] },
    }),
  ]

  return (
    <DeckGL
      initialViewState={VIEW}
      controller
      layers={layers}
      getTooltip={({ object }) => object && `${(object as Point).dong}\n값 ${(object as Point).value.toLocaleString()}\n관광 비중 ${Math.round((object as Point).tourism * 100)}%`}
    />
  )
}
