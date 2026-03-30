import React from 'react';

export default function AnnotatedPlanPanel({ artifacts }) {
  const base64 = artifacts?.annotated_image_base64;
  const mime = artifacts?.annotated_image_mime || 'image/png';
  const doorCount = artifacts?.door_count ?? 0;
  const imageSrc = base64 ? `data:${mime};base64,${base64}` : null;

  return (
    <div style={{
      height: '100%',
      display: 'flex',
      flexDirection: 'column',
      background: '#030a14',
      fontFamily: "'Courier New', monospace",
      color: '#d6e6ef',
    }}>
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        padding: '1rem 1.4rem',
        borderBottom: '1px solid rgba(0,255,255,0.12)',
        background: 'rgba(0,255,255,0.03)',
      }}>
        <div>
          <div style={{ color: '#00ffff', fontSize: '0.65rem', letterSpacing: '3px', marginBottom: '0.25rem' }}>
            2D DOOR REVIEW
          </div>
          <div style={{ color: 'rgba(214,230,239,0.65)', fontSize: '0.72rem', letterSpacing: '1px' }}>
            Red boxes show the doors detected from the uploaded floor plan.
          </div>
        </div>
        <div style={{
          minWidth: '120px',
          textAlign: 'center',
          border: '1px solid rgba(255,70,70,0.3)',
          background: 'rgba(255,70,70,0.08)',
          padding: '0.6rem 0.8rem',
          borderRadius: '3px',
        }}>
          <div style={{ color: '#ff9090', fontSize: '0.58rem', letterSpacing: '2px', marginBottom: '0.2rem' }}>
            DOORS
          </div>
          <div style={{ color: '#fff', fontSize: '1.1rem', fontWeight: 'bold' }}>{doorCount}</div>
        </div>
      </div>

      <div style={{
        flex: 1,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '1.4rem',
      }}>
        {imageSrc ? (
          <img
            src={imageSrc}
            alt="Annotated floor plan with detected doors"
            style={{
              maxWidth: '100%',
              maxHeight: '100%',
              objectFit: 'contain',
              border: '1px solid rgba(0,255,255,0.12)',
              boxShadow: '0 24px 60px rgba(0,0,0,0.45)',
              background: '#ffffff',
            }}
          />
        ) : (
          <div style={{
            color: 'rgba(0,255,255,0.35)',
            fontSize: '0.8rem',
            letterSpacing: '2px',
            textAlign: 'center',
          }}>
            NO ANNOTATED IMAGE AVAILABLE
          </div>
        )}
      </div>
    </div>
  );
}
