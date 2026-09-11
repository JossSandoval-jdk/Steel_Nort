// Defincion de rutas de la aplicacion.
//
// Envuelve las rutas publicas y privadas. Las rutas marcadas como
// protegidas se muestran solo si existe una sesion autenticada; en caso
// contrario redirigen a /login. Escalable: para proteger nuevos modulos
// basta envolverlos en <RequireAuth>.
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Login from './pages/Login.jsx'
import Inicio from './pages/Inicio.jsx'
import Dashboard from './pages/Dashboard.jsx'
import Configuracion from './pages/Configuracion.jsx'
import RolesPermisos from './pages/RolesPermisos.jsx'
import Alertas from './pages/Alertas.jsx'
import { useAuth } from './context/AuthContext.jsx'

// Protege una ruta: si no hay sesion, redirige a /login.
function RequireAuth({ children }) {
  const { isAuthenticated } = useAuth()
  if (!isAuthenticated) {
    return <Navigate to="/" replace />
  }
  return children
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Pagina publica: login */}
        <Route path="/" element={<Login />} />

        {/* Rutas protegidas (requieren iniciar sesion) */}
        <Route
          path="/inicio"
          element={
            <RequireAuth>
              <Inicio />
            </RequireAuth>
          }
        />
        <Route
          path="/dashboard"
          element={
            <RequireAuth>
              <Dashboard />
            </RequireAuth>
          }
        />
        <Route
          path="/configuracion"
          element={
            <RequireAuth>
              <Configuracion />
            </RequireAuth>
          }
        />
        <Route
          path="/roles-permisos"
          element={
            <RequireAuth>
              <RolesPermisos />
            </RequireAuth>
          }
        />
        <Route
          path="/alertas"
          element={
            <RequireAuth>
              <Alertas />
            </RequireAuth>
          }
        />

        {/* Cualquier otra ruta cae al login o a inicio segun la sesion */}
        <Route
          path="*"
          element={
            <Navigate to="/" replace />
          }
        />
      </Routes>
    </BrowserRouter>
  )
}

export default App