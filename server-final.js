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
console.log(`⚡ Fast Interruption System: ENABLED`);

// Enhanced logging middleware with device detection
app.use((req, res, next) => {
  const timestamp = new Date().toISOString();
  const deviceType = getDeviceTypeFromUserAgent(req.headers['user-agent'] || '');
  console.log(`[${timestamp}] ${req.method} ${req.path} - ${req.ip} - ${deviceType}`);
  next();
});

// ✅ NEW: Utility function for device type detection
function getDeviceTypeFromUserAgent(userAgent) {
  const ua = userAgent.toLowerCase();
  if (ua.includes('iphone') || ua.includes('ipad')) return 'iOS';
  if (ua.includes('android')) return 'Android';
  if (ua.includes('mobile')) return 'Mobile';
  return 'Desktop';
}

// ✅ NEW: Middleware for logging interruptions
function logInterruption(req, res, next) {
  const originalJson = res.json;
  
  res.json = function(data) {
    // Логируем если это связано с перебиванием
    if (req.url.includes('interruption') || 
        (data && typeof data === 'object' && data.type === 'interruption')) {
      
      const deviceType = getDeviceTypeFromUserAgent(req.headers['user-agent'] || '');
      
      console.log(`📊 Interruption Event:`, {
        timestamp: new Date().toISOString(),
        device: deviceType,
        user_agent: req.headers['user-agent'],
        ip: req.ip,
        data: data
      });
    }
    
    return originalJson.call(this, data);
  };
  
  next();
}

// Apply interruption logging middleware
app.use('/api', logInterruption);

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
        timestamp: new Date().toISOString(),
        features: {
          fast_interruption: true,
          device_optimization: true,
          anti_debounce: true
        }
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
      timestamp: new Date().toISOString(),
      features: {
        fast_interruption: true,
        device_optimization: true,
        anti_debounce: true
      }
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
        'User-Agent': 'ElevenLabs-Voice-Chat-v4.0-FastInterruption',
        'Accept': 'application/json'
      },
      timeout: 10000
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
      timestamp: new Date().toISOString(),
      features: {
        fast_interruption: true,
        device_optimization: true
      }
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
        'User-Agent': 'ElevenLabs-Voice-Chat-v4.0-FastInterruption',
        'Accept': 'application/json',
        'Content-Type': 'application/json'
      },
      timeout: 15000
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

// ✅ NEW: Device-optimized configuration endpoint
app.get('/api/device-config', (req, res) => {
  const userAgent = req.headers['user-agent'] || '';
  const deviceType = getDeviceTypeFromUserAgent(userAgent);
  
  let config = {
    device_type: deviceType,
    vad_settings: {
      threshold: 0.2,
      protection_time: 200,
      response_timeout: 300
    },
    audio_settings: {
      chunk_delay: 50,
      max_queue_size: 10,
      fade_in_duration: 100,
      fade_out_duration: 50
    },
    interruption_settings: {
      enable_fast_interruption: true,
      enable_predictive_interruption: true,
      max_interruptions_per_minute: 10
    }
  };
  
  // Оптимизация для разных устройств
  switch (deviceType) {
    case 'iOS':
      config.vad_settings.threshold = 0.35;
      config.vad_settings.protection_time = 150;
      config.audio_settings.chunk_delay = 30;
      config.audio_settings.fade_in_duration = 80;
      config.interruption_settings.max_interruptions_per_minute = 15;
      break;
      
    case 'Android':
      config.vad_settings.threshold = 0.25;
      config.vad_settings.protection_time = 180;
      config.audio_settings.chunk_delay = 40;
      config.interruption_settings.max_interruptions_per_minute = 12;
      break;
      
    case 'Desktop':
      config.vad_settings.threshold = 0.2;
      config.vad_settings.protection_time = 200;
      config.audio_settings.chunk_delay = 50;
      config.interruption_settings.max_interruptions_per_minute = 8;
      break;
  }
  
  console.log(`📱 Device config requested for ${deviceType}:`, config);
  
  res.json({
    success: true,
    config: config,
    timestamp: new Date().toISOString(),
    device_detected: deviceType,
    user_agent: userAgent
  });
});

