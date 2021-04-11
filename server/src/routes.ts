import { Application } from 'express';
import { Server } from 'socket.io';
import Player from './game/Player';
import Room from './game/Room';
import Tile from './game/Tile';

export default function routes(app: Application, io: Server): void {
  app.post('/create_room', (req, res) => {
    const { username } = req.body;
    const id = req.sessionID;

    const player = new Player(id, username);
    const room = new Room();
    player.joinRoom(room);

    res.json({ code: room.code });
  });

  app.post('/join_room', (req, res) => {
    const { username, code } = req.body;
    const id = req.sessionID;

    const room = Room.getRoom(code);
    if (!room) {
      return res.status(404).end();
    }

    if (room.players.length >= 4) {
      return res.status(400).end();
    }

    if (room.inGame()) {
      return res.status(400).end();
    }

    const player = new Player(id, username);
    player.joinRoom(room);

    io.to(room.code).emit('update_players', room.playerNames(), room.leader?.username);

    res.json({ players: room.playerNames(), leader: room.leader?.username });
  });

  app.post('/start_game', (req, res) => {
    const id = req.sessionID;
    const player = Player.getPlayer(id);
    const room = player?.room;

    if (!room || room.players.length < 4) {
      return res.status(400).end();
    }

    // Update game state
    room.deck = Tile.shuffledDeck();
    
    // Deal hands
    for (const p of room.players) {
      p.handConcealed = room.deck.splice(0, 13);
    }

    room.turn = 0;
    room.players[0].handConcealed.push(room.deck.pop() as Tile);

    res.status(200).end();

    // Send start game
    io.to(room.code).emit('start_game');
  });

  app.get('/get_game_state', (req, res) => {
    const id = req.sessionID;
    const player = Player.getPlayer(id);
    const room = player?.room;

    if (!room || !room.inGame()) {
      return res.status(400).end();
    }

    res.json(player?.getPerspectiveGameState());
  });
  
}