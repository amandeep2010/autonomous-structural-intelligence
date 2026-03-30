import React, { useRef, useEffect, useState } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { Edges, Grid, OrbitControls } from '@react-three/drei';
import * as THREE from 'three';

import FloorPlanUpload from './components/FloorPlanUpload.jsx';
import AnnotatedPlanPanel from './components/AnnotatedPlanPanel.jsx';
import ThreeViewer from './components/ThreeViewer.jsx';
import MaterialTable from './components/MaterialTable.jsx';
import ExplainPanel from './components/ExplainPanel.jsx';
import { logAnalysisOnChain } from './stellar/integration.js';

// ─────────────────────────────────────────────
// TEAMMATE'S LANDING — scroll-driven blueprint tour
// ─────────────────────────────────────────────
const cameraViews = [
  { title: "Structural Intelligence", desc: "Upload a floor plan — our AI pipeline parses walls, reconstructs geometry in 3D, and recommends optimal construction materials.", position: new THREE.Vector3(0, 2.4, 12), target: new THREE.Vector3(0, 1.2, 0) },
  { title: "Wall Detection", desc: "OpenCV Canny edge detection and HoughLinesP identify every wall segment, junction, and opening in your floor plan image.", position: new THREE.Vector3(2.2, 1.7, 3.4), target: new THREE.Vector3(1.2, 1.2, -1.6) },
  { title: "3D Reconstruction", desc: "Shapely geometry reconstruction classifies load-bearing vs partition walls. Each wall extruded to 3m height with correct positioning.", position: new THREE.Vector3(-2.1, 1.8, 2.4), target: new THREE.Vector3(-1.3, 1.25, -1.8) },
  { title: "Material Optimisation", desc: "Weighted tradeoff scoring selects optimal materials — strength 60%, durability 30%, cost 10% for load-bearing. Reversed for partitions.", position: new THREE.Vector3(-1.4, 5.2, -3.4), target: new THREE.Vector3(-0.5, 4.3, -0.8) },
  { title: "LLM Explainability", desc: "Every material recommendation explained in plain English with span measurements, structural concerns flagged, and cost breakdown.", position: new THREE.Vector3(2.1, 5.6, -2.8), target: new THREE.Vector3(1.0, 4.6, -1.4) },
  { title: "Blockchain Verified", desc: "Analysis hash logged on Stellar Soroban testnet. Every structural report is immutably recorded with a certificate of authenticity.", position: new THREE.Vector3(8, 7.5, -8), target: new THREE.Vector3(0, 3.3, 0) },
];

const CameraController = ({ scrollProgressRef, paused }) => {
  const { camera } = useThree();
  const currentLookAt = useRef(new THREE.Vector3(0, 1.5, 0));
  useFrame((state, delta) => {
    if (paused) {
      return;
    }
    const rawProgress = scrollProgressRef.current * 5;
    const startIndex = Math.min(Math.floor(rawProgress), 4);
    const endIndex = Math.min(startIndex + 1, 5);
    const localT = (startIndex === 4 && rawProgress >= 5) ? 1 : rawProgress - startIndex;
    const targetPos = new THREE.Vector3().lerpVectors(cameraViews[startIndex].position, cameraViews[endIndex].position, localT);
    const targetLookAt = new THREE.Vector3().lerpVectors(cameraViews[startIndex].target, cameraViews[endIndex].target, localT);
    camera.position.lerp(targetPos, delta * 4);
    currentLookAt.current.lerp(targetLookAt, delta * 4);
    camera.lookAt(currentLookAt.current);
  });
  return null;
};

const blueprintMat = new THREE.MeshStandardMaterial({
  color: '#00ffff', transparent: true, opacity: 0.1, depthWrite: false, side: THREE.DoubleSide,
});
const BlueprintEdges = () => <Edges scale={1} threshold={15} color="#00ffff" />;

