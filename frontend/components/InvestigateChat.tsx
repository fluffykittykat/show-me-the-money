'use client';

import { useState, useRef, useEffect } from 'react';

interface InvestigateChatProps {
  slug: string;
  entityName: string;
  onDataRefresh?: () => void;
}

/** Markdown → HTML for chat messages */
function renderMarkdown(text: string): string {
  // Process line by line for better control
  const lines = text.split('\n');
  const html: string[] = [];
  let inTable = false;
  let inList = false;
  let listType = '';

  for (let i = 0; i < lines.length; i++) {
    let line = lines[i];

    // Skip table separator rows
    if (/^\|[\s-:|]+\|$/.test(line)) continue;

    // Table rows
    if (line.startsWith('|') && line.endsWith('|')) {
      const cells = line.split('|').filter(c => c.trim()).map(c => c.trim());
      if (!inTable) {
        html.push('<table class="w-full my-2 text-xs">');
        inTable = true;
        // First table row = header
        html.push('<tr>' + cells.map(c => `<th class="text-left px-2 py-1.5 border-b border-zinc-700 text-zinc-400 font-semibold">${applyInline(c)}</th>`).join('') + '</tr>');
        continue;
      }
      html.push('<tr class="border-b border-zinc-800/50">' + cells.map(c => `<td class="px-2 py-1.5 text-zinc-300">${applyInline(c)}</td>`).join('') + '</tr>');
      continue;
    } else if (inTable) {
      html.push('</table>');
      inTable = false;
    }

    // Headers
    if (line.startsWith('### ')) {
      closeList();
      html.push(`<h4 class="text-xs font-bold text-zinc-200 mt-3 mb-1 uppercase tracking-wide">${applyInline(line.slice(4))}</h4>`);
      continue;
    }
    if (line.startsWith('## ')) {
      closeList();
      html.push(`<h3 class="text-sm font-bold text-amber-400 mt-3 mb-1">${applyInline(line.slice(3))}</h3>`);
      continue;
    }

    // Blockquotes
    if (line.startsWith('> ')) {
      closeList();
      html.push(`<blockquote class="border-l-2 border-amber-500/50 pl-3 my-2 text-amber-200/80 text-xs italic">${applyInline(line.slice(2))}</blockquote>`);
      continue;
    }

    // Horizontal rule
    if (line.trim() === '---') {
      closeList();
      html.push('<hr class="border-zinc-700 my-2" />');
      continue;
    }

    // Unordered list
    if (/^[-*] /.test(line)) {
      if (!inList || listType !== 'ul') {
        closeList();
        html.push('<ul class="my-1.5 space-y-1 ml-1">');
        inList = true;
        listType = 'ul';
      }
      html.push(`<li class="flex gap-2 text-zinc-300"><span class="text-amber-500 mt-0.5">•</span><span>${applyInline(line.replace(/^[-*] /, ''))}</span></li>`);
      continue;
    }

    // Ordered list
    const olMatch = line.match(/^(\d+)\. (.+)/);
    if (olMatch) {
      if (!inList || listType !== 'ol') {
        closeList();
        html.push('<ol class="my-1.5 space-y-1 ml-1">');
        inList = true;
        listType = 'ol';
      }
      html.push(`<li class="flex gap-2 text-zinc-300"><span class="text-amber-500 font-mono text-xs w-4 shrink-0">${olMatch[1]}.</span><span>${applyInline(olMatch[2])}</span></li>`);
      continue;
    }

    // Close list if we hit a non-list line
    closeList();

    // Empty line = paragraph break
    if (line.trim() === '') {
      html.push('<div class="h-2"></div>');
      continue;
    }

    // Regular paragraph
    html.push(`<p class="text-zinc-300 my-1">${applyInline(line)}</p>`);
  }

  closeList();
  if (inTable) html.push('</table>');

  function closeList() {
    if (inList) {
      html.push(listType === 'ul' ? '</ul>' : '</ol>');
      inList = false;
    }
  }

  return html.join('\n');
}

