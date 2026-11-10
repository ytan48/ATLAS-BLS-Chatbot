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
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }, [messages, loading]);

  const sendMessage = async () => {
    const trimmed = query.trim();
    if (!trimmed || loading) return;

    const userMsg: Message = { role: 'user', content: trimmed };
    setMessages((prev: Message[]) => [...prev, userMsg]);
    setQuery('');
    setLoading(true);

    try {
      const response = await fetch(chatApiUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: trimmed })
      });
      const data = await response.json();

      const assistantText = data?.answer || 'I could not process that request. Please try again.';
      setMessages((prev: Message[]) => [...prev, { role: 'assistant', content: assistantText }]);
    } catch {
      setMessages((prev: Message[]) => [
        ...prev,
        {
          role: 'assistant',
          content: 'I could not reach the advisor service. For specific questions, contact the BLS office at bls@illinois.edu.'
        }
      ]);
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
      <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-widget">
        <header className="border-b-4 border-ilOrange bg-gradient-to-r from-ilBlueLight to-ilBlue px-4 py-3 text-white">
          <h1 className="text-sm font-semibold tracking-wide">BLS Virtual Advisor</h1>
          <p className="mt-1 text-xs text-slate-100">University of Illinois Online</p>
        </header>

        <div className="max-h-[420px] space-y-2 overflow-y-auto bg-ilStormLight p-3">
          {messages.map((msg: Message, idx: number) => (
            <article
              key={`${msg.role}-${idx}`}
              className={`rounded-xl p-3 text-sm leading-relaxed ${
                msg.role === 'assistant'
                  ? 'border border-slate-200 bg-white text-slate-800'
                  : 'ml-8 bg-ilOrange font-medium text-ilBlue shadow-[0_3px_12px_rgba(255,95,5,0.24)]'
              }`}
            >
              <p>{msg.content}</p>
              {msg.role === 'assistant' && (
                <button
                  type="button"
                  onClick={() => copyMessage(msg.content, idx)}
                  className="mt-2 inline-flex rounded-md border border-slate-300 px-2 py-1 text-xs text-slate-600 transition hover:border-ilOrange hover:bg-orange-50 hover:text-ilBlue"
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
            value={query}
            onChange={(e: ChangeEvent<HTMLTextAreaElement>) => setQuery(e.target.value)}
            placeholder="Ask about transfer credits, ACE 240, tuition, or advising..."
            className="w-full resize-none rounded-lg border border-slate-300 p-2 text-sm outline-none transition focus:border-ilBlue focus:ring-2 focus:ring-ilOrange/20"
          />
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
              disabled={loading || !query.trim()}
              className="rounded-lg bg-ilBlue px-3 py-2 text-xs font-semibold text-white transition hover:bg-[#0E0F20] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ilOrange disabled:cursor-not-allowed disabled:opacity-50"
            >
              Send
            </button>
          </div>
        </footer>
      </section>
    </main>
  );
}
