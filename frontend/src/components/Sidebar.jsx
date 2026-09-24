import { NavLink } from 'react-router-dom'
import logo from '../assets/brands/logo_steelNort_2.png'
import inicioIcon from '../assets/icons/inicio_icon.png'
import dashboardIcon from '../assets/icons/dashboard_icon.png'
import reporteIcon from '../assets/icons/reporte_icon.png'
import alertaIcon from '../assets/icons/alerta_icon.png'
import configuracionIcon from '../assets/icons/configuracion_icon.png'
import '../css/Sidebar.css'

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
            <img src={item.icon} alt="" />
            <span>{item.label}</span>
          </NavLink>
        ))}
      </nav>
    </aside>
  )
}

export default Sidebar

