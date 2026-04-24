#!/usr/bin/env node

import { chromium } from 'playwright';

function parseArgs(argv) {
  const args = { url: '', timeout: 30000 };
  for (let i = 0; i < argv.length; i += 1) {
    const token = argv[i];
    if (token === '--url') args.url = argv[i + 1] || '';
    if (token === '--timeout') args.timeout = Number(argv[i + 1] || 30000);
  }
  if (!args.url) {
    throw new Error('Missing required --url');
  }
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

function extractAweme(payload) {
  if (!payload || typeof payload !== 'object') return null;
  if (payload.aweme_detail) return payload.aweme_detail;
  if (payload.aweme) return payload.aweme;
  if (payload.item) return payload.item;
  if (Array.isArray(payload.aweme_list) && payload.aweme_list.length) return payload.aweme_list[0];
  if (payload.data && typeof payload.data === 'object') return extractAweme(payload.data);
  return null;
}

function pickPlayUrl(video) {
  if (!video || typeof video !== 'object') return null;
  const direct = firstUrl(video.play_addr?.url_list)
    || firstUrl(video.play_api?.url_list)
    || firstUrl(video.download_addr?.url_list)
    || firstUrl(video.playAddr?.urlList);
  if (direct) return direct;
  if (Array.isArray(video.bit_rate)) {
    for (const item of video.bit_rate) {
      const url = firstUrl(item?.play_addr?.url_list) || firstUrl(item?.playAddr?.urlList);
      if (url) return url;
    }
  }
  return null;
}

async function main() {
  const { url, timeout } = parseArgs(process.argv.slice(2));
  const userAgent = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36';

  let browser;
  try {
    try {
      browser = await chromium.launch({ headless: true, channel: 'chrome' });
    } catch {
      browser = await chromium.launch({ headless: true });
    }

    const context = await browser.newContext({
      userAgent,
      locale: 'zh-CN',
      viewport: { width: 1440, height: 960 },
      extraHTTPHeaders: {
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
      },
    });
    const page = await context.newPage();

    let capturedApiUrl = null;
    let capturedPayload = null;
    let finalUrl = url;

    const matchesDetailApi = (target) => (
      target.includes('/aweme/v1/web/aweme/detail/') ||
      target.includes('/aweme/detail/') ||
      target.includes('/web/api/v2/aweme/iteminfo/')
    );

    page.on('response', async (response) => {
      const responseUrl = response.url();
      if (!matchesDetailApi(responseUrl)) return;
      try {
        const contentType = response.headers()['content-type'] || '';
        if (!contentType.includes('json')) return;
        const body = await response.json();
        const aweme = extractAweme(body);
        if (aweme) {
          capturedApiUrl = responseUrl;
          capturedPayload = body;
        }
      } catch {
        // Ignore malformed JSON or blocked responses.
      }
    });

    await page.goto(url, { waitUntil: 'domcontentloaded', timeout });
    finalUrl = page.url();
    await page.waitForTimeout(5000);

    if (!capturedPayload) {
      try {
        await page.waitForLoadState('networkidle', { timeout: 5000 });
      } catch {
        // Ignore network idle timeout.
      }
      await page.waitForTimeout(2500);
    }

    const rawTitle = await page.title().catch(() => '');
    const html = await page.content().catch(() => '');

    const aweme = extractAweme(capturedPayload);
    const result = {
      final_url: finalUrl,
      captured_api_url: capturedApiUrl,
      title: aweme?.desc || rawTitle?.replace(/ - 抖音$/, '').trim() || null,
      desc: aweme?.desc || null,
      author: aweme?.author?.nickname || null,
      author_uid: aweme?.author?.uid || aweme?.author_user_id || null,
      aweme_id: aweme?.aweme_id || aweme?.awemeId || null,
      create_time: aweme?.create_time || aweme?.createTime || null,
      statistics: aweme?.statistics || null,
      play_url: pickPlayUrl(aweme?.video),
      cover_url: firstUrl(aweme?.video?.cover?.url_list) || firstUrl(aweme?.video?.cover?.urlList),
      music_url: firstUrl(aweme?.music?.play_url?.url_list) || firstUrl(aweme?.music?.playUrl?.urlList),
      html_title: rawTitle || null,
      html_length: html.length,
    };

    process.stdout.write(JSON.stringify(result));
  } finally {
    if (browser) {
      await browser.close().catch(() => {});
    }
  }
}

main().catch((error) => {
  process.stderr.write(String(error?.stack || error));
  process.exit(1);
});
