import React, { useEffect, useState, useRef } from 'react';

const API_BASE = 'http://localhost:8000';

function formatSavedAt(value) {
  if (!value) return 'Unknown time';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

export default function FloorPlanUpload({ onAnalysisComplete, onLoading }) {
  const [isDragging, setIsDragging] = useState(false);
  const [preview, setPreview] = useState(null);
  const [fileName, setFileName] = useState(null);
  const [history, setHistory] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [historyError, setHistoryError] = useState(null);
  const [activeHistoryId, setActiveHistoryId] = useState(null);
  const fileRef = useRef(null);

  useEffect(() => {
    loadHistory();
  }, []);

  const loadHistory = async () => {
    setHistoryLoading(true);
    setHistoryError(null);
    try {
      const res = await fetch(`${API_BASE}/api/history?limit=12`);
      const data = await res.json();
      setHistory(Array.isArray(data.items) ? data.items : []);
    } catch (err) {
      console.error('History load error:', err);
      setHistoryError('History unavailable');
    } finally {
      setHistoryLoading(false);
    }
  };

  const handleFile = async (file) => {
    if (!file || !file.type.startsWith('image/')) return;
    setPreview(URL.createObjectURL(file));
    setFileName(file.name);
    await runPipeline(file);
  };

  const runPipeline = async (file) => {
    onLoading(true);
    try {
      const form = new FormData();
      form.append('file', file);
      const res = await fetch(`${API_BASE}/api/pipeline`, {
        method: 'POST',
        body: form,
      });
      const data = await res.json();
      onAnalysisComplete(data);
    } catch (err) {
      console.error('Pipeline error:', err);
      alert('Backend error — make sure FastAPI is running on port 8000');
    } finally {
      onLoading(false);
    }
  };

  const openSavedResult = async (analysisId) => {
    onLoading(true);
    setActiveHistoryId(analysisId);
    try {
      const res = await fetch(`${API_BASE}/api/history/${analysisId}`);
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data?.detail || 'Could not load saved analysis');
      }
      onAnalysisComplete(data);
    } catch (err) {
      console.error('History open error:', err);
      alert('Could not load saved analysis from backend history');
    } finally {
      setActiveHistoryId(null);
      onLoading(false);
    }
  };

  const onDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files[0];
    handleFile(file);
  };

  return (
    <div style={{
      minHeight: '100vh',
      background: '#030a14',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      fontFamily: "'Courier New', monospace",
    }}>
      {/* Header */}
      <div style={{ textAlign: 'center', marginBottom: '3rem' }}>
        <div style={{ color: '#00ffff', fontSize: '0.75rem', letterSpacing: '6px', marginBottom: '1rem', opacity: 0.7 }}>
          AUTONOMOUS STRUCTURAL INTELLIGENCE
        </div>
        <h1 style={{
          color: '#fff',
          fontSize: '2.8rem',
          fontWeight: '300',
          margin: 0,
          letterSpacing: '2px',
          lineHeight: 1.2,
        }}>
          FLOOR PLAN <span style={{ color: '#00ffff' }}>ANALYSER</span>
        </h1>
        <div style={{ color: '#4a9aba', fontSize: '0.85rem', marginTop: '1rem', letterSpacing: '2px' }}>
          UPLOAD → PARSE → RECONSTRUCT → OPTIMISE
        </div>
      </div>

      {/* Drop Zone */}
      <div
        onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={onDrop}
        onClick={() => fileRef.current.click()}
        style={{
          width: '520px',
          height: '320px',
          border: `2px dashed ${isDragging ? '#00ffff' : 'rgba(0,255,255,0.3)'}`,
          borderRadius: '4px',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          cursor: 'pointer',
          background: isDragging ? 'rgba(0,255,255,0.05)' : 'rgba(0,255,255,0.02)',
          transition: 'all 0.3s ease',
          position: 'relative',
          overflow: 'hidden',
        }}
      >
        {/* Corner accents */}
        {['topLeft','topRight','bottomLeft','bottomRight'].map((pos) => (
          <div key={pos} style={{
            position: 'absolute',
            width: '20px', height: '20px',
            top: pos.includes('top') ? '12px' : 'auto',
            bottom: pos.includes('bottom') ? '12px' : 'auto',
            left: pos.includes('Left') ? '12px' : 'auto',
            right: pos.includes('Right') ? '12px' : 'auto',
            borderTop: pos.includes('top') ? '2px solid #00ffff' : 'none',
            borderBottom: pos.includes('bottom') ? '2px solid #00ffff' : 'none',
            borderLeft: pos.includes('Left') ? '2px solid #00ffff' : 'none',
            borderRight: pos.includes('Right') ? '2px solid #00ffff' : 'none',
          }} />
        ))}

        {preview ? (
          <img src={preview} alt="preview" style={{
            maxWidth: '90%', maxHeight: '85%', objectFit: 'contain',
            opacity: 0.85, borderRadius: '2px',
          }} />
        ) : (
          <>
            {/* Blueprint icon */}
            <svg width="64" height="64" viewBox="0 0 64 64" fill="none" style={{ marginBottom: '1.5rem', opacity: 0.6 }}>
              <rect x="8" y="8" width="48" height="48" stroke="#00ffff" strokeWidth="1.5" fill="none"/>
              <line x1="8" y1="24" x2="56" y2="24" stroke="#00ffff" strokeWidth="0.75" opacity="0.5"/>
              <line x1="8" y1="40" x2="56" y2="40" stroke="#00ffff" strokeWidth="0.75" opacity="0.5"/>
              <line x1="24" y1="8" x2="24" y2="56" stroke="#00ffff" strokeWidth="0.75" opacity="0.5"/>
              <line x1="40" y1="8" x2="40" y2="56" stroke="#00ffff" strokeWidth="0.75" opacity="0.5"/>
              <rect x="18" y="28" width="12" height="10" stroke="#00ffff" strokeWidth="1.5" fill="none"/>
              <rect x="34" y="18" width="14" height="12" stroke="#00ffff" strokeWidth="1.5" fill="none"/>
            </svg>
            <div style={{ color: '#00ffff', fontSize: '1rem', letterSpacing: '3px', marginBottom: '0.5rem' }}>
              DROP FLOOR PLAN
            </div>
            <div style={{ color: 'rgba(0,255,255,0.4)', fontSize: '0.75rem', letterSpacing: '2px' }}>
              OR CLICK TO BROWSE
            </div>
            <div style={{ color: 'rgba(255,255,255,0.2)', fontSize: '0.7rem', marginTop: '1.5rem', letterSpacing: '1px' }}>
              PNG · JPG · JPEG ACCEPTED
            </div>
          </>
        )}
        <input
          ref={fileRef}
          type="file"
          accept="image/*"
          style={{ display: 'none' }}
          onChange={(e) => handleFile(e.target.files[0])}
        />
      </div>

      {fileName && (
        <div style={{
          marginTop: '1.5rem',
          color: 'rgba(0,255,255,0.6)',
          fontSize: '0.75rem',
          letterSpacing: '2px',
        }}>
          ▸ {fileName}
        </div>
      )}

      <div style={{
        width: 'min(1120px, 92vw)',
        marginTop: '3rem',
        display: 'grid',
        gridTemplateColumns: 'minmax(0, 1fr)',
        gap: '1rem',
      }}>
        <div style={{
          border: '1px solid rgba(0,255,255,0.16)',
          background: 'rgba(0,255,255,0.03)',
          padding: '1.2rem 1.25rem',
          borderRadius: '4px',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.9rem', gap: '1rem' }}>
            <div>
              <div style={{ color: '#00ffff', fontSize: '0.68rem', letterSpacing: '3px', marginBottom: '0.35rem' }}>
                SAVED RESULT HISTORY
              </div>
              <div style={{ color: 'rgba(255,255,255,0.38)', fontSize: '0.72rem', letterSpacing: '1px' }}>
                Reopen analyses already stored under the backend uploads directory.
              </div>
            </div>
            <button
              onClick={loadHistory}
              style={{
                background: 'none',
                border: '1px solid rgba(0,255,255,0.22)',
                color: 'rgba(0,255,255,0.72)',
                padding: '0.45rem 0.75rem',
                fontSize: '0.6rem',
                letterSpacing: '2px',
                cursor: 'pointer',
                fontFamily: "'Courier New', monospace",
              }}
            >
              REFRESH
            </button>
          </div>

          {historyLoading && (
            <div style={{ color: 'rgba(0,255,255,0.45)', fontSize: '0.72rem', letterSpacing: '1.5px', padding: '0.5rem 0' }}>
              LOADING SAVED ANALYSES...
            </div>
          )}

          {!historyLoading && historyError && (
            <div style={{ color: 'rgba(255,140,140,0.8)', fontSize: '0.72rem', letterSpacing: '1.2px', padding: '0.5rem 0' }}>
              {historyError}
            </div>
          )}

          {!historyLoading && !historyError && history.length === 0 && (
            <div style={{ color: 'rgba(255,255,255,0.32)', fontSize: '0.72rem', letterSpacing: '1.2px', padding: '0.5rem 0' }}>
              No saved analyses found yet.
            </div>
          )}

          {!historyLoading && !historyError && history.length > 0 && (
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
              gap: '0.85rem',
            }}>
              {history.map((item) => (
                <button
                  key={item.analysis_id}
                  onClick={() => openSavedResult(item.analysis_id)}
                  style={{
                    textAlign: 'left',
                    border: '1px solid rgba(0,255,255,0.14)',
                    background: activeHistoryId === item.analysis_id ? 'rgba(0,255,255,0.08)' : 'rgba(255,255,255,0.015)',
                    padding: '0.95rem',
                    color: '#dff8ff',
                    cursor: 'pointer',
                    fontFamily: "'Courier New', monospace",
                    borderRadius: '4px',
                    transition: 'all 0.2s ease',
                  }}
                >
                  <div style={{ color: '#00ffff', fontSize: '0.62rem', letterSpacing: '2px', marginBottom: '0.4rem' }}>
                    {item.original_filename || 'Saved analysis'}
                  </div>
                  <div style={{ color: 'rgba(255,255,255,0.38)', fontSize: '0.66rem', lineHeight: 1.7 }}>
                    {formatSavedAt(item.saved_at)}
                  </div>
                  <div style={{ color: 'rgba(255,255,255,0.6)', fontSize: '0.66rem', lineHeight: 1.8, marginTop: '0.55rem' }}>
                    WALLS {item.wall_count} · ROOMS {item.room_count} · WINDOWS {item.window_count}
                  </div>
                  <div style={{ color: item.fallback_used ? '#ffc857' : 'rgba(0,255,255,0.55)', fontSize: '0.62rem', letterSpacing: '1.2px', marginTop: '0.55rem' }}>
                    {item.fallback_used ? 'FALLBACK USED' : 'CV PARSE'}
                    {' · '}
                    ISSUES {item.issue_count}
                  </div>
                  <div style={{ color: 'rgba(0,255,255,0.4)', fontSize: '0.58rem', letterSpacing: '1px', marginTop: '0.7rem' }}>
                    {activeHistoryId === item.analysis_id ? 'OPENING...' : item.analysis_id}
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Info row */}
      <div style={{
        display: 'flex', gap: '3rem', marginTop: '3rem',
        color: 'rgba(255,255,255,0.25)', fontSize: '0.7rem', letterSpacing: '2px',
      }}>
        {['WALL DETECTION', '3D RECONSTRUCTION', 'MATERIAL AI', 'BLOCKCHAIN LOG'].map(label => (
          <div key={label} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <div style={{ width: '6px', height: '6px', background: '#00ffff', opacity: 0.4 }} />
            {label}
          </div>
        ))}
      </div>
    </div>
  );
}
