import { json, type LoaderFunctionArgs } from '@remix-run/node';
import { useLoaderData, Link, useFetcher } from '@remix-run/react';
import { useState, useEffect, useRef } from 'react';
import { ArrowLeft, Send, Bot, User, Zap, AlertCircle, Copy, Download } from 'lucide-react';
import { Button } from '~/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '~/components/ui/card';
import { Input } from '~/components/ui/input';
import { Badge } from '~/components/ui/badge';
import { Alert, AlertDescription } from '~/components/ui/alert';
import { ScrollArea } from '~/components/ui/scroll-area';
import { Separator } from '~/components/ui/separator';

interface Agent {
  id: string;
  name: string;
  description: string;
  type: string;
  is_active: boolean;
}

interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
  metadata?: any;
}

interface StreamResponse {
  type: 'message' | 'tool_call' | 'completion' | 'error' | 'conversation_id';
  content: string;
  metadata?: any;
}

export async function loader({ params }: LoaderFunctionArgs) {
  const agentId = params.agentId;
  
  // TODO: Fetch agent details from API
  const agent: Agent = {
    id: agentId!,
    name: 'Asistente de Firma Digital',
    description: 'Agente especializado en la gestión de solicitudes de firma digital',
    type: 'digital_signature',
    is_active: true
  };

  return json({ agent });
}

