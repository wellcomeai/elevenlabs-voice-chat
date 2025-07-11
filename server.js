const express = require('express');
const path = require('path');
const https = require('https');

const app = express();
const PORT = process.env.PORT || 3000;

// Middleware
app.use(express.json());
app.use(express.static('.'));

// ElevenLabs API configuration
const ELEVENLABS_API_KEY = 'sk_29b8a29eb2a7e8a62521a36d7c3c34c245d0ca0daaded3da';
const API_BASE_URL = 'api.elevenlabs.io';

// Function to check account status first
async function checkAccountStatus() {
  return new Promise((resolve, reject) => {
    const options = {
      hostname: API_BASE_URL,
      port: 443,
      path: '/v1/user',
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
        console.log(`🔍 Account check response: ${res.statusCode}`);
        console.log(`📄 Response data: ${data}`);
        
        if (res.statusCode === 200) {
          try {
            const user = JSON.parse(data);
            console.log('✅ Account verified:', user.email || 'User');
            resolve(user);
          } catch (error) {
            console.log('✅ Account verified (parsing issue)');
            resolve({ status: 'ok' });
          }
        } else {
          reject(new Error(`Account Error: ${res.statusCode} - ${data}`));
        }
      });
    });

    req.on('error', (error) => {
      reject(error);
    });

    req.end();
  });
}

// Function to create agent via API
async function createAgent() {
  const agentConfig = {
    name: "Русский ИИ Помощник",
    conversation_config: {
      agent: {
        prompt: {
          prompt: "Ты дружелюбный русскоговорящий ИИ-помощник. Отвечай на русском языке, будь полезным и вежливым. Говори естественно и используй подходящие паузы в речи."
        },
        first_message: "Привет! Я ваш ИИ-помощник. Как дела? Чем могу помочь?",
        language: "ru"
      },
      tts: {
        voice_id: "21m00Tcm4TlvDq8ikWAM" // Rachel voice, можно заменить на русский голос
      }
    }
  };

  return new Promise((resolve, reject) => {
    const postData = JSON.stringify(agentConfig);
    
    console.log('🚀 Creating agent with config:', JSON.stringify(agentConfig, null, 2));
    
    const options = {
      hostname: API_BASE_URL,
      port: 443,
      path: '/v1/convai/agents/create',
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'xi-api-key': ELEVENLABS_API_KEY,
        'Content-Length': Buffer.byteLength(postData)
      }
    };

    console.log('📡 Request options:', JSON.stringify(options, null, 2));

    const req = https.request(options, (res) => {
      let data = '';
      
      res.on('data', (chunk) => {
        data += chunk;
      });
      
      res.on('end', () => {
        console.log(`📥 Response status: ${res.statusCode}`);
        console.log(`📄 Response headers:`, res.headers);
        console.log(`📄 Response data: ${data}`);
        
        try {
          if (res.statusCode === 200 || res.statusCode === 201) {
            const response = JSON.parse(data);
            console.log('✅ Agent created successfully:', response.agent_id);
            resolve(response.agent_id);
          } else {
            console.error('❌ Error creating agent:', data);
            reject(new Error(`API Error: ${res.statusCode} - ${data}`));
          }
        } catch (error) {
          console.error('❌ Parse error:', error.message);
          console.error('❌ Raw response:', data);
          reject(new Error(`Parse Error: ${error.message} - Raw: ${data}`));
        }
      });
    });

    req.on('error', (error) => {
      console.error('❌ Request error:', error);
      reject(error);
    });

    req.write(postData);
    req.end();
  });
}

// Store agent ID and error info globally
let AGENT_ID = null;
let AGENT_ERROR = null;

// Initialize agent on startup
async function initializeAgent() {
  try {
    console.log('🔍 Checking ElevenLabs account...');
    await checkAccountStatus();
    
    console.log('🤖 Creating ElevenLabs agent...');
    AGENT_ID = await createAgent();
    console.log(`🎉 Agent ready with ID: ${AGENT_ID}`);
    AGENT_ERROR = null;
  } catch (error) {
    console.error('💥 Failed to initialize agent:', error.message);
    AGENT_ERROR = error.message;
    
    // Check if it's an authentication error
    if (error.message.includes('401') || error.message.includes('403')) {
      AGENT_ERROR = 'Неверный API ключ ElevenLabs или нет доступа к Conversational AI';
    } else if (error.message.includes('429')) {
      AGENT_ERROR = 'Превышен лимит запросов. Попробуйте позже';
    } else if (error.message.includes('402')) {
      AGENT_ERROR = 'Недостаточно кредитов на аккаунте ElevenLabs';
    }
    
    console.log('🔄 Agent will be available via fallback method...');
  }
}

