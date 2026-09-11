import { NavLink } from 'react-router-dom'
import logo from '../assets/brands/logo_steelNort_2.png'
import inicioIcon from '../assets/icons/inicio_icon.png'
import dashboardIcon from '../assets/icons/dashboard_icon.png'
import reporteIcon from '../assets/icons/reporte_icon.png'
import alertaIcon from '../assets/icons/alerta_icon.png'
import configuracionIcon from '../assets/icons/configuracion_icon.png'
import '../css/Sidebar.css'

function ShieldIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
      <path d="M12 8v4" />
      <path d="M12 16h.01" />
    </svg>
  )
}

/*
 * Sidebar: Componente de navegación lateral.
 * Renderiza una lista de enlaces de navegación con iconos correspondientes.
 * Utiliza NavLink para manejar el estado activo/inactivo de cada sección.
 */
const items = [
  { to: '/inicio', label: 'Inicio', icon: inicioIcon },
  { to: '/dashboard', label: 'Dashboard', icon: dashboardIcon },
  { to: '/reportes', label: 'Reportes', icon: reporteIcon },
  { to: '/alertas', label: 'Alertas', icon: alertaIcon },
  { to: '/roles-permisos', label: 'Roles y Permisos', icon: 'shield' },
  { to: '/configuracion', label: 'Configuración', icon: configuracionIcon },
]

function Sidebar() {
  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <img className="sidebar-logo" src={logo} alt="Steel North" />
      </div>

      <nav className="sidebar-nav">
        {items.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              isActive ? 'sidebar-item active' : 'sidebar-item'
            }
          >
            {item.icon === 'shield' ? <ShieldIcon /> : <img src={item.icon} alt="" />}
            <span>{item.label}</span>
          </NavLink>
        ))}
      </nav>
    </aside>
  )
}

export default Sidebar

