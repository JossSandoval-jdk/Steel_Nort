import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import logo from '../assets/brands/logo_steelNorth.png'
import facebookIcon from '../assets/icons/facebook_icon.png'
import instagramIcon from '../assets/icons/instagram_icon.png'
import whatsappIcon from '../assets/icons/whatsapp_icon.png'
import '../css/Login.css'

function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [remember, setRemember] = useState(false)
  const navigate = useNavigate()

  return (
    <main className="login">
      <div className="login-card">
        <img className="login-logo" src={logo} alt="Steel North" />

        <div className="login-form">
          <div className="login-field">
            <label htmlFor="email">Correo electrónico</label>
            <input
              id="email"
              type="email"
              placeholder="correo@ejemplo.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>

          <div className="login-field">
            <label htmlFor="password">Contraseña</label>
            <input
              id="password"
              type="password"
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>

          <label className="login-remember">
            <input
              type="checkbox"
              checked={remember}
              onChange={(e) => setRemember(e.target.checked)}
            />
            Recordar contraseña
          </label>

          <button
            type="button"
            className="login-button"
            onClick={() => navigate('/inicio')}
          >
            INICIAR SESIÓN
          </button>
        </div>

        <div className="login-links">
          <a href="#recuperar">¿Olvidaste tu contraseña?</a>
          <span>|</span>
          <a href="#registro">Crear cuenta</a>
        </div>

        <div className="login-social">
          <a href="#facebook" aria-label="Facebook">
            <img src={facebookIcon} alt="" />
          </a>
          <a href="#instagram" aria-label="Instagram">
            <img src={instagramIcon} alt="" />
          </a>
          <a href="#whatsapp" aria-label="WhatsApp">
            <img src={whatsappIcon} alt="" />
          </a>
        </div>
      </div>
    </main>
  )
}

export default Login
