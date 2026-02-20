import '../styles/controls.css'

export default function VideoCanvas({ children }) {
  return (
    <div
      className="card"
      style={{
        border: '1px solid #2a2a2a',
        borderRadius: '0.75rem',
        padding: '0.75rem',
        background: '#0b0b0b',
      }}
    >
      {children}
    </div>
  )
}
