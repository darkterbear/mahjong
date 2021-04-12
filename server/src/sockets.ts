
import { Socket, Server } from 'socket.io';
import http from 'http';
import { RequestHandler } from 'express';
import sharedSession from 'express-socket.io-session';
import Player from './game/Player';

export default function sockets(
  httpServer: http.Server, 
  sessionMiddleware: RequestHandler): Server {
    
  const io = new Server(httpServer, { cors: {
    origin: 'http://localhost:5000',
    methods: ['GET', 'POST'],
    credentials: true,
  }});

  io.use(sharedSession(sessionMiddleware, {
    autoSave: true,
  }));

  io.on('connection', (socket: Socket) => {
    // User must create/join room before connecting to socket
    const id = socket.handshake.sessionID;
    console.log('SOCKET CONNECTING ' + id);
    if (!id) {
      return socket.disconnect(true);
    }

    const player = Player.getPlayer(id);
    if (!player || !player.room) {
      console.log('disconnected', player, player.room);
      return socket.disconnect(true);
    }
    
    socket.join(player.room.code);
    player.socket = socket;

    socket.on('disconnect', () => {
      const room = player.room;
      player.destroy();

      // If player was in non-empty room, send update_players
      if (room) {
        io.to(room.code).emit('update_players', room.playerNames(), room.leader?.username);

        // If was in game, no longer in game
        room.deck = [];
        room.turn = -1;
        room.pendingAction = undefined;
      }
    });
  });

  return io;
}