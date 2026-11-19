// 투어 A, B 스크린샷. dev 서버는 :5174, 백엔드는 :8000 가정.
import { chromium } from 'playwright'
import { existsSync, mkdirSync } from 'node:fs'

const OUT = '/Users/seolgyuhan/Desktop/seomjari/docs/screenshots'
if (!existsSync(OUT)) mkdirSync(OUT, { recursive: true })

const URL_DEV = 'http://localhost:5174/'

const browser = await chromium.launch()
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 })

// 투어 A: 랜딩 첫 방문 (localStorage 비움)
{
  const page = await ctx.newPage()
  await page.goto(URL_DEV, { waitUntil: 'networkidle' })
  await page.evaluate(() => { try { localStorage.clear() } catch {} })
  await page.reload({ waitUntil: 'networkidle' })
  await page.waitForSelector('.tour-tooltip.in', { timeout: 8000 }).catch(() => {})
  await page.waitForTimeout(700)
  await page.screenshot({ path: `${OUT}/tour-a-landing.png`, fullPage: false })
  console.log('saved tour-a-landing.png')
  await page.close()
}

// 투어 B: 대시보드 진입 후 ? 버튼으로 수동 오픈 (리포트 로딩 시간 대기 최소화)
{
  const page = await ctx.newPage()
  page.on('pageerror', (e) => console.log('[pageerror]', e.message))
  await page.goto(URL_DEV, { waitUntil: 'networkidle' })
  await page.evaluate(() => {
    try {
      localStorage.setItem('seomjari_tour_v1', '1')
      localStorage.setItem('seomjari_tour_report_v1', '1') // 자동 오픈 막음
    } catch {}
  })
  await page.reload({ waitUntil: 'networkidle' })

  // 질문 전송
  const input = page.locator('[data-tour="entry-input"] input')
  await input.click()
  await input.fill('애월읍에서 카페 창업하려는데요')
  await input.press('Enter')

  // 대시보드 + 리포트 (신호등) 대기
  await page.waitForSelector('.dash', { timeout: 20000 })
  await page.waitForSelector('[data-tour="signals"]', { timeout: 60000 })
  await page.waitForTimeout(1500)

  // ? 버튼으로 투어 B 수동 오픈
  await page.locator('.dash-top .help-btn').click()
  await page.waitForSelector('.tour-tooltip.in', { timeout: 5000 })
  await page.waitForTimeout(600)
  await page.screenshot({ path: `${OUT}/tour-b-dashboard.png`, fullPage: false })
  console.log('saved tour-b-dashboard.png')
  await page.close()
}

await browser.close()
console.log('done')
