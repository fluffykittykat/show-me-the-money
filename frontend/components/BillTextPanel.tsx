import { ExternalLink, FileText } from 'lucide-react';

interface BillTextPanelProps {
  tldr: string;
  officialSummary: string;
  fullTextUrl: string;
  billTitle: string;
}

export default function BillTextPanel({
  tldr,
  officialSummary,
  fullTextUrl,
  billTitle,
}: BillTextPanelProps) {
  return (
    <div className="space-y-6">
      {/* TLDR */}
      {tldr && (
        <div className="rounded-lg border border-money-gold/30 bg-money-gold/5 px-5 py-4">
          <h4 className="mb-2 flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-money-gold">
            <FileText className="h-4 w-4" />
            TL;DR
          </h4>
          <p className="text-sm leading-relaxed text-zinc-200">{tldr}</p>
        </div>
      )}

      {/* Official Summary */}
      {officialSummary && (
        <div>
          <h4 className="mb-2 text-xs font-bold uppercase tracking-wider text-zinc-500">
            Official CRS Summary
          </h4>
          <p className="text-sm leading-relaxed text-zinc-400">
            {officialSummary}
          </p>
        </div>
      )}

      {/* Full text link */}
      {fullTextUrl && (
        <a
          href={fullTextUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-2 rounded-md border border-zinc-700 bg-zinc-900 px-4 py-2.5 text-sm font-medium text-zinc-200 transition-colors hover:border-money-gold/40 hover:text-money-gold"
        >
          <ExternalLink className="h-4 w-4" />
          Read Full Text on Congress.gov
        </a>
      )}

      {!tldr && !officialSummary && (
        <p className="py-8 text-center text-sm text-zinc-600">
          No text summary available for {billTitle}.
        </p>
      )}
    </div>
  );
}
