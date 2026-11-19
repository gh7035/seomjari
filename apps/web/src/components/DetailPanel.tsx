import { useEffect, useState } from 'react'
import { getStores, type StoreItem } from '../api'

interface Props {
  dong: string
  lon: number
  lat: number
  category: string | null
  onClose: () => void
}

export default function DetailPanel({ dong, lon, lat, category, onClose }: Props) {
  const [items, setItems] = useState<StoreItem[] | null>(null)
  const [total, setTotal] = useState<number>(0)
  const [err, setErr] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true); setErr(null); setItems(null)
    getStores(dong, category ?? undefined)
      .then((r) => { setItems(r.items); setTotal(r.total) })
      .catch((e) => setErr(String(e)))
      .finally(() => setLoading(false))
  }, [dong, category])

  const kakaoRoad = `https://map.kakao.com/link/roadview/${lat},${lng(lon)}`
  const kakaoMap = `https://map.kakao.com/link/map/${encodeURIComponent(dong)},${lat},${lng(lon)}`
  const kakaoSearch = category
    ? `https://map.kakao.com/link/search/${encodeURIComponent(`${dong} ${category}`)}`
    : `https://map.kakao.com/link/search/${encodeURIComponent(dong)}`

  return (
    <div className="detail-panel">
      <div className="detail-head">
        <div>
          <div className="detail-dong">{dong}</div>
          <div className="detail-sub">{category ? `${category} · 주변 가게` : '주변 가게'} · {lat.toFixed(4)}, {lng(lon).toFixed(4)}</div>
        </div>
        <button className="detail-close" onClick={onClose} aria-label="닫기">×</button>
      </div>

      <div className="detail-section">
        <div className="detail-section-title">카카오맵 바로가기</div>
        <div className="detail-links">
          <a className="detail-link" href={kakaoRoad} target="_blank" rel="noreferrer">
            <span className="detail-link-ic">📍</span>
            <span>로드뷰 열기</span>
          </a>
          <a className="detail-link" href={kakaoMap} target="_blank" rel="noreferrer">
            <span className="detail-link-ic">🗺</span>
            <span>지도에서 보기</span>
          </a>
          <a className="detail-link" href={kakaoSearch} target="_blank" rel="noreferrer">
            <span className="detail-link-ic">🔎</span>
            <span>{category ?? '동'} 검색</span>
          </a>
        </div>
      </div>

      <div className="detail-section">
        <div className="detail-section-title">
          주변 실 가게
          {items && <span className="detail-count"> · {total}개</span>}
        </div>
        {loading && <div className="detail-empty">불러오는 중…</div>}
        {err && (
          <div className="detail-empty">
            <div>목록을 가져올 수 없습니다.</div>
            <div className="detail-empty-sub">백엔드 <code>/api/stores</code> 미구현 (FE_REQUESTS #6 참조)</div>
          </div>
        )}
        {items && items.length === 0 && !err && (
          <div className="detail-empty">
            <div>아직 표시할 가게 데이터가 없어요.</div>
            <div className="detail-empty-sub">백엔드 <code>/api/stores</code> 배포 대기 중 (FE_REQUESTS #6)</div>
          </div>
        )}
        {items && items.length > 0 && (
          <ul className="detail-stores">
            {items.map((s, i) => (
              <li key={`${s.name}-${i}`} className="detail-store">
                <div className="detail-store-name">{s.name}</div>
                <div className="detail-store-meta">
                  {s.category && <span>{s.category}</span>}
                  {s.distance_m != null && <span>· {s.distance_m}m</span>}
                </div>
                <div className="detail-store-addr">{s.address}</div>
                <a className="detail-store-link" target="_blank" rel="noreferrer"
                   href={`https://map.kakao.com/link/map/${encodeURIComponent(s.name)},${s.lat},${lng(s.lon)}`}>
                  지도에서 보기 ↗
                </a>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}

// 카카오 URL 은 lng 를 그대로 받음. 가독성 위해 함수화.
function lng(lon: number) { return lon }
