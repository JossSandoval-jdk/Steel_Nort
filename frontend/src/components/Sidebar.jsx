import { NavLink } from 'react-router-dom'
import logo from '../assets/brands/logo_steelNort_2.png'
import inicioIcon from '../assets/icons/inicio_icon.png'
import dashboardIcon from '../assets/icons/dashboard_icon.png'
import reporteIcon from '../assets/icons/reporte_icon.png'
import alertaIcon from '../assets/icons/alerta_icon.png'
import configuracionIcon from '../assets/icons/configuracion_icon.png'
import { useAuth } from '../context/AuthContext.jsx'
import '../css/Sidebar.css'

/*
 * Sidebar: menú lateral.
 *
 * Cada entrada declara el permiso que la abre ("modulo:accion"), el mismo
 * que exige el backend. Si el usuario no lo tiene, la pantalla no aparece.
 * Ocultarla no es la seguridad: el backend vuelve a comprobar el permiso en
 * cada llamada. Esto solo evita que se ofrezcan pantallas que no van a
 * poder usarse.
 *
 *   Inicio        -> tablero:leer     (todos los roles)
 *   Dashboard     -> datos:leer
 *   Reportes      -> datos:leer
 *   Alertas       -> deteccion:leer
 *   Configuración -> sistema:leer      (Administrador y Gerente general)
 *
 * Usuarios y Roles se quitó del menú: se maneja desde la pantalla de
 * Configuración, con el botón "Gestionar roles y permisos".
 */
const ITEMS = [
  { to: '/inicio', label: 'Inicio', icon: inicioIcon, permiso: 'tablero:leer' },
  { to: '/dashboard', label: 'Dashboard', icon: dashboardIcon, permiso: 'datos:leer' },
  { to: '/reportes', label: 'Reportes', icon: reporteIcon, permiso: 'datos:leer' },
  { to: '/alertas', label: 'Alertas', icon: alertaIcon, permiso: 'deteccion:leer' },
  { to: '/configuracion', label: 'Configuración', icon: configuracionIcon, permiso: 'sistema:leer' },
]

function Sidebar() {
  const { tiene } = useAuth()
  const visibles = ITEMS.filter((item) => tiene(item.permiso))

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <img className="sidebar-logo" src={logo} alt="Steel North" />
      </div>

      <nav className="sidebar-nav">
        {visibles.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              isActive ? 'sidebar-item active' : 'sidebar-item'
            }
          >
            <img src={item.icon} alt="" />
            <span>{item.label}</span>
          </NavLink>
        ))}
      </nav>
    </aside>
  )
}

export default Sidebar
