'use client';

import { usePathname, useRouter } from 'next/navigation';
import InvestigateChat from './InvestigateChat';

/**
 * Global chat wrapper — lives in root layout, persists across page navigations.
 * Reads the current URL to determine the entity context.
 * When the chat bot runs an investigation, triggers a page reload to show fresh data.
 */
export default function GlobalChat() {
  const pathname = usePathname();
  const router = useRouter();

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

  const triggerPageRefresh = () => {
    // Find and click the PageControls refresh button on the current page
    const refreshBtn = document.querySelector('[data-refresh-investigation]') as HTMLButtonElement;
    if (refreshBtn) {
      refreshBtn.click();
    } else {
      // Fallback: call the refresh API directly if no button found
      fetch(`/api/refresh/${slug}`, { method: 'POST' })
        .then(() => router.refresh())
        .catch(() => {});
    }
  };

  return (
    <InvestigateChat
      slug={slug || 'homepage'}
      entityName={entityName}
      onDataRefresh={() => router.refresh()}
      onTriggerRefresh={triggerPageRefresh}
    />
  );
}
