import { useEffect, useState } from 'react'
import { useHistory, useLocation } from 'react-router'
import { socket, connectSocket } from '../api'
import './LobbyPage.scss'

export function LobbyPage() {
  const history = useHistory()
  const { code, initialPlayers, initialLeader, username } = useLocation().state

  const [players, setPlayers] = useState(initialPlayers)
  const [leader, setLeader] = useState(initialLeader)

  useEffect(() => {
    // Should have gotten here from main or join page
    if (!code || !initialPlayers || initialPlayers.length === 0 || !initialLeader || !username) {
      history.replace('/')
      return null
    }

    // Connect to sockets, subscribe to update_players socket event
    connectSocket()
    socket.on('update_players', (players, leader) => {
      console.log(players, leader)
      setPlayers(players)
      setLeader(leader)
    })
  }, [])

  const handleStartGame = () => {
    // TODO:
  }

  return <div id="lobby-page">
    <h1>Lobby</h1>
    <span id="code">Room code: {code}</span>
    { players.map(p => <p className={p === leader ? 'leader' : ''} key={p}>{p}</p>) }
    { leader === username && 
      <button onClick={handleStartGame}>Start Game</button>
    }
  </div>
}