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

    const req = https.request(options, (res) => {
      let data = '';
      
      res.on('data', (chunk) => {
        data += chunk;
      });
      
      res.on('end', () => {
        try {
          const response = JSON.parse(data);
          if (res.statusCode === 200) {
            console.log('✅ Agent created successfully:', response.agent_id);
            resolve(response.agent_id);
          } else {
            console.error('❌ Error creating agent:', data);
            reject(new Error(`API Error: ${res.statusCode} - ${data}`));
          }
        } catch (error) {
          reject(new Error(`Parse Error: ${error.message}`));
        }
      });
    });

    req.on('error', (error) => {
      reject(error);
    });

    req.write(postData);
    req.end();
  });
}

// Store agent ID globally
let AGENT_ID = null;

// Initialize agent on startup
async function initializeAgent() {
  try {
    console.log('🤖 Creating ElevenLabs agent...');
    AGENT_ID = await createAgent();
    console.log(`🎉 Agent ready with ID: ${AGENT_ID}`);
  } catch (error) {
    console.error('💥 Failed to create agent:', error.message);
    // Fallback: try to use existing agent if creation fails
    console.log('🔄 Using fallback agent configuration...');
  }
}

// API endpoint to get agent ID
app.get('/api/agent-id', (req, res) => {
  if (AGENT_ID) {
    res.json({ agent_id: AGENT_ID, api_key: ELEVENLABS_API_KEY });
  } else {
    res.status(500).json({ error: 'Agent not ready yet' });
  }
});

// Serve index.html for root path
app.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, 'index.html'));
});

// Health check endpoint for Render
app.get('/health', (req, res) => {
  res.status(200).json({ 
    status: 'OK', 
    message: 'Server is running',
    agent_ready: !!AGENT_ID,
    agent_id: AGENT_ID
  });
});

// Start server and initialize agent
app.listen(PORT, () => {
  console.log(`🚀 Server running on port ${PORT}`);
  console.log(`📱 Open http://localhost:${PORT} to view the app`);
  
  // Initialize agent after server starts
  initializeAgent();
});
