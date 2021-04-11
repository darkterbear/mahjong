import React, { Component } from 'react'
import './MenuPage.scss'

export function MenuPage() {
  return <div id="page">
    <h1>麻将</h1>
    <input placeholder="Username"/>
    <button>Create Room</button>
    <button>Join Room</button>
  </div>
}