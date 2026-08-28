import type { Route } from '../api/types';

const routeLabels: Record<Route, string> = {
  RETRIEVAL_ONLY: 'Tra cứu điều luật',
  CALCULATOR_ONLY: 'Tra cứu điều luật',
  RETRIEVAL_AND_CALCULATOR: 'Tra cứu điều luật',
  CASE_ANALYSIS: 'Phân tích tình huống',
  OUT_OF_SCOPE: 'Ngoài phạm vi',
};

export function ModeBadge({ route }: { route?: Route | null }) {
  if (!route) return null;

  return (
    <span className="inline-flex w-fit rounded-full bg-surface-container-high px-2 py-1 text-xs text-on-surface-variant">
      {routeLabels[route]}
    </span>
  );
}
