'use client';

import { useState, useRef, useEffect } from 'react';

interface InvestigateChatProps {
  slug: string;
  entityName: string;
}

interface Message {
  role: 'user' | 'assistant';
  content: string;
}

export default function InvestigateChat({ slug, entityName }: InvestigateChatProps) {
  const [expanded, setExpanded] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (expanded && inputRef.current) {
      inputRef.current.focus();
    }
  }, [expanded]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = async () => {
    const trimmed = input.trim();
    if (!trimmed || loading) return;

    const userMsg: Message = { role: 'user', content: trimmed };
    const updatedMessages = [...messages, userMsg];
    setMessages(updatedMessages);
    setInput('');
    setLoading(true);

    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          slug,
          message: trimmed,
          history: messages,
        }),
      });
      const data = await res.json();
      if (res.ok) {
        setMessages([...updatedMessages, { role: 'assistant', content: data.reply }]);
      } else {
        setMessages([
          ...updatedMessages,
          { role: 'assistant', content: data.detail || 'Something went wrong. Try again.' },
        ]);
      }
    } catch {
      setMessages([
        ...updatedMessages,
        { role: 'assistant', content: 'Network error. Please try again.' },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // --- Collapsed bar ---
  if (!expanded) {
    return (
      <div
        className="fixed bottom-0 left-0 right-0 z-50 cursor-pointer"
        onClick={() => setExpanded(true)}
      >
        <div className="max-w-[900px] mx-auto">
          <div className="flex items-center gap-3 bg-zinc-900/95 backdrop-blur border-t border-zinc-800 px-5 py-3 hover:bg-zinc-800/95 transition-colors">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-amber-400 flex-shrink-0">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
            </svg>
            <span className="text-sm text-zinc-400">
              Ask about <span className="text-amber-400 font-medium">{entityName}</span>...
            </span>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-zinc-600 ml-auto">
              <polyline points="18 15 12 9 6 15" />
            </svg>
          </div>
        </div>
      </div>
    );
  }

  // --- Expanded chat ---
  return (
    <div className="fixed bottom-0 left-0 right-0 z-50">
      <div className="max-w-[900px] mx-auto">
        <div className="bg-zinc-950/98 backdrop-blur-lg border-t border-x border-zinc-800 rounded-t-xl shadow-2xl flex flex-col" style={{ height: '420px' }}>

          {/* Header */}
          <div
            className="flex items-center justify-between px-5 py-3 border-b border-zinc-800 cursor-pointer hover:bg-zinc-900/50 transition-colors"
            onClick={() => setExpanded(false)}
          >
            <div className="flex items-center gap-2">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-amber-400">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
              </svg>
              <span className="text-sm font-semibold text-zinc-200">Investigate {entityName}</span>
            </div>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-zinc-500">
              <polyline points="6 9 12 15 18 9" />
            </svg>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
            {messages.length === 0 && (
              <div className="text-center py-8">
                <p className="text-zinc-500 text-sm mb-3">Ask a probing question about this entity.</p>
                <div className="flex flex-wrap justify-center gap-2">
                  {[
                    'Who are the biggest donors?',
                    'Any suspicious patterns?',
                    'Show me the money trail',
                  ].map((q) => (
                    <button
                      key={q}
                      onClick={() => { setInput(q); }}
                      className="text-xs bg-zinc-800 hover:bg-zinc-700 text-zinc-300 px-3 py-1.5 rounded-full border border-zinc-700 hover:border-amber-500/40 transition-colors"
                    >
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {messages.map((msg, i) => (
              <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div
                  className={`max-w-[80%] rounded-xl px-4 py-2.5 text-sm leading-relaxed ${
                    msg.role === 'user'
                      ? 'bg-blue-600/90 text-white rounded-br-sm'
                      : 'bg-zinc-800 text-zinc-200 border-l-2 border-amber-500/60 rounded-bl-sm'
                  }`}
                >
                  <div className="whitespace-pre-wrap">{msg.content}</div>
                </div>
              </div>
            ))}

            {loading && (
              <div className="flex justify-start">
                <div className="bg-zinc-800 border-l-2 border-amber-500/60 rounded-xl rounded-bl-sm px-4 py-3">
                  <div className="flex gap-1.5">
                    <span className="w-2 h-2 bg-amber-400/60 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                    <span className="w-2 h-2 bg-amber-400/60 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                    <span className="w-2 h-2 bg-amber-400/60 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                  </div>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* Input */}
          <div className="px-4 py-3 border-t border-zinc-800">
            <div className="flex items-center gap-2">
              <input
                ref={inputRef}
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={`Ask about ${entityName}...`}
                disabled={loading}
                className="flex-1 bg-zinc-800 border border-zinc-700 rounded-lg px-4 py-2.5 text-sm text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-amber-500/50 disabled:opacity-50"
              />
              <button
                onClick={handleSend}
                disabled={loading || !input.trim()}
                className="bg-amber-500 hover:bg-amber-400 disabled:bg-zinc-700 disabled:text-zinc-500 text-black font-semibold px-4 py-2.5 rounded-lg text-sm transition-colors"
              >
                Send
              </button>
            </div>
            <div className="text-[10px] text-zinc-600 mt-1.5 text-center">Powered by Claude</div>
          </div>
        </div>
      </div>
    </div>
  );
}
