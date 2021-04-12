export const BASE_URL = 'http://localhost:3000'

export const createRoom = (username) => {
  return fetch(BASE_URL + '/create_room', {
    method: 'POST',
    body: { username }
  })
}