const BlueprintHouse = () => (
  <group position={[0, -0.5, 0]}>
    <mesh position={[0, 1.5, 0]} material={blueprintMat}><boxGeometry args={[6, 3, 6]} /><BlueprintEdges /></mesh>
    <mesh position={[0, 4.5, 0]} material={blueprintMat}><boxGeometry args={[6, 3, 6]} /><BlueprintEdges /></mesh>
    <mesh position={[0, 3, 0]} material={blueprintMat}><boxGeometry args={[6.2, 0.12, 6.2]} /><BlueprintEdges /></mesh>
    <mesh position={[0, 6.05, 0]} material={blueprintMat}><boxGeometry args={[6.4, 0.14, 6.4]} /><BlueprintEdges /></mesh>

    <mesh position={[0, 1.5, 0]} material={blueprintMat}><boxGeometry args={[0.1, 3, 6]} /><BlueprintEdges /></mesh>
    <mesh position={[0, 4.5, 0]} material={blueprintMat}><boxGeometry args={[0.1, 3, 6]} /><BlueprintEdges /></mesh>
    <mesh position={[-1.5, 1.5, 0]} material={blueprintMat}><boxGeometry args={[3, 3, 0.1]} /><BlueprintEdges /></mesh>
    <mesh position={[1.5, 4.5, 0]} material={blueprintMat}><boxGeometry args={[3, 3, 0.1]} /><BlueprintEdges /></mesh>

    <mesh position={[1.5, 1, 3]} material={blueprintMat}><boxGeometry args={[1, 2, 0.1]} /><BlueprintEdges /></mesh>
    <mesh position={[-1.5, 1.5, 3]} material={blueprintMat}><boxGeometry args={[1.5, 1.2, 0.1]} /><BlueprintEdges /></mesh>
    <mesh position={[1.5, 4, 3]} material={blueprintMat}><boxGeometry args={[1, 2, 0.1]} /><BlueprintEdges /></mesh>
    <mesh position={[-1.5, 4.5, 3]} material={blueprintMat}><boxGeometry args={[1.5, 1.2, 0.1]} /><BlueprintEdges /></mesh>

    <mesh position={[-3.05, 3, 0]} material={blueprintMat}><boxGeometry args={[0.12, 6, 6]} /><BlueprintEdges /></mesh>
    <mesh position={[3.05, 3, 0]} material={blueprintMat}><boxGeometry args={[0.12, 6, 6]} /><BlueprintEdges /></mesh>
    <mesh position={[0, 3, -3.05]} material={blueprintMat}><boxGeometry args={[6, 6, 0.12]} /><BlueprintEdges /></mesh>
    <mesh position={[0, 3, 3.05]} material={blueprintMat}><boxGeometry args={[6, 6, 0.12]} /><BlueprintEdges /></mesh>

    {[-3, 0, 3].map((x, i) => [-3, 0, 3].map((z, j) => (
      <mesh key={`p-${i}-${j}`} position={[x, 1.5, z]} material={blueprintMat}>
        <cylinderGeometry args={[0.1, 0.1, 3, 8]} /><BlueprintEdges />
      </mesh>
    )))}
    {[-3, 0, 3].map((x, i) => [-3, 0, 3].map((z, j) => (
      <mesh key={`p-upper-${i}-${j}`} position={[x, 4.5, z]} material={blueprintMat}>
        <cylinderGeometry args={[0.1, 0.1, 3, 8]} /><BlueprintEdges />
      </mesh>
    )))}
    <Grid position={[0, 0, 0]} args={[20, 20]} sectionColor="#00ffff" cellColor="#004444" sectionThickness={1.5} cellThickness={0.5} fadeDistance={25} />
  </group>
);

