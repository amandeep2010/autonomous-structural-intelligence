import React, { useState } from 'react';

export default function ExplainPanel({ reportData }) {
  const [activeTab, setActiveTab] = useState('summary');
  const { summary, element_reports = [], concern_reports = [], cost_summary } = reportData || {};

  const tabs = [
    { key: 'summary', label: 'SUMMARY' },
    { key: 'elements', label: `ELEMENTS (${element_reports.length})` },
    { key: 'concerns', label: `CONCERNS (${concern_reports.length})`, alert: concern_reports.length > 0 },
  ];

  return (
    <div style={{
      fontFamily: "'Courier New', monospace",
      color: '#c0d8e0',
      height: '100%',
      display: 'flex',
      flexDirection: 'column',
    }}>
      {/* Tab bar */}
      <div style={{
        display: 'flex',
        borderBottom: '1px solid rgba(0,255,255,0.15)',
        padding: '0 1.5rem',
        flexShrink: 0,
      }}>
        {tabs.map(tab => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            style={{
              background: 'none',
              border: 'none',
              borderBottom: activeTab === tab.key ? '2px solid #00ffff' : '2px solid transparent',
              color: activeTab === tab.key ? '#00ffff' : 'rgba(0,255,255,0.35)',
              padding: '0.75rem 1.25rem 0.65rem',
              fontSize: '0.65rem',
              letterSpacing: '2px',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '0.4rem',
              transition: 'all 0.2s',
            }}
          >
            {tab.label}
            {tab.alert && (
              <span style={{
                width: '6px', height: '6px',
                borderRadius: '50%', background: '#ff3c3c',
                display: 'inline-block',
              }} />
            )}
          </button>
        ))}
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '1.5rem' }}>

        {/* SUMMARY TAB */}
        {activeTab === 'summary' && (
          <div>
            <div style={{
              background: 'rgba(0,255,255,0.04)',
              border: '1px solid rgba(0,255,255,0.15)',
              borderLeft: '3px solid #00ffff',
              padding: '1.25rem 1.5rem',
              borderRadius: '2px',
              lineHeight: 1.8,
              fontSize: '0.82rem',
              color: '#d0e8f0',
              marginBottom: '1.5rem',
            }}>
              {summary || 'No summary generated.'}
            </div>

            {cost_summary && (
              <div>
                <div style={{ color: 'rgba(0,255,255,0.5)', fontSize: '0.6rem', letterSpacing: '3px', marginBottom: '0.75rem' }}>
                  COST OVERVIEW
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem' }}>
                  {Object.entries(cost_summary).map(([k, v]) => (
                    <div key={k} style={{
                      background: 'rgba(0,255,255,0.03)',
                      border: '1px solid rgba(0,255,255,0.1)',
                      padding: '0.6rem 0.8rem',
                    }}>
                      <div style={{ color: 'rgba(0,255,255,0.4)', fontSize: '0.58rem', letterSpacing: '1.5px', marginBottom: '0.2rem' }}>
                        {k.replace(/_/g, ' ').toUpperCase()}
                      </div>
                      <div style={{ color: '#fff', fontSize: '0.82rem' }}>{v}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* ELEMENTS TAB */}
        {activeTab === 'elements' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {element_reports.length === 0 && (
              <div style={{ color: 'rgba(0,255,255,0.3)', fontSize: '0.8rem', letterSpacing: '2px', textAlign: 'center', paddingTop: '2rem' }}>
                NO ELEMENT REPORTS
              </div>
            )}
            {element_reports.map((el, i) => (
              <div key={i} style={{
                background: 'rgba(0,255,255,0.03)',
                border: '1px solid rgba(0,255,255,0.12)',
                borderRadius: '2px',
                overflow: 'hidden',
              }}>
                <div style={{
                  background: 'rgba(0,255,255,0.06)',
                  padding: '0.5rem 1rem',
                  display: 'flex', alignItems: 'center', gap: '0.6rem',
                  borderBottom: '1px solid rgba(0,255,255,0.1)',
                }}>
                  <div style={{
                    width: '7px', height: '7px', borderRadius: '50%',
                    background: el.element_type?.includes('load') ? '#cd853f' : '#00ffff',
                  }} />
                  <span style={{ color: '#fff', fontSize: '0.72rem', letterSpacing: '1.5px' }}>
                    {(el.element_id || `ELEMENT ${i + 1}`).toString().toUpperCase()}
                  </span>
                  <span style={{ color: 'rgba(0,255,255,0.4)', fontSize: '0.62rem', letterSpacing: '1px' }}>
                    {el.element_type?.toUpperCase()}
                  </span>
                </div>
                <div style={{
                  padding: '0.8rem 1rem',
                  fontSize: '0.78rem',
                  lineHeight: 1.75,
                  color: '#aac8d0',
                }}>
                  {el.explanation || el.report || el.text || JSON.stringify(el)}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* CONCERNS TAB */}
        {activeTab === 'concerns' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {concern_reports.length === 0 && (
              <div style={{
                color: '#4aaa4a', fontSize: '0.8rem', letterSpacing: '2px',
                textAlign: 'center', paddingTop: '2rem',
              }}>
                ✓ NO STRUCTURAL CONCERNS DETECTED
              </div>
            )}
            {concern_reports.map((c, i) => (
              <div key={i} style={{
                background: 'rgba(255,60,60,0.06)',
                border: '1px solid rgba(255,60,60,0.25)',
                borderLeft: '3px solid #ff3c3c',
                padding: '0.9rem 1.1rem',
                borderRadius: '2px',
              }}>
                <div style={{
                  color: '#ff6060', fontSize: '0.65rem', letterSpacing: '2px',
                  marginBottom: '0.4rem', display: 'flex', alignItems: 'center', gap: '0.4rem',
                }}>
                  <span>⚠</span>
                  <span>{(c.concern_type || c.type || 'STRUCTURAL WARNING').toUpperCase()}</span>
                </div>
                <div style={{ color: '#ffb0b0', fontSize: '0.78rem', lineHeight: 1.7 }}>
                  {c.explanation || c.message || c.text || JSON.stringify(c)}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
