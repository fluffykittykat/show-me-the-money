'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { Shield, Loader2, AlertTriangle } from 'lucide-react';
import { getBriefing, listEntities } from '@/lib/api';
import type { Entity, BriefingResponse } from '@/lib/types';
import { formatDate, capitalize } from '@/lib/utils';

interface FBIBriefingProps {
  entitySlug: string;
  entityName: string;
  entityType: string;
}

// Cache entity name -> link mapping so we only fetch once
let entityLinkMap: Map<string, { slug: string; type: string }> | null = null;
let entityLinkMapLoading = false;
const entityLinkMapCallbacks: Array<() => void> = [];

async function getEntityLinkMap(): Promise<Map<string, { slug: string; type: string }>> {
  if (entityLinkMap) return entityLinkMap;
  if (entityLinkMapLoading) {
    return new Promise((resolve) => {
      entityLinkMapCallbacks.push(() => resolve(entityLinkMap!));
    });
  }
  entityLinkMapLoading = true;
  try {
    const data = await listEntities(undefined, 500);
    const map = new Map<string, { slug: string; type: string }>();
    for (const e of data.results) {
      const href = e.entity_type === 'person'
        ? `/officials/${e.slug}`
        : `/entities/${e.entity_type}/${e.slug}`;
      map.set(e.name, { slug: href, type: e.entity_type });
      // Also add common short names (e.g. "JPMorgan Chase" for "JPMorgan Chase & Co")
      const shortName = e.name.replace(/\s*(&.*|,.*|\(.*)\s*$/, '').trim();
      if (shortName !== e.name && shortName.length > 3) {
        map.set(shortName, { slug: href, type: e.entity_type });
      }
    }
    entityLinkMap = map;
    entityLinkMapCallbacks.forEach(cb => cb());
    entityLinkMapCallbacks.length = 0;
    return map;
  } catch {
    entityLinkMapLoading = false;
    return new Map();
  }
}

function getEntityHref(type: string, slug: string): string {
  return type === 'person' ? `/officials/${slug}` : `/entities/${type}/${slug}`;
}

/**
 * Render inline markdown: **bold**, [text](url) links, and auto-link entity names
 */
function InlineMarkdown({ text, linkMap }: { text: string; linkMap?: Map<string, { slug: string; type: string }> }) {
  // First pass: split on **bold** and [link](url) patterns
  const parts = text.split(/(\*\*[^*]+\*\*|\[[^\]]+\]\([^)]+\))/g);
  return (
    <>
      {parts.map((part, i) => {
        // Bold
        if (part.startsWith('**') && part.endsWith('**')) {
          const innerText = part.slice(2, -2);
          return (
            <strong key={i} className="font-semibold text-zinc-100">
              <EntityLinker text={innerText} linkMap={linkMap} className="font-semibold text-money-gold hover:underline" />
            </strong>
          );
        }
        // Markdown link [text](url)
        const linkMatch = part.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
        if (linkMatch) {
          return (
            <a
              key={i}
              href={linkMatch[2]}
              target="_blank"
              rel="noopener noreferrer"
              className="text-money-gold hover:underline"
            >
              {linkMatch[1]}
            </a>
          );
        }
        // Plain text — auto-link entity names
        return <EntityLinker key={i} text={part} linkMap={linkMap} className="text-money-gold hover:underline" />;
      })}
    </>
  );
}

/**
 * Auto-link known entity names within text.
 * Finds the longest matching entity name at each position to avoid partial matches.
 */
function EntityLinker({
  text,
  linkMap,
  className,
}: {
  text: string;
  linkMap?: Map<string, { slug: string; type: string }>;
  className?: string;
}) {
  if (!linkMap || linkMap.size === 0) return <>{text}</>;

  // Sort names by length (longest first) to match greedily
  const names = Array.from(linkMap.keys()).sort((a, b) => b.length - a.length);

  // Build result by scanning through text
  const result: React.ReactNode[] = [];
  let remaining = text;
  let idx = 0;

  while (remaining.length > 0) {
    let matched = false;
    for (const name of names) {
      if (name.length < 4) continue; // Skip very short names
      const pos = remaining.indexOf(name);
      if (pos === 0) {
        const entity = linkMap.get(name)!;
        result.push(
          <Link key={`${idx}-link`} href={entity.slug} className={className}>
            {name}
          </Link>
        );
        remaining = remaining.slice(name.length);
        idx++;
        matched = true;
        break;
      } else if (pos > 0) {
        // Output text before the match
        result.push(<span key={`${idx}-text`}>{remaining.slice(0, pos)}</span>);
        remaining = remaining.slice(pos);
        idx++;
        matched = true;
        break; // Re-check from the new position
      }
    }
    if (!matched) {
      // No entity name found in remaining text
      result.push(<span key={`${idx}-rest`}>{remaining}</span>);
      break;
    }
  }

  return <>{result}</>;
}

