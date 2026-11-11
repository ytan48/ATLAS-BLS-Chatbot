/* All model and error text must pass through this renderer before innerHTML. */
function safeMarkdown(value) {
  const text = String(value ?? '');
  if (!window.marked || !window.DOMPurify) {
    const container = document.createElement('div');
    container.textContent = text;
    return container.innerHTML;
  }
  return DOMPurify.sanitize(marked.parse(text), {
    ALLOWED_TAGS: ['p', 'br', 'strong', 'em', 'ul', 'ol', 'li', 'a',
      'blockquote', 'code', 'pre', 'h1', 'h2', 'h3', 'h4', 'hr',
      'table', 'thead', 'tbody', 'tr', 'th', 'td', 'del'],
    ALLOWED_ATTR: ['href', 'title'],
    ALLOW_DATA_ATTR: false,
    ALLOW_ARIA_ATTR: false
  });
}
