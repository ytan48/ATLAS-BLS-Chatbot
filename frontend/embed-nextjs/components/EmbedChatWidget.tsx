'use client';

import { useEffect, useRef, useState } from 'react';
import type { ChangeEvent } from 'react';

declare global {
  interface Window {
    __BLS_CHAT_API_URL__?: string;
  }
}

type Message = {
  role: 'user' | 'assistant';
  content: string;
};

export default function EmbedChatWidget() {
  const chatApiUrl =
    (typeof window !== 'undefined' && window.__BLS_CHAT_API_URL__) ||
    'http://localhost:5000/api/chat';
  const [query, setQuery] = useState('');
  const [messages, setMessages] = useState<Message[]>([
    {
      role: 'assistant',
      content: 'Hi, I am your BLS Virtual Advisor. Ask about admissions, courses, tuition, or scheduling.'
    }
  ]);
  const [loading, setLoading] = useState(false);
  const [limit, setLimit] = useState<number | null>(null);
  const [error, setError] = useState('');
  const count = Array.from(query).length;
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }, [messages, loading]);

  useEffect(() => {
    const configUrl = chatApiUrl.replace(/\/api\/(chat|ask|stream)\/?(?:\?.*)?$/, '/api/input-config');
    fetch(configUrl).then((r) => { if (!r.ok) throw new Error(); return r.json(); })
      .then((data) => {
        if (!Number.isInteger(data.max_question_chars) || data.max_question_chars < 1) throw new Error();
        setLimit(data.max_question_chars);
      }).catch(() => setError('Could not load the advisor settings. Please reload and try again.'));
  }, [chatApiUrl]);

  const sendMessage = async () => {
    if (!query.trim() || loading || limit === null || count > limit) return;
    const text = query;
    setError('');
    setQuery('');
    setMessages((prev) => [...prev, { role: 'user', content: text }]);
    setLoading(true);
    try {
      const response = await fetch(chatApiUrl, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: text })
      });
      let data: { answer?: string; code?: string } = {};
      try { data = await response.json(); } catch { /* use a generic safe error */ }
      if (!response.ok) {
        if (response.status === 413 || data.code === 'question_too_long') throw new Error(`Your message exceeds the allowed size or ${limit.toLocaleString()}-character limit. Please shorten it or submit it in smaller sections.`);
        if (response.status === 429) throw new Error('Too many requests. Please wait before trying again.');
        if (response.status === 400) throw new Error('The request was invalid. Please check your message and try again.');
        throw new Error('The advisor service is temporarily unavailable. Please try again.');
      }
      const answer = data.answer;
      if (typeof answer !== 'string' || !answer) throw new Error('The advisor returned an empty response. Please try again.');
      setMessages((prev) => [...prev, { role: 'assistant', content: answer }]);
    } catch (err) {
      setMessages((prev) => prev.slice(0, -1));
      setQuery(text);
      setError(err instanceof TypeError ? 'Could not connect to the advisor service. Please check your connection and try again.' : err instanceof Error ? err.message : 'The advisor service is unavailable. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const copyMessage = async (text: string, index: number) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedIndex(index);
      setTimeout(() => setCopiedIndex(null), 1200);
    } catch {
      setCopiedIndex(null);
    }
  };

  return (
    <main className="mx-auto w-full max-w-[400px] p-3">
      <section className="overflow-hidden rounded-2xl border border-slate-200 bg-ilStormLight shadow-widget">
        <header className="bg-ilBlue px-4 py-3 text-white">
          <h1 className="text-sm font-semibold tracking-wide">BLS Virtual Advisor</h1>
          <p className="mt-1 text-xs text-slate-100">University of Illinois Online</p>
        </header>

        <div className="max-h-[420px] space-y-2 overflow-y-auto bg-ilStormLight p-3">
          {messages.map((msg: Message, idx: number) => (
            <article
              key={`${msg.role}-${idx}`}
              className={`rounded-xl p-3 text-sm leading-relaxed ${
                msg.role === 'assistant'
                  ? 'border border-slate-200 bg-white text-ilBlue'
                  : 'ml-8 border border-ilBlue80 bg-ilBlue90 font-medium text-ilBlue'
              }`}
            >
              <p>{msg.content}</p>
              {msg.role === 'assistant' && (
                <button
                  type="button"
                  onClick={() => copyMessage(msg.content, idx)}
                  className="mt-2 inline-flex rounded-md border border-ilBlue30 px-2 py-1 text-xs text-ilBlue transition hover:bg-ilBlue90"
                >
                  {copiedIndex === idx ? 'Copied' : 'Copy to Clipboard'}
                </button>
              )}
            </article>
          ))}
          {loading && (
            <article
              className="flex w-fit items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-sm"
              role="status"
              aria-live="polite"
              aria-label="BLS advisor is typing"
            >
              <span className="typing-dot" aria-hidden="true" />
              <span className="typing-dot" aria-hidden="true" />
              <span className="typing-dot" aria-hidden="true" />
            </article>
          )}
          <div ref={messagesEndRef} aria-hidden="true" />
        </div>

        <footer className="border-t border-slate-200 bg-white p-3">
          <label htmlFor="chat-input" className="sr-only">
            Ask a question
          </label>
          <textarea
            id="chat-input"
            rows={3}
            disabled={loading}
            aria-describedby="input-counter input-error"
            value={query}
            onChange={(e: ChangeEvent<HTMLTextAreaElement>) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault();
                void sendMessage();
              }
            }}
            placeholder="Ask about transfer credits, ACE 240, tuition, or advising..."
            className="w-full resize-none rounded-lg border border-ilBlue30 bg-white p-2 text-sm text-ilBlue outline-none transition placeholder:text-ilStorm30 focus:border-ilBlue30"
          />
          <div id="input-counter" aria-live="polite" className="text-xs text-ilBlue">
            {limit === null ? 'Loading input limit...' : `${count.toLocaleString()} / ${limit.toLocaleString()} characters${count > limit ? ' - over the limit' : count >= limit * 0.9 ? ' - approaching the limit' : ''}`}
          </div>
          <div id="input-error" role="alert" className="text-xs text-red-700">{error}</div>
          <div className="mt-2 flex items-center justify-between gap-2">
            <a
              href="mailto:bls@illinois.edu"
              className="text-xs font-medium text-ilAltgeld underline-offset-2 hover:text-ilBlue hover:underline"
            >
              Contact Advisor
            </a>
            <button
              type="button"
              onClick={sendMessage}
              disabled={loading || !query.trim() || limit === null || count > limit}
              className="rounded-lg bg-ilBlue px-3 py-2 text-xs font-semibold text-white transition hover:bg-ilBlue30 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Send
            </button>
          </div>
        </footer>
      </section>
    </main>
  );
}
