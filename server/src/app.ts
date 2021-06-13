import cors from 'cors';
import express from 'express';
import session from 'express-session';
import http from 'http';
import routes from './routes';
import sockets from './sockets';

const PORT = process.env.PORT;

const app = express();
const sessionMiddleware = session({
  secret: 'mahjong',
  resave: true,
  saveUninitialized: true,
  // genid: () => uuidv4(),
});

app.use(cors({ origin: ['https://mahjong.terranceli.com', 'http://localhost:5000'], credentials: true }));
app.use(express.json());
app.use(sessionMiddleware);

const httpServer = http.createServer(app);

const io = sockets(httpServer, sessionMiddleware);
routes(app, io);

httpServer.listen(PORT, () => {
  console.log('Mahjong Server listening on port ' + PORT);
});