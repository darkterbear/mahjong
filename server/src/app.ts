import cors from 'cors';
import express from 'express';
import session from 'express-session';
import http from 'http';
import routes from './routes';
import sockets from './sockets';

const PORT = 3000;

const app = express();
const sessionMiddleware = session({
  secret: 'mahjong',
  resave: true,
  saveUninitialized: true,
  // genid: () => uuidv4(),
});

app.use(express.json());
app.use(cors({ origin: ['http://localhost:5000', 'https://mahjong.terranceli.com'], credentials: true }));
app.use(sessionMiddleware);

const httpServer = http.createServer(app);

const io = sockets(httpServer, sessionMiddleware);
routes(app, io);

httpServer.listen(PORT, () => {
  console.log('Mahjong Server listening on port ' + PORT);
});