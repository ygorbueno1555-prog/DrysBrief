import fs from 'node:fs/promises';
import path from 'node:path';
import { chromium } from 'playwright';

const BASE_URL = process.env.DEMO_BASE_URL || 'https://cortiq-decisioncopilot.up.railway.app';
const ROOT = process.cwd();
const VIDEO_DIR = path.join(ROOT, 'demo-artifacts', 'videos');

async function ensureDir(dir) {
  await fs.mkdir(dir, { recursive: true });
}

async function pause(page, ms) {
  await page.waitForTimeout(ms);
}

async function typeSlow(locator, text) {
  await locator.click();
  await locator.fill('');
  await locator.type(text, { delay: 45 });
}

async function waitForAnalysis(page) {
  await page.waitForTimeout(4000);
  await page.waitForFunction(
    () => {
      const verdict = document.querySelector('#verdict-tag')?.textContent?.trim() || '';
      const status = document.querySelector('#status-text')?.textContent?.trim() || '';
      const reportLength = document.querySelector('#report-content')?.textContent?.trim()?.length || 0;
      return (
        reportLength > 1200 ||
        status.includes('Análise concluída') ||
        ['TESE MANTIDA', 'TESE ALTERADA', 'TESE INVALIDADA', 'COMPRAR', 'MANTER', 'REDUZIR', 'VENDER'].includes(verdict)
      );
    },
    { timeout: 90000 }
  ).catch(() => {});
}

async function waitForBrief(page) {
  await page.waitForTimeout(3000);
  await page.waitForResponse(
    response => response.url().includes('/api/briefing/run') && response.request().method() === 'POST',
    { timeout: 15000 }
  ).catch(() => {});

  await page.waitForFunction(
    () => {
      const panelVisible = document.querySelector('#draft-panel')?.style.display !== 'none';
      const drafts = document.querySelector('#draft-list')?.textContent?.trim()?.length || 0;
      return panelVisible || drafts > 0;
    },
    { timeout: 120000 }
  ).catch(() => {});
}

async function main() {
  await ensureDir(VIDEO_DIR);

  const browser = await chromium.launch({
    headless: true,
    chromiumSandbox: false,
    slowMo: 180,
  });

  const context = await browser.newContext({
    viewport: { width: 1440, height: 960 },
    recordVideo: {
      dir: VIDEO_DIR,
      size: { width: 1440, height: 960 },
    },
  });

  const page = await context.newPage();
  let videoPath = null;

  try {
    await page.goto(BASE_URL, { waitUntil: 'domcontentloaded', timeout: 30000 });
    await pause(page, 1800);

    await typeSlow(page.locator('#ticker'), 'VALE3');
    await typeSlow(
      page.locator('#thesis'),
      'A Vale pode continuar capturando upside com recuperação operacional e valuation ainda descontado.'
    );
    await typeSlow(page.locator('#mandate'), 'Long-only Brasil, horizonte de 2 a 3 anos.');
    await pause(page, 800);

    await page.click('#btn-equity');
    await waitForAnalysis(page);
    await pause(page, 5000);

    await page.goto(`${BASE_URL}/briefing`, { waitUntil: 'domcontentloaded', timeout: 30000 });
    await pause(page, 1800);

    await page.click('#btn-generate');
    await waitForBrief(page);
    await pause(page, 6000);
  } finally {
    const video = page.video();
    await page.close().catch(() => {});
    await context.close().catch(() => {});
    await browser.close().catch(() => {});

    if (video) {
      videoPath = await video.path().catch(() => null);
    }
  }

  if (!videoPath) {
    throw new Error('Nao foi possivel localizar o video gravado.');
  }

  const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
  const outputPath = path.join(VIDEO_DIR, `cortiq-demo-${timestamp}.webm`);
  const latestPath = path.join(VIDEO_DIR, 'cortiq-demo-latest.webm');

  await fs.copyFile(videoPath, outputPath);
  await fs.copyFile(videoPath, latestPath);

  console.log(`Demo gravada em: ${outputPath}`);
  console.log(`Ultima demo: ${latestPath}`);
}

main().catch(error => {
  console.error(error);
  process.exit(1);
});
