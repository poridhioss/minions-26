import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { Toaster } from 'react-hot-toast'

import App from './App'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
      <Toaster
        position="bottom-right"
        toastOptions={{
          duration: 4000,
          style: {
            background: 'var(--bg-2)',
            color: 'var(--text-0)',
            border: '1px solid var(--border-strong)',
            fontSize: '13px',
          },
          success: { iconTheme: { primary: 'var(--success)', secondary: 'var(--bg-0)' } },
          error: { iconTheme: { primary: 'var(--danger)', secondary: 'var(--bg-0)' } },
        }}
      />
    </BrowserRouter>
  </React.StrictMode>,
)
