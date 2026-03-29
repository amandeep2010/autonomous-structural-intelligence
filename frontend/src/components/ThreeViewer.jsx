import React, { useRef, useEffect, useState } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { Edges, Grid, OrbitControls, Text } from '@react-three/drei';
import * as THREE from 'three';

// Single wall mesh — brown for load-bearing, cyan wireframe for partition
function Wall({ wall }) {
  const { position, dimensions, load_bearing, rotation_y } = wall;
  const color = load_bearing ? '#8B4513' : '#00ffff';
  const opacity = load_bearing ? 0.18 : 0.08;

  return (
    <group position={[position.x, position.y, position.z]} rotation={[0, rotation_y || 0, 0]}>
      <mesh>
        <boxGeometry args={[dimensions.width, dimensions.height, dimensions.depth]} />
        <meshStandardMaterial
          color={color}
          transparent
          opacity={opacity}
          depthWrite={false}
          side={THREE.DoubleSide}
        />
        <Edges scale={1} threshold={15} color={load_bearing ? '#cd853f' : '#00ffff'} />
      </mesh>
    </group>
  );
}

// Floating room label
function RoomLabel({ room }) {
  return (
    <Text
      position={[room.centroid_3d.x, room.centroid_3d.y + 0.3, room.centroid_3d.z]}
      fontSize={0.22}
      color="#00ffff"
      anchorX="center"
      anchorY="middle"
      font={undefined}
      outlineWidth={0.01}
      outlineColor="#000"
      opacity={0.7}
    >
      {room.label}
    </Text>
  );
}

// Floor slab
function FloorSlab({ width, depth }) {
  return (
    <mesh position={[0, -0.02, 0]} rotation={[-Math.PI / 2, 0, 0]}>
      <planeGeometry args={[width, depth]} />
      <meshStandardMaterial color="#00ffff" transparent opacity={0.04} side={THREE.DoubleSide} />
    </mesh>
  );
}

// Scene content
function Scene({ threeJsData }) {
  const { walls = [], rooms = [], floor_dimensions = {} } = threeJsData;
  const { width_m = 10, depth_m = 10 } = floor_dimensions;

  return (
    <>
      <color attach="background" args={['#030a14']} />
      <ambientLight intensity={0.5} />
      <directionalLight position={[10, 15, 10]} intensity={1.5} color="#ccffff" />
      <pointLight position={[0, 8, 0]} intensity={0.4} color="#00ffff" />

      {walls.map((wall) => <Wall key={wall.id} wall={wall} />)}
      {rooms.map((room) => <RoomLabel key={room.id} room={room} />)}

      <FloorSlab width={width_m} depth={depth_m} />

      <Grid
        position={[0, -0.05, 0]}
        args={[40, 40]}
        sectionColor="#00ffff"
        cellColor="#004444"
        sectionThickness={1.2}
        cellThickness={0.4}
        fadeDistance={30}
      />

      <OrbitControls
        enablePan={true}
        enableZoom={true}
        enableRotate={true}
        minDistance={3}
        maxDistance={40}
      />
    </>
  );
}

export default function ThreeViewer({ threeJsData }) {
  const loadBearingCount = threeJsData?.walls?.filter(w => w.load_bearing).length || 0;
  const partitionCount = threeJsData?.walls?.filter(w => !w.load_bearing).length || 0;

  return (
    <div style={{ width: '100%', height: '100%', position: 'relative' }}>
      <Canvas
        camera={{ position: [12, 8, 12], fov: 45 }}
        style={{ width: '100%', height: '100%' }}
      >
        <Scene threeJsData={threeJsData} />
      </Canvas>

      {/* Legend overlay */}
      <div style={{
        position: 'absolute', bottom: '20px', left: '20px',
        background: 'rgba(3,10,20,0.85)',
        border: '1px solid rgba(0,255,255,0.2)',
        borderLeft: '3px solid #00ffff',
        padding: '1rem 1.2rem',
        backdropFilter: 'blur(10px)',
        fontFamily: "'Courier New', monospace",
      }}>
        <div style={{ color: '#00ffff', fontSize: '0.65rem', letterSpacing: '3px', marginBottom: '0.75rem' }}>
          WALL LEGEND
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            <div style={{ width: '24px', height: '10px', background: '#cd853f', borderRadius: '1px' }} />
            <span style={{ color: '#e0d0c0', fontSize: '0.7rem', letterSpacing: '1px' }}>
              LOAD-BEARING ({loadBearingCount})
            </span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            <div style={{ width: '24px', height: '10px', background: '#00ffff', borderRadius: '1px', opacity: 0.6 }} />
            <span style={{ color: '#b0d4d4', fontSize: '0.7rem', letterSpacing: '1px' }}>
              PARTITION ({partitionCount})
            </span>
          </div>
        </div>
      </div>

      {/* Controls hint */}
      <div style={{
        position: 'absolute', bottom: '20px', right: '20px',
        color: 'rgba(0,255,255,0.35)', fontSize: '0.65rem',
        fontFamily: "'Courier New', monospace", letterSpacing: '1.5px',
        textAlign: 'right', lineHeight: 1.8,
      }}>
        DRAG TO ROTATE<br />
        SCROLL TO ZOOM<br />
        RIGHT-DRAG TO PAN
      </div>
    </div>
  );
}
