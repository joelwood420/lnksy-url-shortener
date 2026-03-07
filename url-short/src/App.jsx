import { useState, useRef, useEffect } from 'react'
import Hero from './components/Hero'
import MyUrls from './components/MyUrls'
import Create_User from './components/CreateUser'
import './App.css'

function App() {
  const [showMyUrls, setShowMyUrls] = useState(false)
  const [showLogin, setShowLogin] = useState(false)
  const [currentUser, setCurrentUser] = useState(null)
  const myUrlsRef = useRef(null)

  useEffect(() => {
    // Check if user is already logged in on page load
    fetch('/me', { credentials: 'include' })
      .then(res => res.json())
      .then(data => {
        if (data.email) {
          setCurrentUser(data.email)
        }
      })
      .catch(err => console.error('Session check failed:', err))
  }, [])

  useEffect(() => {
    if (showMyUrls && myUrlsRef.current) {
      if (window.innerWidth < 768) {
        setTimeout(() => {
          myUrlsRef.current.scrollIntoView({ 
            behavior: 'smooth',
            block: 'start'
          })
        }, 100) 
      }
    }
  }, [showMyUrls])

  const handleLoginSuccess = (email) => {
    setCurrentUser(email)
    setShowLogin(false)
    if (showMyUrls) {
      setShowMyUrls(false)
      setTimeout(() => setShowMyUrls(true), 100)
    }
  }

  const handleLogout = async () => {
    try {
      await fetch('/logout', {
        method: 'POST',
        credentials: 'include'
      })
      setCurrentUser(null)
      setShowMyUrls(false)
    } catch (error) {
      console.error('Logout error:', error)
    }
  }

  return (
    <div className="App">
      <Hero 
        onViewMyLinks={() => setShowMyUrls(!showMyUrls)} 
        showMyUrls={showMyUrls}
        onShowLogin={() => setShowLogin(true)}
        currentUser={currentUser}
        onLogout={handleLogout}
      />
      {showMyUrls && <div ref={myUrlsRef}><MyUrls /></div>}
      {showLogin && (
        <Create_User 
          onClose={() => setShowLogin(false)}
          onLoginSuccess={handleLoginSuccess}
        />
      )}
    </div>
  )
}

export default App
