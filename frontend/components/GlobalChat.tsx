'use client';

import { usePathname } from 'next/navigation';
import InvestigateChat from './InvestigateChat';

/**
 * Global chat wrapper — lives in root layout, persists across page navigations.
 * Reads the current URL to determine the entity context.
 */
export default function GlobalChat() {
  const pathname = usePathname();

  // Extract slug and entity name from URL
  let slug = '';
  let entityName = 'Follow the Money';

  if (pathname.startsWith('/officials/')) {
    slug = pathname.split('/officials/')[1]?.split('/')[0]?.split('#')[0] || '';
    entityName = slug.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
  } else if (pathname.startsWith('/bills/')) {
    slug = pathname.split('/bills/')[1]?.split('/')[0]?.split('#')[0] || '';
    entityName = `Bill ${slug}`;
  } else if (pathname.startsWith('/entities/')) {
    const parts = pathname.split('/entities/')[1]?.split('/') || [];
    slug = parts[1]?.split('#')[0] || '';
    entityName = slug.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
  }

  // Always show the chat — even on homepage. Slug can be empty for general questions.
  return <InvestigateChat slug={slug || 'homepage'} entityName={entityName} />;
}
