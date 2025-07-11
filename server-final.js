const express = require('express');
const path = require('path');
const https = require('https');

const app = express();
const PORT = process.env.PORT || 3000;

// Middleware
app.use(express.json());
app.use(express.static('.'));

// ElevenLabs configuration
const ELEVENLABS_API_KEY = 'sk_95a5725ca01fdba20e15bd662d8b76152971016ff045377f';
const AGENT_ID = 'agent_01jzwcew2ferttga9m1zcn3js1';

console.log(`🎯 Server starting with Agent ID: ${AGENT_ID}`);
console.log(`🔑 API Key configured: ${ELEVENLABS_API_KEY ? 'Yes' : 'No'}`);

// Enhanced logging middleware
app.use((req, res, next) => {
  const timestamp = new Date().toISOString();
  console.log(`[${timestamp}] ${req.method} ${req.path} - ${req.ip}`);
  next();
});

// ✅ ОСНОВНОЙ ENDPOINT - Возвращает готовые данные агента
app.get('/api/agent-id', async (req, res) => {
  console.log('📡 Agent ID requested');
  
  try {
    // Проверяем что агент существует в ElevenLabs
    const agentExists = await checkAgentExists();
    
    if (agentExists) {
      res.json({ 
        agent_id: AGENT_ID, 
        api_key: ELEVENLABS_API_KEY,
        status: 'ready',
        source: 'verified',
        message: 'Агент подтвержден и готов к работе',
        timestamp: new Date().toISOString()
      });
    } else {
      res.status(404).json({
        error: 'Agent not found',
        status: 'error',
        details: 'Агент не найден в ElevenLabs',
        agent_id: AGENT_ID,
        timestamp: new Date().toISOString()
      });
    }
  } catch (error) {
    console.error('❌ Error checking agent:', error.message);
    
    // Возвращаем данные без проверки если API недоступен
    res.json({ 
      agent_id: AGENT_ID, 
      api_key: ELEVENLABS_API_KEY,
      status: 'ready',
      source: 'fallback',
      message: 'Агент готов (без проверки)',
      warning: 'Не удалось проверить статус агента в ElevenLabs',
      timestamp: new Date().toISOString()
    });
  }
});

// Function to check if agent exists
function checkAgentExists() {
  return new Promise((resolve, reject) => {
    const options = {
      hostname: 'api.elevenlabs.io',
      port: 443,
      path: `/v1/convai/agents/${AGENT_ID}`,
      method: 'GET',
      headers: {
        'xi-api-key': ELEVENLABS_API_KEY
      },
      timeout: 5000 // 5 second timeout
    };

    const req = https.request(options, (res) => {
      let data = '';
      
      res.on('data', (chunk) => {
        data += chunk;
      });
      
      res.on('end', () => {
        console.log(`📊 Agent check response: ${res.statusCode}`);
        
        if (res.statusCode === 200) {
          console.log('✅ Agent exists and is accessible');
          resolve(true);
        } else if (res.statusCode === 404) {
          console.log('❌ Agent not found');
          resolve(false);
        } else {
          console.log(`⚠️ Unexpected status: ${res.statusCode}`);
          reject(new Error(`API returned ${res.statusCode}: ${data}`));
        }
      });
    });

    req.on('error', (error) => {
      console.log(`❌ Agent check failed: ${error.message}`);
      reject(error);
    });

    req.on('timeout', () => {
      console.log('⏰ Agent check timeout');
      req.destroy();
      reject(new Error('Request timeout'));
    });

    req.end();
  });
}

