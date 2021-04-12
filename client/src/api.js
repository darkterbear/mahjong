import { io } from 'socket.io-client'

export const BASE_URL = 'http://localhost:3000'

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