import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Login from './pages/Login.jsx'
import Inicio from './pages/Inicio.jsx'
import Configuracion from './pages/Configuracion.jsx'
import Alertas from './pages/Alertas.jsx'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Login />} />
        <Route path="/inicio" element={<Inicio />} />
        <Route path="/configuracion" element={<Configuracion />} />
        <Route path="/alertas" element={<Alertas />} />
        <Route path="*" element={<Inicio />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
