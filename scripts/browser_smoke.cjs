const {chromium}=require('playwright');
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH || '/usr/bin/chromium',headless:true,args:['--no-sandbox','--enable-unsafe-swiftshader']});
 const page=await browser.newPage({viewport:{width:390,height:844},deviceScaleFactor:1});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('https://telegram.org/**',r=>r.abort());
 await page.route('https://cdn.jsdelivr.net/**',r=>r.abort());
 await page.goto((process.env.BASE_URL || 'http://127.0.0.1:8000')+'/app');await page.waitForFunction(()=>document.getElementById('eggBalance').textContent==='120');
 await page.screenshot({path:(process.env.SCREENSHOT_DIR || '/tmp')+'/cocochi-home.png',fullPage:true});
 await page.locator('[data-route="rewards"]').first().click();
 await page.locator('#dailyRewardBtn').click();await page.waitForFunction(()=>document.getElementById('eggBalance').textContent==='150');
 await page.reload();await page.waitForFunction(()=>document.getElementById('eggBalance').textContent==='150');
 await page.locator('[data-route="market"]').last().click();await page.locator('[data-action="sell"]').click();await page.locator('#modalActions button').click();await page.waitForFunction(()=>document.getElementById('eggBalance').textContent==='140');
 await page.screenshot({path:(process.env.SCREENSHOT_DIR || '/tmp')+'/cocochi-market.png',fullPage:true});
 console.log(JSON.stringify({errors,canvas:await page.locator('#chickenScene canvas').count(),overflow:await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),balance:await page.locator('#eggBalance').textContent()}));
 await page.context().storageState({path:'/tmp/cocochi-qa-session.json'});
 const canvas=await page.locator('#chickenScene canvas').count();const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
 await browser.close();if(errors.length || canvas!==1 || overflow)process.exit(1);
})();
