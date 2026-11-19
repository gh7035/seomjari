import { useEffect, useMemo, useState } from 'react'
import DeckGL from '@deck.gl/react'
import { ColumnLayer, SolidPolygonLayer, TextLayer } from '@deck.gl/layers'
import { SimpleMeshLayer } from '@deck.gl/mesh-layers'
import { AmbientLight, DirectionalLight, LightingEffect } from '@deck.gl/core'
import { getMapLayer } from '../api'
import type { MapLayer, MapPoint } from '../types'
import { HALLASAN, JEJU_ANCHOR, JEJU_MESH, JEJU_SEA, reliefZ } from './jejuTerrain'

// 북동쪽 햇빛. ambient 를 낮춰 사면 음영이 남게 한다.
const lighting = new LightingEffect({
  ambient: new AmbientLight({ color: [255, 255, 255], intensity: 0.55 }),
  dir1: new DirectionalLight({ color: [255, 236, 210], intensity: 2.2, direction: [-1.4, -2.4, -1.5] }),
  dir2: new DirectionalLight({ color: [170, 200, 230], intensity: 0.45, direction: [2.2, 1.2, -0.6] }),
})

const VIEW = { longitude: 126.55, latitude: 33.38, zoom: 9.0, pitch: 50, bearing: -10 }

const LAYERS: { key: MapLayer; label: string; hint: string }[] = [
  { key: 'demand', label: '수요', hint: '기둥 높이는 2018–2019년 월평균 카드 매출입니다. 색은 관광객 비중이라 파랑은 도민형, 주황은 관광형입니다.' },
  { key: 'tourism', label: '관광', hint: '관광객 매출이 전체에서 차지하는 비중입니다. 기둥이 높고 주황에 가까울수록 관광에 기대는 지역입니다.' },
  { key: 'supply', label: '공급', hint: '선택한 업종의 점포 수입니다. 기둥이 높을수록 같은 업종 가게가 많습니다.' },
  { key: 'footfall', label: '유동', hint: '방문인구 월평균입니다. 업종과 상관없이 사람이 많이 드나드는 지역을 보여 줍니다.' },
  { key: 'survival', label: '생존', hint: '기둥 높이는 점포 수, 색은 3년 생존율입니다. 주황에 가까울수록 생존율이 낮습니다.' },
]

// 관광 의존도 0(파랑, 도민형) → 1(주황, 관광형)
function tourismColor(t: number): [number, number, number] {
  const r = Math.round(60 + 195 * Math.max(0, Math.min(1, t)))
  const b = Math.round(230 - 180 * Math.max(0, Math.min(1, t)))
  return [r, 120, b]
}

function densityColor(v: number, max: number): [number, number, number] {
  const r = v / Math.max(1, max)
  return [80 + Math.round(160 * r), 80 + Math.round(60 * r), 150 - Math.round(40 * r)]
}

interface Props {
  layer: MapLayer
  category: string | null
  highlight: string[]
  month: number
  onSelectDong?: (p: { dong: string; lon: number; lat: number }) => void
}

