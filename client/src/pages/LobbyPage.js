import { useEffect, useState } from 'react'
import { useHistory, useLocation } from 'react-router'
import { socket, startSession } from '../api'
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

    // Socket already connected and authed in MenuPage/JoinPage before navigating here
    socket.on('lobby_update', ({ players, leader }) => {
      setPlayers(players)
      setLeader(leader)
    })

    socket.on('start_game', () => {
      history.replace('/game', { username, code })
    })

    socket.on('disconnect', () => {
      history.replace('/')
    })

    return () => {
      socket.off('lobby_update')
      socket.off('start_game')
      socket.off('disconnect')
    }
  }, [])

  return <div id="lobby-page">
    <h1>Lobby</h1>
    <span id="code">Room code: {code}</span>
    { players.map(p => <p className={p === leader ? 'leader' : ''} key={p}>{p}</p>) }
    { players.length < 4
      ? <p className="lobby-status">{players.length}/4 players</p>
      : leader === username
        ? <button onClick={() => startSession(code)}>Start Game</button>
        : <p className="lobby-status">Waiting for {leader} to start…</p>
    }
  </div>
}