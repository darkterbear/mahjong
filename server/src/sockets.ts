
import { Socket, Server } from 'socket.io';
import http from 'http';
import { RequestHandler } from 'express';
import sharedSession from 'express-socket.io-session';
import Player from '@game/Player';

export default function sockets(
  httpServer: http.Server, 
  sessionMiddleware: RequestHandler): void {
    
  const io = new Server(httpServer);
  io.use(sharedSession(sessionMiddleware, {
    autoSave: true,
  }));

  io.on('connection', (socket: Socket) => {
    // User must create/join room before connecting to socket
    const id = socket.handshake.sessionID;
    if (!id) {
      return socket.disconnect(true);
    }

    const player = Player.getPlayer(id);
    if (!player || !player.room) {
      return socket.disconnect(true);
    }

    socket.join(player.room.code);
    player.socket = socket;
  });
}