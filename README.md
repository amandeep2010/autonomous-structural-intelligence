# 🪐 ReCraft-3D Dashboard

[![Deployed on Vercel](https://img.shields.io/badge/Deployed_on-Vercel-black?style=for-the-badge&logo=vercel)](https://recraft-3d.vercel.app/)
[![Deployed on Render](https://img.shields.io/badge/Backend-Render-46E3B7?style=for-the-badge&logo=render&logoColor=white)](#)
[![React](https://img.shields.io/badge/React-20232A?style=for-the-badge&logo=react&logoColor=61DAFB)](#)
[![Three.js](https://img.shields.io/badge/Three.js-black?style=for-the-badge&logo=three.js&logoColor=white)](#)
[![GSAP](https://img.shields.io/badge/GSAP-88CE02?style=for-the-badge&logo=greensock&logoColor=white)](#)

> An immersive, highly animated 3D web dashboard built for seamlessly visualizing and managing 3D components and real-time generation pipelines.

## 🚀 Overview

**ReCraft-3D Dashboard** is a high-performance web application designed to bring complex 3D rendering and model analysis straight into the browser. Featuring a rich, interactive workspace, this project leverages the power of WebGL and modern UI components to deliver a fluid, native-feeling experience while staying seamlessly synced with a live backend.

## ✨ Key Features

- **Automated 2D to 3D Generation:** Seamlessly translate flat designs and floor plans into fully explorable 3D models with material analysis.
- **Interactive 3D Workspace:** Hardware-accelerated rendering for fluid model manipulation, scaling, and viewing.
- **Real-Time Data Sync:** Robust handling of 3D object states, scene lighting, and configurations via live WebSocket connections.
- **Cinematic UI Animations:** Complex, seamless transitions across the dashboard powered by GSAP.
- **Sleek, Modern Interface:** Accessible, highly customizable UI components built with Tailwind CSS and `shadcn/ui`.

## 🛠️ Tech Stack

**Frontend:** Next.js / React, Three.js & React Three Fiber (R3F), GSAP, Tailwind CSS, shadcn/ui (Deployed on Vercel)  
**Backend:** Node.js, Express, WebSockets (ws/Socket.io) (Deployed on Render)

---

## ⚙️ Getting Started & Installation Dependencies

### Prerequisites
Make sure you have Node.js (v18+) and your preferred package manager installed.

### 1. Frontend Setup (Dashboard)

Navigate to the frontend directory and install the core UI and 3D dependencies:

```bash
# Clone the repository
git clone [https://github.com/your-username/recraft-3d.git](https://github.com/your-username/recraft-3d.git)
cd recraft-3d/frontend

# Install dependencies
npm install
```

**Key Frontend Dependencies Installed:**
* `three` & `@react-three/fiber` & `@react-three/drei` (3D rendering engine)
* `gsap` (Advanced UI animations)
* `tailwindcss`, `clsx`, `tailwind-merge` (Styling & shadcn utilities)
* `lucide-react` (Iconography)

**Frontend Environment Variables:**
Create a `.env.local` file in the `frontend` root:
```env
NEXT_PUBLIC_API_URL=[https://your-render-backend-url.onrender.com](https://your-render-backend-url.onrender.com)
NEXT_PUBLIC_WS_URL=wss://your-render-backend-url.onrender.com
```

**Run the Development Server:**
```bash
npm run dev
```
Open [http://localhost:3000](http://localhost:3000) to view the dashboard in your browser.

### 2. Backend Setup (Real-time Server)

Navigate to the backend directory and install the server-side dependencies:

```bash
cd ../backend

# Install dependencies
npm install
```

**Key Backend Dependencies Installed:**
* `express` (HTTP server)
* `ws` or `socket.io` (Real-time bi-directional WebSocket communication)
* `cors` (Cross-Origin Resource Sharing for Vercel integration)
* `dotenv` (Environment variable management)

**Backend Environment Variables:**
Create a `.env` file in the `backend` root:
```env
PORT=8080
ALLOWED_ORIGIN=[https://recraft-3d.vercel.app](https://recraft-3d.vercel.app)
```

**Run the Backend Server:**
```bash
npm run dev
```

---

## 📂 Project Structure

```text
📦 recraft-3d
 ┣ 📂 frontend
 ┃ ┣ 📂 components
 ┃ ┃ ┣ 📂 3d         # Three.js canvas, models, and lighting components
 ┃ ┃ ┣ 📂 ui         # Reusable shadcn/ui components
 ┃ ┃ ┗ 📂 layout     # Dashboard wrappers, sidebars, and navigation
 ┃ ┣ 📂 src/app      # Next.js routing and core pages
 ┃ ┣ 📂 public       # Static assets, textures, and 3D models (.gltf/.glb)
 ┃ ┗ 📜 package.json
 ┣ 📂 backend
 ┃ ┣ 📂 src
 ┃ ┃ ┣ 📜 server.js  # Express entry point
 ┃ ┃ ┣ 📜 socket.js  # WebSocket configuration and handlers
 ┃ ┃ ┗ 📂 routes     # API endpoints
 ┃ ┗ 📜 package.json
 ┗ 📜 README.md
```

## 🤝 Contributing

Contributions, issues, and feature requests are welcome! Feel free to check the issues page to report bugs or suggest enhancements.

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📄 License
Distributed under the MIT License. See `LICENSE` for more information.
