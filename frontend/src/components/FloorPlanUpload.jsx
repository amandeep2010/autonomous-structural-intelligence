import React, { useState, useRef } from 'react';

export default function FloorPlanUpload({ onAnalysisComplete, onLoading }) {
  const [isDragging, setIsDragging] = useState(false);
  const [preview, setPreview] = useState(null);
  const [fileName, setFileName] = useState(null);
  const fileRef = useRef(null);

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
      const res = await fetch('http://localhost:8000/api/pipeline', {
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
