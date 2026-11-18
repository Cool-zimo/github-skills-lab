let chromium;
try {
    ({chromium} = require('playwright'));
} catch (e) {
    ({chromium} = require('/usr/local/lib/node_modules/playwright'));
}
const CHROME = process.env.CHROME_PATH || '/usr/local/bin/chromium';

(async () => {
    const browser = await chromium.launch({
        headless: true,
        executablePath: CHROME,
        args: ['--no-sandbox', '--disable-dev-shm-usage', '--use-gl=angle',
            '--use-angle=swiftshader', '--enable-webgl', '--enable-unsafe-swiftshader']
    });
    const page = await browser.newPage({viewport: {width: 560, height: 560}});
    const lines = [];
    page.on('console', m => lines.push('[' + m.type() + '] ' + m.text()));
    page.on('pageerror', e => lines.push('[pageerror] ' + e.message));
    page.on('requestfailed', r => lines.push('[reqfail] ' + r.url() + ' ' + (r.failure() && r.failure().errorText)));

    await page.goto('http://127.0.0.1:8123/', {waitUntil: 'load', timeout: 60000});
    await page.waitForTimeout(12000);

    const info = await page.evaluate(() => ({
        globals: {
            VirtualMachine: typeof window.VirtualMachine,
            ScratchStorage: typeof window.ScratchStorage,
            ScratchRender: typeof window.ScratchRender,
            ScratchSVGRenderer: typeof window.ScratchSVGRenderer,
            vm: typeof window.vm,
            load: typeof window.__load,
            state: typeof window.__state
        },
        state: window.__state ? window.__state() : null,
        errors: window.__errors || [],
        statusText: document.getElementById('status') && document.getElementById('status').textContent
    }));

    console.log('INFO=' + JSON.stringify(info, null, 2));
    console.log('LINES:\n' + lines.join('\n'));
    await browser.close();
})().catch(e => {
    console.error('DIAG FAILED:', e);
    process.exit(1);
});
