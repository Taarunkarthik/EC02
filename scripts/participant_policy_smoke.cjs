const {chromium}=require('playwright');
const assert=require('node:assert/strict');
if (process.env.EXITCODE_E2E !== '1') throw new Error('Set EXITCODE_E2E=1 only against an isolated test database; this check resets the event.');
const base=process.env.TEST_URL || 'http://127.0.0.1:5057';
(async()=>{
 const browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
 const ctx=await browser.newContext({viewport:{width:1440,height:1000}});
 const adminCtx=await browser.newContext();const admin=await adminCtx.newPage(); const page=await ctx.newPage();
 const errors=[];page.on('pageerror',e=>errors.push(e.message));admin.on('pageerror',e=>errors.push(e.message));
 async function enter(){await page.locator('#participant-enter').click();await page.waitForFunction(()=>window.ParticipantGuard?.active===true);}
 async function post(url,data){const r=await admin.request.post(base+url,{data});assert.equal(r.status(),200,await r.text());return r.json();}
 try{
 await admin.request.post(base+'/admin/login',{form:{username:'admin',password:'exitcode0_admin_2026'}});
 await post('/api/admin/reset-event',{confirmation:'RESET EVENT'});
 await page.goto(base+'/register');
 await page.locator('#register-tab').click();await page.locator('#reg-name').fill('Participant Flow QA');await page.locator('#reg-member1').fill('Ada');await page.locator('#reg-member2').fill('Lin');await page.locator('#team-register-form button[type=submit]').click();
 await page.waitForURL(/waiting/);await enter();console.log('PASS login requires fullscreen in waiting room');
 await post('/api/admin/event-action',{action:'start'});await page.waitForURL(/arena/);await enter();
 let progress=await (await page.request.get(base+'/api/team-progress')).json();assert.equal(progress.questions[0].is_answered,false);
 await page.locator('#error_location').fill('3');await page.locator('#error_type').selectOption('Logical Error');await page.locator('#expected_output').fill('10');await page.locator('#cause').fill('The loop stops before the last element because the range excludes the upper bound.');await page.locator('#correction').fill('Use range(len(numbers)) to include every number.');
 await page.locator('[data-powerup=rubber-duck]').click();await page.locator('#confirm-accept').click();await page.waitForFunction(()=>!document.getElementById('rubber-duck-hint-box').hidden);
 await page.locator('#commit-fix-btn').click();await page.locator('#confirm-accept').click();await page.waitForFunction(()=>document.getElementById('commit-fix-btn').disabled && !document.getElementById('answer-status').hidden);
 progress=await (await page.request.get(base+'/api/team-progress')).json();assert.equal(progress.questions[0].is_answered,true);assert.equal(progress.questions[0].hint_used,1);assert.ok(progress.questions[0].awarded_score<=18);assert.equal(progress.questions[0].field_results.length,5);assert.equal(await page.locator('#answer-status .answer-breakdown li').count(),5);assert.equal(await page.locator('.field-result').count(),5);
 await page.reload();await enter();await page.waitForFunction(()=>document.getElementById('cause').disabled && document.getElementById('cause').value.length>0);assert.match(await page.locator('#answer-status').innerText(),/final/i);console.log('PASS final debugging answer, hint penalty, persisted status/response');
 await page.evaluate(()=>document.exitFullscreen());await page.waitForFunction(()=>document.getElementById('participant-violations').textContent.startsWith('1 /'));assert.equal(await page.locator('#participant-gate').isVisible(),true);
 const denied=await page.request.post(base+'/api/submit-bug-fix',{data:{question_id:'Q02'}});assert.equal(denied.status(),403);await enter();console.log('PASS first exit warns and gates submission until fullscreen restored');
 await post('/api/admin/event-action',{action:'end'});await page.goto(base+'/result');await enter();await page.locator('.debugging-review-question summary').first().click();assert.equal(await page.locator('.debugging-field').count(),5);await page.screenshot({path:'/tmp/exitcode-field-results.png',fullPage:true});console.log('PASS individual results available after round ends');await post('/api/admin/quiz-action',{action:'open'});
 await page.goto(base+'/quiz');await enter();await page.locator('#quiz-start').click();await page.waitForFunction(()=>!document.getElementById('quiz-play').hidden);
 for(let i=0;i<10;i++) {await page.locator('#quiz-options input').nth(i===0?1:0).check();await page.locator('#quiz-lock').click();if(i<9) await page.waitForFunction(n=>document.getElementById('quiz-progress-label').textContent.startsWith('QUESTION '+String(n).padStart(2,'0')),i+2);}
 await page.locator('#quiz-finish').waitFor({state:'visible'});assert.equal(await page.locator('.quiz-review-item').count(),10);
 for(const id of ['clarity','difficulty','interface','pacing','enjoyment','overall']) await page.locator(`input[name=${id}][value="4"]`).check();
 await page.locator('#quiz-feedback-note').fill('Clear questions and helpful results.');await page.locator('#quiz-feedback-submit').click();await page.waitForFunction(()=>document.getElementById('quiz-feedback-status').textContent.includes('Feedback received'));
 await page.reload();await enter();await page.waitForFunction(()=>document.getElementById('quiz-feedback-submit').disabled);assert.equal(await page.locator('#quiz-feedback-note').inputValue(),'Clear questions and helpful results.');await page.screenshot({path:'/tmp/exitcode-quiz-feedback.png',fullPage:true});console.log('PASS quiz review and six ratings/note survive refresh');
 await admin.goto(base+'/admin/dashboard#feedback');await admin.waitForFunction(()=>document.getElementById('admin-feedback-body').textContent.includes('Clear questions'));console.log('PASS organizer can read feedback');
 await page.evaluate(()=>document.exitFullscreen());await page.waitForFunction(()=>document.getElementById('participant-gate-title').textContent==='Account blocked');
 assert.equal((await page.request.get(base+'/api/team-progress')).status(),403);await page.goto(base+'/result');assert.ok(page.url().endsWith('/blocked'));await page.goto(base+'/logout');
 const relogin=await page.request.post(base+'/register',{form:{action:'login',team_lookup:'Participant Flow QA'}});assert.equal(relogin.status(),403);console.log('PASS second exit during quiz blocks across rounds and logout/login');
 assert.deepEqual(errors,[]);console.log('PASS no browser errors');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
