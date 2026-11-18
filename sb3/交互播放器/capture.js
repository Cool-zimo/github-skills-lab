/* 分三帧截取舞台：初始 / 绿旗运行 / 点击角色；并记录 VM 运行时状态。 */
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

(async () => {
    const browser = await chromium.launch({
        headless: true,
        executablePath: CHROME,
        args: [
            '--no-sandbox', '--disable-dev-shm-usage',
            '--use-gl=angle', '--use-angle=swiftshader',
            '--enable-webgl', '--enable-unsafe-swiftshader'
        ]
    });
    const page = await browser.newPage({viewport: {width: 560, height: 560}, deviceScaleFactor: 2});
    const lines = [];
    page.on('console', m => lines.push('[' + m.type() + '] ' + m.text()));
    page.on('pageerror', e => lines.push('[pageerror] ' + e.message));

    await page.goto(URL, {waitUntil: 'load', timeout: 90000});
    await page.waitForFunction(() => window.__state && window.__state().ready, null, {timeout: 90000});
    await page.waitForTimeout(700);

    const states = {};
    const card = page.locator('.card');
    states.initial = await page.evaluate(() => window.__state());
    await card.screenshot({path: path.join(OUT, '01_初始舞台.png')});

    await page.evaluate(() => window.__greenFlag());
    await page.waitForTimeout(800);
    states.afterGreenFlag = await page.evaluate(() => window.__state());
    await card.screenshot({path: path.join(OUT, '02_绿旗运行.png')});

    await page.evaluate(() => window.__click(250, 180));
    await page.waitForTimeout(600);
    states.afterClick = await page.evaluate(() => window.__state());
    await card.screenshot({path: path.join(OUT, '03_点击角色.png')});

    await page.locator('#stage').screenshot({path: path.join(OUT, '04_纯舞台.png')});

    console.log('STATES=' + JSON.stringify(states, null, 2));
    console.log('CONSOLE:\n' + lines.join('\n'));
    await browser.close();
})().catch(e => {
    console.error('CAPTURE FAILED:', e);
    process.exit(1);
});
