import React from 'react'
import ReactDOM from 'react-dom'
import { BrowserRouter as Router, Switch, Route } from 'react-router-dom'
import { JoinPage } from './pages/JoinPage'
import { LobbyPage } from './pages/LobbyPage'
import { MenuPage } from './pages/MenuPage'
import { unregister } from './registerServiceWorker'

ReactDOM.render(
  <Router>
    <Switch>
      <Route exact path="/" component={MenuPage} />
      <Route exact path="/join" component={JoinPage} />
      <Route exact path="/lobby" component={LobbyPage} />
    </Switch>
  </Router>, 
  document.getElementById('root')
);

unregister();
