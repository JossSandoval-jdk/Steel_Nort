// src/components/AnomaliasTable.jsx
import { useEffect, useState } from 'react'
import api from '../services/api'
import { useAuth } from '../context/AuthContext.jsx';
// import IconRefresh from '../components/IconRefresh.jsx' // optional icon component

function AnomaliasTable() {
  const { accessToken } = useAuth()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    async function fetchAnomalias() {
      try {
        const result = await api.get('/anomalias/diagnostico', { token: accessToken })
        setData(result)
      } catch (err) {
        setError(err.message || 'Error al cargar anomalías')
      } finally {
        setLoading(false)
      }
    }
    fetchAnomalias()
  }, [])

  if (loading) return <p>Cargando anomalías...</p>
  if (error) return <p className="error">{error}</p>
  if (!data || !data.por_fault || Object.keys(data.por_fault).length === 0) {
    return (
      <section className="card">
        <div className="card-head">
          <h3 className="card-title">Anomalías detectadas</h3>
        </div>
        <div className="card-body" style={{ padding: '1rem' }}>
          <p>0 ms – sin consultas</p>
        </div>
      </section>
    );
  }

  const rows = Object.entries(data.por_fault).map(([fault, info]) => {
    const timestamp = info.ventana || ''
    const tipo = fault
    const severidad = info.deteccion?.tpr ? 'alta' : 'baja' // simple heuristic
    const diagnostico = info.reglas?.diagnostico || 'sin diagnóstico'
    return (
      <tr key={fault}>
        <td>{timestamp}</td>
        <td>{tipo}</td>
        <td>{severidad}</td>
        <td>{diagnostico}</td>
        <td>
          {/* Placeholder for actions, could be view details */}
          <button className="btn btn-sm btn-outline" title="Ver detalle">
            Ver
          </button>
        </td>
      </tr>
    )
  })

  return (
    <section className="card">
      <div className="card-head">
        <h3 className="card-title">Anomalías detectadas</h3>
      </div>
      <div className="card-body table-wrapper" style={{ maxHeight: '400px', overflowY: 'auto' }}>
        <table className="alerts-table">
          <thead>
            <tr>
              <th>Marca de tiempo</th>
              <th>Tipo de anomalía</th>
              <th>Severidad</th>
              <th>Diagnóstico / Causa</th>
              <th>Acciones</th>
            </tr>
          </thead>
          <tbody>{rows}</tbody>
        </table>
      </div>
    </section>
  )
}

export default AnomaliasTable

