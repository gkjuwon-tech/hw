import type { ReactNode } from "react";

export interface StepProps {
  num: string;
  title: string;
  body: ReactNode;
  state?: "active" | "done" | "pending";
}

/**
 * Numbered step card, matching the `.step` block on the landing page's
 * "how it works" section. Used in the Calibration wizard to render the
 * five-sample flow as four discrete states.
 */
export function Step({ num, title, body, state = "pending" }: StepProps): JSX.Element {
  return (
    <li className="step" data-state={state}>
      <span className="step__num">{num}</span>
      <h3 className="step__title">{title}</h3>
      <p className="step__body">{body}</p>
    </li>
  );
}