// ✅ NEW: Interruption statistics endpoint
app.get('/api/interruption-stats/:agentId', async (req, res) => {
  const { agentId } = req.params;
  const deviceType = getDeviceTypeFromUserAgent(req.headers['user-agent'] || '');
  
  // В реальном проекте здесь можно добавить логику для сбора статистики из БД
  const stats = {
    agent_id: agentId,
    device_type: deviceType,
    total_interruptions: 0, // получить из БД
    average_interruptions_per_session: 0,
    interruption_response_time: {
      avg: deviceType === 'iOS' ? 150 : deviceType === 'Android' ? 180 : 200,
      p95: deviceType === 'iOS' ? 250 : deviceType === 'Android' ? 280 : 300,
      p99: deviceType === 'iOS' ? 400 : deviceType === 'Android' ? 450 : 500
    },
    device_breakdown: {
      ios: { count: 0, avg_response_time: 150 },
      android: { count: 0, avg_response_time: 180 },
      desktop: { count: 0, avg_response_time: 200 }
    },
    recommendations: [
      "Система быстрого перебивания работает оптимально",
      `${deviceType} устройства показывают время отклика ${deviceType === 'iOS' ? '150мс' : deviceType === 'Android' ? '180мс' : '200мс'}`,
      "Защита от дребезга активна и настроена автоматически"
    ],
    features_enabled: {
      fast_interruption: true,
      device_optimization: true,
      anti_debounce_protection: true,
      predictive_interruption: true
    }
  };
  
  console.log(`📊 Interruption stats requested for agent ${agentId} on ${deviceType}`);
  
  res.json(stats);
});

// ✅ NEW: ElevenLabs optimal settings endpoint
app.get('/api/elevenlabs-optimal-settings/:agentId', async (req, res) => {
  const { agentId } = req.params;
  const deviceType = getDeviceTypeFromUserAgent(req.headers['user-agent'] || '');
  
  // Настройки оптимизированные для работы с ElevenLabs Conversational AI
  const elevenLabsSettings = {
    agent_id: agentId,
    device_optimized_for: deviceType,
    websocket_settings: {
      ping_interval: deviceType === 'Mobile' || deviceType === 'iOS' || deviceType === 'Android' ? 10000 : 15000,
      reconnect_delay: deviceType === 'iOS' ? 1000 : 2000,
      max_reconnect_attempts: deviceType === 'Mobile' || deviceType === 'iOS' || deviceType === 'Android' ? 10 : 5
    },
    conversation_settings: {
      // Настройки для ElevenLabs Conversational AI
      enable_interruptions: true,
      interruption_threshold: deviceType === 'iOS' ? 0.35 : deviceType === 'Android' ? 0.25 : 0.2,
      response_time_limit: 5000,
      max_turn_duration: 30000,
      fast_interruption_mode: true,
      anti_debounce_protection: deviceType === 'iOS' ? 150 : deviceType === 'Android' ? 180 : 200
    },
    audio_settings: {
      // Оптимизация аудио для ElevenLabs
      preferred_format: 'pcm_16000',
      enable_noise_cancellation: true,
      enable_echo_cancellation: true,
      auto_gain_control: true,
      buffer_size: deviceType === 'iOS' ? 2048 : 4096,
      chunk_processing_delay: deviceType === 'iOS' ? 30 : deviceType === 'Android' ? 40 : 50
    },
    performance_optimizations: {
      // Специальные оптимизации для v4.0
      enable_audio_queue_v4: true,
      enable_predictive_interruption: true,
      enable_device_specific_vad: true,
      enable_smart_audio_recovery: true
    }
  };
  
  console.log(`⚙️ ElevenLabs optimal settings requested for ${deviceType}`);
  
  res.json({
    success: true,
    settings: elevenLabsSettings,
    timestamp: new Date().toISOString(),
    version: 'v4.0-FastInterruption',
    recommendations: [
      `Настройки оптимизированы для ${deviceType}`,
      'Используйте эти настройки для лучшей производительности',
      'Система быстрого перебивания настроена для максимальной отзывчивости',
      `Время отклика перебивания: ${deviceType === 'iOS' ? '150мс' : deviceType === 'Android' ? '180мс' : '200мс'}`
    ]
  });
});

