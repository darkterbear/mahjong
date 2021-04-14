import { useEffect, useState } from 'react'
import { useHistory } from 'react-router'
import { getGameState, playAction, socket } from '../api'
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
  const [players, setPlayers] = useState(Array.from({ length: 3}, () => ({ username: '', handExposed: [], discarded: [] })))

  useEffect(async () => {
    // Fetch game state
    const res = await getGameState()
    if (!res.ok) {
      history.replace('/')
      return
    }
    updateGameState(await res.json())

    socket.on('game_state_update', (state) => {
      updateGameState(state)
    })

    socket.on('disconnect', () => {
      history.replace('/')
    })
  }, [])

  const updateGameState = (state) => {
    setHandConcealed(state.handConcealed)
    setHandExposed(state.handExposed)
    setDiscarded(state.discarded)
    setTurn(state.turn)
    setPendingAction(state.pendingAction)
    setPlayers(state.players)
  }

  const hiddenTileCount = (i) => {
    const p = players[i];
    if (!p.handExposed) return 0;
    return 13 - p.handExposed.length * 3 + (1 ? turn === i : 0);
  }

  /**
   * Discards a tile that was clicked on, if it is this player's turn
   * @param {number} i Index of tile to discard
   * @returns void
   */
  const handleTileClick = (i) => {
    if (turn !== 3) return;
    playAction(0, [i])
  }

  return <div id="game-page">
    <div id="my-tiles">
      {
        handConcealed.map((t, i) => <img onClick={() => handleTileClick(i)} src={`https://files.terranceli.com/mahjong/MJ${t.suit}${t.value}-.svg`}/>)
      }
    </div>
    <div id="my-discards">
      {
        discarded.map(t => <img src={`https://files.terranceli.com/mahjong/MJ${t.suit}${t.value}-.svg`}/>)
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
    <div id="l-discards">
      {
        players[2].discarded.map(t => <img src={`https://files.terranceli.com/mahjong/MJ${t.suit}${t.value}-.svg`}/>)
      }
    </div>
    <span id="l-username">{players[2].username}</span>
    <div id="t-tiles">
      {
        Array.from({ length: hiddenTileCount(1) }, () => <img src={'https://files.terranceli.com/mahjong/MJhide.svg'} />)
      }
    </div>
    <div id="t-discards">
      {
        players[1].discarded.map(t => <img src={`https://files.terranceli.com/mahjong/MJ${t.suit}${t.value}-.svg`}/>)
      }
    </div>
    <span id="t-username">{players[1].username}</span>
    <div id="r-tiles">
      {
        Array.from({ length: hiddenTileCount(0) }, () => <img src={'https://files.terranceli.com/mahjong/MJhide.svg'} />)
      }
    </div>
    <div id="r-discards">
      {
        players[0].discarded.map(t => <img src={`https://files.terranceli.com/mahjong/MJ${t.suit}${t.value}-.svg`}/>)
      }
    </div>
    <span id="r-username">{players[0].username}</span>
  </div>
}