export default function Map3D({ layer: initialLayer, category, highlight, month, onSelectDong }: Props) {
  const [layer, setLayer] = useState<MapLayer>(initialLayer)
  const [viewState, setViewState] = useState<typeof VIEW>(VIEW)
  const [autoRotate, setAutoRotate] = useState(false)
  const [points, setPoints] = useState<MapPoint[]>([])
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => { setLayer(initialLayer) }, [initialLayer])

  // 자동 회전: bearing 을 초당 약 6도 증가
  useEffect(() => {
    if (!autoRotate) return
    let raf = 0
    let last = performance.now()
    const tick = (t: number) => {
      const dt = (t - last) / 1000
      last = t
      setViewState((v) => ({ ...v, bearing: ((v.bearing + dt * 6 + 540) % 360) - 180 }))
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [autoRotate])

  useEffect(() => {
    if (!category) { setPoints([]); return }
    setLoading(true); setErr(null)
    getMapLayer(layer, category, month > 0 ? month : undefined)
      .then((d) => { setErr(null); setPoints(d.points ?? []) })
      .catch(() => { /* 429 등 전파된 재시도도 실패하면 조용히 빈 상태 유지 */ })
      .finally(() => setLoading(false))
  }, [layer, category, month])

  const max = Math.max(1, ...points.map((p) => p.value))

  const deckLayers = useMemo(() => [
    new SolidPolygonLayer({
      id: 'jeju-sea',
      data: [{ polygon: JEJU_SEA }],
      getPolygon: (d) => d.polygon,
      _full3d: true,
      extruded: false,
      stroked: false,
      filled: true,
      getFillColor: [6, 32, 52, 255],
      pickable: false,
      material: false,
    }),
    new SimpleMeshLayer({
      id: 'jeju-terrain',
      data: [0],
      mesh: JEJU_MESH,
      getPosition: JEJU_ANCHOR,
      getColor: [255, 255, 255, 255],
      pickable: false,
      material: { ambient: 0.38, diffuse: 0.9, shininess: 4, specularColor: [20, 28, 22] },
    }),
    new TextLayer({
      id: 'hallasan-label',
      data: [{ lon: HALLASAN.lon, lat: HALLASAN.lat, z: reliefZ(HALLASAN.lon, HALLASAN.lat) + 420 }],
      getPosition: (d: { lon: number; lat: number; z: number }) => [d.lon, d.lat, d.z],
      getText: () => '한라산 고도 1947m',
      getSize: 11,
      getColor: [220, 230, 240, 230],
      sizeUnits: 'pixels',
      background: true,
      getBackgroundColor: [4, 7, 13, 180],
      backgroundPadding: [4, 2, 4, 2],
      fontFamily: 'Inter, system-ui, sans-serif',
      pickable: false,
    }),
    // ③ 행정동 기둥
    new ColumnLayer<MapPoint>({
      id: `columns-${layer}`,
      data: points,
      diskResolution: 14,
      radius: 850,
      extruded: true,
      pickable: true,
      onClick: (info) => {
        const p = info.object as MapPoint | undefined
        if (p && onSelectDong) onSelectDong({ dong: p.dong, lon: p.lon, lat: p.lat })
      },
      getPosition: (p) => [p.lon, p.lat, Math.max(0, reliefZ(p.lon, p.lat)) + 160],
      getElevation: (p) => (p.value / max) * 26000,
      getFillColor: (p) => {
        if (highlight.includes(p.dong)) return [255, 210, 60]
        if (layer === 'supply' || layer === 'footfall') return densityColor(p.value, max)
        // survival: tourism 필드가 (1 - 3년 생존율). 0=안전(파랑) 1=위험(주황)
        return tourismColor(p.tourism)
      },
      stroked: true,
      lineWidthMinPixels: 1,
      getLineColor: (p) => (highlight.includes(p.dong) ? [255, 170, 0, 255] : [0, 0, 0, 0]),
      updateTriggers: {
        getFillColor: [highlight.join(','), layer, max],
        getElevation: [max, month, points.length],
        getLineColor: [highlight.join(',')],
      },
      transitions: {
        getElevation: { duration: 600, easing: (t: number) => t * (2 - t) },
      },
      material: { ambient: 0.6, diffuse: 0.9, shininess: 30, specularColor: [255, 255, 255] },
    }),
  ], [points, layer, highlight, max, onSelectDong, month])

  return (
    <div className="map-root">
      <div className="map-canvas">
      <DeckGL
        viewState={viewState}
        onViewStateChange={(e) => setViewState(e.viewState as typeof VIEW)}
        controller
        effects={[lighting]}
        layers={deckLayers}
        getTooltip={({ object }) => {
          if (!object) return null
          const p = object as MapPoint
          return {
            html: `<div style="font-size:12px;line-height:1.5">
              <b>${p.dong}</b><br/>
              값 ${p.value.toLocaleString()}<br/>
              관광 비중 ${Math.round(p.tourism * 100)}%
              ${p.stores != null ? `<br/>점포수 ${p.stores}` : ''}
            </div>`,
            style: { background: 'rgba(15,23,42,0.92)', color: '#fff', padding: '6px 8px', borderRadius: '6px' },
          }
        }}
      />

      <div className="map-toolbar">
        <div className="layer-toggle" data-tour="map-layers">
          {LAYERS.map((l) => (
            <button
              key={l.key}
              onClick={() => setLayer(l.key)}
              className={layer === l.key ? 'active' : ''}
              type="button"
              aria-describedby={`layer-hint-${l.key}`}
            >
              {l.label}
              <span className="layer-hint" role="tooltip" id={`layer-hint-${l.key}`}>{l.hint}</span>
            </button>
          ))}
        </div>
        <div className="legend">
          {(layer === 'demand' || layer === 'tourism') ? (
            <>
              <span className="legend-swatch" style={{ background: 'rgb(60,120,230)' }} />도민형
              <span className="legend-grad" />
              <span className="legend-swatch" style={{ background: 'rgb(255,120,50)' }} />관광형
            </>
          ) : layer === 'survival' ? (
            <>
              <span className="legend-swatch" style={{ background: 'rgb(60,120,230)' }} />안전
              <span className="legend-grad" />
              <span className="legend-swatch" style={{ background: 'rgb(255,120,50)' }} />위험
            </>
          ) : (
            <>
              <span className="legend-swatch" style={{ background: 'rgb(90,90,140)' }} />낮음
              <span className="legend-grad" />
              <span className="legend-swatch" style={{ background: 'rgb(230,130,110)' }} />높음
            </>
          )}
          {highlight.length > 0 && (
            <>
              <span className="legend-swatch" style={{ background: 'rgb(255,210,60)', marginLeft: 10 }} />
              <span className="legend-hi">강조 {highlight.join(', ')}</span>
            </>
          )}
        </div>
      </div>

      <div className="map-ctrl">
        <button
          type="button"
          className="map-ctrl-btn"
          title="시점 초기화"
          onClick={() => { setAutoRotate(false); setViewState(VIEW) }}
        >⟲</button>
        <button
          type="button"
          className={`map-ctrl-btn ${autoRotate ? 'active' : ''}`}
          title={autoRotate ? '자동 회전 끄기' : '자동 회전 켜기'}
          onClick={() => setAutoRotate((v) => !v)}
        >↻</button>
        <button
          type="button"
          className="map-ctrl-btn"
          title={viewState.pitch > 20 ? '2D 평면 보기' : '3D 입체 보기'}
          onClick={() => setViewState({ ...viewState, pitch: viewState.pitch > 20 ? 0 : 45 })}
        >{viewState.pitch > 20 ? '2D' : '3D'}</button>
      </div>

      {!category && <div className="map-hint">진단을 실행하면 지도가 그려집니다.</div>}
      {loading && <div className="map-hint" style={{ bottom: 'auto', top: 60 }}>불러오는 중…</div>}
      {err && <div className="map-hint" style={{ color: '#fecaca' }}>지도 오류: {err}</div>}
      </div>
    </div>
  )
}
