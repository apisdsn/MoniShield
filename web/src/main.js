import './theme.css';
import './theme.js';   // apply the stored theme before the app is drawn
import { mount } from 'svelte';
import App from './App.svelte';

mount(App, { target: document.getElementById('app') });
