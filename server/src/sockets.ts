
import { Socket, Server } from 'socket.io';
import http from 'http';
import Player from '@game/Player';
import Room from '@game/Room';
import { RequestHandler } from 'express';
import sharedSession from 'express-socket.io-session';

export default function sockets(
  httpServer: http.Server, 
  sessionMiddleware: RequestHandler,
  players: Map<string, Player>, 
  rooms: Map<string, Room>): void {
    
  const io = new Server(httpServer);
  io.use(sharedSession(sessionMiddleware, {
    autoSave: true,
  }));

  io.on('connection', (socket: Socket) => {
    console.log(socket.handshake.sessionID);
    // socket.emit('id', socket.id);

    // socket.on('create_room', username => {
    //   const player = new Player(socket.id, username);
    //   players.set(socket.id, player);
    //   rooms.set(socket.id, new Room(player));
    // });
  });
}