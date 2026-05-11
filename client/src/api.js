import { io } from 'socket.io-client';

export const BASE_URL = process.env.REACT_APP_API_URL;

export let socket = null;
export const connectSocket = () => {
  socket = io(BASE_URL, { withCredentials: true, transports: ['websocket'] });
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
export const undo                 = ()        => emit('undo');
export const nextHand             = ()        => emit('next_hand');

// TODO: remove once GamePage is rewritten in Task 7.3
export const playAction = () => {};
export const getGameState = () => Promise.resolve({ ok: false });