// API endpoint to get agent ID
app.get('/api/agent-id', (req, res) => {
  console.log(`📡 Agent ID request - AGENT_ID: ${AGENT_ID}, ERROR: ${AGENT_ERROR}`);
  
  if (AGENT_ID) {
    res.json({ 
      agent_id: AGENT_ID, 
      api_key: ELEVENLABS_API_KEY,
      status: 'ready'
    });
  } else if (AGENT_ERROR) {
    res.status(500).json({ 
      error: 'Agent creation failed', 
      details: AGENT_ERROR,
      status: 'error'
    });
  } else {
    res.status(202).json({ 
      error: 'Agent is still being created', 
      details: 'Please wait and try again',
      status: 'creating'
    });
  }
});

// Serve index.html for root path
app.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, 'index.html'));
});

// Serve debug page
app.get('/debug', (req, res) => {
  res.sendFile(path.join(__dirname, 'debug.html'));
});

// Handle favicon requests
app.get('/favicon.ico', (req, res) => {
  res.status(204).end(); // No content
});

// Health check endpoint for Render
app.get('/health', (req, res) => {
  res.status(200).json({ 
    status: 'OK', 
    message: 'Server is running',
    agent_ready: !!AGENT_ID,
    agent_id: AGENT_ID,
    agent_error: AGENT_ERROR,
    timestamp: new Date().toISOString()
  });
});

// Serve test API endpoint
app.get('/test-api', (req, res) => {
  res.sendFile(path.join(__dirname, 'test-api.js'));
});

// API endpoint to run diagnostics
app.get('/api/diagnostics', async (req, res) => {
  console.log('🔍 Running API diagnostics...');
  
  try {
    // Test 1: Check user account
    const userResult = await checkAccountStatus();
    
    // Test 2: Try simple TTS
    const ttsResult = await testSimpleTTS();
    
    res.json({
      success: true,
      tests: {
        user_check: { status: 'passed', data: userResult },
        tts_check: { status: 'passed', data: ttsResult }
      },
      recommendations: [
        'API ключ работает',
        'Попробуйте создать агент вручную через elevenlabs.io',
        'Возможно, нужен другой план подписки для Conversational AI'
      ]
    });
    
  } catch (error) {
    console.error('❌ Diagnostics failed:', error.message);
    
    let recommendations = [];
    let issue = 'unknown';
    
    if (error.message.includes('401')) {
      issue = 'authentication';
      recommendations = [
        'Проверьте правильность API ключа',
        'Создайте новый API ключ на elevenlabs.io',
        'Убедитесь, что ключ имеет нужные разрешения'
      ];
    } else if (error.message.includes('402')) {
      issue = 'payment';
      recommendations = [
        'Пополните баланс кредитов',
        'Обновите план подписки',
        'Проверьте статус платежа'
      ];
    } else if (error.message.includes('403')) {
      issue = 'permissions';
      recommendations = [
        'Нет доступа к Conversational AI',
        'Обновите план до Creator или выше',
        'Проверьте разрешения API ключа'
      ];
    }
    
    res.status(500).json({
      success: false,
      issue: issue,
      error: error.message,
      recommendations: recommendations
    });
  }
});

// Test simple TTS to verify basic API access
async function testSimpleTTS() {
  return new Promise((resolve, reject) => {
    const postData = JSON.stringify({
      text: "Test",
      model_id: "eleven_multilingual_v2"
    });

    const options = {
      hostname: API_BASE_URL,
      port: 443,
      path: '/v1/text-to-speech/21m00Tcm4TlvDq8ikWAM',
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'xi-api-key': ELEVENLABS_API_KEY,
        'Content-Length': Buffer.byteLength(postData)
      }
    };

    const req = https.request(options, (res) => {
      if (res.statusCode === 200) {
        resolve({ status: 'TTS works' });
      } else {
        let data = '';
        res.on('data', (chunk) => {
          data += chunk;
        });
        res.on('end', () => {
          reject(new Error(`TTS Error: ${res.statusCode} - ${data}`));
        });
      }
    });

    req.on('error', (error) => {
      reject(error);
    });

    req.write(postData);
    req.end();
  });
}

// Start server and initialize agent
app.listen(PORT, () => {
  console.log(`🚀 Server running on port ${PORT}`);
  console.log(`📱 Open http://localhost:${PORT} to view the app`);
  
  // Initialize agent after server starts
  initializeAgent();
});
