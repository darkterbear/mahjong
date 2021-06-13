import { useEffect, useState } from 'react'
import { useHistory, useLocation } from 'react-router'
import { getGameState, playAction, socket } from '../api'
import './GamePage.scss'

export function GamePage() {
  const history = useHistory()
  const { username } = useLocation().state

  const [handConcealed, setHandConcealed] = useState([])
  const [handExposed, setHandExposed] = useState([])
  const [discarded, setDiscarded] = useState([])

  // Of players, whose turn is it? Indexes the players state; 3 represents self
  const [turn, setTurn] = useState(-1)
  const [winner, setWinner] = useState(-1)

  const [pendingAction, setPendingAction] = useState(null)
  const [interrupts, setInterrupts] = useState([])
  const [hover, setHover] = useState(null)
  
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

  useEffect(async () => {
    setInterrupts(getAvailableInterrupts())
  }, [pendingAction])

  const updateGameState = (state) => {
    setHandConcealed(state.handConcealed)
    setHandExposed(state.handExposed)
    setDiscarded(state.discarded)
    setPlayers(state.players)
    setPendingAction(state.pendingAction)
    setWinner(state.winner)

    if (state.pendingAction) {
      setTurn(-1)
    } else {
      setTurn(state.turn)
    }
  }

  // TODO: handle mahjong interrupt (wins the game)
  const getAvailableInterrupts = () => {
    // If no pending action, cannot interrupt
    if (!pendingAction) return []

    // If we are the pending action, we can't do anything
    if (pendingAction.username === username) return []
    
    let t = pendingAction.tile

    const availableInterrupts = []

    for (let i = 0; i < handConcealed.length; i++) {
      const ti = handConcealed[i];

      // If t and ti are not the same suit, or are more than 2 ranks removed, cannot possibly form meld
      if (ti.suit !== t.suit || Math.abs(ti.value - t.value) > 2) continue;

      for (let j = i + 1; j < handConcealed.length; j++) {
        const tj = handConcealed[j];

        // If t and tj are not the same suit, or are more than 2 ranks removed from t or ti, cannot possibly form meld
        if (tj.suit !== t.suit || Math.abs(tj.value - t.value) > 2 || Math.abs(tj.value - ti.value) > 2) continue;

        // Does tile t form a meld with the ones at indexes i and j in handConcealed?
        if (t.value === ti.value && ti.value === tj.value) {
          // Forms a pong; add iff pending action is discard or chow
          if (pendingAction.action < 2) {
            availableInterrupts.push([i, j])
          }

          // Check if forms a kong
          for (let k = j + 1; k < handConcealed.length; k++) {
            const tk = handConcealed[k];
            if (t.suit === tk.suit && t.value === tk.value) {
              // Forms a kong; add iff pending action is discard or chow
              if (pendingAction.action < 2) {
                availableInterrupts.push([i, j, k])
              }
            }
          }
        }

        const values = [t, ti, tj].map(tile => tile.value).sort()
        if (t.suit !== 'd' && t.suit !== 'f' && values[1] - values[0] === 1 && values[2] - values[1] === 1) {
          // Forms a chow; add iff pending action is a discard from the player immediately prior
          if (pendingAction.action < 1 && pendingAction.username === players[2].username) {
            availableInterrupts.push([i, j])
          }
        }
      }
    }

    // Remove any duplicate interrupts
    for (let i = 0; i < availableInterrupts.length; i++) {
      for (let j = i + 1; j < availableInterrupts.length; j++) {
        let a = availableInterrupts[i];
        let b = availableInterrupts[j];

        // Kongs are not duplicate w/ pongs & chows
        if (a.length !== b.length) continue;

        // Iterate through each tile of each actions...
        if (a.every((t, p) => handConcealed[t].suit === handConcealed[b[p]].suit && handConcealed[t].value === handConcealed[b[p]].value)) {
          // if the tileset is identical, remove action j
          availableInterrupts.splice(j, 1)
          j--
        }
      }
    }

    return availableInterrupts
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
    if (winner >= 0) return;

    // Tile click only valid in 2 scenarios...
    if (turn === 3 && !pendingAction) {
      // 1. It is our turn, and we are discarding
      playAction(0, [i])
      return
    } else if (turn !== 3 && pendingAction) {
      // 2. There is a pending discard that isn't ours
      const interrupt = getAssociatedInterrupt(i)
      if (!interrupt) return

      // Is this a chow or pong/kong?
      const t1 = handConcealed[interrupt[0]]
      const t2 = handConcealed[interrupt[1]]
      if (t1.value === t2.value) {
        console.log('play pong/kong')
        // Pong or kong
        playAction(2, interrupt)
      } else {
        console.log('play chow')
        // Chow
        playAction(1, interrupt)
      }
    }
  }

  const getAssociatedInterrupt = (i) => {
    return interrupts.find(interrupt => interrupt.includes(i))
  }

  let status;
  if (pendingAction) {
    console.log(pendingAction)
    switch (pendingAction.action) {
      case 0:
        // DISCARD
        let t = pendingAction.tile
        status = <div id="pending-action">
          <p>{ pendingAction.username } discarded:</p>
          <img src={`https://files.terranceli.com/mahjong/MJ${t.suit}${t.value}-.svg`}/>
        </div>
        break;
      // TODO: Handle cases for other pendingActions
      default:
        break;
    }
  }

  if (winner >= 0) {
    if (winner === 4) {
      status = <div id="pending-action">
      <h2>Draw: out of tiles</h2>
    </div>
    } else {
      const winnerUsername = winner === 3 ? 'You' : players[winner].username
      status = <div id="pending-action">
        <h2>{ winnerUsername } won!</h2>
      </div>
    }
  }

  console.log(handExposed)
  return <div id="game-page">
    {status}
    <div id="my-tiles">
      {
        handConcealed.map((t, i) => {
          const interrupt = getAssociatedInterrupt(i)
          if (interrupt) {
            return <img className={`interrupt ${hover !== null && getAssociatedInterrupt(hover).includes(i) ? 'hover' : ''}`} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)} onClick={() => handleTileClick(i)} src={`https://files.terranceli.com/mahjong/MJ${t.suit}${t.value}-.svg`}/>
          }
          return <img onClick={() => handleTileClick(i)} src={`https://files.terranceli.com/mahjong/MJ${t.suit}${t.value}-.svg`}/>
        })
      }
      {
        handExposed.map((meld, i) => {
          return <div className="exposed">
            {
              meld.map((t, j) => <img src={`https://files.terranceli.com/mahjong/MJ${t.suit}${t.value}-.svg`}/>)
            }
          </div>
        })
      }
    </div>
    <div id="my-discards">
      {
        discarded.map(t => <img src={`https://files.terranceli.com/mahjong/MJ${t.suit}${t.value}-.svg`}/>)
      }
    </div>
    { turn >= 0 && winner < 0 &&
      <span id="my-turn-indicator">{ turn === 3 ? 'Your turn!' : `${players[turn].username}'s turn`}</span>
    }
    <div id="l-tiles">
      {
        Array.from({ length: hiddenTileCount(2) }, () => <img src={'https://files.terranceli.com/mahjong/MJhide.svg'} />)
      }
      {
        players[2].handExposed.map((meld, i) => {
          return <div className="exposed">
            {
              meld.map((t, j) => <img src={`https://files.terranceli.com/mahjong/MJ${t.suit}${t.value}-.svg`}/>)
            }
          </div>
        })
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
      {
        players[1].handExposed.map((meld, i) => {
          return <div className="exposed">
            {
              meld.map((t, j) => <img src={`https://files.terranceli.com/mahjong/MJ${t.suit}${t.value}-.svg`}/>)
            }
          </div>
        })
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
      {
        players[0].handExposed.map((meld, i) => {
          return <div className="exposed">
            {
              meld.map((t, j) => <img src={`https://files.terranceli.com/mahjong/MJ${t.suit}${t.value}-.svg`}/>)
            }
          </div>
        })
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