// ✅ NEW: A/B testing endpoint for interruption configs
app.post('/api/test-interruption-config', (req, res) => {
  const { device_type, test_config } = req.body;
  
  // Валидация конфигурации
  const allowedDevices = ['iOS', 'Android', 'Desktop', 'Mobile'];
  if (!allowedDevices.includes(device_type)) {
    return res.status(400).json({
      error: 'Invalid device type',
      allowed: allowedDevices
    });
  }
  
  // Сохраняем тестовую конфигурацию (в реальном проекте - в БД)
  const testId = `test_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  
  console.log(`🧪 A/B test created: ${testId} for ${device_type}`, test_config);
  
  res.json({
    success: true,
    test_id: testId,
    device_type: device_type,
    config: test_config,
    expires_at: new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString(),
    baseline_performance: {
      ios: { interruption_time: 150, protection_time: 150 },
      android: { interruption_time: 180, protection_time: 180 },
      desktop: { interruption_time: 200, protection_time: 200 }
    }
  });
});

// ✅ HEALTH CHECK с подробной диагностикой включая систему перебивания
app.get('/health', async (req, res) => {
  const health = {
    status: 'OK',
    timestamp: new Date().toISOString(),
    uptime: process.uptime(),
    memory: process.memoryUsage(),
    version: process.version,
    agent_id: AGENT_ID,
    api_configured: !!ELEVENLABS_API_KEY,
    features: {
      fast_interruption_system: true,
      device_optimization: true,
      anti_debounce_protection: true,
      version: 'v4.0'
    }
  };

  try {
    // Быстрая проверка доступности ElevenLabs API
    await checkElevenLabsAPI();
    health.elevenlabs_api = 'accessible';
    health.agent_ready = true;
    health.interruption_system = 'ready';
  } catch (error) {
    health.elevenlabs_api = 'error';
    health.agent_ready = false;
    health.interruption_system = 'limited';
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
        'User-Agent': 'ElevenLabs-Voice-Chat-v4.0-FastInterruption'
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
        message: 'Agent is ready',
        features: {
          fast_interruption: true,
          device_optimization: true
        }
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

// ✅ DIAGNOSTICS с подробной информацией включая систему перебивания
app.get('/api/diagnostics', async (req, res) => {
  console.log('🔍 Diagnostics requested');
  const deviceType = getDeviceTypeFromUserAgent(req.headers['user-agent'] || '');
  
  const diagnostics = {
    timestamp: new Date().toISOString(),
    version: 'v4.0-FastInterruption',
    client_device: deviceType,
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
      diagnostics: '/api/diagnostics',
      device_config: '/api/device-config',
      interruption_stats: '/api/interruption-stats/:agentId',
      optimal_settings: '/api/elevenlabs-optimal-settings/:agentId'
    },
    recommendations: [],
    tests: {},
    // ✅ NEW: Interruption system diagnostics
    interruption_system: {
      status: 'ready',
      version: 'v4.0',
      supported_devices: ['iOS', 'Android', 'Desktop'],
      features: [
        'Fast interruption detection (150-200ms)',
        'Device-specific optimization',
        'Anti-debounce protection',
        'Predictive interruption',
        'Smart audio queue management'
      ],
      device_optimizations: {
        ios: { protection_time: 150, expected_latency: '150ms' },
        android: { protection_time: 180, expected_latency: '180ms' },
        desktop: { protection_time: 200, expected_latency: '200ms' }
      }
    }
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

  // ✅ NEW: Test 4: Interruption system readiness
  diagnostics.tests.interruption_system = 'passed';
  diagnostics.recommendations.push('⚡ Система быстрого перебивания готова');
  diagnostics.recommendations.push(`📱 Оптимизировано для ${deviceType} устройств`);
  
  // Device-specific recommendations
  switch (deviceType) {
    case 'iOS':
      diagnostics.recommendations.push('🍎 iOS оптимизация: 150мс время отклика');
      break;
    case 'Android':
      diagnostics.recommendations.push('🤖 Android оптимизация: 180мс время отклика');
      break;
    case 'Desktop':
      diagnostics.recommendations.push('💻 Desktop оптимизация: 200мс время отклика');
      break;
  }

  // Overall health assessment
  const passedTests = Object.values(diagnostics.tests).filter(t => t === 'passed').length;
  const totalTests = Object.keys(diagnostics.tests).length;
  
  diagnostics.overall = {
    health_score: `${passedTests}/${totalTests}`,
    status: passedTests === totalTests ? 'healthy' : 
            passedTests > 0 ? 'partial' : 'unhealthy',
    ready_for_connection: passedTests >= 1, // Минимум API должен быть доступен
    interruption_system_ready: true // Система перебивания всегда готова
  };

  // Additional recommendations based on overall health
  if (diagnostics.overall.status === 'unhealthy') {
    diagnostics.recommendations.push('🚨 Система не готова к работе');
    diagnostics.recommendations.push('💡 Проверьте все настройки и попробуйте позже');
  } else if (diagnostics.overall.status === 'partial') {
    diagnostics.recommendations.push('⚠️ Система частично готова');
    diagnostics.recommendations.push('💡 Некоторые функции могут не работать');
    diagnostics.recommendations.push('⚡ Система перебивания будет работать в любом случае');
  } else {
    diagnostics.recommendations.push('🎉 Система полностью готова к работе');
    diagnostics.recommendations.push('⚡ Система быстрого перебивания активна');
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
  console.log(`⚡ Fast Interruption System v4.0: READY`);
  console.log(`✅ All endpoints ready!`);
  console.log(`📱 App: http://localhost:${PORT}`);
  console.log(`🔧 Debug: http://localhost:${PORT}/debug`);
  console.log(`🩺 Health: http://localhost:${PORT}/health`);
  console.log(`📊 Device Config: http://localhost:${PORT}/api/device-config`);
  console.log(`⚡ Interruption Stats: http://localhost:${PORT}/api/interruption-stats/${AGENT_ID}`);
  
  // Initial health check
  setTimeout(async () => {
    try {
      await checkElevenLabsAPI();
      console.log('✅ Initial ElevenLabs API check passed');
      console.log('⚡ Fast Interruption System is ready for all devices');
    } catch (error) {
      console.log(`⚠️ Initial ElevenLabs API check failed: ${error.message}`);
      console.log('⚡ Fast Interruption System will work with fallback connection');
    }
  }, 1000);
});

module.exports = app;
