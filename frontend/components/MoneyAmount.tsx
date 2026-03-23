import { formatMoney } from '@/lib/utils';
import clsx from 'clsx';

interface MoneyAmountProps {
  amount?: number | null;
  label?: string | null;
  fromCents?: boolean;
  className?: string;
}

export default function MoneyAmount({
  amount,
  label,
  fromCents = false,
  className,
}: MoneyAmountProps) {
  const display = label || (amount != null ? formatMoney(amount, { fromCents }) : '$0');

  return (
    <span className={clsx('font-semibold text-money-success', className)}>
      {display}
    </span>
  );
}
