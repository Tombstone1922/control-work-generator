import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.jsx';
import './styles.css';
import './analysis.css';
import './fos.css';
import './item-bank.css';
import './upload-picker.css';
import './compact-generation.css';
import './competency-editor.css';
import './theme.css';
import './dark-item-bank.css';
import './workspace-tabs.css';
import './admin-user-tools.js';

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
