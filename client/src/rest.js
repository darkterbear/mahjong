export const BASE_URL = 'http://localhost:3000'

export const createRoom = (username) => {
  return fetch(BASE_URL + '/create_room', {
    headers: {
      'Content-Type': 'application/json'
    },
    method: 'POST',
    body: JSON.stringify({ username })
  })
}

export const joinRoom = (username, code) => {
  return fetch(BASE_URL + '/join_room', {
    headers: {
      'Content-Type': 'application/json'
    },
    method: 'POST',
    body: JSON.stringify({ username, code })
  })
}