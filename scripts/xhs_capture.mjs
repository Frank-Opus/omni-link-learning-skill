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

function firstUrl(value) {
  if (!value) return null;
  if (typeof value === 'string' && value.startsWith('http')) return value;
  if (Array.isArray(value)) {
    for (const item of value) {
      if (typeof item === 'string' && item.startsWith('http')) return item;
    }
  }
  return null;
}

function walk(obj, visit) {
  if (Array.isArray(obj)) {
    for (const item of obj) walk(item, visit);
    return;
  }
  if (!obj || typeof obj !== 'object') return;
  visit(obj);
  for (const value of Object.values(obj)) walk(value, visit);
}

function extractVideoUrl(obj) {
  let candidate = null;
  walk(obj, (node) => {
    if (candidate) return;
    for (const [key, value] of Object.entries(node)) {
      const lower = key.toLowerCase();
      if (typeof value === 'string' && value.startsWith('http') && (value.includes('.mp4') || value.includes('.m3u8'))) {
        candidate = value;
        return;
      }
      if (lower.includes('video') || lower.includes('stream') || lower.includes('masterurl')) {
        const url = firstUrl(value);
        if (url && (url.includes('.mp4') || url.includes('.m3u8') || url.includes('video'))) {
          candidate = url;
          return;
        }
      }
    }
  });
  return candidate;
}

async function main() {
  const { url, timeout } = parseArgs(process.argv.slice(2));
  let browser;
  const errors = [];
  try {
    try {
      browser = await chromium.launch({ headless: true, channel: 'chrome' });
    } catch {
      browser = await chromium.launch({ headless: true });
    }
    const context = await browser.newContext({
      userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36',
      locale: 'zh-CN',
      viewport: { width: 1440, height: 960 },
    });
    const page = await context.newPage();
    let videoUrl = null;

    page.on('response', async (response) => {
      if (videoUrl) return;
      const responseUrl = response.url();
      try {
        if (responseUrl.includes('.mp4') || responseUrl.includes('.m3u8')) {
          videoUrl = responseUrl;
          return;
        }
        const contentType = response.headers()['content-type'] || '';
        if (!contentType.includes('json')) return;
        const data = await response.json();
        const extracted = extractVideoUrl(data);
        if (extracted) videoUrl = extracted;
      } catch {
      }
    });

    await page.goto(url, { waitUntil: 'domcontentloaded', timeout });
    await page.waitForTimeout(5000);

    if (!videoUrl) {
      const html = await page.content().catch(() => '');
      const match = html.match(/https?:\/\/[^"'\s]+(?:\.mp4|\.m3u8)[^"'\s]*/);
      if (match) videoUrl = match[0].replace(/\\u002F/g, '/');
    }

    process.stdout.write(JSON.stringify({ final_url: page.url(), video_url: videoUrl, errors }));
  } finally {
    if (browser) await browser.close().catch(() => {});
  }
}

main().catch((error) => {
  process.stderr.write(String(error?.stack || error));
  process.exit(1);
});
