import './theme.css';
import './theme.js';   // pasang tema tersimpan sebelum aplikasi digambar
import { mount } from 'svelte';
import App from './App.svelte';

mount(App, { target: document.getElementById('app') });