/**
 * Parse the pre-formatted briefing text from the backend into styled sections.
 * Handles: **bold**, ## headings, bullet points (*, -, •), --- dividers,
 * KEY FINDINGS, INVESTIGATIVE ASSESSMENT, SUBJECT/CLASSIFICATION lines.
 */
function BriefingContent({ text, linkMap }: { text: string; linkMap?: Map<string, { slug: string; type: string }> }) {
  const lines = text.split('\n');
  const elements: React.ReactNode[] = [];
  let inAssessment = false;
  let assessmentLines: string[] = [];
  let bulletGroup: string[] = [];

  function flushBullets() {
    if (bulletGroup.length === 0) return;
    elements.push(
      <ul key={`bullets-${elements.length}`} className="my-3 space-y-2.5 pl-1">
        {bulletGroup.map((b, i) => (
          <li key={i} className="flex items-start gap-2.5 text-zinc-300 text-sm leading-relaxed">
            <span className="mt-1.5 inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-money-gold" />
            <span><InlineMarkdown text={b.replace(/^[•\-\*]\s*/, '')} linkMap={linkMap} /></span>
          </li>
        ))}
      </ul>
    );
    bulletGroup = [];
  }

  function flushAssessment() {
    if (assessmentLines.length === 0) return;
    elements.push(
      <div
        key={`assessment-${elements.length}`}
        className="mt-5 rounded-lg border border-amber-500/20 bg-amber-500/5 p-5"
      >
        <h4 className="mb-3 font-mono text-xs font-bold uppercase tracking-wider text-amber-400">
          Investigative Assessment
        </h4>
        <div className="space-y-3 text-sm leading-relaxed text-zinc-300">
          {assessmentLines.map((line, i) => {
            const trimmed = line.trim();
            if (!trimmed) return null;
            if (trimmed.startsWith('•') || trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
              return (
                <div key={i} className="flex items-start gap-2.5 pl-1">
                  <span className="mt-1.5 inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-amber-400" />
                  <span><InlineMarkdown text={trimmed.replace(/^[•\-\*]\s*/, '')} linkMap={linkMap} /></span>
                </div>
              );
            }
            return <p key={i}><InlineMarkdown text={trimmed} linkMap={linkMap} /></p>;
          })}
        </div>
      </div>
    );
    assessmentLines = [];
  }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();

    // Skip empty lines
    if (!trimmed) {
      if (inAssessment) {
        assessmentLines.push('');
      } else {
        flushBullets();
      }
      continue;
    }

    // Horizontal rule / divider
    if (/^-{3,}$/.test(trimmed)) {
      flushBullets();
      continue; // Skip dividers — the component has its own visual structure
    }

    // ## Markdown heading
    if (trimmed.startsWith('## ')) {
      flushBullets();
      const headingText = trimmed.replace(/^##\s*/, '').replace(/\*\*/g, '');
      // Check if it's the assessment heading
      if (headingText.toUpperCase().includes('INVESTIGATIVE ASSESSMENT')) {
        inAssessment = true;
        continue;
      }
      if (headingText.toUpperCase().includes('KEY FINDINGS')) {
        elements.push(
          <h4
            key={`kf-${elements.length}`}
            className="mb-1 mt-4 font-mono text-xs font-bold uppercase tracking-wider text-money-gold"
          >
            KEY FINDINGS
          </h4>
        );
        continue;
      }
      // Generic section heading
      elements.push(
        <h4
          key={`h-${elements.length}`}
          className="mb-1 mt-4 font-mono text-xs font-bold uppercase tracking-wider text-zinc-400"
        >
          {headingText}
        </h4>
      );
      continue;
    }

    // INVESTIGATIVE ASSESSMENT section (plain text variant)
    if (trimmed.toUpperCase().startsWith('INVESTIGATIVE ASSESSMENT')) {
      flushBullets();
      inAssessment = true;
      continue;
    }

    if (inAssessment) {
      assessmentLines.push(trimmed);
      continue;
    }

    // CLASSIFICATION line
    if (trimmed.toUpperCase().startsWith('CLASSIFICATION:') || trimmed.toUpperCase().startsWith('**CLASSIFICATION')) {
      flushBullets();
      elements.push(
        <p
          key={`class-${elements.length}`}
          className="font-mono text-[11px] uppercase tracking-wider text-zinc-600"
        >
          {trimmed.replace(/\*\*/g, '')}
        </p>
      );
      continue;
    }

    // SUBJECT line
    if (trimmed.toUpperCase().startsWith('SUBJECT:') || trimmed.toUpperCase().startsWith('**SUBJECT')) {
      flushBullets();
      continue; // Skip — the component header already shows the subject
    }

    // PREPARED BY / DATE lines
    if (trimmed.toUpperCase().startsWith('PREPARED BY') || trimmed.toUpperCase().startsWith('**PREPARED BY') || trimmed.toUpperCase().startsWith('**DATE')) {
      flushBullets();
      elements.push(
        <p
          key={`meta-${elements.length}`}
          className="font-mono text-[11px] uppercase tracking-wider text-zinc-600"
        >
          {trimmed.replace(/\*\*/g, '')}
        </p>
      );
      continue;
    }

    // KEY FINDINGS header (plain text variant)
    if (trimmed.toUpperCase().startsWith('KEY FINDINGS')) {
      flushBullets();
      elements.push(
        <h4
          key={`kf-${elements.length}`}
          className="mb-1 mt-4 font-mono text-xs font-bold uppercase tracking-wider text-money-gold"
        >
          KEY FINDINGS
        </h4>
      );
      continue;
    }

    // Follow the Money / Hidden Connections section headers
    if (trimmed.startsWith('**Follow the Money') || trimmed.startsWith('**The Hidden Connections')) {
      flushBullets();
      const label = trimmed.replace(/\*\*/g, '').replace(/:$/, '');
      elements.push(
        <h4
          key={`sh-${elements.length}`}
          className="mb-1 mt-4 font-mono text-xs font-bold uppercase tracking-wider text-zinc-400"
        >
          {label}
        </h4>
      );
      continue;
    }

    // Bullet points (*, -, •)
    if (trimmed.startsWith('•') || trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
      bulletGroup.push(trimmed);
      continue;
    }

    // Sources section header
    if (trimmed.toUpperCase().startsWith('SOURCES:') || trimmed.toUpperCase() === 'SOURCES') {
      flushBullets();
      elements.push(
        <h4
          key={`src-h-${elements.length}`}
          className="mb-1 mt-4 font-mono text-[10px] font-bold uppercase tracking-wider text-zinc-500"
        >
          Sources
        </h4>
      );
      continue;
    }

    // Sources line at the end
    if (trimmed.startsWith('*Sources consulted') || trimmed.startsWith('*All findings')) {
      flushBullets();
      elements.push(
        <p key={`src-${elements.length}`} className="mt-4 text-[10px] italic text-zinc-600">
          <InlineMarkdown text={trimmed.replace(/^\*/, '').replace(/\*$/, '')} linkMap={linkMap} />
        </p>
      );
      continue;
    }

    // Regular paragraph
    flushBullets();
    elements.push(
      <p key={`p-${elements.length}`} className="my-2 text-sm leading-relaxed text-zinc-300">
        <InlineMarkdown text={trimmed} linkMap={linkMap} />
      </p>
    );
  }

  // Flush remaining
  flushBullets();
  if (inAssessment) {
    flushAssessment();
  }

  return <>{elements}</>;
}

