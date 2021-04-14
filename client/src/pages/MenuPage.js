import { useState } from 'react'
import { useHistory } from 'react-router'
import { createRoom } from '../api'
import './MenuPage.scss'

export function MenuPage() {
  const [username, setUsername] = useState('')
  const history = useHistory()

  const handleJoinRoom = () => {
    if (!username) return
    history.push('/join', { username })
  }

  const handleCreateRoom = async () => {
    if (!username) return
    const res = await createRoom(username)
    if (res.ok) {
      const { code } = await res.json()
      history.replace('/lobby', { code, initialPlayers: [username], initialLeader: username, username })
    }
  }

  return <div id="menu-page">
    <h1>麻将</h1>
    <input value={username} onChange={e => setUsername(e.target.value)} placeholder="Username"/>
    <button onClick={handleCreateRoom}>Create Room</button>
    <button onClick={handleJoinRoom}>Join Room</button>
    <p id="attribution"><a href="https://commons.wikimedia.org/wiki/Category:SVG_Oblique_illustrations_of_Mahjong_tiles">Mahjong tiles</a> by <a href="https://commons.wikimedia.org/wiki/User:Cangjie6">Cangjie6</a> is licensed under CC BY-SA 4.0</p>
  </div>
}