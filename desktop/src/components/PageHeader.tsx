import type { ReactNode } from "react";

export interface PageHeaderProps {
  eyebrow: string;
  title: string;
  lede?: string | undefined;
  actions?: ReactNode | undefined;
}

/**
 * Compact page header in the industrial register:
 *
 *   [eyebrow · TITLE]            [actions]
 *
 * The previous landing-page "eyebrow → h2 → lede" cluster is replaced
 * with a single uppercase title (`h1`) and an optional muted subtitle
 * shown after it on the same line on wide screens.
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
        <h1 className="h1" style={{ marginTop: 2 }}>{title}</h1>
        {lede ? <p className="lede" style={{ marginTop: 4 }}>{lede}</p> : null}
      </div>
      {actions ? <div className="actions">{actions}</div> : null}
    </header>
  );
}