export default function AgentChat() {
  const { agent } = useLoaderData<typeof loader>();
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [currentStreamMessage, setCurrentStreamMessage] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const scrollAreaRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, currentStreamMessage]);

  const sendMessage = async () => {
    if (!inputValue.trim() || isStreaming) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: inputValue,
      timestamp: new Date().toISOString()
    };

    setMessages(prev => [...prev, userMessage]);
    setInputValue('');
    setIsStreaming(true);
    setCurrentStreamMessage('');

    try {
      // TODO: Replace with actual API endpoint
      const response = await fetch(`/api/v1/agents/${agent.id}/chat/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          message: inputValue,
          conversation_id: conversationId,
          context: {}
        })
      });

      if (!response.body) {
        throw new Error('No response body');
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data: StreamResponse = JSON.parse(line.slice(6));
              
              switch (data.type) {
                case 'conversation_id':
                  setConversationId(data.content);
                  break;
                  
                case 'message':
                  setCurrentStreamMessage(prev => prev + data.content);
                  break;
                  
                case 'tool_call':
                  setCurrentStreamMessage(prev => prev + `\n🔧 ${data.content}\n`);
                  break;
                  
                case 'completion':
                  // Finalize the assistant message
                  const assistantMessage: Message = {
                    id: (Date.now() + 1).toString(),
                    role: 'assistant',
                    content: currentStreamMessage,
                    timestamp: new Date().toISOString(),
                    metadata: data.metadata
                  };
                  setMessages(prev => [...prev, assistantMessage]);
                  setCurrentStreamMessage('');
                  break;
                  
                case 'error':
                  const errorMessage: Message = {
                    id: (Date.now() + 1).toString(),
                    role: 'system',
                    content: `Error: ${data.content}`,
                    timestamp: new Date().toISOString()
                  };
                  setMessages(prev => [...prev, errorMessage]);
                  setCurrentStreamMessage('');
                  break;
              }
            } catch (e) {
              console.error('Error parsing SSE data:', e);
            }
          }
        }
      }
    } catch (error) {
      console.error('Chat error:', error);
      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'system',
        content: `Error de conexión: ${error}`,
        timestamp: new Date().toISOString()
      };
      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setIsStreaming(false);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
  };

  const getAgentIcon = (type: string) => {
    switch (type) {
      case 'digital_signature':
        return '📝';
      case 'document_analyzer':
        return '🔍';
      default:
        return '🤖';
    }
  };

  const formatTimestamp = (timestamp: string) => {
    return new Date(timestamp).toLocaleTimeString('es-ES', {
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)]">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b">
        <div className="flex items-center space-x-4">
          <Link to="/dashboard/agents">
            <Button variant="ghost" size="sm">
              <ArrowLeft className="mr-2 h-4 w-4" />
              Volver
            </Button>
          </Link>
          <div className="flex items-center space-x-3">
            <div className="text-2xl">{getAgentIcon(agent.type)}</div>
            <div>
              <h1 className="text-xl font-semibold">{agent.name}</h1>
              <p className="text-sm text-muted-foreground">{agent.description}</p>
            </div>
          </div>
        </div>
        <div className="flex items-center space-x-2">
          <Badge variant={agent.is_active ? 'default' : 'secondary'}>
            {agent.is_active ? 'Activo' : 'Inactivo'}
          </Badge>
          <Badge variant="outline">{agent.type.replace('_', ' ')}</Badge>
        </div>
      </div>

      {/* Chat Messages */}
      <ScrollArea className="flex-1 p-4" ref={scrollAreaRef}>
        <div className="space-y-4">
          {/* Welcome Message */}
          {messages.length === 0 && (
            <Card>
              <CardContent className="p-4">
                <div className="flex items-start space-x-3">
                  <div className="text-2xl">{getAgentIcon(agent.type)}</div>
                  <div>
                    <p className="font-medium">¡Hola! Soy {agent.name}</p>
                    <p className="text-sm text-muted-foreground mt-1">
                      {agent.description}. ¿En qué puedo ayudarte hoy?
                    </p>
                    <div className="mt-3 space-y-2">
                      <p className="text-xs font-medium">Ejemplos de lo que puedo hacer:</p>
                      {agent.type === 'digital_signature' && (
                        <div className="space-y-1 text-xs text-muted-foreground">
                          <p>• "Crear una solicitud de firma para Juan Pérez"</p>
                          <p>• "¿Cuál es el estado de mi última solicitud?"</p>
                          <p>• "Listar todas mis solicitudes pendientes"</p>
                        </div>
                      )}
                      {agent.type === 'document_analyzer' && (
                        <div className="space-y-1 text-xs text-muted-foreground">
                          <p>• "Analiza este documento y dame un resumen"</p>
                          <p>• "Extrae las palabras clave principales"</p>
                          <p>• "Busca documentos sobre contratos"</p>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Chat Messages */}
          {messages.map((message) => (
            <div key={message.id} className="space-y-2">
              <div className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div className={`flex items-start space-x-2 max-w-[80%] ${
                  message.role === 'user' ? 'flex-row-reverse space-x-reverse' : ''
                }`}>
                  <div className={`flex items-center justify-center w-8 h-8 rounded-full ${
                    message.role === 'user' 
                      ? 'bg-blue-500 text-white' 
                      : message.role === 'system'
                      ? 'bg-red-500 text-white'
                      : 'bg-gray-100'
                  }`}>
                    {message.role === 'user' ? (
                      <User className="w-4 h-4" />
                    ) : message.role === 'system' ? (
                      <AlertCircle className="w-4 h-4" />
                    ) : (
                      <span className="text-sm">{getAgentIcon(agent.type)}</span>
                    )}
                  </div>
                  <Card className={`${
                    message.role === 'user' 
                      ? 'bg-blue-50 border-blue-200' 
                      : message.role === 'system'
                      ? 'bg-red-50 border-red-200'
                      : ''
                  }`}>
                    <CardContent className="p-3">
                      <div className="whitespace-pre-wrap text-sm">{message.content}</div>
                      <div className="flex items-center justify-between mt-2">
                        <span className="text-xs text-muted-foreground">
                          {formatTimestamp(message.timestamp)}
                        </span>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-6 w-6 p-0"
                          onClick={() => copyToClipboard(message.content)}
                        >
                          <Copy className="h-3 w-3" />
                        </Button>
                      </div>
                      {/* Metadata */}
                      {message.metadata && (
                        <div className="mt-2 pt-2 border-t">
                          <details className="text-xs">
                            <summary className="cursor-pointer text-muted-foreground">
                              Detalles técnicos
                            </summary>
                            <pre className="mt-1 p-2 bg-gray-50 rounded text-xs overflow-auto">
                              {JSON.stringify(message.metadata, null, 2)}
                            </pre>
                          </details>
                        </div>
                      )}
                    </CardContent>
                  </Card>
                </div>
              </div>
            </div>
          ))}

          {/* Current Streaming Message */}
          {currentStreamMessage && (
            <div className="flex justify-start">
              <div className="flex items-start space-x-2 max-w-[80%]">
                <div className="flex items-center justify-center w-8 h-8 rounded-full bg-gray-100">
                  <span className="text-sm">{getAgentIcon(agent.type)}</span>
                </div>
                <Card>
                  <CardContent className="p-3">
                    <div className="whitespace-pre-wrap text-sm">{currentStreamMessage}</div>
                    <div className="flex items-center mt-2">
                      <div className="flex space-x-1">
                        <div className="w-2 h-2 bg-blue-500 rounded-full animate-bounce"></div>
                        <div className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '0.1s' }}></div>
                        <div className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }}></div>
                      </div>
                      <span className="ml-2 text-xs text-muted-foreground">
                        Escribiendo...
                      </span>
                    </div>
                  </CardContent>
                </Card>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>
      </ScrollArea>

      {/* Input Area */}
      <div className="border-t p-4">
        <div className="flex space-x-2">
          <Input
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder="Escribe tu mensaje aquí..."
            disabled={isStreaming || !agent.is_active}
            className="flex-1"
          />
          <Button 
            onClick={sendMessage}
            disabled={isStreaming || !inputValue.trim() || !agent.is_active}
            size="icon"
          >
            {isStreaming ? (
              <div className="h-4 w-4 animate-spin rounded-full border-2 border-background border-t-foreground" />
            ) : (
              <Send className="h-4 w-4" />
            )}
          </Button>
        </div>
        
        {!agent.is_active && (
          <Alert className="mt-2">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>
              Este agente está inactivo y no puede procesar mensajes.
            </AlertDescription>
          </Alert>
        )}
        
        <p className="text-xs text-muted-foreground mt-2">
          Presiona Enter para enviar, Shift+Enter para nueva línea
        </p>
      </div>
    </div>
  );
}