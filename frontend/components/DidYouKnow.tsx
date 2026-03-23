interface DidYouKnowProps {
  fact: string;
}

export default function DidYouKnow({ fact }: DidYouKnowProps) {
  return (
    <div className="mt-4 rounded-lg border border-amber-500/30 bg-amber-500/10 p-4">
      <p className="text-sm text-amber-200">
        <span className="mr-1.5" aria-hidden="true">💡</span>
        <span className="font-semibold">Did you know?</span>{' '}
        {fact}
      </p>
    </div>
  );
}
