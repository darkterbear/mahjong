import { useState } from 'react'
import { useHistory, useLocation } from 'react-router'
import { joinRoom } from '../rest'
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

  const handleJoinRoom = async () => {
    const res = await joinRoom(username, code)
    if (res.ok) {
      const { players, leader } = await res.json()
      history.push('/lobby', { code, players, leader, username })
    }
  }

  return <div id="page">
    <h1>Join a Room</h1>
    <input value={code} onChange={e => setCode(e.target.value)} placeholder="Room Code"/>
    <button onClick={handleJoinRoom}>Join Room</button>
  </div>
}