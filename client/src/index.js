import React from 'react'
import ReactDOM from 'react-dom'
import { BrowserRouter as Router, Switch, Route } from 'react-router-dom'
import { MenuPage } from './pages/MenuPage'
import { unregister } from './registerServiceWorker'

ReactDOM.render(
  <Router>
    <Switch>
      <Route exact path="/" component={MenuPage} />
    </Switch>
  </Router>, 
  document.getElementById('root')
);

unregister();
