import 'socket.io';

declare module 'socket.io/dist/socket' {
  interface Handshake {
    sessionID?: string;
  }
}