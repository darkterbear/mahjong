import Player from '@game/Player';
import Room from '@game/Room';
import cors from 'cors';
import express from 'express';
import session from 'express-session';
import sharedSession from 'express-socket.io-session';
import http from 'http';
import routes from './routes';
import sockets from './sockets';
import { v4 as uuidv4 } from 'uuid';


const PORT = 3000;

const app = express();
const sessionMiddleware = session({
  secret: 'mahjong',
  resave: false,
  saveUninitialized: true,
  genid: () => uuidv4(),
});

app.use(express.json());
app.use(cors());
app.use(sessionMiddleware);

const httpServer = http.createServer(app);

// SERVER STATE
// Maps player ids to Players and Rooms
const players: Map<string, Player> = new Map();
const rooms: Map<string, Room> = new Map();

sockets(httpServer, sessionMiddleware, players, rooms);
routes(app, players, rooms);

httpServer.listen(PORT, () => {
  console.log('Mahjong Server listening on port ' + PORT);
});