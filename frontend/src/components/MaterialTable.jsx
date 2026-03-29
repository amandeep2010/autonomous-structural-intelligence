import React, { useState } from 'react';

const scoreBar = (score, color) => (
  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
    <div style={{
      width: '80px', height: '4px',
      background: 'rgba(255,255,255,0.08)', borderRadius: '2px', overflow: 'hidden',
    }}>
      <div style={{
        width: `${Math.min(score * 10, 100)}%`,
        height: '100%',
        background: color,
        borderRadius: '2px',
        transition: 'width 0.6s ease',
      }} />
    </div>
    <span style={{ color: color, fontSize: '0.72rem', fontFamily: "'Courier New', monospace" }}>
      {typeof score === 'number' ? score.toFixed(2) : score}
    </span>
  </div>
);

const rankBadge = (rank) => {
  const colors = { 1: '#00ffff', 2: '#4a9aba', 3: '#2a5a6a' };
  const labels = { 1: '★ BEST', 2: '2ND', 3: '3RD' };
  return (
    <div style={{
      background: colors[rank] || '#1a2a3a',
      color: rank === 1 ? '#030a14' : '#fff',
      fontSize: '0.6rem',
      fontWeight: 'bold',
      padding: '2px 8px',
      borderRadius: '2px',
      letterSpacing: '1px',
      fontFamily: "'Courier New', monospace",
      whiteSpace: 'nowrap',
    }}>
      {labels[rank] || `#${rank}`}
    </div>
  );
};