function LandingPage({ onEnter }) {
  const [activeIndex, setActiveIndex] = useState(0);
  const [manualCameraControl, setManualCameraControl] = useState(false);
  const scrollProgressRef = useRef(0);
  const lastScrollProgress = useRef(0);

  useEffect(() => {
    const handleScroll = () => {
      const maxScroll = document.documentElement.scrollHeight - window.innerHeight;
      const progress = maxScroll > 0 ? window.scrollY / maxScroll : 0;
      scrollProgressRef.current = Math.max(0, Math.min(1, progress));
      if (Math.abs(scrollProgressRef.current - lastScrollProgress.current) > 0.0005) {
        setManualCameraControl(false);
      }
      lastScrollProgress.current = scrollProgressRef.current;
      const newIndex = Math.min(Math.floor(scrollProgressRef.current * 5.99), 5);
      setActiveIndex(newIndex);
    };
    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  const activeView = cameraViews[activeIndex];
  const isLast = activeIndex === 5;

  return (
    <div style={{ position: 'relative', width: '100%', background: '#030a14' }}>
      <div style={{ height: '600vh' }} />
      <div style={{ position: 'fixed', top: 0, left: 0, width: '100vw', height: '100vh', zIndex: 2, pointerEvents: 'none' }}>
        <Canvas camera={{ position: cameraViews[0].position, fov: 45 }}>
          <color attach="background" args={['#030a14']} />
          <ambientLight intensity={0.4} />
          <directionalLight position={[10, 15, 10]} intensity={2} color="#ccffff" />
          <BlueprintHouse />
          <CameraController scrollProgressRef={scrollProgressRef} paused={manualCameraControl} />
          <OrbitControls
            enableRotate
            enablePan={false}
            enableZoom={false}
            enableDamping
            dampingFactor={0.08}
            rotateSpeed={0.75}
            mouseButtons={{
              LEFT: THREE.MOUSE.ROTATE,
              MIDDLE: THREE.MOUSE.DOLLY,
              RIGHT: THREE.MOUSE.PAN,
            }}
            onStart={() => setManualCameraControl(true)}
          />
        </Canvas>
      </div>

      <div style={{ position: 'fixed', top: 0, left: 0, width: '100vw', height: '100vh', zIndex: 3, display: 'flex', alignItems: 'center', justifyContent: 'flex-start', pointerEvents: 'none' }}>
        <div style={{
          background: 'rgba(3,10,20,0.88)', backdropFilter: 'blur(14px)',
          border: '1px solid rgba(0,255,255,0.25)', borderLeft: '4px solid #00ffff',
          padding: '2.5rem 3rem', marginLeft: '5vw', maxWidth: '420px',
          borderRadius: '4px', color: '#e0f2fe', boxShadow: '0 20px 60px rgba(0,0,0,0.7)',
          pointerEvents: 'auto', fontFamily: "'Courier New', monospace", transition: 'all 0.4s ease',
        }}>
          <div style={{ color: 'rgba(0,255,255,0.5)', fontSize: '0.6rem', letterSpacing: '4px', marginBottom: '0.5rem' }}>
            AUTONOMOUS STRUCTURAL INTELLIGENCE · PS 2 · AI/ML
          </div>
          <div style={{ color: '#00ffff', fontSize: '1.6rem', fontWeight: '300', letterSpacing: '1px', marginBottom: '0.5rem', lineHeight: 1.2 }}>
            {activeView.title}
          </div>
          <div style={{ width: '40px', height: '2px', background: '#00ffff', marginBottom: '1.2rem', opacity: 0.6 }} />
          <p style={{ color: '#bae6fd', fontSize: '0.85rem', lineHeight: 1.7, margin: 0, fontWeight: 300 }}>
            {activeView.desc}
          </p>
          <div style={{ display: 'flex', gap: '0.4rem', marginTop: '1.5rem' }}>
            {cameraViews.map((_, i) => (
              <div key={i} style={{
                width: i === activeIndex ? '20px' : '6px', height: '6px', borderRadius: '3px',
                background: i === activeIndex ? '#00ffff' : 'rgba(0,255,255,0.2)', transition: 'all 0.3s ease',
              }} />
            ))}
          </div>
          {isLast && (
            <button onClick={onEnter} style={{
              marginTop: '1.5rem', background: '#00ffff', color: '#030a14', border: 'none',
              padding: '0.75rem 2rem', fontSize: '0.75rem', letterSpacing: '3px',
              fontFamily: "'Courier New', monospace", fontWeight: 'bold', cursor: 'pointer',
              borderRadius: '2px', width: '100%',
            }}>
              UPLOAD FLOOR PLAN →
            </button>
          )}
        </div>
      </div>

      {activeIndex === 0 && (
        <div style={{
          position: 'fixed', bottom: '2rem', left: '50%', transform: 'translateX(-50%)',
          zIndex: 10, color: 'rgba(0,255,255,0.45)', fontSize: '0.65rem', letterSpacing: '3px',
          fontFamily: "'Courier New', monospace", display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '0.5rem',
        }}>
          <div>SCROLL TO EXPLORE</div>
          <div style={{ fontSize: '1rem' }}>↓</div>
        </div>
      )}

      <div style={{
        position: 'fixed',
        top: '2rem',
        right: '2rem',
        zIndex: 10,
        color: 'rgba(0,255,255,0.42)',
        fontSize: '0.62rem',
        letterSpacing: '2px',
        fontFamily: "'Courier New', monospace",
        textAlign: 'right',
        lineHeight: 1.8,
        pointerEvents: 'none',
      }}>
        LEFT-DRAG TO MOVE POV
        <br />
        SCROLL TO RESUME TOUR
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────
// LOADING SCREEN
// ─────────────────────────────────────────────
function LoadingScreen() {
  const stages = ['PARSING FLOOR PLAN', 'RECONSTRUCTING GEOMETRY', 'ANALYSING MATERIALS', 'GENERATING REPORT', 'LOGGING TO BLOCKCHAIN'];
  const [current, setCurrent] = useState(0);
  useEffect(() => {
    const iv = setInterval(() => setCurrent(p => Math.min(p + 1, stages.length - 1)), 1800);
    return () => clearInterval(iv);
  }, []);

  return (
    <div style={{ minHeight: '100vh', background: '#030a14', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', fontFamily: "'Courier New', monospace" }}>
      <div style={{ position: 'relative', width: '100px', height: '100px', marginBottom: '3rem' }}>
        {[0, 1, 2].map(i => (
          <div key={i} style={{
            position: 'absolute', inset: `${i * 14}px`,
            border: '1px solid rgba(0,255,255,0.35)', borderRadius: '2px',
            animation: `spin ${3 + i}s linear infinite ${i % 2 === 0 ? '' : 'reverse'}`,
          }} />
        ))}
        <div style={{ position: 'absolute', inset: '42px', background: '#00ffff', borderRadius: '50%', animation: 'blink 1.5s ease-in-out infinite' }} />
      </div>
      <div style={{ color: '#00ffff', fontSize: '0.65rem', letterSpacing: '4px', marginBottom: '1.2rem' }}>PIPELINE RUNNING</div>
      {stages.map((stage, i) => (
        <div key={stage} style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.5rem', opacity: i < current ? 0.4 : i === current ? 1 : 0.15, transition: 'opacity 0.5s' }}>
          <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: i < current ? '#4aaa4a' : i === current ? '#00ffff' : 'rgba(0,255,255,0.2)', transition: 'background 0.5s' }} />
          <span style={{ color: i < current ? '#4aaa4a' : i === current ? '#00ffff' : 'rgba(0,255,255,0.2)', fontSize: '0.72rem', letterSpacing: '2px' }}>
            {i < current ? `✓ ${stage}` : stage}
          </span>
        </div>
      ))}
      <style>{`@keyframes spin{to{transform:rotate(360deg)}} @keyframes blink{0%,100%{opacity:.8;transform:scale(1)}50%{opacity:.3;transform:scale(.5)}}`}</style>
    </div>
  );
}

// ─────────────────────────────────────────────
// RESULTS DASHBOARD
// ─────────────────────────────────────────────
function ResultsDashboard({ result, onReset }) {
  const [activePanel, setActivePanel] = useState('review');
  const [stellar, setStellar] = useState({ loading: true, txHash: null, explorerUrl: null });

  useEffect(() => {
    logAnalysisOnChain(result).then(res => setStellar({ loading: false, ...res }));
  }, [result]);

  const stats = [
    { label: 'WALLS', value: result?.geometry?.stats?.total_walls ?? result?.three_js?.walls?.length ?? '—' },
    { label: 'ROOMS', value: result?.geometry?.stats?.total_rooms ?? result?.three_js?.rooms?.length ?? '—' },
    { label: 'DOORS', value: result?.artifacts?.door_count ?? result?.three_js?.doors?.length ?? '—' },
    { label: 'LOAD-BEARING', value: result?.geometry?.stats?.load_bearing_walls ?? result?.three_js?.walls?.filter(w => w.load_bearing).length ?? '—' },
    { label: 'FALLBACK', value: result?.fallback_used ? 'YES' : 'NO' },
  ];

  return (
    <div style={{ height: '100vh', background: '#030a14', display: 'flex', flexDirection: 'column', fontFamily: "'Courier New', monospace", overflow: 'hidden' }}>
      {/* Top bar */}
      <div style={{ borderBottom: '1px solid rgba(0,255,255,0.15)', padding: '0 2rem', display: 'flex', alignItems: 'center', justifyContent: 'space-between', height: '52px', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <div style={{ color: '#00ffff', fontSize: '0.75rem', letterSpacing: '3px' }}>AXIS<span style={{ color: '#fff' }}>STRUCT</span></div>
          <div style={{ width: '1px', height: '16px', background: 'rgba(0,255,255,0.2)' }} />
          <div style={{ color: 'rgba(0,255,255,0.4)', fontSize: '0.6rem', letterSpacing: '2px' }}>ANALYSIS COMPLETE</div>
        </div>
        <div style={{ display: 'flex', gap: '2.5rem' }}>
          {stats.map(s => (
            <div key={s.label} style={{ textAlign: 'center' }}>
              <div style={{ color: '#00ffff', fontSize: '1rem', fontWeight: 'bold' }}>{s.value}</div>
              <div style={{ color: 'rgba(0,255,255,0.35)', fontSize: '0.55rem', letterSpacing: '1.5px' }}>{s.label}</div>
            </div>
          ))}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          {stellar.loading
            ? <div style={{ color: 'rgba(0,255,255,0.4)', fontSize: '0.62rem', letterSpacing: '1.5px' }}>◌ LOGGING TO CHAIN...</div>
            : stellar.txHash
              ? <a href={stellar.explorerUrl} target="_blank" rel="noreferrer" style={{ color: '#4aaa4a', fontSize: '0.62rem', letterSpacing: '1.5px', textDecoration: 'none' }}>✓ ON-CHAIN · {stellar.txHash.substring(0, 12)}...</a>
              : <div style={{ color: 'rgba(255,100,100,0.6)', fontSize: '0.62rem', letterSpacing: '1.5px' }}>⚠ CHAIN LOG FAILED</div>
          }
          <button onClick={onReset} style={{ background: 'none', border: '1px solid rgba(0,255,255,0.25)', color: 'rgba(0,255,255,0.6)', padding: '0.35rem 0.9rem', fontSize: '0.6rem', letterSpacing: '2px', cursor: 'pointer', fontFamily: "'Courier New', monospace", borderRadius: '2px' }}>
            NEW PLAN
          </button>
        </div>
      </div>

      {/* Stellar cert banner */}
      {!stellar.loading && stellar.txHash && (
        <div style={{ background: 'rgba(74,170,74,0.07)', borderBottom: '1px solid rgba(74,170,74,0.2)', padding: '0.45rem 2rem', display: 'flex', alignItems: 'center', gap: '1.5rem', fontSize: '0.6rem', letterSpacing: '1.5px', flexShrink: 0 }}>
          <span style={{ color: '#4aaa4a' }}>✓ STELLAR BLOCKCHAIN CERTIFICATE</span>
          <span style={{ color: 'rgba(74,170,74,0.5)' }}>TX: {stellar.txHash}</span>
          <span style={{ color: 'rgba(74,170,74,0.5)' }}>HASH: {stellar.analysisHash?.substring(0, 36)}...</span>
          <a href={stellar.explorerUrl} target="_blank" rel="noreferrer" style={{ color: '#4aaa4a', textDecoration: 'none', marginLeft: 'auto' }}>VIEW ON STELLAR EXPERT →</a>
        </div>
      )}

      {result?.fallback_used && (
        <div style={{ background: 'rgba(255,180,0,0.07)', borderBottom: '1px solid rgba(255,180,0,0.2)', padding: '0.4rem 2rem', color: 'rgba(255,200,0,0.7)', fontSize: '0.62rem', letterSpacing: '1.5px', flexShrink: 0 }}>
          ⚠ FALLBACK COORDINATES USED — CV parsing failed, manual wall coordinates applied. Disclosed per PS 2 rules.
        </div>
      )}

      {!!result?.verification?.issues?.length && (
        <div style={{ background: 'rgba(255,120,120,0.08)', borderBottom: '1px solid rgba(255,120,120,0.2)', padding: '0.45rem 2rem', display: 'flex', alignItems: 'center', gap: '1.25rem', fontSize: '0.6rem', letterSpacing: '1.4px', flexShrink: 0 }}>
          <span style={{ color: 'rgba(255,145,145,0.95)' }}>MODEL CHECK</span>
          <span style={{ color: 'rgba(255,200,200,0.75)' }}>{result.verification.summary}</span>
          <span style={{ color: 'rgba(255,180,180,0.55)' }}>
            MISSING WINDOW CANDIDATES: {result.verification.counts?.unmatched_window_candidates ?? 0}
          </span>
        </div>
      )}

      {/* Panel tabs */}
      <div style={{ borderBottom: '1px solid rgba(0,255,255,0.1)', padding: '0 2rem', display: 'flex', flexShrink: 0 }}>
        {[{ key: 'review', label: '2D REVIEW' }, { key: '3d', label: '3D MODEL' }, { key: 'materials', label: 'MATERIALS' }, { key: 'report', label: 'AI REPORT' }].map(p => (
          <button key={p.key} onClick={() => setActivePanel(p.key)} style={{
            background: 'none', border: 'none',
            borderBottom: activePanel === p.key ? '2px solid #00ffff' : '2px solid transparent',
            color: activePanel === p.key ? '#00ffff' : 'rgba(0,255,255,0.3)',
            padding: '0.7rem 1.5rem 0.6rem', fontSize: '0.65rem', letterSpacing: '2.5px',
            cursor: 'pointer', fontFamily: "'Courier New', monospace", transition: 'all 0.2s',
          }}>{p.label}</button>
        ))}
      </div>

      {/* Panel content */}
      <div style={{ flex: 1, overflow: 'hidden' }}>
        {activePanel === 'review' && <AnnotatedPlanPanel artifacts={result?.artifacts} />}
        {activePanel === '3d' && (
          result?.three_js
            ? <ThreeViewer threeJsData={result.three_js} />
            : <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'rgba(0,255,255,0.3)', fontSize: '0.8rem', letterSpacing: '2px' }}>NO 3D DATA</div>
        )}
        {activePanel === 'materials' && <div style={{ height: '100%', overflowY: 'auto' }}><MaterialTable materialsData={result?.materials} /></div>}
        {activePanel === 'report' && <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}><ExplainPanel reportData={result?.report} /></div>}
      </div>

      <style>{`
        *{box-sizing:border-box}
        ::-webkit-scrollbar{width:4px}
        ::-webkit-scrollbar-track{background:#030a14}
        ::-webkit-scrollbar-thumb{background:rgba(0,255,255,0.2);border-radius:2px}
      `}</style>
    </div>
  );
}

// ─────────────────────────────────────────────
// ROOT
// ─────────────────────────────────────────────
export default function App() {
  const [phase, setPhase] = useState('landing');
  const [result, setResult] = useState(null);

  if (phase === 'landing') return <LandingPage onEnter={() => { window.scrollTo(0,0); setPhase('upload'); }} />;
  if (phase === 'loading') return <LoadingScreen />;
  if (phase === 'results' && result) return <ResultsDashboard result={result} onReset={() => { setResult(null); setPhase('upload'); }} />;

  return (
    <FloorPlanUpload
      onAnalysisComplete={(data) => { setResult(data); setPhase('results'); }}
      onLoading={(v) => { if (v) setPhase('loading'); }}
    />
  );
}
