import React, { useState } from 'react';
import { CustomerView } from './CustomerView';
import { ReviewerConsole } from './ReviewerConsole';
import './styles.css';

export default function App() {
  const [currentView, setCurrentView] = useState<'customer' | 'reviewer'>('customer');

  return (
    <div className="app-layout">
      {/* WCAG 2.4.1 Bypass Blocks: Skip Link */}
      <a href="#main-content" className="skip-link">
        Skip to main content
      </a>

      {/* Main Header Landmark */}
      <header className="header-bar" role="banner">
        <h1 className="brand-h1">
          <span aria-hidden="true">🌿</span> Aster &amp; Row Support
        </h1>

        <nav aria-label="Main Navigation">
          <div className="nav-links">
            <button
              className={`nav-button ${currentView === 'customer' ? 'active' : ''}`}
              onClick={() => setCurrentView('customer')}
              aria-current={currentView === 'customer' ? 'page' : undefined}
            >
              Customer Chat
            </button>
            <button
              className={`nav-button ${currentView === 'reviewer' ? 'active' : ''}`}
              onClick={() => setCurrentView('reviewer')}
              aria-current={currentView === 'reviewer' ? 'page' : undefined}
            >
              Reviewer Console
            </button>
          </div>
        </nav>
      </header>

      {/* Main Content Landmark */}
      <main id="main-content" role="main" style={{ display: 'flex', flexDirection: 'column', flex: 1 }}>
        {currentView === 'customer' ? <CustomerView /> : <ReviewerConsole />}
      </main>
    </div>
  );
}
