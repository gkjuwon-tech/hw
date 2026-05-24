import type { ReactNode } from "react";

export interface PageHeaderProps {
  eyebrow: string;
  title: string;
  lede?: string | undefined;
  actions?: ReactNode | undefined;
}

/**
 * Page-level header in the landing-page grammar:
 *   eyebrow (lime dot + uppercase) → h2 (light weight, tight tracking) → lede.
 * Actions land to the right of the heading on a single baseline.
 */
export function PageHeader({
  eyebrow,
  title,
  lede,
  actions,
}: PageHeaderProps): JSX.Element {
  return (
    <header className="page__head">
      <div>
        <p className="eyebrow">
          <span className="eyebrow__dot" aria-hidden="true" />
          {eyebrow}
        </p>
        <h1 className="h2">{title}</h1>
        {lede ? <p className="lede">{lede}</p> : null}
      </div>
      {actions ? <div className="actions">{actions}</div> : null}
    </header>
  );
}
