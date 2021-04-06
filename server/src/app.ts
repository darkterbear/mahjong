import cors from 'cors';
import express from 'express';
import http from 'http';
import { Socket, Server } from 'socket.io';

const PORT = 3000;

const app = express();
app.use(express.json());
app.use(cors());

const httpServer = http.createServer(app);

const io = new Server(httpServer);
io.on('connection', (socket: Socket) => {

});

httpServer.listen(PORT, () => {
  console.log('Mahjong Server listening on port ' + PORT);
});