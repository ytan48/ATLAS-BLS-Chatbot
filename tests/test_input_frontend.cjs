const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { TextDecoder, TextEncoder } = require('node:util');
const { JSDOM } = require(path.resolve(process.argv[2]));
const root = path.resolve(__dirname, '..');
async function run(file) {
  const html = fs.readFileSync(path.join(root, 'frontend', file), 'utf8');
  const dom = new JSDOM(html, { runScripts: 'outside-only', url: 'http://localhost/', pretendToBeVisual: true });
  const w = dom.window;
  w.TextDecoder = TextDecoder;
  w.HTMLElement.prototype.scrollTo = () => {};
  w.requestAnimationFrame = cb => { cb(); return 1; };
  w.safeMarkdown = text => text;
  let attempts = 0;
  let submittedQuery;
  let resolveRequest;
  w.fetch = async (url, options) => {
    if (url === '/api/input-config') return {ok:true, json:async()=>({max_question_chars: 40, use_last_response:false, max_previous_response_chars:16000})};
    attempts++;
    submittedQuery = JSON.parse(options.body).query;
    return new Promise(resolve => { resolveRequest = resolve; });
  };
  function completeReply() {
    let sent = false;
    resolveRequest({ok:true, body:{getReader:()=>({read:async()=> sent ? {done:true} : (sent = true, {done:false, value:new TextEncoder().encode('data: {"type":"answer","content":"OK"}\n\ndata: {"type":"done"}\n\n')})})}});
  }
  w.eval(fs.readFileSync(path.join(root, 'frontend/vendor/input-validation.js'), 'utf8'));
  const scripts = [...w.document.querySelectorAll('script:not([src])')];
  scripts.forEach(script => w.eval(script.textContent));
  await new Promise(resolve => setTimeout(resolve, 20));
  const input = w.document.getElementById('user-input');
  const counter = w.document.getElementById('input-counter');
  const error = w.document.getElementById('input-error');
  const send = w.document.getElementById('send-btn');
  const chip = w.document.querySelector('.q-chip');
  const question = chip.textContent;
  const enter = (options = {}) => input.dispatchEvent(new w.KeyboardEvent('keydown', { key: 'Enter', cancelable: true, ...options }));
  const userMessages = () => [...w.document.querySelectorAll('.user-msg')].map(msg => msg.textContent);
  function assertPending(text, expectedAttempts, previous = []) {
    assert.equal(attempts, expectedAttempts);
    assert.equal(submittedQuery, text);
    assert.equal(input.value, '');
    assert.equal(input.style.height, 'auto');
    assert.equal(send.disabled, true);
    assert.match(counter.textContent, /^0 \/ 40/);
    assert.deepEqual(userMessages(), [...previous, text]);
    assert.equal(w.document.querySelector('.typing-bubble').parentElement.previousElementSibling.querySelector('.user-msg').textContent, text);
  }

  input.value = '🙂'.repeat(41); input.dispatchEvent(new w.Event('input'));
  assert.match(counter.textContent, /41 \/ 40.*over the limit/);
  assert.equal(send.disabled, true);
  enter();
  assert.equal(attempts, 0);
  input.value = '🙂'.repeat(39) + ' a'; input.dispatchEvent(new w.Event('input'));
  assert.match(counter.textContent, /41 \/ 40/);
  input.value = '🙂'.repeat(39) + 'a'; input.dispatchEvent(new w.Event('input'));
  assert.match(counter.textContent, /40 \/ 40.*approaching/);
  assert.equal(enter({ shiftKey: true }), true);
  assert.equal(enter({ isComposing: true }), true);
  assert.equal(attempts, 0);

  chip.click();
  assertPending(question, 1);
  chip.click();
  enter();
  assertPending(question, 1);
  resolveRequest({ok:false, status:429, json:async()=>({error:'private details'})});
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(input.value, question);
  assert.match(error.textContent, /Too many requests/);
  assert.doesNotMatch(error.textContent, /private/);
  assert.deepEqual(userMessages(), []);
  assert.equal(w.document.querySelector('.typing-bubble'), null);

  enter();
  assertPending(question, 2);
  completeReply();
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(userMessages(), [question]);
  assert.equal(w.document.querySelector('.typing-bubble'), null);
  assert.equal([...w.document.querySelectorAll('.bot-msg')].at(-1).textContent, 'OK');

  input.value = '🙂abc'; input.dispatchEvent(new w.Event('input'));
  send.click();
  assertPending('🙂abc', 3, [question]);
  completeReply();
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(userMessages(), [question, '🙂abc']);
  assert.equal(input.value, '');
  assert.match(w.BLSInput.message(413, '', 4), /shorten/);
  assert.match(w.BLSInput.message(400, '', 4), /invalid/);
  dom.window.close();
}
(async () => { for (const file of ['index.html','widget.html']) await run(file); console.log('HTML validation, optimistic submission, draft restoration and retry checks passed.'); })().catch(err => {console.error(err); process.exitCode=1;});

