import type { ReactNode } from 'react';
import './logo.css';

/**
 * Full-bleed FTY backdrop: color-graded wash, film grain + vignette,
 * breathing glow, and the rotating emblem — with the login glass docked
 * systematically below the animation.
 */
export default function LogoStage({ children }: { children?: ReactNode }) {
  return (
    <div className="fty-stage">
      <div className="fty-grade" aria-hidden="true" />
      <div className="fty-grain" aria-hidden="true" />
      <div className="fty-vignette" aria-hidden="true" />

      <div className="fty-hero">
        <div className="fty-emblem-wrap" aria-hidden="true">
          <div className="fty-glow" />
          <div className="fty-emblem">
            <img src="/fty-logo.png" alt="" className="fty-logo" draggable={false} />
          </div>
        </div>
        <div className="fty-caption" aria-label="Free the youth">
          {'FREE THE YOUTH'.split('').map((ch, i) => (
            <span key={i} style={{ animationDelay: `${0.9 + i * 0.045}s` }}>{ch === ' ' ? ' ' : ch}</span>
          ))}
        </div>
      </div>

      {children}
    </div>
  );
}
