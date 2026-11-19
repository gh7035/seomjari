import { DEM, HALLASAN, elevationAt } from './jejuDem'

// 한라산이 보이되 데이터 기둥보다 낮게. 얕은 바다는 덜 과장한다.
export const LAND_EXAG = 5
const SHELF_FLOOR = -42
const SHELF_EXAG = 2.6
export const SEA_Z = SHELF_FLOOR * SHELF_EXAG

export { HALLASAN }

const ANCHOR = {
  lon: DEM.lon0 + (DEM.dlon * (DEM.cols - 1)) / 2,
  lat: DEM.lat0 + (DEM.dlat * (DEM.rows - 1)) / 2,
}
export const JEJU_ANCHOR: [number, number] = [ANCHOR.lon, ANCHOR.lat]

const M_LAT = 110540
const M_LON = 111320 * Math.cos((ANCHOR.lat * Math.PI) / 180)

export function reliefZ(lon: number, lat: number): number {
  const h = elevationAt(lon, lat)
  if (h >= 0) return h * LAND_EXAG
  return Math.max(h, SHELF_FLOOR) * SHELF_EXAG
}

type RGB = [number, number, number]

const STOPS: [number, RGB][] = [
  [-42, [0.05, 0.20, 0.32]],
  [-16, [0.07, 0.38, 0.48]],
  [-3, [0.16, 0.55, 0.54]],
  [2, [0.22, 0.25, 0.20]],
  [16, [0.48, 0.62, 0.30]],
  [80, [0.28, 0.55, 0.24]],
  [260, [0.16, 0.44, 0.22]],
  [620, [0.24, 0.40, 0.20]],
  [1000, [0.42, 0.42, 0.26]],
  [1400, [0.58, 0.50, 0.38]],
  [1700, [0.76, 0.73, 0.66]],
  [1947, [0.93, 0.92, 0.89]],
]

function colorAt(h: number, lon: number, lat: number): RGB {
  let i = 1
  while (i < STOPS.length && h > STOPS[i][0]) i++
  const [h0, c0] = STOPS[Math.max(0, i - 1)]
  const [h1, c1] = STOPS[Math.min(STOPS.length - 1, i)]
  const t = h1 === h0 ? 0 : Math.max(0, Math.min(1, (h - h0) / (h1 - h0)))
  let r = c0[0] + (c1[0] - c0[0]) * t
  let g = c0[1] + (c1[1] - c0[1]) * t
  let b = c0[2] + (c1[2] - c0[2]) * t
  if (h > 8) {
    const grain = Math.sin(lon * 340) * Math.sin(lat * 290)
    const k = 1 + grain * 0.055
    r *= k
    g *= k
    b *= k
  }
  return [r, g, b]
}

function buildMesh() {
  const { cols, rows, lon0, lat0, dlon, dlat } = DEM
  const n = cols * rows
  const positions = new Float32Array(n * 3)
  const colors = new Float32Array(n * 3)
  const height = new Float32Array(n)

  for (let r = 0; r < rows; r++) {
    const lat = lat0 + r * dlat
    for (let c = 0; c < cols; c++) {
      const lon = lon0 + c * dlon
      const h = elevationAt(lon, lat)
      const i = r * cols + c
      height[i] = h
      const z = h >= 0 ? h * LAND_EXAG : Math.max(h, SHELF_FLOOR) * SHELF_EXAG
      positions[i * 3] = (lon - ANCHOR.lon) * M_LON
      positions[i * 3 + 1] = (lat - ANCHOR.lat) * M_LAT
      positions[i * 3 + 2] = z
      const [cr, cg, cb] = colorAt(h, lon, lat)
      colors[i * 3] = cr
      colors[i * 3 + 1] = cg
      colors[i * 3 + 2] = cb
    }
  }

  const tris: number[] = []
  for (let r = 0; r < rows - 1; r++) {
    for (let c = 0; c < cols - 1; c++) {
      const i00 = r * cols + c
      const i10 = i00 + 1
      const i01 = i00 + cols
      const i11 = i01 + 1
      const top = Math.max(height[i00], height[i10], height[i01], height[i11])
      if (top <= SHELF_FLOOR) continue
      tris.push(i00, i10, i11, i00, i11, i01)
    }
  }

  const indices = new Uint32Array(tris)
  const normals = new Float32Array(n * 3)
  for (let t = 0; t < indices.length; t += 3) {
    const ia = indices[t] * 3
    const ib = indices[t + 1] * 3
    const ic = indices[t + 2] * 3
    const ax = positions[ib] - positions[ia]
    const ay = positions[ib + 1] - positions[ia + 1]
    const az = positions[ib + 2] - positions[ia + 2]
    const bx = positions[ic] - positions[ia]
    const by = positions[ic + 1] - positions[ia + 1]
    const bz = positions[ic + 2] - positions[ia + 2]
    const nx = ay * bz - az * by
    const ny = az * bx - ax * bz
    const nz = ax * by - ay * bx
    for (const k of [ia, ib, ic]) {
      normals[k] += nx
      normals[k + 1] += ny
      normals[k + 2] += nz
    }
  }
  let up = 0
  for (let i = 2; i < normals.length; i += 3) up += normals[i]
  const flip = up < 0 ? -1 : 1
  for (let i = 0; i < normals.length; i += 3) {
    const x = normals[i] * flip
    const y = normals[i + 1] * flip
    const z = normals[i + 2] * flip
    const len = Math.hypot(x, y, z) || 1
    normals[i] = x / len
    normals[i + 1] = y / len
    normals[i + 2] = z / len
  }

  return {
    attributes: {
      positions: { size: 3, value: positions },
      normals: { size: 3, value: normals },
      colors: { size: 3, value: colors },
    },
    indices: { size: 1, value: indices },
  }
}

export const JEJU_MESH = buildMesh()

const SEA_PAD = 0.18
export const JEJU_SEA: [number, number, number][] = [
  [DEM.lon0 - SEA_PAD, DEM.lat0 - SEA_PAD, SEA_Z],
  [DEM.lon0 + DEM.dlon * (DEM.cols - 1) + SEA_PAD, DEM.lat0 - SEA_PAD, SEA_Z],
  [DEM.lon0 + DEM.dlon * (DEM.cols - 1) + SEA_PAD, DEM.lat0 + DEM.dlat * (DEM.rows - 1) + SEA_PAD, SEA_Z],
  [DEM.lon0 - SEA_PAD, DEM.lat0 + DEM.dlat * (DEM.rows - 1) + SEA_PAD, SEA_Z],
]
