import { io } from 'socket.io-client';

// When REACT_APP_API_URL is set (dev mode pointing at a separate server),
// use it. Otherwise default to same-origin (production / single-port build).
export const BASE_URL = process.env.REACT_APP_API_URL || '';

export let socket = null;
export const connectSocket = () => {
  // Empty string → socket.io-client uses window.location for same-origin connect.
  // Let socket.io do its normal handshake (polling first, then upgrade to WS).
  // Hardcoding transports to ['websocket'] breaks behind some edge proxies
  // (e.g. Render) that don't preserve the upgrade headers on the first hit.
  socket = io(BASE_URL || undefined, { withCredentials: true });
  return socket;
};

function getOrCreatePlayerId() {
  // Use sessionStorage (per-tab) so multiple tabs of the same origin act as
  // separate players. Persists across page refresh within a tab; cleared when
  // the tab closes (re-opening generates a new id).
  let pid = sessionStorage.getItem('mahjong.player_id');
  if (!pid) {
    pid = (crypto.randomUUID && crypto.randomUUID()) || `${Date.now()}-${Math.random()}`;
    sessionStorage.setItem('mahjong.player_id', pid);
  }
  return pid;
}

const playerId = () => getOrCreatePlayerId();

export const createRoom = async (username) => {
  const r = await fetch(BASE_URL + '/create_room', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ player_id: playerId(), username }),
  });
  return r;
};

export const joinRoom = async (username, code) => {
  return fetch(BASE_URL + '/join_room', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ player_id: playerId(), username, code }),
  });
};

export const startSession = async (code) => {
  return fetch(BASE_URL + '/start_session', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ player_id: playerId(), code }),
  });
};

export const startWithCpus = async (code) => {
  return fetch(BASE_URL + '/start_with_cpus', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ player_id: playerId(), code }),
  });
};

export const authSocket = (code) => {
  socket.emit('auth', { player_id: playerId(), code });
};

export const emit = (event, payload = {}) => socket.emit(event, payload);

// Convenience wrappers used by GamePage.
export const rollDice             = ()        => emit('roll_dice');
export const drawFront            = ()        => emit('draw_front');
export const drawBack             = ()        => emit('draw_back');
export const discard              = (tile_id) => emit('discard', { tile_id });
export const declareFlower        = (tile_id) => emit('declare_flower', { tile_id });
export const claim                = (action, tiles) => emit('claim', { action, tiles });
export const declareConcealedGang = (tile_id) => emit('declare_concealed_gang', { tile_id });
export const declareAddedGang     = (tile_id) => emit('declare_added_gang', { tile_id });
export const declareSelfHu        = ()        => emit('declare_self_hu');
export const nextHand             = ()        => emit('next_hand');
export const claimDecision        = (action, tiles) => emit('claim_decision', { action, tiles });
export const claimWait            = (wait)    => emit('claim_wait', { wait });

// TODO: remove once GamePage is rewritten in Task 7.3
export const playAction = () => {};
export const getGameState = () => Promise.resolve({ ok: false });
