const express = require('express');
const path = require('path');
const https = require('https');

const app = express();
const PORT = process.env.PORT || 3000;

// Middleware
app.use(express.json());
app.use(express.static('.'));

// ElevenLabs configuration
const ELEVENLABS_API_KEY = 'sk_29b8a29eb2a7e8a62521a36d7c3c34c245d0ca0daaded3da';
const AGENT_ID = 'agent_01jzwcew2ferttga9m1zcn3js1';

console.log(`🎯 Server starting with Agent ID: ${AGENT_ID}`);

// ✅ ОСНОВНОЙ ENDPOINT - Возвращает готовые данные агента
app.get('/api/agent-id', (req, res) => {
  console.log('📡 Agent ID requested');
  
  // Возвращаем данные без проверок API
  res.json({ 
    agent_id: AGENT_ID, 
    api_key: ELEVENLABS_API_KEY,
    status: 'ready',
    source: 'manual',
    message: 'Агент готов к работе'
  });
});

// ✅ SIGNED URL ENDPOINT - Получает безопасный URL для WebSocket
app.get('/api/signed-url', async (req, res) => {
  console.log('🔐 Signed URL requested');
  
  try {
    const signedUrl = await getSignedUrl();
    console.log('✅ Signed URL obtained');
    
    res.json({
      signed_url: signedUrl,
      agent_id: AGENT_ID,
      status: 'ready'
    });
    
  } catch (error) {
    console.error('❌ Signed URL error:', error.message);
    
    // Fallback URL if signed URL fails
    res.status(200).json({
      error: 'Signed URL failed',
      fallback_url: `wss://api.elevenlabs.io/v1/convai/conversation?agent_id=${AGENT_ID}`,
      agent_id: AGENT_ID,
      details: error.message
    });
  }
});

// Function to get signed URL
function getSignedUrl() {
  return new Promise((resolve, reject) => {
    const options = {
      hostname: 'api.elevenlabs.io',
      port: 443,
      path: `/v1/convai/conversation/get-signed-url?agent_id=${AGENT_ID}`,
      method: 'GET',
      headers: {
        'xi-api-key': ELEVENLABS_API_KEY
      }
    };

    const req = https.request(options, (res) => {
      let data = '';
      
      res.on('data', (chunk) => {
        data += chunk;
      });
      
      res.on('end', () => {
        console.log(`📊 Signed URL response: ${res.statusCode}`);
        
        if (res.statusCode === 200) {
          try {
            const response = JSON.parse(data);
            resolve(response.signed_url);
          } catch (error) {
            reject(new Error(`Parse error: ${error.message}`));
          }
        } else {
          reject(new Error(`API error: ${res.statusCode} - ${data}`));
        }
      });
    });

    req.on('error', (error) => {
      reject(error);
    });

    req.end();
  });
}

// ✅ HEALTH CHECK
app.get('/health', (req, res) => {
  res.json({ 
    status: 'OK', 
    agent_ready: true,
    agent_id: AGENT_ID,
    timestamp: new Date().toISOString()
  });
});

// ✅ DIAGNOSTICS
app.get('/api/diagnostics', (req, res) => {
  res.json({
    agent_id: AGENT_ID,
    agent_status: 'ready',
    api_key_configured: true,
    timestamp: new Date().toISOString(),
    recommendations: [
      '✅ Агент готов',
      '✅ Можно подключаться'
    ]
  });
});

// ✅ STATIC FILES
app.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, 'index.html'));
});

app.get('/debug', (req, res) => {
  res.sendFile(path.join(__dirname, 'debug.html'));
});

app.get('/favicon.ico', (req, res) => {
  res.status(204).end();
});

// ✅ START SERVER
app.listen(PORT, () => {
  console.log(`🚀 Server running on port ${PORT}`);
  console.log(`🎯 Agent ID: ${AGENT_ID}`);
  console.log(`✅ All endpoints ready!`);
  console.log(`📱 App: http://localhost:${PORT}`);
  console.log(`🔧 Debug: http://localhost:${PORT}/debug`);
});
