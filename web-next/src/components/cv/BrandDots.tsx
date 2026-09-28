/** The three CDE dots of the brand (casca spec 4.1): decoration only, never text. `size` is the
 *  diameter in px (8 in the header, 6 in the footer signature). */
export function BrandDots({size = 8}: {size?: number}) {
  return (
    <span className="cv-dots" aria-hidden style={{'--cv-dot': `${size}px`} as React.CSSProperties}>
      <i /><i /><i />
    </span>
  );
}
