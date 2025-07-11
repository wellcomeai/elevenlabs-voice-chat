const express = require('express');
const path = require('path');
const https = require('https');

const app = express();
const PORT = process.env.PORT || 3000;

// Middleware
app.use(express.json());
app.use(express.static('.'));

// ElevenLabs configuration
const ELEVENLABS_API_KEY = process.env.ELEVENLABS_API_KEY || 'sk_95a5725ca01fdba20e15bd662d8b76152971016ff045377f';
const AGENT_ID = process.env.AGENT_ID || 'agent_01jzwcew2ferttga9m1zcn3js1';

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

// Function to check if agent exists - ИСПРАВЛЕНО
function checkAgentExists() {
  return new Promise((resolve, reject) => {
    const options = {
      hostname: 'api.elevenlabs.io',
      port: 443,
      path: `/v1/convai/agents/${AGENT_ID}`,
      method: 'GET',
      headers: {
        'xi-api-key': ELEVENLABS_API_KEY,
        'User-Agent': 'ElevenLabs-Voice-Chat/2.0',  // ✅ Добавлен User-Agent
        'Accept': 'application/json'
      },
      timeout: 10000 // Увеличен таймаут
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
        } else if (res.statusCode === 401) {
          console.log('❌ Unauthorized - check API key');
          reject(new Error('Unauthorized access to agent'));
        } else {
          console.log(`⚠️ Unexpected status: ${res.statusCode}`);
          console.log('Response:', data);
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

// ✅ SIGNED URL ENDPOINT - ИСПРАВЛЕН КРИТИЧЕСКИЙ БАГИ
app.get('/api/signed-url', async (req, res) => {
  console.log('🔐 Signed URL requested');
  
  try {
    // Сначала проверяем что агент существует
    console.log('Checking agent availability before signed URL...');
    const agentExists = await checkAgentExists();
    
    if (!agentExists) {
      console.log('❌ Agent not found, cannot create signed URL');
      return res.status(404).json({
        error: 'Agent not found',
        fallback_url: `wss://api.elevenlabs.io/v1/convai/conversation?agent_id=${AGENT_ID}`,
        agent_id: AGENT_ID,
        details: 'Agent does not exist or is not accessible',
        status: 'agent_not_found',
        timestamp: new Date().toISOString()
      });
    }
    
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
    
    // Более детальная обработка ошибок
    let errorDetails = error.message;
    let statusCode = 500;
    let status = 'error';
    
    if (error.message.includes('Unauthorized')) {
      statusCode = 401;
      status = 'unauthorized';
      errorDetails = 'Invalid API key or insufficient permissions';
    } else if (error.message.includes('Agent not found')) {
      statusCode = 404;
      status = 'agent_not_found';
      errorDetails = 'Agent ID not found in ElevenLabs';
    } else if (error.message.includes('Rate limit')) {
      statusCode = 429;
      status = 'rate_limited';
      errorDetails = 'API rate limit exceeded';
    } else if (error.message.includes('timeout')) {
      statusCode = 504;
      status = 'timeout';
      errorDetails = 'ElevenLabs API timeout';
    }
    
    res.status(statusCode).json({
      error: 'Signed URL failed',
      fallback_url: `wss://api.elevenlabs.io/v1/convai/conversation?agent_id=${AGENT_ID}`,
      agent_id: AGENT_ID,
      details: errorDetails,
      status: status,
      timestamp: new Date().toISOString(),
      recommendations: getErrorRecommendations(status)
    });
  }
});

// Helper function for error recommendations
function getErrorRecommendations(status) {
  switch (status) {
    case 'unauthorized':
      return [
        'Check your ElevenLabs API key',
        'Verify API key has proper permissions',
        'Check if API key is expired'
      ];
    case 'agent_not_found':
      return [
        'Verify agent ID in ElevenLabs Dashboard',
        'Check if agent is active and published',
        'Ensure agent is accessible with current API key'
      ];
    case 'rate_limited':
      return [
        'Wait before retrying',
        'Check your ElevenLabs usage limits',
        'Consider upgrading your plan'
      ];
    case 'timeout':
      return [
        'Check internet connection',
        'Retry after a few moments',
        'ElevenLabs API may be experiencing issues'
      ];
    default:
      return [
        'Try refreshing the page',
        'Check ElevenLabs service status',
        'Contact support if problem persists'
      ];
  }
}

// ✅ ИСПРАВЛЕНА КРИТИЧЕСКАЯ ОШИБКА: endpoint с подчеркиванием
function getSignedUrl() {
  return new Promise((resolve, reject) => {
    const options = {
      hostname: 'api.elevenlabs.io',
      port: 443,
      // ✅ ИСПРАВЛЕНО: get-signed-url → get_signed_url
      path: `/v1/convai/conversation/get_signed_url?agent_id=${AGENT_ID}`,
      method: 'GET',
      headers: {
        'xi-api-key': ELEVENLABS_API_KEY,
        'User-Agent': 'ElevenLabs-Voice-Chat/2.0',  // ✅ Добавлен User-Agent
        'Accept': 'application/json',
        'Content-Type': 'application/json'
      },
      timeout: 15000 // Увеличен таймаут до 15 секунд
    };

    const req = https.request(options, (res) => {
      let data = '';
      
      res.on('data', (chunk) => {
        data += chunk;
      });
      
      res.on('end', () => {
        console.log(`📊 Signed URL response: ${res.statusCode}`);
        console.log('Response headers:', res.headers);
        
        if (res.statusCode === 200) {
          try {
            const response = JSON.parse(data);
            console.log('Signed URL response:', response);
            if (response.signed_url) {
              resolve(response.signed_url);
            } else {
              reject(new Error('No signed_url in response'));
            }
          } catch (error) {
            console.error('Parse error:', error);
            console.error('Raw response:', data);
            reject(new Error(`Parse error: ${error.message}`));
          }
        } else if (res.statusCode === 401) {
          reject(new Error('Unauthorized - check API key'));
        } else if (res.statusCode === 404) {
          reject(new Error('Agent not found or endpoint not found'));
        } else if (res.statusCode === 429) {
          reject(new Error('Rate limit exceeded'));
        } else {
          let errorMsg = `API error: ${res.statusCode}`;
          try {
            const errorData = JSON.parse(data);
            if (errorData.detail) {
              errorMsg += ` - ${errorData.detail}`;
            } else if (errorData.error) {
              errorMsg += ` - ${errorData.error}`;
            }
          } catch (e) {
            errorMsg += ` - ${data}`;
          }
          console.error('Full error response:', data);
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
        'xi-api-key': ELEVENLABS_API_KEY,
        'User-Agent': 'ElevenLabs-Voice-Chat/2.0'
      },
      timeout: 5000
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
    recommendations: [],
    tests: {}
  };

  // Test 1: ElevenLabs API accessibility
  try {
    await checkElevenLabsAPI();
    diagnostics.elevenlabs = {
      status: 'accessible',
      message: 'API is responding',
      test_endpoint: '/v1/user'
    };
    diagnostics.recommendations.push('✅ ElevenLabs API доступен');
    diagnostics.tests.api_connectivity = 'passed';
  } catch (error) {
    diagnostics.elevenlabs = {
      status: 'error',
      message: error.message,
      test_endpoint: '/v1/user'
    };
    diagnostics.recommendations.push('❌ Проблема с ElevenLabs API');
    diagnostics.recommendations.push('💡 Проверьте API ключ и интернет-соединение');
    diagnostics.tests.api_connectivity = 'failed';
  }

  // Test 2: Agent existence and accessibility
  try {
    const agentExists = await checkAgentExists();
    if (agentExists) {
      diagnostics.agent = {
        status: 'found',
        id: AGENT_ID,
        test_endpoint: `/v1/convai/agents/${AGENT_ID}`
      };
      diagnostics.recommendations.push('✅ Агент найден и доступен');
      diagnostics.tests.agent_accessibility = 'passed';
    } else {
      diagnostics.agent = {
        status: 'not_found',
        id: AGENT_ID,
        test_endpoint: `/v1/convai/agents/${AGENT_ID}`
      };
      diagnostics.recommendations.push('❌ Агент не найден');
      diagnostics.recommendations.push('💡 Проверьте ID агента в ElevenLabs Dashboard');
      diagnostics.tests.agent_accessibility = 'failed';
    }
  } catch (error) {
    diagnostics.agent = {
      status: 'error',
      error: error.message,
      id: AGENT_ID
    };
    diagnostics.recommendations.push('⚠️ Не удалось проверить статус агента');
    diagnostics.tests.agent_accessibility = 'error';
  }

  // Test 3: Signed URL generation
  try {
    const signedUrl = await getSignedUrl();
    diagnostics.signed_url = {
      status: 'working',
      message: 'Can generate signed URLs',
      url_preview: signedUrl.substring(0, 80) + '...'
    };
    diagnostics.recommendations.push('✅ Signed URL генерация работает');
    diagnostics.tests.signed_url_generation = 'passed';
  } catch (error) {
    diagnostics.signed_url = {
      status: 'error',
      message: error.message
    };
    diagnostics.recommendations.push('⚠️ Проблема с генерацией Signed URL');
    diagnostics.recommendations.push('💡 Будет использовано прямое подключение');
    diagnostics.tests.signed_url_generation = 'failed';
  }

  // Overall health assessment
  const passedTests = Object.values(diagnostics.tests).filter(t => t === 'passed').length;
  const totalTests = Object.keys(diagnostics.tests).length;
  
  diagnostics.overall = {
    health_score: `${passedTests}/${totalTests}`,
    status: passedTests === totalTests ? 'healthy' : 
            passedTests > 0 ? 'partial' : 'unhealthy',
    ready_for_connection: passedTests >= 1 // Минимум API должен быть доступен
  };

  // Additional recommendations based on overall health
  if (diagnostics.overall.status === 'unhealthy') {
    diagnostics.recommendations.push('🚨 Система не готова к работе');
    diagnostics.recommendations.push('💡 Проверьте все настройки и попробуйте позже');
  } else if (diagnostics.overall.status === 'partial') {
    diagnostics.recommendations.push('⚠️ Система частично готова');
    diagnostics.recommendations.push('💡 Некоторые функции могут не работать');
  } else {
    diagnostics.recommendations.push('🎉 Система полностью готова к работе');
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