// ✅ SIGNED URL ENDPOINT - Получает безопасный URL для WebSocket
app.get('/api/signed-url', async (req, res) => {
  console.log('🔐 Signed URL requested');
  
  try {
    const signedUrl = await getSignedUrl();
    console.log('✅ Signed URL obtained successfully');
    
    res.json({
      signed_url: signedUrl,
      agent_id: AGENT_ID,
      status: 'ready',
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('❌ Signed URL error:', error.message);
    
    // Fallback URL if signed URL fails
    res.status(200).json({
      error: 'Signed URL failed',
      fallback_url: `wss://api.elevenlabs.io/v1/convai/conversation?agent_id=${AGENT_ID}`,
      agent_id: AGENT_ID,
      details: error.message,
      status: 'fallback',
      timestamp: new Date().toISOString()
    });
  }
});

// Function to get signed URL with enhanced error handling
function getSignedUrl() {
  return new Promise((resolve, reject) => {
    const options = {
      hostname: 'api.elevenlabs.io',
      port: 443,
      path: `/v1/convai/conversation/get-signed-url?agent_id=${AGENT_ID}`,
      method: 'GET',
      headers: {
        'xi-api-key': ELEVENLABS_API_KEY,
        'User-Agent': 'ElevenLabs-Voice-Chat/1.0',
        'Content-Type': 'application/json'
      },
      timeout: 10000 // 10 second timeout
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
            if (response.signed_url) {
              resolve(response.signed_url);
            } else {
              reject(new Error('No signed_url in response'));
            }
          } catch (error) {
            reject(new Error(`Parse error: ${error.message}`));
          }
        } else if (res.statusCode === 401) {
          reject(new Error('Unauthorized - check API key'));
        } else if (res.statusCode === 404) {
          reject(new Error('Agent not found'));
        } else if (res.statusCode === 429) {
          reject(new Error('Rate limit exceeded'));
        } else {
          let errorMsg = `API error: ${res.statusCode}`;
          try {
            const errorData = JSON.parse(data);
            if (errorData.detail) {
              errorMsg += ` - ${errorData.detail}`;
            }
          } catch (e) {
            errorMsg += ` - ${data}`;
          }
          reject(new Error(errorMsg));
        }
      });
    });

    req.on('error', (error) => {
      console.error('🌐 Network error:', error.message);
      reject(new Error(`Network error: ${error.message}`));
    });

    req.on('timeout', () => {
      console.error('⏰ Request timeout');
      req.destroy();
      reject(new Error('Request timeout - ElevenLabs API not responding'));
    });

    req.end();
  });
}

// ✅ HEALTH CHECK с подробной диагностикой
app.get('/health', async (req, res) => {
  const health = {
    status: 'OK',
    timestamp: new Date().toISOString(),
    uptime: process.uptime(),
    memory: process.memoryUsage(),
    version: process.version,
    agent_id: AGENT_ID,
    api_configured: !!ELEVENLABS_API_KEY
  };

  try {
    // Быстрая проверка доступности ElevenLabs API
    await checkElevenLabsAPI();
    health.elevenlabs_api = 'accessible';
    health.agent_ready = true;
  } catch (error) {
    health.elevenlabs_api = 'error';
    health.agent_ready = false;
    health.api_error = error.message;
  }

  const statusCode = health.elevenlabs_api === 'accessible' ? 200 : 503;
  res.status(statusCode).json(health);
});

// Quick API availability check
function checkElevenLabsAPI() {
  return new Promise((resolve, reject) => {
    const options = {
      hostname: 'api.elevenlabs.io',
      port: 443,
      path: '/v1/user',
      method: 'GET',
      headers: {
        'xi-api-key': ELEVENLABS_API_KEY
      },
      timeout: 3000 // Quick 3 second timeout
    };

    const req = https.request(options, (res) => {
      if (res.statusCode === 200 || res.statusCode === 401) {
        // 200 = OK, 401 = API key issue but API is accessible
        resolve();
      } else {
        reject(new Error(`API status: ${res.statusCode}`));
      }
      
      // Consume response data
      res.on('data', () => {});
    });

    req.on('error', reject);
    req.on('timeout', () => {
      req.destroy();
      reject(new Error('API timeout'));
    });

    req.end();
  });
}

