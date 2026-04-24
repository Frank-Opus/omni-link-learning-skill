#!/usr/bin/env node

import { chromium } from 'playwright';

function parseArgs(argv) {
  const args = { url: '', timeout: 30000 };
  for (let i = 0; i < argv.length; i += 1) {
    const token = argv[i];
    if (token === '--url') args.url = argv[i + 1] || '';
    if (token === '--timeout') args.timeout = Number(argv[i + 1] || 30000);
  }
  if (!args.url) throw new Error('Missing required --url');
  return args;
}

async function main() {
  const { url, timeout } = parseArgs(process.argv.slice(2));
  let browser;
  try {
    try {
      browser = await chromium.launch({ headless: true, channel: 'chrome' });
    } catch {
      browser = await chromium.launch({ headless: true });
    }

    const page = await browser.newPage({
      userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36',
    });

    await page.goto(url, { waitUntil: 'domcontentloaded', timeout });
    await page.waitForTimeout(4000);

    const article = page.locator('article').first();
    const articleText = await article.innerText().catch(() => '');
    const title = await page.title().catch(() => '');
    const author = await page.locator('[data-testid=\"User-Name\"]').first().innerText().catch(() => '');
    const publishedAt = await page.locator('time').first().getAttribute('datetime').catch(() => null);
    const mediaUrls = await page.locator('article img').evaluateAll((nodes) =>
      nodes.map((node) => node.getAttribute('src')).filter(Boolean)
    ).catch(() => []);

    const lines = articleText.split('\n').map((line) => line.trim()).filter(Boolean);
    const handle = lines.find((line) => line.startsWith('@')) || null;

    const payload = {
      final_url: page.url(),
      title,
      author: author ? author.split('\n')[0] : null,
      handle,
      published_at: publishedAt,
      article_text: articleText,
      media_urls: mediaUrls,
    };
    process.stdout.write(JSON.stringify(payload));
  } finally {
    if (browser) await browser.close().catch(() => {});
  }
}

main().catch((error) => {
  process.stderr.write(String(error?.stack || error));
  process.exit(1);
});
