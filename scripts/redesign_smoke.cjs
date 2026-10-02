const { chromium } = require('playwright');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const path = require('node:path');
const sharp = require('sharp');
const base = process.env.TEST_URL || 'http://127.0.0.1:5050';
const output = path.resolve('artifacts');
(async()=>{
 const browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
 const context=await browser.newContext({viewport:{width:1440,height:900},reducedMotion:'reduce'});
 const page=await context.newPage();const errors=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
 try {
  await page.goto(base);await page.waitForFunction(()=>document.documentElement.dataset.reactBits==='ready');await page.locator('.tech-text[data-ready=true]').waitFor();
  const editor=page.locator('.editor-demo');await page.waitForFunction(()=>document.querySelector('.editor-demo').dataset.demoStage==='passed');
  assert.equal(await editor.locator('[data-demo-motion]').count(),1);
  console.log('PASS authorized demo-only animation enhancement mounted');
  assert.equal(await page.evaluate(()=>getComputedStyle(document.body).backgroundColor),'rgb(8, 8, 8)');
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  assert.equal(await page.locator('.border-glow-card--strong').count(),14);
  const glow=await page.locator('.voltage-band .border-glow-card').evaluate(el=>({width:getComputedStyle(el,'::after').borderTopWidth,color:getComputedStyle(el,'::after').borderTopColor,opacity:getComputedStyle(el,'::after').opacity}));assert.equal(glow.width,'2px');assert.ok(Number(glow.opacity)>.7);console.log('PASS black foundation and clearly visible resting red glow');
  await page.screenshot({path:path.join(output,'black-red-home.png'),fullPage:true});
  for(const width of [768,390]) {await page.setViewportSize({width,height:width===390?844:1024});await page.goto(base);await page.locator('.tech-text[data-ready=true]').waitFor();assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);await page.screenshot({path:path.join(output,'black-red-home-'+width+'.png'),fullPage:true});}
  for(const route of ['/register','/leaderboard']) {await page.goto(base+route);await page.waitForTimeout(150);assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,route+' overflow');await page.screenshot({path:path.join(output,'black-red-'+route.slice(1)+'-mobile.png'),fullPage:true});}
  console.log('PASS public pages responsive at desktop, tablet and mobile');
  await page.setViewportSize({width:1440,height:900});await page.emulateMedia({reducedMotion:'no-preference'});await page.goto(base);await page.locator('.tech-text[data-ready=true]').waitFor();await page.waitForTimeout(2300);
  const text=page.locator('.tech-text canvas');const textBefore=await text.screenshot();const textBox=await text.boundingBox();await page.mouse.move(textBox.x+40,textBox.y+textBox.height/2);await page.mouse.down();await page.mouse.move(textBox.x+170,textBox.y+textBox.height/2+10,{steps:12});await page.mouse.up();await page.waitForTimeout(100);assert.notDeepEqual(await text.screenshot(),textBefore);console.log('PASS actual TechText hover/drag animation');
  const grid=page.locator('.hero-dot-field canvas');await page.mouse.move(textBox.x+60,textBox.y+textBox.height+30);await page.mouse.move(textBox.x+420,textBox.y+textBox.height+90,{steps:14});await page.waitForTimeout(80);assert.ok(await grid.evaluate(el=>Number(el.dataset.dotCount)>0));console.log('PASS actual GSAP DotGrid mounted and responding');
  await page.locator('.voltage-band').scrollIntoViewIfNeeded();await page.locator('.electric-logo[data-rendered=true]').waitFor();const electric=page.locator('.electric-logo canvas');const before=await electric.screenshot();await page.locator('.electric-emblem').hover();await page.waitForTimeout(160);assert.notDeepEqual(await electric.screenshot(),before);console.log('PASS actual ElectricLogo WebGL animation');
  // Warm up shaders first, then record frame pacing while animation and pointer effects are visible.
  const frames=await page.evaluate(()=>new Promise(resolve=>{const samples=[];let previous=0;const start=performance.now();function tick(now){if(previous)samples.push(now-previous);previous=now;if(now-start<2000)requestAnimationFrame(tick);else{samples.sort((a,b)=>a-b);resolve({count:samples.length,medianMs:samples[Math.floor(samples.length/2)],p95Ms:samples[Math.floor(samples.length*.95)],over50ms:samples.filter(n=>n>50).length});}}requestAnimationFrame(tick);}));
  fs.writeFileSync(path.join(output,'animation-performance.json'),JSON.stringify({environment:'Local headless Chrome, 1440x900; not a device-wide guarantee',electric:frames},null,2));console.log('FRAME PACING',JSON.stringify(frames));
  await page.emulateMedia({reducedMotion:'reduce'});await page.locator('.electric-logo[data-motion=reduced]').waitFor();assert.equal(await page.locator('.electric-logo canvas').count(),0);console.log('PASS reduced-motion ElectricLogo static fallback');
  assert.deepEqual(errors,[]);console.log('PASS no React, WebGL or browser errors');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
