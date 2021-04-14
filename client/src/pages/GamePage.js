import { useEffect, useState } from 'react'
import { useHistory } from 'react-router'
import { getGameState, socket } from '../api'
import './GamePage.scss'

export function GamePage() {
  const history = useHistory()

  const [handConcealed, setHandConcealed] = useState([])
  const [handExposed, setHandExposed] = useState([])
  const [discarded, setDiscarded] = useState([])

  // Of players, whose turn is it? Indexes the players state; 3 represents self
  const [turn, setTurn] = useState(-1)

  const [pendingAction, setPendingAction] = useState(null)
  
  // List of the 3 other players, in left, top, right order
  const [players, setPlayers] = useState([{}, {}, {}])

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

  const hiddenTileCount = (i) => {
    const p = players[i];
    if (!p.handExposed) return 0;
    return 13 - p.handExposed.length * 3 + (1 ? turn === i : 0);
  }

  return <div id="game-page">
    <div id="my-tiles">
      {
        handConcealed.map(t => <img src={`https://files.terranceli.com/mahjong/MJ${t.suit}${t.value}-.svg`}/>)
      }
    </div>
    { turn >= 0 &&
      <span id="my-turn-indicator">{ turn === 3 ? 'Your turn!' : `${players[turn].username}'s turn`}</span>
    }
    <div id="l-tiles">
      {
        Array.from({ length: hiddenTileCount(2) }, () => <img src={'https://files.terranceli.com/mahjong/MJhide.svg'} />)
      }
    </div>
    <span id="l-username">{players[2].username}</span>
    <div id="t-tiles">
      {
        Array.from({ length: hiddenTileCount(1) }, () => <img src={'https://files.terranceli.com/mahjong/MJhide.svg'} />)
      }
    </div>
    <span id="t-username">{players[1].username}</span>
    <div id="r-tiles">
      {
        Array.from({ length: hiddenTileCount(0) }, () => <img src={'https://files.terranceli.com/mahjong/MJhide.svg'} />)
      }
    </div>
    <span id="r-username">{players[0].username}</span>
  </div>
}