// Run: node tests/test_safe_markdown.cjs <path-to-jsdom-module>
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require(path.resolve(process.argv[2]));
const dom = new JSDOM('', { runScripts: 'outside-only' });
const window = dom.window;
for (const name of ['marked.js', 'purify.min.js', 'safe-markdown.js']) {
  window.eval(fs.readFileSync(path.join(__dirname, '../frontend/vendor', name), 'utf8'));
}
const attacks = [
  '<img src=x onerror="alert(1)">',
  '<svg onload="alert(1)"></svg>',
  '<script>alert(1)</script>',
  '[click](javascript:alert%281%29)',
  '<a href="data:text/html,attack" onclick="alert(1)">click</a>',
  '<iframe src="https://attacker.example"></iframe>',
  '<style>body{display:none}</style>',
  '<form id="chat-input"><input name="query"></form>'
];
for (const attack of attacks) {
  // Both clients render partial answers while animating.
  for (let length = 1; length <= attack.length; length++) {
    const container = window.document.createElement('div');
    container.innerHTML = window.safeMarkdown(attack.slice(0, length));
    assert.equal(container.querySelector('img,svg,script,iframe,style,form,input'), null);
    for (const element of container.querySelectorAll('*')) {
      for (const attr of element.attributes) {
        assert.ok(['href', 'title'].includes(attr.name), attr.name);
        if (attr.name === 'href') assert.ok(!/^\s*(javascript|data):/i.test(attr.value));
      }
    }
  }
}
const formatted = window.safeMarkdown('**Tuition** [Admissions](https://illinois.edu)');
assert.ok(formatted.includes('<strong>Tuition</strong>'));
assert.ok(formatted.includes('href="https://illinois.edu"'));
window.DOMPurify = undefined;
assert.ok(!window.safeMarkdown('<img src=x onerror=alert(1)>').includes('<img'));
console.log('Markdown attack, partial rendering, formatting, and fallback checks passed.');
dom.window.close();
