import Sidebar from '../components/Sidebar.jsx'
import Topbar from '../components/Topbar.jsx'
import '../css/Layout.css'
import '../css/Configuracion.css'

const usuarios = [
  { id: 1, nombre: 'Carlos Mendoza', mail: 'cmendoza@steelnort.com', rol: 'Administrador', iniciales: 'CM' },
  { id: 2, nombre: 'Ana Torres', mail: 'atorres@steelnort.com', rol: 'Operador', iniciales: 'AT' },
  { id: 3, nombre: 'Jorge Salazar', mail: 'jsalazar@steelnort.com', rol: 'Supervisor', iniciales: 'JS' },
  { id: 4, nombre: 'Lucía Fernández', mail: 'lfernandez@steelnort.com', rol: 'Operador', iniciales: 'LF' },
]

const logsInfo = [
  { label: 'Host', value: 'logs.steelnort.local' },
]

function IconEye() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  )
}

function IconTrash() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="3 6 5 6 21 6" />
      <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
      <line x1="10" y1="11" x2="10" y2="17" />
      <line x1="14" y1="11" x2="14" y2="17" />
    </svg>
  )
}

function IconPlus() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="12" y1="5" x2="12" y2="19" />
      <line x1="5" y1="12" x2="19" y2="12" />
    </svg>
  )
}

function IconShield() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    </svg>
  )
}

function IconRefresh() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="23 4 23 10 17 10" />
      <polyline points="1 20 1 14 7 14" />
      <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
    </svg>
  )
}

function InfoRow({ label, value }) {
  return (
    <li className="info-item">
      <span className="info-label">{label}</span>
      <span className="info-value">{value}</span>
    </li>
  )
}

function Configuracion() {
  return (
    <div className="layout">
      <Sidebar />
      <div className="layout-main">
        <Topbar nombre="Nombre Usuario" cargo="Cargo" />
        <main className="layout-content">
          <div className="config">
            <section className="config-col">
              <article className="card">
                <div className="card-head">
                  <h3 className="card-title">Gestión de usuarios y roles</h3>
                  <span className="card-subtitle">{usuarios.length} usuarios registrados</span>
                </div>

                <table className="users-table">
                  <thead>
                    <tr>
                      <th>Nombre</th>
                      <th>Rol</th>
                      <th style={{ textAlign: 'right' }}>Acciones</th>
                    </tr>
                  </thead>
                  <tbody>
                    {usuarios.map((u) => (
                      <tr key={u.id}>
                        <td>
                          <div className="user-cell">
                            <span className="user-avatar">{u.iniciales}</span>
                            <span className="user-name">
                              {u.nombre}
                              <span className="user-mail">{u.mail}</span>
                            </span>
                          </div>
                        </td>
                        <td>
                          <span className={`rol-pill ${u.rol.toLowerCase()}`}>{u.rol}</span>
                        </td>
                        <td>
                          <div className="row-actions">
                            <button type="button" className="icon-btn" title="Ver usuario">
                              <IconEye />
                            </button>
                            <button type="button" className="icon-btn danger" title="Eliminar usuario">
                              <IconTrash />
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>

                <div className="card-actions">
                  <button type="button" className="btn btn-primary">
                    <IconPlus />
                    Crear usuario
                  </button>
                  <button type="button" className="btn btn-outline">
                    <IconShield />
                    Administrar roles
                  </button>
                </div>
              </article>
            </section>

            <section className="config-col">
              <article className="card">
                <div className="card-head">
                  <div className="head-text">
                    <h3 className="card-title">SQL Server (OLTP)</h3>
                    <span className="card-subtitle">Conexión al servidor SQL</span>
                  </div>
                  <span className="conn-pill">
                    <span className="status-led online" />
                    Conectado
                  </span>
                </div>

                <div className="subhead">
                  <h4 className="subhead-title">Servidor de logs</h4>
                  <span className="conn-pill">
                    <span className="status-led online" />
                    En línea
                  </span>
                </div>

                <ul className="info-list">
                  {logsInfo.map((row) => (
                    <InfoRow key={row.label} {...row} />
                  ))}
                </ul>

                <div className="card-foot">
                  <button type="button" className="btn btn-outline">
                    <IconRefresh />
                    Probar conexión
                  </button>
                </div>
              </article>

              <article className="card">
                <div className="card-head">
                  <h3 className="card-title">Modelo de aprendizaje</h3>
                </div>

                <ul className="info-list">
                  <li className="info-item">
                    <div className="field-stack">
                      <span className="info-label">Modelo de entrenamiento: Isolation Forest</span>
                      <div className="input-group">
                        <input className="text-input" aria-label="Modelo de entrenamiento" />
                        <button type="button" className="btn btn-primary btn-sm">
                          <IconRefresh />
                          Reentrenar modelo
                        </button>
                      </div>
                    </div>
                  </li>
                  <li className="info-item">
                    <span className="info-label">Umbral de anomalía</span>
                    <div className="suffix-input">
                      <input className="text-input sm" defaultValue="85" aria-label="Umbral de anomalía" />
                      <span>%</span>
                    </div>
                  </li>
                  <li className="info-item">
                    <span className="info-label">Variables de entrenamiento</span>
                    <button type="button" className="icon-btn" title="Ver variables">
                      <IconEye />
                    </button>
                  </li>
                </ul>
              </article>
            </section>
          </div>
        </main>
      </div>
    </div>
  )
}

export default Configuracion