// ✅ RETRY AGENT ENDPOINT
app.post('/api/retry-agent', async (req, res) => {
  console.log('🔄 Agent retry requested');
  
  try {
    const exists = await checkAgentExists();
    
    if (exists) {
      res.json({
        success: true,
        agent_id: AGENT_ID,
        status: 'ready',
        message: 'Agent is ready'
      });
    } else {
      res.status(404).json({
        success: false,
        error: 'Agent not found',
        agent_id: AGENT_ID,
        message: 'Agent does not exist in ElevenLabs'
      });
    }
  } catch (error) {
    res.status(500).json({
      success: false,
      error: error.message,
      agent_id: AGENT_ID,
      message: 'Failed to verify agent'
    });
  }
});

// ✅ DIAGNOSTICS с подробной информацией
app.get('/api/diagnostics', async (req, res) => {
  console.log('🔍 Diagnostics requested');
  
  const diagnostics = {
    timestamp: new Date().toISOString(),
    server: {
      status: 'running',
      uptime: process.uptime(),
      memory: process.memoryUsage(),
      version: process.version
    },
    configuration: {
      agent_id: AGENT_ID,
      api_key_configured: !!ELEVENLABS_API_KEY,
      api_key_preview: ELEVENLABS_API_KEY ? 
        `${ELEVENLABS_API_KEY.substring(0, 8)}...` : 'not set'
    },
    endpoints: {
      health: '/health',
      agent_id: '/api/agent-id',
      signed_url: '/api/signed-url',
      diagnostics: '/api/diagnostics'
    },
    recommendations: []
  };

  try {
    // Test ElevenLabs API
    await checkElevenLabsAPI();
    diagnostics.elevenlabs = {
      status: 'accessible',
      message: 'API is responding'
    };
    diagnostics.recommendations.push('✅ ElevenLabs API доступен');
  } catch (error) {
    diagnostics.elevenlabs = {
      status: 'error',
      message: error.message
    };
    diagnostics.recommendations.push('❌ Проблема с ElevenLabs API');
    diagnostics.recommendations.push('💡 Проверьте API ключ и интернет-соединение');
  }

  try {
    // Test agent existence
    const agentExists = await checkAgentExists();
    diagnostics.agent = {
      status: agentExists ? 'found' : 'not_found',
      id: AGENT_ID
    };
    
    if (agentExists) {
      diagnostics.recommendations.push('✅ Агент найден и доступен');
    } else {
      diagnostics.recommendations.push('❌ Агент не найден');
      diagnostics.recommendations.push('💡 Проверьте ID агента в ElevenLabs Dashboard');
    }
  } catch (error) {
    diagnostics.agent = {
      status: 'error',
      error: error.message
    };
    diagnostics.recommendations.push('⚠️ Не удалось проверить статус агента');
  }

  res.json(diagnostics);
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

// ✅ ERROR HANDLING
app.use((err, req, res, next) => {
  console.error('❌ Server error:', err);
  res.status(500).json({
    error: 'Internal server error',
    message: err.message,
    timestamp: new Date().toISOString()
  });
});

// 404 handler
app.use((req, res) => {
  res.status(404).json({
    error: 'Not found',
    path: req.path,
    method: req.method,
    timestamp: new Date().toISOString()
  });
});

// ✅ GRACEFUL SHUTDOWN
process.on('SIGTERM', () => {
  console.log('🛑 SIGTERM received, shutting down gracefully');
  process.exit(0);
});

process.on('SIGINT', () => {
  console.log('🛑 SIGINT received, shutting down gracefully');
  process.exit(0);
});

// ✅ START SERVER
const server = app.listen(PORT, () => {
  console.log(`🚀 Server running on port ${PORT}`);
  console.log(`🎯 Agent ID: ${AGENT_ID}`);
  console.log(`✅ All endpoints ready!`);
  console.log(`📱 App: http://localhost:${PORT}`);
  console.log(`🔧 Debug: http://localhost:${PORT}/debug`);
  console.log(`🩺 Health: http://localhost:${PORT}/health`);
  
  // Initial health check
  setTimeout(async () => {
    try {
      await checkElevenLabsAPI();
      console.log('✅ Initial ElevenLabs API check passed');
    } catch (error) {
      console.log(`⚠️ Initial ElevenLabs API check failed: ${error.message}`);
    }
  }, 1000);
});

module.exports = app;
