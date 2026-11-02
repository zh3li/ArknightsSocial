import { chromium } from 'playwright'
import { spawn } from 'child_process'

const PORT = 4319

async function main() {
  const server = spawn('npx', ['vite', 'preview', '--port', String(PORT), '--strictPort'], {
    cwd: process.cwd(),
    stdio: 'pipe',
  })
  await new Promise((res) => {
    server.stdout.on('data', (d) => {
      if (String(d).includes('Local')) res(null)
    })
    setTimeout(res, 4000)
  })

  const browser = await chromium.launch()
  const page = await browser.newPage({ viewport: { width: 1500, height: 900 } })
  const errors = []
  page.on('pageerror', (e) => errors.push(String(e)))
  page.on('console', (m) => {
    if (m.type() === 'error') errors.push(m.text())
  })

  await page.goto(`http://localhost:${PORT}/`)
  await page.waitForTimeout(3500)

  // 1. initial ego view loaded
  const stat = await page.textContent('#statCounts')
  console.log('STATUS:', stat)
  const panel = await page.textContent('#panelContent')
  console.log('PANEL has 阿米娅:', panel.includes('阿米娅'))

  await page.screenshot({ path: 'shot-ego.png' })

  // 2. relations table rows
  const rows = await page.locator('.relrow').count()
  console.log('RELATION ROWS:', rows)

  // 3. click first relation row -> evidence
  if (rows > 0) {
    await page.locator('.relrow').first().click()
    await page.waitForTimeout(400)
    const quotes = await page.locator('.evbox:not(.hidden) .quote').count()
    console.log('EVIDENCE QUOTES visible:', quotes)
    await page.screenshot({ path: 'shot-evidence.png' })
  }

  // 4. switch to path mode
  await page.click('button[data-mode="path"]')
  await page.waitForTimeout(300)
  await page.fill('#pathA', '塔露拉')
  await page.fill('#pathB', '阿米娅')
  await page.click('#btnPath')
  await page.waitForTimeout(1500)
  const pathText = await page.textContent('#panelContent')
  console.log('PATH panel snippet:', pathText.slice(0, 160).replace(/\n/g, ' '))
  await page.screenshot({ path: 'shot-path.png' })

  // 5. full graph mode
  await page.click('button[data-mode="full"]')
  await page.waitForTimeout(4000)
  const stat2 = await page.textContent('#statCounts')
  console.log('FULL STATUS:', stat2)
  await page.screenshot({ path: 'shot-full.png' })

  // 6. search jump
  await page.click('button[data-mode="ego"]')
  await page.fill('#search', '银灰')
  await page.click('#btnGo')
  await page.waitForTimeout(1500)
  const panel2 = await page.textContent('#panelContent')
  console.log('SILVERASH panel:', panel2.slice(0, 100).replace(/\n/g, ' '))

  // 7. rankings
  await page.click('#btnRank')
  await page.waitForTimeout(300)
  const rankRows = await page.locator('.rankrow').count()
  console.log('RANK ROWS:', rankRows)
  await page.screenshot({ path: 'shot-rank.png' })
  await page.click('#btnRankClose')

  console.log('PAGE ERRORS:', errors.length ? errors.slice(0, 5) : 'none')

  await browser.close()
  server.kill()
}

main().catch((e) => {
  console.error('SMOKE FAIL', e)
  process.exit(1)
})
