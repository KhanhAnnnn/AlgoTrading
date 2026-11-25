import puppeteer from 'puppeteer-core';
import fs from 'fs';
import path from 'path';

(async () => {
  const browser = await puppeteer.launch({
    executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });

  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 900 });

  const consoleLogs = [];
  page.on('console', msg => {
    consoleLogs.push({ type: msg.type(), text: msg.text() });
    console.log(`[BROWSER ${msg.type().toUpperCase()}] ${msg.text()}`);
  });

  page.on('pageerror', err => {
    console.error(`[PAGE ERROR] ${err.toString()}`);
  });

  console.log('Navigating to http://localhost:5173...');
  try {
    await page.goto('http://localhost:5173', { waitUntil: 'networkidle0', timeout: 15000 });
  } catch (e) {
    console.log('Navigation wait finished or timed out:', e.message);
  }

  await new Promise(r => setTimeout(r, 2000));

  const screenshotPath = 'd:\\AlgoTrading\\screenshot_initial.png';
  await page.screenshot({ path: screenshotPath, fullPage: true });
  console.log(`Screenshot saved to ${screenshotPath}`);

  const pageTitle = await page.title();
  console.log('Page Title:', pageTitle);

  // Check DOM elements
  const rootHtml = await page.evaluate(() => {
    const root = document.getElementById('root');
    return root ? { childCount: root.children.length, textLength: root.innerText.length } : null;
  });
  console.log('Root element stats:', rootHtml);

  await browser.close();
})();

