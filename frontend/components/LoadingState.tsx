import clsx from 'clsx';

interface LoadingStateProps {
  variant?: 'card' | 'table-row' | 'profile' | 'text';
  count?: number;
}

function SkeletonBlock({ className }: { className?: string }) {
  return (
    <div
      className={clsx('skeleton-pulse rounded bg-zinc-800', className)}
    />
  );
}

function CardSkeleton() {
  return (
    <div className="rounded-lg border border-zinc-800 bg-money-surface p-6">
      <SkeletonBlock className="mb-4 h-12 w-12 rounded-full" />
      <SkeletonBlock className="mb-2 h-5 w-3/4" />
      <SkeletonBlock className="mb-2 h-4 w-1/2" />
      <SkeletonBlock className="h-4 w-2/3" />
    </div>
  );
}

function TableRowSkeleton() {
  return (
    <div className="flex items-center gap-4 border-b border-zinc-800 px-4 py-3">
      <SkeletonBlock className="h-4 w-1/4" />
      <SkeletonBlock className="h-4 w-1/5" />
      <SkeletonBlock className="h-4 w-1/6" />
      <SkeletonBlock className="h-4 w-1/4" />
    </div>
  );
}

function ProfileSkeleton() {
  return (
    <div className="space-y-6">
      <div className="flex items-start gap-6">
        <SkeletonBlock className="h-24 w-24 rounded-full" />
        <div className="flex-1 space-y-3">
          <SkeletonBlock className="h-8 w-1/3" />
          <SkeletonBlock className="h-5 w-1/4" />
          <SkeletonBlock className="h-4 w-1/2" />
        </div>
      </div>
      <div className="flex gap-6">
        {[1, 2, 3, 4].map((i) => (
          <SkeletonBlock key={i} className="h-16 w-32" />
        ))}
      </div>
      <SkeletonBlock className="h-48 w-full" />
    </div>
  );
}

function TextSkeleton() {
  return (
    <div className="space-y-2">
      <SkeletonBlock className="h-4 w-full" />
      <SkeletonBlock className="h-4 w-5/6" />
      <SkeletonBlock className="h-4 w-4/6" />
    </div>
  );
}

export default function LoadingState({
  variant = 'card',
  count = 1,
}: LoadingStateProps) {
  const items = Array.from({ length: count }, (_, i) => i);

  if (variant === 'profile') {
    return <ProfileSkeleton />;
  }

  if (variant === 'text') {
    return (
      <div className="space-y-4">
        {items.map((i) => (
          <TextSkeleton key={i} />
        ))}
      </div>
    );
  }

  if (variant === 'table-row') {
    return (
      <div>
        {items.map((i) => (
          <TableRowSkeleton key={i} />
        ))}
      </div>
    );
  }

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {items.map((i) => (
        <CardSkeleton key={i} />
      ))}
    </div>
  );
}
