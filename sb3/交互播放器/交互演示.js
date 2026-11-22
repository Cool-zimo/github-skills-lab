/* 交互演示：用真实点击（而非直接调内部 API）驱动播放器，并演示上传自己的 sb3。
 * 前置：python3 -m http.server 8123 --directory <player目录>
 * 运行：node 交互演示.js
 */
const path = require('path');
let chromium;
try {
    ({chromium} = require('playwright'));
} catch (e) {
    ({chromium} = require('/usr/local/lib/node_modules/playwright'));
}
const CHROME = process.env.CHROME_PATH || '/usr/local/bin/chromium';

const fs = require('fs');
const OUT = path.resolve(__dirname, 'shots');
fs.mkdirSync(OUT, {recursive: true});
const URL = process.env.PLAYER_URL || 'http://127.0.0.1:8123/';
const SB3 = process.env.SB3 || path.resolve(__dirname, '最小示例.sb3');

(async () => {
    const browser = await chromium.launch({
        headless: true,
        executablePath: CHROME,
        args: ['--no-sandbox', '--disable-dev-shm-usage']
    });
    const page = await browser.newPage({viewport: {width: 560, height: 600}, deviceScaleFactor: 2});
    const lines = [];
    page.on('pageerror', e => lines.push('[pageerror] ' + e.message));
    page.on('console', m => { if (m.type() === 'error') lines.push('[error] ' + m.text()); });

    await page.goto(URL, {waitUntil: 'load', timeout: 60000});
    await page.waitForFunction(() => window.__state && window.__state().ready, null, {timeout: 60000});
    await page.waitForTimeout(400);

    const states = {};

    // ① 上传一份 sb3（走 file input 的 change 事件）
    await page.locator('#file').setInputFiles(SB3);
    await page.waitForFunction(() => window.__state().ready, null, {timeout: 60000});
    await page.waitForTimeout(400);
    states.uploaded = await page.evaluate(() => window.__state());
    await page.locator('.card').screenshot({path: path.join(OUT, '05_上传后初始.png')});

    // ② 真实点击「绿旗」按钮
    await page.locator('#flag').click();
    await page.waitForTimeout(800);
    states.greenFlag = await page.evaluate(() => window.__state());
    await page.locator('.card').screenshot({path: path.join(OUT, '06_按钮绿旗.png')});

    // ③ 真实点击「点击角色」按钮
    await page.locator('#click').click();
    await page.waitForTimeout(600);
    states.clickSprite = await page.evaluate(() => window.__state());
    await page.locator('.card').screenshot({path: path.join(OUT, '07_按钮点击角色.png')});

    // ④ 重载后状态应复位
    await page.locator('#reload').click();
    await page.waitForTimeout(500);
    states.reloaded = await page.evaluate(() => window.__state());

    console.log('STATES=' + JSON.stringify(states, null, 2));
    console.log('PAGE_ERRORS=' + JSON.stringify(lines));
    await browser.close();
})().catch(e => {
    console.error('INTERACT FAILED:', e);
    process.exit(1);
});
