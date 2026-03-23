export default function Footer() {
  return (
    <footer className="border-t border-zinc-800 bg-zinc-950">
      <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        <div className="flex flex-col items-center justify-between gap-4 sm:flex-row">
          <div className="flex items-baseline gap-1 text-sm font-bold tracking-widest">
            <span className="text-zinc-500">FOLLOW THE</span>
            <span className="text-money-gold/60">MONEY</span>
          </div>
          <p className="text-xs text-zinc-600">
            Political intelligence platform. Data sourced from public records.
          </p>
          <p className="text-xs text-zinc-600">
            &copy; {new Date().getFullYear()} Project Jerry Maguire
          </p>
        </div>
      </div>
    </footer>
  );
}