// In-memory cache so tab switches don't re-fetch
const briefingCache = new Map<string, BriefingResponse>();

export default function FBIBriefing({
  entitySlug,
  entityName,
  entityType,
}: FBIBriefingProps) {
  const cached = briefingCache.get(entitySlug);
  const [briefing, setBriefing] = useState<BriefingResponse | null>(cached || null);
  const [loading, setLoading] = useState(!cached);
  const [error, setError] = useState<string | null>(null);
  const [linkMap, setLinkMap] = useState<Map<string, { slug: string; type: string }> | undefined>(entityLinkMap || undefined);

  useEffect(() => {
    // Load entity link map for auto-linking names in briefing text
    getEntityLinkMap().then(setLinkMap);

    // Already have briefing cached in memory — skip fetch
    if (briefingCache.has(entitySlug)) {
      setBriefing(briefingCache.get(entitySlug)!);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    getBriefing(entitySlug)
      .then((data) => {
        briefingCache.set(entitySlug, data);
        setBriefing(data);
      })
      .catch(() => {
        setError('Briefing generation unavailable');
      })
      .finally(() => {
        setLoading(false);
      });
  }, [entitySlug]);

  return (
    <div className="relative overflow-hidden rounded-lg border border-zinc-700 bg-zinc-950/80">
      {/* Gold top border accent */}
      <div className="h-1 bg-gradient-to-r from-money-gold via-money-gold/60 to-transparent" />

      {/* Watermark */}
      <div className="pointer-events-none absolute inset-0 flex items-center justify-center opacity-[0.02]">
        <span className="select-none text-6xl font-black uppercase tracking-[0.3em] text-white rotate-[-15deg]">
          FOLLOW THE MONEY
        </span>
      </div>

      <div className="relative p-5 sm:p-6">
        {/* Header */}
        <div className="mb-4 flex items-center justify-between border-b border-dashed border-zinc-700 pb-3">
          <div className="flex items-center gap-2">
            <Shield className="h-4 w-4 text-money-gold" />
            <span className="font-mono text-xs font-bold uppercase tracking-[0.2em] text-money-gold">
              FBI Special Agent Briefing // Follow The Money
            </span>
          </div>
          <div className="flex items-center gap-2">
            {briefing && !loading && (
              <button
                onClick={() => {
                  setLoading(true);
                  setError(null);
                  setBriefing(null);
                  briefingCache.delete(entitySlug);
                  getBriefing(entitySlug, true)
                    .then((data) => {
                      briefingCache.set(entitySlug, data);
                      setBriefing(data);
                    })
                    .catch(() => {
                      setError('Regeneration failed. Try again.');
                    })
                    .finally(() => {
                      setLoading(false);
                    });
                }}
                className="rounded border border-zinc-700 px-2 py-1 font-mono text-[10px] text-zinc-400 hover:border-money-gold hover:text-money-gold transition-colors"
              >
                Regenerate
              </button>
            )}
            <span className="hidden font-mono text-xs text-zinc-600 sm:inline">
              {capitalize(entityType)} // {entitySlug}
            </span>
          </div>
        </div>

        {/* Classification line */}
        <p className="mb-1 font-mono text-[10px] uppercase tracking-[0.15em] text-zinc-600">
          Classification: Unclassified // For Official Use Only
        </p>
        <p className="mb-4 font-mono text-[10px] uppercase tracking-[0.15em] text-zinc-600">
          Prepared By: Financial Crimes &amp; Public Corruption Unit
        </p>

        {/* Subject */}
        <div className="mb-4 border-b border-dashed border-zinc-800 pb-3">
          <span className="font-mono text-xs uppercase tracking-wider text-zinc-500">
            Subject:
          </span>
          <span className="ml-2 font-mono text-sm font-semibold text-zinc-200">
            {entityName}
          </span>
        </div>

        {/* Loading state */}
        {loading && (
          <div className="flex items-center gap-3 py-8">
            <Loader2 className="h-5 w-5 animate-spin text-money-gold" />
            <span className="font-mono text-sm text-zinc-400">
              Generating intelligence briefing...
            </span>
          </div>
        )}

        {/* Error state with retry button */}
        {error && !loading && (
          <div className="flex items-center justify-between gap-3 rounded-md border border-yellow-500/20 bg-yellow-500/5 px-4 py-3">
            <div className="flex items-center gap-3">
              <AlertTriangle className="h-4 w-4 shrink-0 text-yellow-500" />
              <span className="font-mono text-sm text-yellow-200">{error}</span>
            </div>
            <button
              onClick={() => {
                setLoading(true);
                setError(null);
                getBriefing(entitySlug)
                  .then((data) => {
                    briefingCache.set(entitySlug, data);
                    setBriefing(data);
                  })
                  .catch(() => {
                    setError('Briefing generation unavailable. AI service may be offline.');
                  })
                  .finally(() => {
                    setLoading(false);
                  });
              }}
              className="shrink-0 rounded-md bg-money-gold px-3 py-1.5 text-xs font-bold text-zinc-950 hover:bg-money-gold-hover transition-colors"
            >
              Retry
            </button>
          </div>
        )}

        {/* Briefing content */}
        {briefing && !loading && (
          <div className="space-y-0 font-mono text-sm leading-relaxed">
            <BriefingContent text={briefing.briefing_text} linkMap={linkMap} />

            {briefing.generated_at && (
              <p className="mt-4 text-[10px] text-zinc-600">
                Intelligence generated {formatDate(briefing.generated_at)}
              </p>
            )}
          </div>
        )}

        {/* Classification footer */}
        <div className="mt-5 border-t border-dashed border-zinc-800 pt-3 text-center">
          <span className="font-mono text-[10px] font-bold uppercase tracking-[0.3em] text-zinc-700">
            Follow The Money // End Briefing
          </span>
        </div>
      </div>
    </div>
  );
}
