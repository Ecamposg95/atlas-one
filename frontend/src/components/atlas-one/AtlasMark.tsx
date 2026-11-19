import React from 'react';

interface AtlasMarkProps {
  size?: number;
  color?: string;
  /** Se conserva por compatibilidad: la marca es de una sola tinta. */
  accent?: string | null;
}

/** Marca de Atlas Tech: la "A" geométrica dentro del círculo. Una sola tinta
 *  (`color`), sin degradado interno. `size` es el alto. */
export function AtlasMark({ size = 22, color = 'currentColor' }: AtlasMarkProps) {
  return (
    <svg height={size} viewBox="0 0 375.71 340" fill={color} aria-hidden="true" style={{ width: 'auto', flexShrink: 0 }}>
      <polygon points="252.36 236.3 195.47 110.84 140.66 236.21 98.8 235.8 174.88 71.93 216.92 71.85 295.23 235.73 252.36 236.3" />
      <polygon points="235.1 264.18 156.85 264.18 169.04 236.37 222.59 236.45 235.1 264.18" />
      <path d="M322.77,271.46c-5.63,7.02-12.31,13.43-18.68,19.74-31,30.74-75.65,46.25-119.14,44.73-92.04-3.23-164.14-80-162.22-171.68C24.29,89.2,76.26,23.61,149.63,4.95,164.96,1.05,180.47-.39,196.78.09c49.74,1.45,95.91,25.54,126.33,64.35,47.43,60.52,48.14,146.58-.34,207.02ZM285.77,268.38c61.55-58.4,56.66-157.12-9.84-209.36-54.27-42.64-132.41-38.36-181.82,10.11-54.43,53.4-55.5,140.38-2.56,195.07,52.52,54.26,139.28,56.32,194.22,4.19Z" />
    </svg>
  );
}
