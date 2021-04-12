import { useState } from 'react'
import { useHistory, useLocation } from 'react-router'
import './LobbyPage.scss'

export function LobbyPage() {

  const history = useHistory()
  const { code, players, leader, username } = useLocation().state

  // Should have gotten here from main or join page
  if (!code || !players || players.length === 0 || !leader || !username) {
    history.replace('/')
    return null
  }

  const handleStartGame = () => {
    // TODO:
  }

  return <div id="page">
    <h1>Lobby</h1>
    <span id="code">Room code: {code}</span>
    { players.map(p => <p className={p === leader ? 'leader' : ''}>{p}</p>) }
    { leader === username && 
      <button onClick={handleStartGame}>Start Game</button>
    }
  </div>
}