import '@fontsource-variable/manrope'
import '@fontsource-variable/newsreader'

import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'

import App from './app/App'
import { AppErrorBoundary } from './components/common/AppErrorBoundary'
import './styles/index.css'

const container = document.getElementById('root')

if (!container) {
  throw new Error('Root element #root was not found in index.html')
}

ReactDOM.createRoot(container).render(
  <React.StrictMode>
    <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <AppErrorBoundary>
        <App />
      </AppErrorBoundary>
    </BrowserRouter>
  </React.StrictMode>,
)