export default function MaterialTable({ materialsData }) {
  const [expandedElement, setExpandedElement] = useState(null);
  const { recommendations = [], cost_summary = {}, structural_concerns = [] } = materialsData || {};

  return (
    <div style={{
      fontFamily: "'Courier New', monospace",
      color: '#c0d8e0',
      height: '100%',
      overflowY: 'auto',
      padding: '1.5rem',
    }}>
      <div style={{ color: '#00ffff', fontSize: '0.65rem', letterSpacing: '4px', marginBottom: '1.5rem' }}>
        MATERIAL ANALYSIS & COST–STRENGTH TRADEOFF
      </div>

      {/* Cost Summary */}
      {Object.keys(cost_summary).length > 0 && (
        <div style={{
          display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)',
          gap: '0.75rem', marginBottom: '1.5rem',
        }}>
          {Object.entries(cost_summary).map(([key, val]) => (
            <div key={key} style={{
              background: 'rgba(0,255,255,0.04)',
              border: '1px solid rgba(0,255,255,0.15)',
              padding: '0.75rem 1rem',
              borderRadius: '2px',
            }}>
              <div style={{ color: 'rgba(0,255,255,0.5)', fontSize: '0.6rem', letterSpacing: '2px', marginBottom: '0.3rem' }}>
                {key.replace(/_/g, ' ').toUpperCase()}
              </div>
              <div style={{ color: '#fff', fontSize: '0.9rem' }}>{val}</div>
            </div>
          ))}
        </div>
      )}

      {/* Structural Concerns */}
      {structural_concerns.length > 0 && (
        <div style={{ marginBottom: '1.5rem' }}>
          {structural_concerns.map((concern, i) => (
            <div key={i} style={{
              background: 'rgba(255,60,60,0.07)',
              border: '1px solid rgba(255,60,60,0.3)',
              borderLeft: '3px solid #ff3c3c',
              padding: '0.6rem 1rem',
              marginBottom: '0.4rem',
              fontSize: '0.75rem',
              color: '#ff9090',
              letterSpacing: '0.5px',
            }}>
              ⚠ {typeof concern === 'string' ? concern : concern.message || JSON.stringify(concern)}
            </div>
          ))}
        </div>
      )}

      {/* Recommendations */}
      {recommendations.map((elem, idx) => (
        <div key={idx} style={{
          marginBottom: '1rem',
          border: '1px solid rgba(0,255,255,0.12)',
          borderRadius: '2px',
          overflow: 'hidden',
        }}>
          {/* Element header */}
          <div
            onClick={() => setExpandedElement(expandedElement === idx ? null : idx)}
            style={{
              background: 'rgba(0,255,255,0.05)',
              padding: '0.8rem 1rem',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              cursor: 'pointer',
              borderBottom: expandedElement === idx ? '1px solid rgba(0,255,255,0.12)' : 'none',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
              <div style={{
                width: '8px', height: '8px',
                background: elem.element_type?.includes('load') ? '#cd853f' : '#00ffff',
                borderRadius: '50%',
              }} />
              <span style={{ color: '#fff', fontSize: '0.8rem', letterSpacing: '1px' }}>
                {(elem.element_id || elem.element_type || `ELEMENT ${idx + 1}`).toString().toUpperCase()}
              </span>
              <span style={{
                color: 'rgba(0,255,255,0.4)', fontSize: '0.65rem', letterSpacing: '1px',
              }}>
                {elem.element_type?.toUpperCase()}
              </span>
            </div>
            <div style={{ color: '#00ffff', fontSize: '0.75rem' }}>
              {expandedElement === idx ? '▲' : '▼'}
            </div>
          </div>

          {/* Expanded material rows */}
          {expandedElement === idx && (
            <div>
              {/* Table header */}
              <div style={{
                display: 'grid',
                gridTemplateColumns: '40px 1fr 120px 120px 120px 80px',
                gap: '0.5rem',
                padding: '0.5rem 1rem',
                color: 'rgba(0,255,255,0.4)',
                fontSize: '0.6rem',
                letterSpacing: '2px',
                borderBottom: '1px solid rgba(0,255,255,0.08)',
              }}>
                <div>RANK</div>
                <div>MATERIAL</div>
                <div>STRENGTH</div>
                <div>DURABILITY</div>
                <div>COST</div>
                <div>SCORE</div>
              </div>

              {(elem.recommendations || []).map((mat, mIdx) => (
                <div key={mIdx} style={{
                  display: 'grid',
                  gridTemplateColumns: '40px 1fr 120px 120px 120px 80px',
                  gap: '0.5rem',
                  padding: '0.65rem 1rem',
                  alignItems: 'center',
                  borderBottom: mIdx < elem.recommendations.length - 1
                    ? '1px solid rgba(0,255,255,0.05)' : 'none',
                  background: mIdx === 0 ? 'rgba(0,255,255,0.03)' : 'transparent',
                }}>
                  <div>{rankBadge(mIdx + 1)}</div>
                  <div style={{ color: mIdx === 0 ? '#fff' : '#8ab0b8', fontSize: '0.78rem', letterSpacing: '0.5px' }}>
                    {mat.material || mat.name}
                  </div>
                  <div>{scoreBar(mat.strength_score ?? mat.strength ?? 0, '#cd853f')}</div>
                  <div>{scoreBar(mat.durability_score ?? mat.durability ?? 0, '#4a9aba')}</div>
                  <div>{scoreBar(mat.cost_score ?? mat.cost ?? 0, '#6aaa6a')}</div>
                  <div style={{
                    color: mIdx === 0 ? '#00ffff' : '#4a7a8a',
                    fontSize: '0.78rem',
                    fontWeight: mIdx === 0 ? 'bold' : 'normal',
                  }}>
                    {typeof mat.tradeoff_score === 'number'
                      ? mat.tradeoff_score.toFixed(3)
                      : mat.score?.toFixed(3) || '—'}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      ))}

      {recommendations.length === 0 && (
        <div style={{
          color: 'rgba(0,255,255,0.3)', textAlign: 'center',
          padding: '3rem', fontSize: '0.8rem', letterSpacing: '2px',
        }}>
          NO MATERIAL DATA AVAILABLE
        </div>
      )}
    </div>
  );
}
