import { useEffect, useState } from 'react'
import { useHistory } from 'react-router'
import { getGameState, socket } from '../api'
import './GamePage.scss'

export function GamePage() {
  const history = useHistory()

  const [handConcealed, setHandConcealed] = useState([])
  const [handExposed, setHandExposed] = useState([])
  const [discarded, setDiscarded] = useState([])
  const [turn, setTurn] = useState(-1)
  const [pendingAction, setPendingAction] = useState(null)
  const [players, setPlayers] = useState([])

  useEffect(async () => {
    // Fetch game state
    const res = await getGameState()
    if (!res.ok) {
      history.replace('/')
      return
    }

    const state = await res.json()

    setHandConcealed(state.handConcealed)
    setHandExposed(state.handExposed)
    setDiscarded(state.setDiscarded)
    setTurn(state.turn)
    setPendingAction(state.pendingAction)
    setPlayers(state.players)

    socket.on('disconnect', () => {
      history.replace('/')
    })
  }, [])

  return <div id="game-page">
    <h1>Game</h1>
    <p>{JSON.stringify(handConcealed)}</p>
  </div>
}