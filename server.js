const express = require('express');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 3000;

// Middleware
app.use(express.json());
app.use(express.static('.'));

// ✅ ВАШ АГЕНТ - НИКАКИХ API ВЫЗОВОВ!
const AGENT_ID = 'agent_01jzwcew2ferttga9m1zcn3js1';
const API_KEY = 'sk_29b8a29eb2a7e8a62521a36d7c3c34c245d0ca0daaded3da';

console.log(`🎯 Готов к работе с агентом: ${AGENT_ID}`);

// ПРОСТОЙ endpoint - только возврат данных, БЕЗ API вызовов
app.get('/api/agent-id', (req, res) => {
  console.log('📡 Agent ID requested - returning ready agent');
  
  // Возвращаем готовые данные без проверок
  res.json({ 
    agent_id: AGENT_ID, 
    api_key: API_KEY,
    status: 'ready',
    source: 'manual',
    message: 'Агент готов к работе'
  });
});

// Главная страница
app.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, 'index.html'));
});

// Debug страница  
app.get('/debug', (req, res) => {
  res.sendFile(path.join(__dirname, 'debug.html'));
});

// Favicon
app.get('/favicon.ico', (req, res) => {
  res.status(204).end();
});

// Health check - простой ответ
app.get('/health', (req, res) => {
  res.status(200).json({ 
    status: 'OK', 
    message: 'Server is running',
    agent_ready: true,
    agent_id: AGENT_ID,
    agent_source: 'manual',
    timestamp: new Date().toISOString()
  });
});

// Диагностика - без API вызовов
app.get('/api/diagnostics', (req, res) => {
  res.json({
    timestamp: new Date().toISOString(),
    agent_id: AGENT_ID,
    agent_status: 'ready',
    source: 'manual',
    api_key_configured: true,
    recommendations: [
      '✅ Агент готов к работе',
      '✅ Можно начинать голосовое общение',
      '💡 Используйте наушники для лучшего качества'
    ]
  });
});

// Запуск сервера
app.listen(PORT, () => {
  console.log(`🚀 Server running on port ${PORT}`);
  console.log(`📱 Main app: http://localhost:${PORT}`);
  console.log(`🔧 Debug: http://localhost:${PORT}/debug`);
  console.log(`✅ Agent ready: ${AGENT_ID}`);
  console.log(`🎉 NO API CALLS - IMMEDIATE READY!`);
});
