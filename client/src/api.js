import { io } from 'socket.io-client'

export const BASE_URL = process.env.REACT_APP_API_URL

export let socket = null;
export const connectSocket = () => socket = io(BASE_URL, { withCredentials: true })

export const createRoom = (username) => {
  return fetch(BASE_URL + '/create_room', {
    headers: {
      'Content-Type': 'application/json'
    },
    method: 'POST',
    body: JSON.stringify({ username }),
    credentials: 'include'
  })
}

export const joinRoom = (username, code) => {
  return fetch(BASE_URL + '/join_room', {
    headers: {
      'Content-Type': 'application/json'
    },
    method: 'POST',
    body: JSON.stringify({ username, code }),
    credentials: 'include'
  })
}

export const startGame = () => {
  return fetch(BASE_URL + '/start_game', {
    headers: {
      'Content-Type': 'application/json'
    },
    method: 'POST',
    credentials: 'include'
  })
}

export const getGameState = () => {
  return fetch(BASE_URL + '/get_game_state', {
    headers: {
      'Content-Type': 'application/json'
    },
    credentials: 'include'
  })
}

export const playAction = (type, targetTiles) => {
  return fetch(BASE_URL + '/play_action', {
    headers: {
      'Content-Type': 'application/json'
    },
    method: 'POST',
    body: JSON.stringify({ type, targetTiles }),
    credentials: 'include'
  })
}