/** Apply inline markdown (bold, code, links) */
function applyInline(text: string): string {
  return text
    .replace(/\*\*(.+?)\*\*/g, '<strong class="text-zinc-100 font-semibold">$1</strong>')
    .replace(/`([^`]+)`/g, '<code class="bg-zinc-700/50 text-amber-300 px-1 py-0.5 rounded text-[10px] font-mono">$1</code>')
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener" class="text-blue-400 hover:text-blue-300 underline">$1</a>');
}

interface Message {
  role: 'user' | 'assistant';
  content: string;
}

interface ChatSession {
  id: string;
  name: string;
  slug: string;  // entity slug this session was started on
  messages: Message[];
}

export default function InvestigateChat({ slug, entityName, onDataRefresh }: InvestigateChatProps) {
  const [expanded, setExpanded] = useState(false);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string>('');
  const [showSessions, setShowSessions] = useState(false);
  const [editingSessionId, setEditingSessionId] = useState<string | null>(null);
  const [editName, setEditName] = useState('');
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // When page changes, auto-create a session for this page if one doesn't exist
  // and switch to it
  useEffect(() => {
    if (!slug) return;
    setSessions(prev => {
      const existing = prev.find(s => s.slug === slug);
      if (existing) {
        // Session for this page exists — switch to it
        setActiveSessionId(existing.id);
        return prev;
      }
      // Create new session for this page
      const id = `page-${slug}`;
      const newSession: ChatSession = { id, name: entityName, slug, messages: [] };
      setActiveSessionId(id);
      return [...prev, newSession];
    });
  }, [slug, entityName]);

  const activeSession = sessions.find(s => s.id === activeSessionId) || sessions[0];
  const messages = activeSession?.messages || [];
  const setMessages = (msgs: Message[]) => {
    setSessions(prev => prev.map(s => s.id === activeSessionId ? { ...s, messages: msgs } : s));
  };

  const createNewSession = () => {
    const id = `session-${Date.now()}`;
    setSessions(prev => [...prev, { id, name: `Investigation ${prev.length + 1}`, slug, messages: [] }]);
    setActiveSessionId(id);
    setShowSessions(false);
  };

  const clearSession = (id: string) => {
    setSessions(prev => prev.map(s => s.id === id ? { ...s, messages: [] } : s));
  };

  const deleteSession = (id: string) => {
    setSessions(prev => {
      const filtered = prev.filter(s => s.id !== id);
      if (filtered.length === 0) {
        // Always keep at least one session
        return [{ id: `page-${slug}`, name: entityName, slug, messages: [] }];
      }
      return filtered;
    });
    if (activeSessionId === id) {
      setSessions(prev => { setActiveSessionId(prev[0]?.id || ''); return prev; });
    }
  };

  const startRenaming = (id: string, currentName: string) => {
    setEditingSessionId(id);
    setEditName(currentName);
  };

  const finishRenaming = () => {
    if (editingSessionId && editName.trim()) {
      setSessions(prev => prev.map(s => s.id === editingSessionId ? { ...s, name: editName.trim() } : s));
    }
    setEditingSessionId(null);
    setEditName('');
  };
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
      // Trim history if too long — send last 30 messages + a summary of earlier ones
      let historyToSend = messages;
      let historySummary = '';
      if (messages.length > 30) {
        const older = messages.slice(0, messages.length - 30);
        historyToSend = messages.slice(messages.length - 30);
        // Summarize older messages
        const topics = older
          .filter(m => m.role === 'user')
          .map(m => m.content.slice(0, 50))
          .join(', ');
        historySummary = `[Earlier in this conversation, the user asked about: ${topics}]`;
      }

      const payload = {
        slug: activeSession?.slug || slug,
        message: historySummary ? `${historySummary}\n\n${trimmed}` : trimmed,
        history: historyToSend,
        session_id: activeSessionId,
        other_sessions: sessions
          .filter(s => s.id !== activeSessionId && s.messages.length > 0)
          .map(s => ({ name: s.name, slug: s.slug, message_count: s.messages.length, last_message: s.messages[s.messages.length - 1]?.content?.slice(0, 200) })),
      };

      // Retry logic — up to 3 attempts with increasing timeout
      let lastError = '';
      for (let attempt = 0; attempt < 3; attempt++) {
        try {
          const controller = new AbortController();
          const timeoutMs = attempt === 0 ? 180000 : 240000; // 3 min first try, 4 min retry
          const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

          if (attempt > 0) {
            // Show retry message
            setMessages([...updatedMessages, { role: 'assistant', content: `⏳ Taking longer than expected (attempt ${attempt + 1}/3)... Running full investigation, this can take a few minutes.` }]);
          }

          const res = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
            signal: controller.signal,
          });
          clearTimeout(timeoutId);

          const data = await res.json();
          if (res.ok) {
            setMessages([...updatedMessages, { role: 'assistant', content: data.reply }]);
            if (data.action_taken === 'refreshed' || data.action_taken === 'regenerated_briefing') {
              onDataRefresh?.();
            }
            lastError = '';
            break;
          } else {
            lastError = data.detail || 'Something went wrong.';
            if (attempt === 2) {
              setMessages([...updatedMessages, { role: 'assistant', content: `I ran into an issue: ${lastError}\n\nTry asking me again, or click the **Refresh Investigation** button at the top of the page instead.` }]);
            }
          }
        } catch (err) {
          const isTimeout = err instanceof DOMException && err.name === 'AbortError';
          lastError = isTimeout ? 'Request timed out' : 'Network error';
          if (attempt === 2) {
            setMessages([...updatedMessages, { role: 'assistant', content: isTimeout
              ? `The investigation is taking longer than expected. This usually means the backend is fetching a lot of data from FEC.\n\nTry clicking the **Refresh Investigation** button at the top of the page first, then ask me again once it completes.`
              : `I'm having trouble connecting. Check that the site is running and try again.`
            }]);
          }
        }
      }
    } catch (outerErr) {
      setMessages([...updatedMessages, { role: 'assistant', content: 'Something unexpected happened. Try again.' }]);
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

  // --- Floating bubble (collapsed) ---
  if (!expanded) {
    return (
      <div className="fixed bottom-6 right-6 z-50">
        <button
          onClick={() => setExpanded(true)}
          className="w-14 h-14 rounded-full bg-amber-500 hover:bg-amber-400 shadow-lg shadow-amber-500/20 flex items-center justify-center transition-all hover:scale-110"
        >
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#000" strokeWidth="2">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
          </svg>
        </button>
        {messages.length === 0 && (
          <div className="absolute bottom-16 right-0 bg-zinc-900 border border-zinc-700 rounded-xl px-4 py-2 text-xs text-zinc-300 whitespace-nowrap shadow-xl">
            Ask me about {entityName}
            <div className="absolute -bottom-1 right-5 w-2 h-2 bg-zinc-900 border-r border-b border-zinc-700 rotate-45" />
          </div>
        )}
      </div>
    );
  }

  // --- Chat panel (expanded) ---
  return (
    <div className="fixed bottom-6 right-6 z-50 w-[400px]" style={{ maxHeight: 'calc(100vh - 100px)' }}>
      <div
        className="bg-zinc-950 border border-zinc-800 rounded-2xl shadow-2xl shadow-black/50 flex flex-col overflow-hidden transition-all duration-300 ease-out"
        style={{ height: messages.length === 0 ? '380px' : messages.length <= 2 ? '450px' : messages.length <= 5 ? '520px' : '600px' }}
      >

        {/* Header */}
        <div className="flex items-center justify-between px-4 py-2.5 bg-zinc-900 border-b border-zinc-800">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-full bg-amber-500 flex items-center justify-center flex-shrink-0">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#000" strokeWidth="2">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
              </svg>
            </div>
            <div className="min-w-0">
              <button
                onClick={() => setShowSessions(!showSessions)}
                className="text-sm font-semibold text-zinc-200 hover:text-amber-400 transition-colors flex items-center gap-1"
              >
                {activeSession?.name || 'Investigation'}
                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" className="text-zinc-500">
                  <polyline points="6 9 12 15 18 9" />
                </svg>
              </button>
              <div className="text-[10px] text-zinc-500">Viewing: {entityName}</div>
            </div>
          </div>
          <div className="flex items-center gap-1">
            <button
              onClick={createNewSession}
              className="text-zinc-500 hover:text-amber-400 p-1.5 rounded-lg hover:bg-zinc-800 transition-colors"
              title="New investigation"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
              </svg>
            </button>
            <button onClick={() => setExpanded(false)} className="text-zinc-500 hover:text-zinc-300 p-1.5 rounded-lg hover:bg-zinc-800 transition-colors" title="Minimize">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <line x1="5" y1="12" x2="19" y2="12" />
              </svg>
            </button>
          </div>
        </div>

        {/* Session switcher dropdown */}
        {showSessions && (
          <div className="border-b border-zinc-800 bg-zinc-900/80 px-3 py-2 space-y-1">
            {sessions.map(s => (
              <div
                key={s.id}
                className={`flex items-center justify-between rounded-lg px-3 py-2 cursor-pointer transition-colors ${
                  s.id === activeSessionId ? 'bg-amber-500/10 border border-amber-500/30' : 'hover:bg-zinc-800'
                }`}
                onClick={() => { setActiveSessionId(s.id); setShowSessions(false); }}
              >
                <div className="flex-1 min-w-0">
                  {editingSessionId === s.id ? (
                    <input
                      autoFocus
                      value={editName}
                      onChange={(e) => setEditName(e.target.value)}
                      onBlur={finishRenaming}
                      onKeyDown={(e) => { if (e.key === 'Enter') finishRenaming(); if (e.key === 'Escape') setEditingSessionId(null); }}
                      onClick={(e) => e.stopPropagation()}
                      className="bg-zinc-800 border border-amber-500/50 rounded px-2 py-0.5 text-xs text-zinc-200 w-full focus:outline-none"
                    />
                  ) : (
                    <div className="text-xs font-medium text-zinc-200 truncate">{s.name}</div>
                  )}
                  <div className="text-[10px] text-zinc-500">{s.messages.length} messages</div>
                </div>
                <div className="flex items-center gap-0.5 ml-2 flex-shrink-0">
                  <button
                    onClick={(e) => { e.stopPropagation(); startRenaming(s.id, s.name); }}
                    className="text-zinc-600 hover:text-amber-400 p-1"
                    title="Rename"
                  >
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z" />
                    </svg>
                  </button>
                  {s.messages.length > 0 && (
                    <button
                      onClick={(e) => { e.stopPropagation(); clearSession(s.id); }}
                      className="text-zinc-600 hover:text-amber-400 p-1"
                      title="Clear messages"
                    >
                      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M3 6h18M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2" />
                      </svg>
                    </button>
                  )}
                  <button
                    onClick={(e) => { e.stopPropagation(); deleteSession(s.id); }}
                    className="text-zinc-600 hover:text-red-400 p-1"
                    title="Delete session"
                  >
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
                    </svg>
                  </button>
                </div>
              </div>
            ))}
            <button
              onClick={createNewSession}
              className="w-full text-left text-xs text-amber-400 hover:text-amber-300 px-3 py-2 rounded-lg hover:bg-zinc-800 transition-colors"
            >
              + New investigation thread
            </button>
          </div>
        )}

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
          {messages.length === 0 && (
            <div className="py-6">
              <div className="flex items-center gap-2 mb-4">
                <div className="w-6 h-6 rounded-full bg-amber-500/20 flex items-center justify-center">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#d4a017" strokeWidth="2">
                    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                  </svg>
                </div>
                <p className="text-zinc-400 text-xs">I can investigate, run queries, and trace money trails.</p>
              </div>
              <div className="space-y-2">
                {[
                  'Who are the biggest donors?',
                  'Any suspicious patterns?',
                  'Trace the money trail',
                  'How many donors does this person have?',
                  'Run a full investigation',
                ].map((q) => (
                  <button
                    key={q}
                    onClick={() => { setInput(q); }}
                    className="w-full text-left text-xs bg-zinc-900 hover:bg-zinc-800 text-zinc-300 px-3 py-2 rounded-lg border border-zinc-800 hover:border-amber-500/30 transition-colors"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((msg, i) => (
            <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'} gap-2`}>
              {msg.role === 'assistant' && (
                <div className="w-6 h-6 rounded-full bg-amber-500/20 flex items-center justify-center flex-shrink-0 mt-1">
                  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="#d4a017" strokeWidth="2.5">
                    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                  </svg>
                </div>
              )}
              <div
                className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
                  msg.role === 'user'
                    ? 'bg-amber-500 text-black rounded-br-md'
                    : 'bg-zinc-800/80 text-zinc-200 rounded-bl-md'
                }`}
              >
                  {msg.role === 'assistant' ? (
                    <div className="prose-sm prose-invert" dangerouslySetInnerHTML={{ __html: renderMarkdown(msg.content) }} />
                  ) : (
                    <div className="whitespace-pre-wrap">{msg.content}</div>
                  )}
                </div>
              </div>
            ))}

            {loading && (
              <div className="flex justify-start gap-2">
                <div className="w-6 h-6 rounded-full bg-amber-500/20 flex items-center justify-center flex-shrink-0 mt-1">
                  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="#d4a017" strokeWidth="2.5">
                    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                  </svg>
                </div>
                <div className="bg-zinc-800/80 rounded-2xl rounded-bl-md px-4 py-3">
                  <div className="flex gap-1.5">
                    <span className="w-1.5 h-1.5 bg-amber-400/60 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                    <span className="w-1.5 h-1.5 bg-amber-400/60 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                    <span className="w-1.5 h-1.5 bg-amber-400/60 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                  </div>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* Input */}
          <div className="px-3 py-3 border-t border-zinc-800 bg-zinc-900/50">
            <div className="flex items-center gap-2">
              <input
                ref={inputRef}
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask a question..."
                disabled={loading}
                className="flex-1 bg-zinc-800 border border-zinc-700 rounded-full px-4 py-2 text-sm text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-amber-500/50 disabled:opacity-50"
              />
              <button
                onClick={handleSend}
                disabled={loading || !input.trim()}
                className="w-9 h-9 rounded-full bg-amber-500 hover:bg-amber-400 disabled:bg-zinc-700 flex items-center justify-center transition-colors flex-shrink-0"
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={loading || !input.trim() ? '#666' : '#000'} strokeWidth="2">
                  <line x1="22" y1="2" x2="11" y2="13" /><polygon points="22 2 15 22 11 13 2 9 22 2" />
                </svg>
              </button>
            </div>
          </div>
        </div>
      </div>
  );
}
