import { useState } from 'react'
import { useHistory } from 'react-router'
import './MenuPage.scss'

export function MenuPage() {
  const [username, setUsername] = useState('')
  const history = useHistory()

  const joinRoom = () => {
    history.push('/join', { username })
  }

  const createRoom = () => {
    // TODO:
  }

  return <div id="page">
    <h1>麻将</h1>
    <input value={username} onChange={e => setUsername(e.target.value)} placeholder="Username"/>
    <button onClick={createRoom}>Create Room</button>
    <button onClick={joinRoom}>Join Room</button>
    <p id="attribution"><a href="https://commons.wikimedia.org/wiki/Category:SVG_Oblique_illustrations_of_Mahjong_tiles">Mahjong tiles</a> by <a href="https://commons.wikimedia.org/wiki/User:Cangjie6">Cangjie6</a> is licensed under CC BY-SA 4.0</p>
  </div>
}