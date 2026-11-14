import React, { useState, useRef, useEffect } from 'react';
import { Info } from 'lucide-react';
import { CanonicalQuantTerm, QUANT_TERM_DEFINITIONS } from '../../i18n/translations';
import { SupportedLanguage } from '../../types/sirix';

interface TermTooltipProps {
  term: CanonicalQuantTerm;
  language: SupportedLanguage;
  labelOverride?: string;
  className?: string;
}

/**
 * TermTooltip — F00 Section 4.2 & F03 Section 5.1.1
 * Preserves canonical English quantitative terms (e.g., "Triple-Barrier", "Chandelier Stop", "Portfolio Heat")
 * in LTR isolation while providing an interactive tap/hover ⓘ tooltip with a localized explanation.
 */
export const TermTooltip: React.FC<TermTooltipProps> = ({
  term,
  language,
  labelOverride,
  className = '',
}) => {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!open) return;
    const handleOutsideClick = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handleOutsideClick);
    return () => document.removeEventListener('mousedown', handleOutsideClick);
  }, [open]);

  const definition = QUANT_TERM_DEFINITIONS[term]?.[language] || QUANT_TERM_DEFINITIONS[term]?.en;

  return (
    <span
      ref={containerRef}
      className={` relative inline-flex items-center gap-1 align-baseline ${className}`}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <span dir="ltr" className="font-medium tracking-tight">
        {labelOverride || term}
      </span>
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          setOpen((prev) => !prev);
        }}
        aria-label={`Definition for ${term}`}
        className="inline-flex items-center justify-center rounded-full p-0.5 text-[var(--text-muted)] hover:text-[var(--accent-brand)] focus:outline-none transition-colors cursor-pointer"
      >
        <Info className="w-3.5 h-3.5" />
      </button>

      {open && (
        <span
          role="tooltip"
          onClick={(e) => e.stopPropagation()}
          className="fixed sm:absolute z-50 left-4 right-4 sm:left-0 sm:right-auto bottom-auto sm:bottom-full sm:mb-2 sm:w-72 p-3 rounded-lg border border-[var(--border-strong)] bg-[var(--bg-surface)] text-[var(--text-primary)] shadow-xl text-xs leading-relaxed font-normal"
        >
          <span className="flex items-center justify-between gap-2 pb-1.5 mb-1.5 border-b border-[var(--border-subtle)]">
            <span dir="ltr" className="font-mono-tabular font-semibold text-[var(--accent-brand)]">
              {term}
            </span>
            <span className="text-[10px] uppercase tracking-wider text-[var(--text-muted)]">
              SIRIX Quant Lexicon
            </span>
          </span>
          <span className="block text-[var(--text-secondary)]">{definition}</span>
        </span>
      )}
    </span>
  );
};
