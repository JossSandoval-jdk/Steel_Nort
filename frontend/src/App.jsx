// Rutas de la aplicacion.
//
// Hay dos filtros:
//   1. RequireAuth: si no hay sesion, al login.
//   2. RequirePermiso: si el rol no tiene el permiso de la pantalla, la
//      redirige a /inicio. El backend tambien lo comprueba en cada llamada;
//      esto es solo para que el usuario no aterrice en una pantalla vacia.
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Login from './pages/Login.jsx'
import Inicio from './pages/Inicio.jsx'
import Dashboard from './pages/Dashboard.jsx'
import Alertas from './pages/Alertas.jsx'
import Reportes from './pages/Reportes.jsx'
import Configuracion from './pages/Configuracion.jsx'
import { useAuth } from './context/AuthContext.jsx'

// Protege una ruta: si no hay sesion, al login.
function RequireAuth({ children }) {
  const { isAuthenticated } = useAuth()
  if (!isAuthenticated) {
    return <Navigate to="/" replace />
  }
  return children
}

// Protege una ruta por permiso: sin el permiso, a Inicio.
function RequirePermiso({ permiso, children }) {
  const { tiene } = useAuth()
  if (!tiene(permiso)) {
    return <Navigate to="/inicio" replace />
  }
  return children
}

// Atajo para no repetir el envoltura en cada ruta.
function Privada({ permiso, children }) {
  return (
    <RequireAuth>
      <RequirePermiso permiso={permiso}>{children}</RequirePermiso>
    </RequireAuth>
  )
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Pública: login */}
        <Route path="/" element={<Login />} />

        {/* Privadas: cada una con el permiso que la abre */}
        <Route path="/inicio" element={<Privada permiso="tablero:leer"><Inicio /></Privada>} />
        {/* El Dashboard lee /sistema/resumen y /sistema/resumen/heatmap,
            que exigen "tablero:leer". Con "datos:leer" la pagina abria pero
            todas sus llamadas devolvian 403. */}
        <Route path="/dashboard" element={<Privada permiso="tablero:leer"><Dashboard /></Privada>} />
        <Route path="/reportes" element={<Privada permiso="datos:leer"><Reportes /></Privada>} />
        <Route path="/alertas" element={<Privada permiso="deteccion:leer"><Alertas /></Privada>} />
        <Route
          path="/configuracion"
          element={<Privada permiso="sistema:leer"><Configuracion /></Privada>}
        />

        {/* Cualquier otra ruta va al login */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
