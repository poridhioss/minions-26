interface Props {
  size?: 'sm' | 'lg'
}

/** Centred inline spinner. For full-page loading, use LoadingOverlay. */
export default function Spinner({ size = 'sm' }: Props) {
  return <span className={`spinner ${size === 'lg' ? 'lg' : ''}`} aria-label="Loading" />
}
