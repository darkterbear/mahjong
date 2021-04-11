import { useState } from 'react'
import { useHistory, useLocation } from 'react-router'
import './JoinPage.scss'

export function JoinPage() {

  const [code, setCode] = useState('')
  const history = useHistory()
  const { username } = useLocation().state

  // Should have gotten here from main page with username set; otherwise, go back
  if (!username) {
    history.replace('/')
    return null
  }

  const joinRoom = () => {
    // TODO:
    console.log(`${username} join room ${code}`)
  }

  return <div id="page">
    <h1>Join a Room</h1>
    <input value={code} onChange={e => setCode(e.target.value)} placeholder="Room Code"/>
    <button onClick={joinRoom}>Join Room</button>
  </div>
}