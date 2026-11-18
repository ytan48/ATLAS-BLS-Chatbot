/* Shared client-side input validation. Never display untrusted server text. */
window.BLSInput = {
  count: text => Array.from(text).length,
  message(status, code, limit) {
    if (status === 413 || code === 'question_too_long') return `Your message exceeds the allowed size or ${limit.toLocaleString()}-character limit. Please shorten it or submit it in smaller sections.`;
    if (status === 429) return 'Too many requests. Please wait before trying again.';
    if (status === 400) return 'The request was invalid. Please check your message and try again.';
    return 'The advisor service is temporarily unavailable. Please try again.';
  }
};
