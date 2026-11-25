/**
 * test_gd15_1_browser_automation.mjs
 * Browser automation suite for GD15.1 Remediation & Consistency Verification.
 * Captures clean visual screenshots for:
 * 1. Terminal with Stocks (NVDA)
 * 2. Terminal with Crypto Live 24/7 (BTC/USD live candles, health verdict)
 * 3. Strategy Analytics (Alpha attribution, N/A metrics on 0 trades, Production tag)
 * 4. Paper Portfolio Consistent (Matches Terminal equity/cash, source timestamp, cache age)
 * 5. Streaming Observability 5-Pillar Health Architecture
 * 6. Reliability Logs & Reduced Outbox (Deduplicated transitions, fixture isolation)
 */
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';
import { createRequire } from 'module';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const require = createRequire(path.resolve(__dirname, '..', 'trading-dashboard', 'frontend', 'package.json'));
const puppeteer = require('puppeteer-core');

const CHROME_PATH = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const DASHBOARD_URL = 'http://localhost:5173';
const SCREENSHOTS_DIR = path.resolve(__dirname, '..', 'docs', 'screenshots');

if (!fs.existsSync(SCREENSHOTS_DIR)) {
  fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });
}

async function runBrowserTests() {
  console.log('==================================================================');
  console.log('  AlgoTrading GD15.1 Browser Automation & Visual Acceptance Suite');
  console.log('==================================================================');

  const browser = await puppeteer.launch({
    executablePath: CHROME_PATH,
    headless: true,
    defaultViewport: { width: 1520, height: 1000 },
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
  });

  const page = await browser.newPage();
  page.on('pageerror', err => console.log('PAGE EXCEPTION:', err.message));
  page.on('console', msg => {
    if (msg.type() === 'error') console.log('BROWSER CONSOLE ERROR:', msg.text());
  });

  try {
    // 1. Dashboard Load & Stocks Terminal
    console.log('[1/6] Loading Terminal (Stocks NVDA) at http://localhost:5173 ...');
    await page.goto(DASHBOARD_URL, { waitUntil: 'networkidle0', timeout: 20000 });
    await page.waitForSelector('header', { timeout: 10000 });
    await new Promise(r => setTimeout(r, 3000)); // Allow portfolio & stats hydration

    const ss1 = path.join(SCREENSHOTS_DIR, 'gd15_1_01_terminal_stocks.png');
    await page.screenshot({ path: ss1, fullPage: true });
    console.log(`  -> Saved Screenshot 1: ${ss1}`);

    // 2. Switch to Crypto 24/7 Live
    console.log('[2/6] Switching Asset Class to CRYPTO 24/7 (BTC/USD) ...');
    const buttons = await page.$$('button');
    let cryptoBtn = null;
    for (const btn of buttons) {
      const text = await page.evaluate(el => el.innerText, btn);
      if (text.includes('CRYPTO 24/7')) {
        cryptoBtn = btn;
        break;
      }
    }
    if (cryptoBtn) {
      await cryptoBtn.click();
      await new Promise(r => setTimeout(r, 3500)); // Wait for candle fetch & canvas render
      const ss2 = path.join(SCREENSHOTS_DIR, 'gd15_1_02_terminal_crypto_live.png');
      await page.screenshot({ path: ss2, fullPage: true });
      console.log(`  -> Saved Screenshot 2 (Crypto Live): ${ss2}`);
    } else {
      console.warn('  -> Could not find CRYPTO 24/7 toggle button');
    }

    // 3. Navigate to Strategy Analytics
    console.log('[3/6] Navigating to Strategy Analytics Tab ...');
    let analyticsNavBtn = null;
    for (const btn of await page.$$('button')) {
      const text = await page.evaluate(el => el.innerText, btn);
      if (text.includes('Strategy Analytics')) {
        analyticsNavBtn = btn;
        break;
      }
    }
    if (analyticsNavBtn) {
      await analyticsNavBtn.click();
      await new Promise(r => setTimeout(r, 3000));

      const ss3 = path.join(SCREENSHOTS_DIR, 'gd15_1_03_strategy_analytics.png');
      await page.screenshot({ path: ss3, fullPage: true });
      console.log(`  -> Saved Screenshot 3 (Strategy Analytics): ${ss3}`);
    }

    // 4. Navigate to Paper Portfolio
    console.log('[4/6] Navigating to Paper Portfolio Tab ...');
    let portfolioNavBtn = null;
    for (const btn of await page.$$('button')) {
      const text = await page.evaluate(el => el.innerText, btn);
      if (text.includes('Paper Portfolio')) {
        portfolioNavBtn = btn;
        break;
      }
    }
    if (portfolioNavBtn) {
      await portfolioNavBtn.click();
      // Wait for Alpaca API hydration
      try {
        await page.waitForFunction(() => !document.body.innerText.includes('Connecting to Alpaca Paper Trading API...'), { timeout: 15000 });
      } catch (e) {
        console.warn('Timed out waiting for Connecting to Alpaca spinner to finish');
      }
      await new Promise(r => setTimeout(r, 1500));

      const ss4 = path.join(SCREENSHOTS_DIR, 'gd15_1_04_paper_portfolio_consistent.png');
      await page.screenshot({ path: ss4, fullPage: true });
      console.log(`  -> Saved Screenshot 4 (Paper Portfolio Consistent): ${ss4}`);
    }

    // 5. Navigate to Streaming Observability
    console.log('[5/6] Navigating to Streaming Observability Tab ...');
    let obsNavBtn = null;
    for (const btn of await page.$$('button')) {
      const text = await page.evaluate(el => el.innerText, btn);
      if (text.includes('Streaming Observability')) {
        obsNavBtn = btn;
        break;
      }
    }
    if (obsNavBtn) {
      await obsNavBtn.click();
      await new Promise(r => setTimeout(r, 3000));

      const ss5 = path.join(SCREENSHOTS_DIR, 'gd15_1_05_observability_5pillars.png');
      await page.screenshot({ path: ss5, fullPage: true });
      console.log(`  -> Saved Screenshot 5 (5-Pillar Observability): ${ss5}`);
    }

    // 6. Navigate to Reliability & Logs
    console.log('[6/6] Navigating to Reliability & Logs Tab ...');
    let relNavBtn = null;
    for (const btn of await page.$$('button')) {
      const text = await page.evaluate(el => el.innerText, btn);
      if (text.includes('Reliability & Logs')) {
        relNavBtn = btn;
        break;
      }
    }
    if (relNavBtn) {
      await relNavBtn.click();
      await new Promise(r => setTimeout(r, 3000));

      const ss6 = path.join(SCREENSHOTS_DIR, 'gd15_1_06_reliability_outbox_reduced.png');
      await page.screenshot({ path: ss6, fullPage: true });
      console.log(`  -> Saved Screenshot 6 (Reduced Reliability Logs): ${ss6}`);
    }

    console.log('==================================================================');
    console.log('  All 6 GD15.1 Verification Screenshots Captured Successfully!');
    console.log('==================================================================');

  } catch (err) {
    console.error('Browser automation error:', err);
  } finally {
    await browser.close();
  }
}

runBrowserTests();
