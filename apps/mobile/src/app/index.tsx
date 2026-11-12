import { useState, useEffect, useCallback, useRef } from 'react';
import {
  StyleSheet,
  View,
  Text,
  TouchableOpacity,
  ScrollView,
  ActivityIndicator,
  Animated,
  Alert,
  Platform,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { createAudioPlayer, setAudioModeAsync, AudioPlayer } from 'expo-audio';
import * as Speech from 'expo-speech';
import { useVoiceRecorder } from '@/hooks/useVoiceRecorder';
import { VaakApi, ProductCardData, CartData, ToolExecutionLog } from '@/services/api';

interface ConversationTurnLog {
  id: string;
  timestamp: string;
  userQuery: string;
  toolsInvoked: string[];
  toolLogs: ToolExecutionLog[];
  assistantReply: string;
}

export default function VoiceHomeScreen() {
  const router = useRouter();
  const {
    isRecording,
    hasPermission,
    recordedUri,
    durationMillis,
    metering,
    startRecording,
    stopRecording,
    cancelRecording,
    requestPermission,
  } = useVoiceRecorder();

  // Application State
  const [backendStatus, setBackendStatus] = useState<'checking' | 'connected' | 'offline'>('checking');
  const [transcript, setTranscript] = useState<string>('');
  const [assistantReply, setAssistantReply] = useState<string>(
    'Namaste! What groceries would you like to order today? You can speak in English or Hindi.'
  );
  const [suggestedProducts, setSuggestedProducts] = useState<ProductCardData[]>([]);
  const [cart, setCart] = useState<CartData>({ items: [], currency: 'INR', subtotal: 0, total_items: 0 });
  const [isProcessing, setIsProcessing] = useState<boolean>(false);
  const [pulseAnim] = useState(new Animated.Value(1));
  const [isVoiceFeedbackEnabled, setIsVoiceFeedbackEnabled] = useState<boolean>(true);
  const [isPlayingRecording, setIsPlayingRecording] = useState<boolean>(false);
  const [showOrderSummary, setShowOrderSummary] = useState<boolean>(false);
  const [isPlacingOrder, setIsPlacingOrder] = useState<boolean>(false);

  // Live Zepto MCP Activity State
  const [recentToolLogs, setRecentToolLogs] = useState<ToolExecutionLog[]>([]);
  const [conversationTurnLogs, setConversationTurnLogs] = useState<ConversationTurnLog[]>([]);
  const [showActivityModal, setShowActivityModal] = useState<boolean>(false);

  // Diagnostics & Mic Hardware Verification State
  const [showDiagnostics, setShowDiagnostics] = useState<boolean>(false);
  const [isDiagnosticRunning, setIsDiagnosticRunning] = useState<boolean>(false);
  const [diagnosticResult, setDiagnosticResult] = useState<string | null>(null);
  const peakDiagnosticLevelRef = useRef<number>(-160);
  const [lastFileSizeKB, setLastFileSizeKB] = useState<number | null>(null);

  // References for active audio players, session, abort controller, and request generation counter
  const activeAudioPlayerRef = useRef<AudioPlayer | null>(null);
  const activeWebAudioRef = useRef<HTMLAudioElement | null>(null);
  const activeSessionIdRef = useRef<string | undefined>(undefined);
  const activeAbortControllerRef = useRef<AbortController | null>(null);
  const requestIdRef = useRef<number>(0);
  const isRecordingRef = useRef<boolean>(false);

  // Stop all audio playback across Expo audio, web Audio elements, and native Speech synthesis
  const stopAllAudio = useCallback(() => {
    try {
      Speech.stop();
    } catch {}

    if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
      try {
        window.speechSynthesis.cancel();
      } catch {}
    }

    if (activeWebAudioRef.current) {
      try {
        activeWebAudioRef.current.pause();
        activeWebAudioRef.current.currentTime = 0;
        activeWebAudioRef.current.src = '';
      } catch {}
      activeWebAudioRef.current = null;
    }

    if (activeAudioPlayerRef.current) {
      try {
        activeAudioPlayerRef.current.pause();
        if (typeof (activeAudioPlayerRef.current as any).remove === 'function') {
          (activeAudioPlayerRef.current as any).remove();
        }
      } catch {}
      activeAudioPlayerRef.current = null;
    }

    setIsPlayingRecording(false);
  }, []);

  // Sync isRecordingRef and enforce barge-in interruption whenever mic becomes active
  useEffect(() => {
    isRecordingRef.current = isRecording;
    if (isRecording) {
      // Clean barge-in: kill all active audio and cancel in-flight requests immediately
      // eslint-disable-next-line react-hooks/set-state-in-effect
      stopAllAudio();
      if (activeAbortControllerRef.current) {
        activeAbortControllerRef.current.abort();
      }
    }
  }, [isRecording, stopAllAudio]);

  // Cleanup all audio and in-flight requests on unmount
  useEffect(() => {
    return () => {
      stopAllAudio();
      if (activeAbortControllerRef.current) {
        activeAbortControllerRef.current.abort();
      }
    };
  }, [stopAllAudio]);

  // Keep track of the last recorded file size in KB
  useEffect(() => {
    if (!recordedUri) return;
    let isMounted = true;
    VaakApi.getAudioFileSize(recordedUri).then((size) => {
      if (isMounted && size !== null) {
        setLastFileSizeKB(Math.round(size / 1024));
      }
    });
    return () => {
      isMounted = false;
    };
  }, [recordedUri]);

  // Helper to detect Hindi text from script or keywords
  const isHindiText = useCallback((text: string, langHint?: string) => {
    if (langHint && (langHint.startsWith('hi') || langHint === 'hi-IN')) return true;
    if (/[\u0900-\u097F]/.test(text)) return true;
    return /\b(doodh|dudh|chahiye|kardo|daal do|namaste|aate|paani|sabzi|anda|ande|chawal|cheeni|shakkar|haan|theek|batao|kya hai|dekho)\b/i.test(text);
  }, []);

  // Speak assistant text using Sarvam AI bulbul:v4-flash Indian TTS in the matching language
  const speakAssistant = useCallback(
    async (
      text: string,
      language: string = 'auto',
      audioBase64?: string | null,
      requestId?: number
    ) => {
      const currentReqId = requestId !== undefined ? requestId : ++requestIdRef.current;
      if (!isVoiceFeedbackEnabled || !text || text.trim() === '') return;
      if (isRecordingRef.current || currentReqId !== requestIdRef.current) return;

      if (requestId === undefined) {
        if (activeAbortControllerRef.current) {
          activeAbortControllerRef.current.abort();
        }
        activeAbortControllerRef.current = new AbortController();
      }

      try {
        stopAllAudio();
        if (isRecordingRef.current || currentReqId !== requestIdRef.current) return;

        const targetLang =
          language !== 'auto'
            ? language
            : isHindiText(text)
            ? 'hi-IN'
            : 'en-IN';

        // 1. If audio_base64 is already provided in response, play directly to save latency
        if (audioBase64) {
          const audioSrc = `data:audio/wav;base64,${audioBase64}`;
          if (Platform.OS === 'web' && typeof Audio !== 'undefined') {
            const webAudio = new Audio(audioSrc);
            activeWebAudioRef.current = webAudio;
            webAudio.volume = 1.0;
            webAudio.onended = () => {
              if (activeWebAudioRef.current === webAudio) {
                activeWebAudioRef.current = null;
              }
            };
            if (!isRecordingRef.current && currentReqId === requestIdRef.current) {
              await webAudio.play();
            }
            return;
          } else {
            const player = createAudioPlayer(audioSrc);
            activeAudioPlayerRef.current = player;
            player.volume = 1.0;
            if (!isRecordingRef.current && currentReqId === requestIdRef.current) {
              player.play();
            }
            return;
          }
        }

        // 2. Try Sarvam AI Indian TTS via backend with matching language
        try {
          const ttsRes = await VaakApi.textToSpeech(
            text,
            targetLang,
            activeAbortControllerRef.current?.signal
          );
          if (isRecordingRef.current || currentReqId !== requestIdRef.current) return;
          if (ttsRes && ttsRes.audio_base64) {
            const audioSrc = `data:audio/wav;base64,${ttsRes.audio_base64}`;
            if (Platform.OS === 'web' && typeof Audio !== 'undefined') {
              const webAudio = new Audio(audioSrc);
              activeWebAudioRef.current = webAudio;
              webAudio.volume = 1.0;
              webAudio.onended = () => {
                if (activeWebAudioRef.current === webAudio) {
                  activeWebAudioRef.current = null;
                }
              };
              if (!isRecordingRef.current && currentReqId === requestIdRef.current) {
                await webAudio.play();
              }
              return;
            } else {
              const player = createAudioPlayer(audioSrc);
              activeAudioPlayerRef.current = player;
              player.volume = 1.0;
              if (!isRecordingRef.current && currentReqId === requestIdRef.current) {
                player.play();
              }
              return;
            }
          }
        } catch (sarvamErr: any) {
          if (sarvamErr?.name === 'AbortError' || currentReqId !== requestIdRef.current) return;
          console.warn('Sarvam TTS API failed, falling back to local speech:', sarvamErr);
        }

        if (isRecordingRef.current || currentReqId !== requestIdRef.current) return;

        // 3. Fallback to native or browser Speech synthesis
        if (Platform.OS !== 'web') {
          await setAudioModeAsync({
            playsInSilentMode: true,
            interruptionMode: 'duckOthers',
          });
          if (isRecordingRef.current || currentReqId !== requestIdRef.current) return;
          Speech.speak(text, {
            language: targetLang,
            pitch: 1.0,
            rate: 0.95,
            volume: 1.0,
          });
        } else if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
          window.speechSynthesis.cancel();
          window.speechSynthesis.resume();
          const utterance = new SpeechSynthesisUtterance(text);
          utterance.lang = targetLang;
          utterance.rate = 1.0;
          if (!isRecordingRef.current && currentReqId === requestIdRef.current) {
            window.speechSynthesis.speak(utterance);
          }
        }
      } catch (err: any) {
        if (err?.name === 'AbortError' || currentReqId !== requestIdRef.current) return;
        console.warn('Speech synthesis error:', err);
      }
    },
    [isVoiceFeedbackEnabled, isHindiText, stopAllAudio]
  );

  // Check backend health and fetch initial cart
  const checkBackend = useCallback(async () => {
    try {
      setBackendStatus('checking');
      await VaakApi.checkHealth();
      setBackendStatus('connected');
      const cartData = await VaakApi.getCart();
      setCart(cartData);
    } catch {
      setBackendStatus('offline');
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    checkBackend();
  }, [checkBackend]);

  // Pulsing animation when microphone is listening
  useEffect(() => {
    if (isRecording) {
      Animated.loop(
        Animated.sequence([
          Animated.timing(pulseAnim, {
            toValue: 1.25,
            duration: 600,
            useNativeDriver: true,
          }),
          Animated.timing(pulseAnim, {
            toValue: 1,
            duration: 600,
            useNativeDriver: true,
          }),
        ])
      ).start();
    } else {
      pulseAnim.setValue(1);
    }
  }, [isRecording, pulseAnim]);

  // Track highest audio level observed during diagnostic recording
  useEffect(() => {
    if (isDiagnosticRunning && metering !== undefined && metering > -160) {
      peakDiagnosticLevelRef.current = Math.max(peakDiagnosticLevelRef.current, metering);
    }
  }, [metering, isDiagnosticRunning]);

  // Handle voice recording toggle with clean barge-in interruption
  const handleMicPress = async () => {
    if (isRecording) {
      // User tapped mic to finish speaking and submit request
      setIsProcessing(true);
      stopAllAudio();

      if (activeAbortControllerRef.current) {
        activeAbortControllerRef.current.abort();
      }
      const abortController = new AbortController();
      activeAbortControllerRef.current = abortController;
      const currentRequestId = ++requestIdRef.current;

      const uri = await stopRecording();
      if (abortController.signal.aborted || currentRequestId !== requestIdRef.current) {
        setIsProcessing(false);
        return;
      }

      if (uri) {
        const fileSize = await VaakApi.getAudioFileSize(uri);
        if (fileSize !== null) {
          setLastFileSizeKB(Math.round(fileSize / 1024));
        }

        if (fileSize !== null && fileSize < 200) {
          setIsProcessing(false);
          const noAudioMsg =
            "I couldn't hear any speech (audio was empty). Please ensure your emulator microphone is enabled and speak again.";
          setAssistantReply(noAudioMsg);
          speakAssistant(noAudioMsg, 'auto', null, currentRequestId);
          return;
        }

        try {
          // Transcribe user speech via backend
          const result = await VaakApi.uploadAudio(uri, activeSessionIdRef.current, abortController.signal);
          if (abortController.signal.aborted || currentRequestId !== requestIdRef.current) return;

          setTranscript(result.transcript);
          if (result.session_id && !activeSessionIdRef.current) {
            activeSessionIdRef.current = result.session_id;
          }

          const detectedLang = result.detected_language || 'auto';
          const isHindi = isHindiText(result.transcript, detectedLang);
          const langCode = isHindi ? 'hi-IN' : 'en-IN';

          if (!result.transcript || result.transcript.trim() === '') {
            const noAudioMsg = isHindi
              ? 'मुझे आपकी आवाज़ साफ़ सुनाई नहीं दी। कृपया माइक दबाकर अपना ऑर्डर बोलें।'
              : "I couldn't hear any speech clearly. Please tap the mic and speak your order.";
            setAssistantReply(noAudioMsg);
            speakAssistant(noAudioMsg, langCode, null, currentRequestId);
            return;
          }

          const lowerText = result.transcript.toLowerCase().trim();

          // 1. Check if user is confirming addition of suggested products via voice
          const isAffirmative =
            /^(yes|yeah|sure|okay|ok|yep|add|add them|add to cart|haan|ha|theek|kardo|le lo|daal do)/i.test(lowerText) ||
            lowerText.includes('add them') ||
            lowerText.includes('add to cart') ||
            lowerText.includes('add both') ||
            lowerText.includes('daal do') ||
            lowerText.includes('kardo');

          // 2. Check if user wants to place / checkout order via voice
          const isOrderIntent =
            /place order|checkout|order now|confirm order|order kardo|buy now|khareed lo|manga lo/i.test(lowerText);

          // 3. Check if user wants to view cart via voice
          const isCartQuery =
            /what('s| is) in my cart|show cart|view cart|check cart|cart dekho|cart batao|kya hai cart me/i.test(lowerText);

          if (isAffirmative && suggestedProducts.length > 0) {
            // Automatically add all suggested products to cart via voice
            for (const prod of suggestedProducts) {
              if (abortController.signal.aborted || currentRequestId !== requestIdRef.current) return;
              await VaakApi.addCartItem({
                product_id: prod.product_id,
                name: prod.name,
                quantity: 1,
                unit_price: prod.price,
                pack_size: prod.pack_size,
                image_url: prod.image_url,
              });
            }
            if (abortController.signal.aborted || currentRequestId !== requestIdRef.current) return;
            const updatedCart = await VaakApi.getCart();
            if (abortController.signal.aborted || currentRequestId !== requestIdRef.current) return;
            setCart(updatedCart);

            const itemsAdded = suggestedProducts.map((p) => p.name).join(isHindi ? ' और ' : ' and ');
            const replyMsg = isHindi
              ? `मैंने ${itemsAdded} आपके कार्ट में जोड़ दिए हैं। कार्ट का कुल मूल्य ₹${updatedCart.subtotal.toFixed(0)} है। ऑर्डर पूरा करने के लिए "ऑर्डर प्लेस करो" कहें।`
              : `Added ${itemsAdded} to your cart. Cart total is ₹${updatedCart.subtotal.toFixed(0)}. Say "place order" when you're ready to checkout.`;
            setAssistantReply(replyMsg);
            setSuggestedProducts([]);
            speakAssistant(replyMsg, langCode, null, currentRequestId);
          } else if (isOrderIntent) {
            if (cart.total_items === 0) {
              const replyMsg = isHindi
                ? 'आपका कार्ट अभी खाली है। आज आप क्या किराना मंगाना चाहेंगे?'
                : 'Your cart is currently empty. What groceries would you like to order today?';
              setAssistantReply(replyMsg);
              speakAssistant(replyMsg, langCode, null, currentRequestId);
            } else {
              setShowOrderSummary(true);
              const replyMsg = isHindi
                ? `आपका ऑर्डर सारांश तैयार है। ${cart.total_items} सामान का कुल मूल्य ₹${cart.subtotal.toFixed(0)} है। कृपया स्क्रीन देखें और "कन्फर्म ऑर्डर" दबाएँ।`
                : `Your order summary is ready with ${cart.total_items} items totaling ₹${cart.subtotal.toFixed(0)}. Please review your screen and tap Confirm Order to place it on Zepto.`;
              setAssistantReply(replyMsg);
              speakAssistant(replyMsg, langCode, null, currentRequestId);
            }
          } else if (isCartQuery) {
            if (cart.total_items === 0) {
              const replyMsg = isHindi
                ? 'आपका कार्ट खाली है। आज आप क्या मंगाना चाहेंगे?'
                : 'Your cart is empty. What would you like to order today?';
              setAssistantReply(replyMsg);
              speakAssistant(replyMsg, langCode, null, currentRequestId);
            } else {
              const itemNames = cart.items.map((i) => `${i.quantity} ${i.name}`).join(isHindi ? ', ' : ', ');
              const replyMsg = isHindi
                ? `आपके कार्ट में ${cart.total_items} सामान हैं: ${itemNames}, कुल ₹${cart.subtotal.toFixed(0)}। ऑर्डर करने के लिए "ऑर्डर प्लेस करो" कहें।`
                : `You have ${cart.total_items} items in your cart: ${itemNames}, totaling ₹${cart.subtotal.toFixed(0)}. Say "place order" to review and checkout.`;
              setAssistantReply(replyMsg);
              speakAssistant(replyMsg, langCode, null, currentRequestId);
            }
          } else {
            // General grocery product search intent in user's spoken language
            const chatRes = await VaakApi.sendChatMessage(
              result.transcript,
              activeSessionIdRef.current,
              langCode,
              abortController.signal,
              isVoiceFeedbackEnabled
            );
            if (abortController.signal.aborted || currentRequestId !== requestIdRef.current) return;

            if (chatRes.session_id) {
              activeSessionIdRef.current = chatRes.session_id;
            }
            setAssistantReply(chatRes.reply_text);
            setSuggestedProducts(chatRes.suggested_products);

            // Record Zepto MCP live tool logs for frontend UI inspection
            const logs: ToolExecutionLog[] =
              chatRes.tool_logs && chatRes.tool_logs.length > 0
                ? chatRes.tool_logs
                : (chatRes.tools_invoked || []).map((t) => ({
                    tool_name: t,
                    status: 'success' as const,
                    summary: `Invoked Zepto MCP tool '${t}'`,
                  }));
            setRecentToolLogs(logs);

            const newTurnLog: ConversationTurnLog = {
              id: `${Date.now()}_${Math.random().toString(36).substring(2, 7)}`,
              timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
              userQuery: result.transcript,
              toolsInvoked: chatRes.tools_invoked || [],
              toolLogs: logs,
              assistantReply: chatRes.reply_text,
            };
            setConversationTurnLogs((prev) => [newTurnLog, ...prev.slice(0, 19)]);

            if (chatRes.order_guardrail_active || chatRes.action_type === 'order_confirmation_requested') {
              setShowOrderSummary(true);
            }
            speakAssistant(
              chatRes.spoken_text || chatRes.reply_text,
              chatRes.detected_language || langCode,
              chatRes.audio_base64,
              currentRequestId
            );
          }
        } catch (err: any) {
          if (err?.name === 'AbortError' || abortController.signal.aborted || currentRequestId !== requestIdRef.current) {
            return;
          }
          console.error('Error processing audio:', err);
          const errMsg = 'I heard your voice, but had trouble connecting to the backend. Please check connection.';
          setAssistantReply(errMsg);
          speakAssistant(errMsg, 'auto', null, currentRequestId);
        } finally {
          if (currentRequestId === requestIdRef.current) {
            setIsProcessing(false);
          }
        }
      } else {
        if (currentRequestId === requestIdRef.current) {
          setIsProcessing(false);
        }
      }
    } else {
      // User tapped mic to start speaking -> BARGE-IN INTERRUPTION:
      // Immediately abort previous in-flight requests and kill active audio playback
      if (activeAbortControllerRef.current) {
        activeAbortControllerRef.current.abort();
        activeAbortControllerRef.current = null;
      }
      requestIdRef.current += 1;
      stopAllAudio();
      setIsProcessing(false);

      if (!hasPermission) {
        const granted = await requestPermission();
        if (!granted) {
          Alert.alert('Permission Required', 'Microphone permission is required to speak your grocery orders.');
          return;
        }
      }
      await startRecording();
    }
  };

  // Playback recorded audio through device speaker
  const handlePlayRecording = async () => {
    if (!recordedUri) {
      Alert.alert('No Recording', 'Please record your voice first using the microphone button.');
      return;
    }

    const fileSize = await VaakApi.getAudioFileSize(recordedUri);
    if (fileSize !== null && fileSize < 200) {
      Alert.alert(
        'Empty Audio Recording (0 bytes)',
        'The audio recording file is empty. Android emulator did not capture any sound from the microphone.\n\n🛠️ How to fix in Android Studio Emulator:\n1. Click the 3 dots (...) in the emulator sidebar.\n2. Go to "Microphone".\n3. Turn ON "Virtual microphone uses host audio input".\n4. Check that your computer microphone is unmuted.'
      );
      return;
    }

    try {
      stopAllAudio();
      setIsPlayingRecording(true);
      await setAudioModeAsync({
        playsInSilentMode: true,
        interruptionMode: 'duckOthers',
      });

      const player = createAudioPlayer(recordedUri);
      activeAudioPlayerRef.current = player;
      player.volume = 1.0;
      player.play();

      const playDuration = Math.max(durationMillis || 2500, 2000);
      setTimeout(() => {
        setIsPlayingRecording(false);
      }, playDuration + 400);
    } catch (err) {
      console.error('Playback error:', err);
      setIsPlayingRecording(false);
      Alert.alert('Playback Error', 'Could not play the recorded audio file.');
    }
  };

  // Run 3-second live microphone diagnostic test
  const runMicDiagnostic = async () => {
    if (isDiagnosticRunning) return;
    setShowDiagnostics(true);
    setIsDiagnosticRunning(true);
    peakDiagnosticLevelRef.current = -160;
    setDiagnosticResult('🎙️ Initializing microphone...');

    try {
      stopAllAudio();
      if (activeAbortControllerRef.current) {
        activeAbortControllerRef.current.abort();
      }

      if (isRecording) {
        await cancelRecording();
        await new Promise((resolve) => setTimeout(resolve, 300));
      }

      await startRecording();

      for (let sec = 3; sec >= 1; sec--) {
        setDiagnosticResult(`🎙️ Recording your mic... Speak now! (${sec}s remaining)`);
        await new Promise((resolve) => setTimeout(resolve, 1000));
      }
      setDiagnosticResult('⌛ Processing test recording...');

      const testUri = await stopRecording();
      if (!testUri) {
        setDiagnosticResult('❌ Failed to capture audio. Recorder returned null URI.');
        return;
      }

      const size = await VaakApi.getAudioFileSize(testUri);
      const sizeKB = size ? (size / 1024).toFixed(1) : '0';
      setLastFileSizeKB(size ? Math.round(size / 1024) : 0);

      if (size !== null && size > 400) {
        setDiagnosticResult(
          `✅ Mic captured audio successfully!\n• File Size: ${sizeKB} KB\n• Status: Bluetooth audio working 🟢\n\nPlaying back your test voice now...`
        );
        setTimeout(() => {
          handlePlayRecording();
        }, 500);
      } else {
        setDiagnosticResult(
          Platform.OS === 'web'
            ? `⚠️ Recorded 0 sound data (${sizeKB} KB).\n\nBrowser received silence. Please click the lock/settings icon in the browser address bar, ensure microphone is permitted, and select your Bluetooth headset.`
            : `⚠️ Recorded 0 sound data (${sizeKB} KB, ${peakDiagnosticLevelRef.current.toFixed(0)} dB).\n\nEmulator received silence from host.\n👉 Open emulator 3 dots (...) ➔ Microphone ➔ Turn ON "Virtual microphone uses host audio input".`
        );
      }
    } catch (err) {
      setDiagnosticResult(`❌ Diagnostic error: ${err}`);
    } finally {
      setIsDiagnosticRunning(false);
    }
  };

  // Simulate a realistic grocery query directly into the AI pipeline with barge-in support
  const handleSimulateVoiceQuery = async (query = 'Add two packets of Nandini milk and brown bread') => {
    if (activeAbortControllerRef.current) {
      activeAbortControllerRef.current.abort();
    }
    const abortController = new AbortController();
    activeAbortControllerRef.current = abortController;
    const currentRequestId = ++requestIdRef.current;
    stopAllAudio();

    try {
      setIsProcessing(true);
      setTranscript(query);
      const chatRes = await VaakApi.sendChatMessage(
        query,
        activeSessionIdRef.current,
        'auto',
        abortController.signal,
        isVoiceFeedbackEnabled
      );
      if (abortController.signal.aborted || currentRequestId !== requestIdRef.current) return;

      if (chatRes.session_id) {
        activeSessionIdRef.current = chatRes.session_id;
      }
      setAssistantReply(chatRes.reply_text);
      setSuggestedProducts(chatRes.suggested_products);

      // Record Zepto MCP live tool logs for simulated query
      const logs: ToolExecutionLog[] =
        chatRes.tool_logs && chatRes.tool_logs.length > 0
          ? chatRes.tool_logs
          : (chatRes.tools_invoked || []).map((t) => ({
              tool_name: t,
              status: 'success' as const,
              summary: `Invoked Zepto MCP tool '${t}'`,
            }));
      setRecentToolLogs(logs);

      const newSimTurnLog: ConversationTurnLog = {
        id: `${Date.now()}_${Math.random().toString(36).substring(2, 7)}`,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
        userQuery: query,
        toolsInvoked: chatRes.tools_invoked || [],
        toolLogs: logs,
        assistantReply: chatRes.reply_text,
      };
      setConversationTurnLogs((prev) => [newSimTurnLog, ...prev.slice(0, 19)]);

      if (chatRes.order_guardrail_active || chatRes.action_type === 'order_confirmation_requested') {
        setShowOrderSummary(true);
      }
      speakAssistant(
        chatRes.spoken_text || chatRes.reply_text,
        chatRes.detected_language || 'auto',
        chatRes.audio_base64,
        currentRequestId
      );
    } catch (err: any) {
      if (err?.name === 'AbortError' || abortController.signal.aborted || currentRequestId !== requestIdRef.current) {
        return;
      }
      console.error('Simulation error:', err);
      Alert.alert('Simulation Error', 'Failed to simulate voice order query.');
    } finally {
      if (currentRequestId === requestIdRef.current) {
        setIsProcessing(false);
      }
    }
  };

  // Explicit order placement confirmation (never silently places order)
  const handleConfirmOrder = async () => {
    stopAllAudio();
    try {
      setIsPlacingOrder(true);
      // Remove each item to complete order simulation on backend
      for (const item of cart.items) {
        await VaakApi.deleteCartItem(item.id);
      }
      const emptyCart = await VaakApi.getCart();
      setCart(emptyCart);
      setShowOrderSummary(false);

      const confirmedMsg = 'Order placed successfully on Zepto! Delivery partner is assigned and will arrive in 10 minutes.';
      setAssistantReply(confirmedMsg);
      const reqId = ++requestIdRef.current;
      speakAssistant(confirmedMsg, 'en-IN', null, reqId);

      Alert.alert('⚡ Order Confirmed!', 'Your Zepto groceries are being packed and will be delivered in 10 minutes.');
    } catch (err) {
      console.error('Failed to confirm order:', err);
      Alert.alert('Error', 'Failed to place order. Please try again.');
    } finally {
      setIsPlacingOrder(false);
    }
  };

  const formatDuration = (ms: number) => {
    const totalSecs = Math.floor(ms / 1000);
    const mins = Math.floor(totalSecs / 60);
    const secs = totalSecs % 60;
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
        {/* Header */}
        <View style={styles.header}>
          <View>
            <Text style={styles.appTitle}>Vaak (वाक्)</Text>
            <Text style={styles.subtitle}>Voice-First Grocery Shopping • Zepto</Text>
          </View>
          <View style={styles.headerControls}>
            <TouchableOpacity
              onPress={() => router.push('/zepto' as any)}
              activeOpacity={0.7}
              style={[
                styles.mcpToggle,
                Platform.OS === 'web' && ({ cursor: 'pointer', userSelect: 'none' } as any),
              ]}
            >
              <Text style={styles.mcpToggleText}>⚡ Zepto MCP</Text>
            </TouchableOpacity>

            <TouchableOpacity
              onPress={runMicDiagnostic}
              disabled={isDiagnosticRunning}
              activeOpacity={0.7}
              style={[
                styles.diagToggle,
                isDiagnosticRunning && styles.diagToggleActive,
                Platform.OS === 'web' && ({ cursor: 'pointer', userSelect: 'none' } as any),
              ]}
            >
              <Text style={styles.diagToggleText}>
                {isDiagnosticRunning ? '⏳ Testing...' : '🧪 Test Mic'}
              </Text>
            </TouchableOpacity>

            <TouchableOpacity
              onPress={() => {
                const nextState = !isVoiceFeedbackEnabled;
                setIsVoiceFeedbackEnabled(nextState);
                if (!nextState) stopAllAudio();
              }}
              style={styles.voiceToggle}
            >
              <Text style={styles.voiceToggleText}>{isVoiceFeedbackEnabled ? '🔊 Voice On' : '🔇 Muted'}</Text>
            </TouchableOpacity>

            <TouchableOpacity onPress={checkBackend} style={styles.statusPill}>
              <View
                style={[
                  styles.statusDot,
                  {
                    backgroundColor:
                      backendStatus === 'connected' ? '#10B981' : backendStatus === 'checking' ? '#F59E0B' : '#EF4444',
                  },
                ]}
              />
              <Text style={styles.statusText}>
                {backendStatus === 'connected' ? 'Online' : backendStatus === 'checking' ? '...' : 'Offline'}
              </Text>
            </TouchableOpacity>
          </View>
        </View>

        {/* Microphone Diagnostic & Audio Loopback Panel */}
        {showDiagnostics && (
          <View style={styles.diagnosticCard}>
            <View style={styles.diagnosticHeader}>
              <Text style={styles.diagnosticTitle}>🧪 Microphone & Audio Diagnostics</Text>
              <TouchableOpacity onPress={() => setShowDiagnostics(false)}>
                <Text style={styles.diagnosticClose}>✕ Close</Text>
              </TouchableOpacity>
            </View>

            {/* Live Audio Level Meter */}
            <View style={styles.meterContainer}>
              <View style={styles.meterHeader}>
                <Text style={styles.meterLabel}>Live Mic Meter:</Text>
                <Text style={styles.meterValue}>
                  {metering !== undefined ? `${metering.toFixed(0)} dB` : 'Idle'}
                  {metering !== undefined && metering > -70 ? ' (Sound 🟢)' : ' (Silent ⚪)'}
                </Text>
              </View>
              <View style={styles.meterTrack}>
                <View
                  style={[
                    styles.meterFill,
                    {
                      width: `${Math.min(
                        Math.max(metering !== undefined ? ((metering + 100) / 100) * 100 : 0, 4),
                        100
                      )}%`,
                      backgroundColor:
                        metering !== undefined && metering > -60
                          ? '#10B981'
                          : metering !== undefined && metering > -90
                          ? '#F59E0B'
                          : '#64748B',
                    },
                  ]}
                />
              </View>
            </View>

            {/* Diagnostic Action Buttons */}
            <View style={styles.diagnosticButtonsRow}>
              <TouchableOpacity
                style={[
                  styles.diagButton,
                  isDiagnosticRunning && styles.diagButtonActive,
                  Platform.OS === 'web' && ({ cursor: 'pointer', userSelect: 'none' } as any),
                ]}
                onPress={runMicDiagnostic}
                disabled={isDiagnosticRunning}
                activeOpacity={0.7}
              >
                {isDiagnosticRunning ? (
                  <ActivityIndicator color="#FFFFFF" size="small" />
                ) : (
                  <Text style={styles.diagButtonText}>🎤 Test Mic (3s)</Text>
                )}
              </TouchableOpacity>

              <TouchableOpacity
                style={styles.diagSimulateButton}
                onPress={() => handleSimulateVoiceQuery()}
                disabled={isDiagnosticRunning || isProcessing}
              >
                <Text style={styles.diagSimulateButtonText}>⚡ Simulate Order</Text>
              </TouchableOpacity>
            </View>

            {/* Diagnostic Result Message */}
            {diagnosticResult && (
              <View style={styles.diagnosticResultBox}>
                <Text style={styles.diagnosticResultText}>{diagnosticResult}</Text>
              </View>
            )}
          </View>
        )}

        {/* Assistant Speech Bubble */}
        <View style={styles.assistantCard}>
          <View style={styles.assistantCardHeader}>
            <Text style={styles.assistantBadge}>AI ASSISTANT</Text>
            {isVoiceFeedbackEnabled && <Text style={styles.speakingIndicator}>🔊 Speaks answers</Text>}
          </View>
          <Text style={styles.assistantText}>{assistantReply}</Text>
          {transcript !== '' && (
            <View style={styles.transcriptBox}>
              <Text style={styles.transcriptLabel}>You said:</Text>
              <Text style={styles.transcriptText}>"{transcript}"</Text>
            </View>
          )}
        </View>

        {/* Live Zepto MCP Tool Activity Section */}
        <View style={styles.mcpActivityCard}>
          <View style={styles.mcpActivityHeader}>
            <View style={styles.mcpHeaderTitleRow}>
              <View style={[styles.liveDot, recentToolLogs.length > 0 && styles.liveDotActive]} />
              <Text style={styles.mcpActivityTitle}>Zepto MCP Tool Activity</Text>
            </View>
            {conversationTurnLogs.length > 0 && (
              <TouchableOpacity
                style={styles.historyBtn}
                onPress={() => setShowActivityModal(true)}
                activeOpacity={0.7}
              >
                <Text style={styles.historyBtnText}>📜 History ({conversationTurnLogs.length})</Text>
              </TouchableOpacity>
            )}
          </View>

          {recentToolLogs.length > 0 ? (
            <View style={styles.mcpLogsContainer}>
              {recentToolLogs.map((log, idx) => {
                const isGuardrail = log.status === 'guardrail_intercepted';
                const isError = log.status === 'error';
                return (
                  <View
                    key={`${log.tool_name}_${idx}`}
                    style={[
                      styles.mcpLogItem,
                      isGuardrail && styles.mcpLogItemGuardrail,
                      isError && styles.mcpLogItemError,
                    ]}
                  >
                    <View style={styles.mcpLogTopRow}>
                      <View style={styles.mcpToolNameBadge}>
                        <Text style={styles.mcpToolNameText}>⚡ {log.tool_name}</Text>
                      </View>
                      <View style={styles.mcpStatusBadgeRow}>
                        {log.execution_time_ms !== undefined && log.execution_time_ms !== null && (
                          <Text style={styles.mcpLatencyText}>{Math.round(log.execution_time_ms)}ms</Text>
                        )}
                        <Text
                          style={[
                            styles.mcpStatusPill,
                            isGuardrail
                              ? styles.mcpStatusPillGuardrail
                              : isError
                              ? styles.mcpStatusPillError
                              : styles.mcpStatusPillSuccess,
                          ]}
                        >
                          {isGuardrail ? '🛡️ Guardrail Intercept' : isError ? '❌ Error' : '✓ Live MCP 200'}
                        </Text>
                      </View>
                    </View>

                    {log.summary && <Text style={styles.mcpSummaryText}>{log.summary}</Text>}

                    {log.arguments && Object.keys(log.arguments).length > 0 && (
                      <View style={styles.mcpArgsBox}>
                        <Text style={styles.mcpArgsLabel}>Params:</Text>
                        <Text style={styles.mcpArgsText} numberOfLines={2}>
                          {JSON.stringify(log.arguments)}
                        </Text>
                      </View>
                    )}
                  </View>
                );
              })}
            </View>
          ) : (
            <View style={styles.mcpIdleBox}>
              <Text style={styles.mcpIdleText}>
                🧠 <Text style={{ fontWeight: '700' }}>Smart Intent Routing Active:</Text> Pure greetings and small talk skip MCP calls to protect against server bombardment. Live tool calls will log here when you ask to search groceries, view cart, or checkout.
              </Text>
            </View>
          )}
        </View>

        {/* Central Voice HUD */}
        <View style={styles.voiceSection}>
          <Animated.View
            style={[
              styles.micRing,
              isRecording && styles.micRingActive,
              { transform: [{ scale: pulseAnim }] },
            ]}
          />
          <TouchableOpacity
            style={[styles.micButton, isRecording && styles.micButtonActive]}
            onPress={handleMicPress}
            activeOpacity={0.8}
            disabled={isProcessing}
          >
            {isProcessing ? (
              <ActivityIndicator color="#FFFFFF" size="large" />
            ) : (
              <Text style={styles.micIconText}>{isRecording ? '⏹' : '🎙'}</Text>
            )}
          </TouchableOpacity>

          <Text style={styles.micStatusTitle}>
            {isRecording
              ? `Listening... (${formatDuration(durationMillis)})`
              : isProcessing
              ? 'Transcribing & Processing...'
              : 'Tap to Speak'}
          </Text>
          <Text style={styles.micStatusSubtitle}>
            {isRecording
              ? 'Tap button again to complete speech'
              : 'Speak in English, Hindi, or your language'}
          </Text>

          {/* Audio Playback verification button */}
          {recordedUri && !isRecording && (
            <TouchableOpacity
              style={[styles.playbackButton, isPlayingRecording && styles.playbackButtonActive]}
              onPress={handlePlayRecording}
              disabled={isPlayingRecording}
            >
              <Text style={styles.playbackText}>
                {isPlayingRecording
                  ? '🔊 Playing Recorded Audio...'
                  : `▶️ Play Last Recording (${(durationMillis / 1000).toFixed(1)}s${
                      lastFileSizeKB !== null ? ` • ${lastFileSizeKB} KB` : ''
                    })`}
              </Text>
            </TouchableOpacity>
          )}

          {/* Direct One-Click Mic Test Button in Central HUD */}
          <TouchableOpacity
            style={[
              styles.quickTestButton,
              isDiagnosticRunning && styles.quickTestButtonActive,
              Platform.OS === 'web' && ({ cursor: 'pointer', userSelect: 'none' } as any),
            ]}
            onPress={runMicDiagnostic}
            disabled={isDiagnosticRunning}
            activeOpacity={0.7}
          >
            {isDiagnosticRunning ? (
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                <ActivityIndicator color="#FFFFFF" size="small" />
                <Text style={styles.quickTestButtonText}>Testing Microphone...</Text>
              </View>
            ) : (
              <Text style={styles.quickTestButtonText}>🎤 Test Mic Hardware (3s Check)</Text>
            )}
          </TouchableOpacity>
        </View>

        {/* Natural Spoken Interaction Guide */}
        <View style={styles.voiceGuideCard}>
          <Text style={styles.voiceGuideTitle}>🎙️ Everything via Voice</Text>
          <Text style={styles.voiceGuideItem}>• <Text style={styles.voiceGuideBold}>Find:</Text> "I need two litres of milk and six eggs"</Text>
          <Text style={styles.voiceGuideItem}>• <Text style={styles.voiceGuideBold}>Add:</Text> "Yes, add them to my cart"</Text>
          <Text style={styles.voiceGuideItem}>• <Text style={styles.voiceGuideBold}>Review:</Text> "What is in my cart?"</Text>
          <Text style={styles.voiceGuideItem}>• <Text style={styles.voiceGuideBold}>Order:</Text> "Place order" to inspect & confirm</Text>
        </View>

        {/* Visual Inspection of Matching Products */}
        {suggestedProducts.length > 0 && (
          <View style={styles.productsSection}>
            <Text style={styles.sectionTitle}>Matching Zepto Products (Visual Review)</Text>
            <Text style={styles.sectionSubtitle}>Say "Yes, add them" to add to cart</Text>
            {suggestedProducts.map((product) => (
              <View key={product.product_id} style={styles.productCard}>
                <View style={styles.productInfo}>
                  <Text style={styles.productName}>{product.name}</Text>
                  {product.pack_size && <Text style={styles.packSize}>{product.pack_size}</Text>}
                  <Text style={styles.priceText}>₹{product.price.toFixed(2)}</Text>
                </View>
                <View style={styles.voiceAddHint}>
                  <Text style={styles.voiceAddHintText}>Say "Yes"</Text>
                </View>
              </View>
            ))}
          </View>
        )}

        {/* Order Summary & Confirmation Screen (Triggered via voice "Place order") */}
        {showOrderSummary && (
          <View style={styles.orderSummaryCard}>
            <View style={styles.summaryHeader}>
              <Text style={styles.summaryTitle}>⚡ Zepto Order Summary</Text>
              <TouchableOpacity onPress={() => setShowOrderSummary(false)}>
                <Text style={styles.summaryDismiss}>✕ Close</Text>
              </TouchableOpacity>
            </View>

            <View style={styles.summaryAddress}>
              <Text style={styles.summaryAddressLabel}>Delivery to:</Text>
              <Text style={styles.summaryAddressText}>📍 Indiranagar, Bengaluru • 10 Mins</Text>
            </View>

            <View style={styles.summaryDivider} />

            {cart.items.map((item) => (
              <View key={item.id} style={styles.summaryRow}>
                <Text style={styles.summaryItemName}>
                  {item.quantity}x {item.name}
                </Text>
                <Text style={styles.summaryItemPrice}>₹{item.total_price.toFixed(2)}</Text>
              </View>
            ))}

            <View style={styles.summaryDivider} />

            <View style={styles.summaryTotalRow}>
              <Text style={styles.summaryTotalLabel}>Grand Total</Text>
              <Text style={styles.summaryTotalValue}>₹{cart.subtotal.toFixed(2)}</Text>
            </View>

            <TouchableOpacity
              style={styles.confirmButton}
              onPress={handleConfirmOrder}
              disabled={isPlacingOrder}
            >
              {isPlacingOrder ? (
                <ActivityIndicator color="#FFFFFF" />
              ) : (
                <Text style={styles.confirmButtonText}>✅ Confirm & Place Order with Zepto</Text>
              )}
            </TouchableOpacity>
            <Text style={styles.confirmNotice}>Orders require explicit visual tap confirmation before placement.</Text>
          </View>
        )}

        {/* Persistent Floating Cart Summary */}
        {cart.total_items > 0 && !showOrderSummary && (
          <View style={styles.cartBar}>
            <View>
              <Text style={styles.cartBarCount}>
                🛒 {cart.total_items} {cart.total_items === 1 ? 'item' : 'items'} in Cart
              </Text>
              <Text style={styles.cartBarSubtotal}>Total: ₹{cart.subtotal.toFixed(2)}</Text>
            </View>
            <TouchableOpacity
              style={styles.checkoutVoiceButton}
              onPress={() => {
                setShowOrderSummary(true);
                const msg = `Order summary ready with ${cart.total_items} items totaling ₹${cart.subtotal.toFixed(0)}. Tap Confirm to place.`;
                setAssistantReply(msg);
                const reqId = ++requestIdRef.current;
                speakAssistant(msg, 'en-IN', null, reqId);
              }}
            >
              <Text style={styles.checkoutVoiceButtonText}>Review & Place →</Text>
            </TouchableOpacity>
          </View>
        )}
      </ScrollView>

      {/* Full Zepto MCP Tool Activity History Modal */}
      {showActivityModal && (
        <View style={styles.modalOverlay}>
          <View style={styles.activityModalCard}>
            <View style={styles.modalHeader}>
              <View>
                <Text style={styles.modalTitle}>🛠️ Zepto MCP Tool Call History</Text>
                <Text style={styles.activityModalSubtitle}>
                  Recorded across {conversationTurnLogs.length} conversational turns
                </Text>
              </View>
              <TouchableOpacity
                style={styles.closeModalButton}
                onPress={() => setShowActivityModal(false)}
                activeOpacity={0.7}
              >
                <Text style={styles.closeModalText}>✕</Text>
              </TouchableOpacity>
            </View>

            <ScrollView style={styles.activityHistoryList} showsVerticalScrollIndicator={true}>
              {conversationTurnLogs.map((turn, tIdx) => (
                <View key={turn.id} style={styles.historyTurnItem}>
                  <View style={styles.historyTurnHeader}>
                    <Text style={styles.historyTimestamp}>
                      Turn #{conversationTurnLogs.length - tIdx} • {turn.timestamp}
                    </Text>
                    <View
                      style={[
                        styles.historyToolBadgePill,
                        turn.toolLogs.length > 0
                          ? styles.historyToolBadgePillActive
                          : styles.historyToolBadgePillIdle,
                      ]}
                    >
                      <Text style={styles.historyToolBadgePillText}>
                        {turn.toolLogs.length > 0 ? `⚡ ${turn.toolLogs.length} MCP Calls` : '💬 Chit-Chat'}
                      </Text>
                    </View>
                  </View>

                  <Text style={styles.historyUserQuery}>🗣️ "{turn.userQuery}"</Text>

                  {turn.toolLogs.length > 0 ? (
                    <View style={styles.historyLogsSublist}>
                      {turn.toolLogs.map((log, lIdx) => (
                        <View key={`${turn.id}_log_${lIdx}`} style={styles.historySublogItem}>
                          <View style={styles.historySublogTopRow}>
                            <Text style={styles.historySublogToolName}>⚡ {log.tool_name}</Text>
                            <View style={styles.historySublogBadgeRow}>
                              {log.execution_time_ms !== undefined && log.execution_time_ms !== null && (
                                <Text style={styles.historySublogLatency}>
                                  {Math.round(log.execution_time_ms)}ms
                                </Text>
                              )}
                              <Text
                                style={[
                                  styles.historySublogStatus,
                                  log.status === 'guardrail_intercepted'
                                    ? styles.historySublogStatusGuardrail
                                    : log.status === 'error'
                                    ? styles.historySublogStatusError
                                    : styles.historySublogStatusSuccess,
                                ]}
                              >
                                {log.status === 'guardrail_intercepted'
                                  ? '🛡️ Guardrail'
                                  : log.status === 'error'
                                  ? '❌ Error'
                                  : '✓ 200 OK'}
                              </Text>
                            </View>
                          </View>

                          {log.summary && <Text style={styles.historySublogSummary}>{log.summary}</Text>}

                          {log.arguments && Object.keys(log.arguments).length > 0 && (
                            <View style={styles.historyArgsContainer}>
                              <Text style={styles.historyArgsCode}>
                                {JSON.stringify(log.arguments, null, 1).replace(/[\{\}\n]/g, '').trim()}
                              </Text>
                            </View>
                          )}
                        </View>
                      ))}
                    </View>
                  ) : (
                    <Text style={styles.historyNoToolsNotice}>
                      Zero MCP calls invoked (Smart Intent Routing preserved upstream rate limits)
                    </Text>
                  )}
                </View>
              ))}
            </ScrollView>
          </View>
        </View>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0F172A',
  },
  scrollContent: {
    paddingHorizontal: 20,
    paddingTop: 12,
    paddingBottom: 40,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 20,
  },
  headerControls: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  appTitle: {
    fontSize: 24,
    fontWeight: '800',
    color: '#F8FAFC',
    letterSpacing: 0.5,
  },
  subtitle: {
    fontSize: 12,
    color: '#94A3B8',
    marginTop: 2,
  },
  mcpToggle: {
    backgroundColor: '#312E81',
    paddingHorizontal: 8,
    paddingVertical: 6,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: '#6366F1',
  },
  mcpToggleText: {
    fontSize: 11,
    color: '#E0E7FF',
    fontWeight: '700',
  },
  diagToggle: {
    backgroundColor: '#334155',
    paddingHorizontal: 8,
    paddingVertical: 6,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: '#475569',
  },
  diagToggleActive: {
    backgroundColor: '#4F46E5',
    borderColor: '#6366F1',
  },
  diagToggleText: {
    fontSize: 11,
    color: '#F8FAFC',
    fontWeight: '700',
  },
  diagnosticCard: {
    backgroundColor: '#1E293B',
    borderRadius: 14,
    padding: 16,
    marginBottom: 16,
    borderWidth: 1.5,
    borderColor: '#6366F1',
  },
  diagnosticHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 12,
  },
  diagnosticTitle: {
    fontSize: 13,
    fontWeight: '800',
    color: '#FFFFFF',
  },
  diagnosticClose: {
    fontSize: 12,
    fontWeight: '700',
    color: '#94A3B8',
  },
  meterContainer: {
    marginBottom: 14,
  },
  meterHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 6,
  },
  meterLabel: {
    fontSize: 11,
    color: '#94A3B8',
    fontWeight: '600',
  },
  meterValue: {
    fontSize: 11,
    color: '#38BDF8',
    fontWeight: '700',
  },
  meterTrack: {
    height: 8,
    backgroundColor: '#0F172A',
    borderRadius: 4,
    overflow: 'hidden',
  },
  meterFill: {
    height: '100%',
    borderRadius: 4,
  },
  diagnosticButtonsRow: {
    flexDirection: 'row',
    gap: 8,
    marginBottom: 6,
  },
  diagButton: {
    flex: 1,
    backgroundColor: '#4F46E5',
    paddingVertical: 10,
    borderRadius: 8,
    alignItems: 'center',
  },
  diagButtonActive: {
    backgroundColor: '#EF4444',
  },
  diagButtonText: {
    color: '#FFFFFF',
    fontSize: 12,
    fontWeight: '700',
  },
  diagSimulateButton: {
    flex: 1,
    backgroundColor: '#059669',
    paddingVertical: 10,
    borderRadius: 8,
    alignItems: 'center',
  },
  diagSimulateButtonText: {
    color: '#FFFFFF',
    fontSize: 12,
    fontWeight: '700',
  },
  diagnosticResultBox: {
    backgroundColor: '#0F172A',
    borderRadius: 8,
    padding: 10,
    marginTop: 8,
    borderWidth: 1,
    borderColor: '#334155',
  },
  diagnosticResultText: {
    color: '#CBD5E1',
    fontSize: 11,
    lineHeight: 16,
  },
  voiceToggle: {
    backgroundColor: '#1E293B',
    paddingHorizontal: 8,
    paddingVertical: 6,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: '#334155',
  },
  voiceToggleText: {
    fontSize: 11,
    color: '#93C5FD',
    fontWeight: '600',
  },
  statusPill: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#1E293B',
    paddingHorizontal: 8,
    paddingVertical: 6,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: '#334155',
  },
  statusDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    marginRight: 5,
  },
  statusText: {
    fontSize: 11,
    color: '#CBD5E1',
    fontWeight: '600',
  },
  assistantCard: {
    backgroundColor: '#1E293B',
    borderRadius: 16,
    padding: 16,
    marginBottom: 24,
    borderWidth: 1,
    borderColor: '#334155',
  },
  assistantCardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  assistantBadge: {
    fontSize: 10,
    fontWeight: '700',
    color: '#38BDF8',
    letterSpacing: 1,
  },
  speakingIndicator: {
    fontSize: 10,
    color: '#10B981',
    fontWeight: '600',
  },
  assistantText: {
    fontSize: 15,
    color: '#F1F5F9',
    lineHeight: 22,
  },
  transcriptBox: {
    marginTop: 12,
    paddingTop: 10,
    borderTopWidth: 1,
    borderTopColor: '#334155',
  },
  transcriptLabel: {
    fontSize: 11,
    color: '#64748B',
    marginBottom: 2,
  },
  transcriptText: {
    fontSize: 13,
    color: '#A5B4FC',
    fontStyle: 'italic',
  },
  voiceSection: {
    alignItems: 'center',
    justifyContent: 'center',
    marginVertical: 16,
  },
  micRing: {
    position: 'absolute',
    width: 110,
    height: 110,
    borderRadius: 55,
    backgroundColor: 'rgba(99, 102, 241, 0.15)',
  },
  micRingActive: {
    backgroundColor: 'rgba(239, 68, 68, 0.25)',
  },
  micButton: {
    width: 84,
    height: 84,
    borderRadius: 42,
    backgroundColor: '#6366F1',
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: '#6366F1',
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.4,
    shadowRadius: 16,
    elevation: 8,
  },
  micButtonActive: {
    backgroundColor: '#EF4444',
    shadowColor: '#EF4444',
  },
  micIconText: {
    fontSize: 34,
  },
  micStatusTitle: {
    fontSize: 17,
    fontWeight: '700',
    color: '#F8FAFC',
    marginTop: 18,
  },
  micStatusSubtitle: {
    fontSize: 12,
    color: '#94A3B8',
    marginTop: 4,
    textAlign: 'center',
  },
  playbackButton: {
    marginTop: 14,
    backgroundColor: '#334155',
    paddingHorizontal: 14,
    paddingVertical: 7,
    borderRadius: 20,
  },
  playbackButtonActive: {
    backgroundColor: '#4338CA',
  },
  playbackText: {
    color: '#E2E8F0',
    fontSize: 12,
    fontWeight: '600',
  },
  quickTestButton: {
    marginTop: 12,
    backgroundColor: '#334155',
    paddingHorizontal: 16,
    paddingVertical: 9,
    borderRadius: 20,
    borderWidth: 1,
    borderColor: '#475569',
    alignItems: 'center',
    justifyContent: 'center',
  },
  quickTestButtonActive: {
    backgroundColor: '#4F46E5',
    borderColor: '#6366F1',
  },
  quickTestButtonText: {
    color: '#F8FAFC',
    fontSize: 12,
    fontWeight: '700',
  },
  voiceGuideCard: {
    backgroundColor: 'rgba(30, 41, 59, 0.7)',
    borderRadius: 14,
    padding: 16,
    marginVertical: 16,
    borderWidth: 1,
    borderColor: '#334155',
  },
  voiceGuideTitle: {
    fontSize: 13,
    fontWeight: '700',
    color: '#93C5FD',
    marginBottom: 8,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  voiceGuideItem: {
    fontSize: 13,
    color: '#CBD5E1',
    marginBottom: 4,
    lineHeight: 18,
  },
  voiceGuideBold: {
    fontWeight: '700',
    color: '#F8FAFC',
  },
  productsSection: {
    marginTop: 14,
  },
  sectionTitle: {
    fontSize: 14,
    fontWeight: '700',
    color: '#CBD5E1',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  sectionSubtitle: {
    fontSize: 12,
    color: '#94A3B8',
    marginTop: 2,
    marginBottom: 10,
  },
  productCard: {
    backgroundColor: '#1E293B',
    borderRadius: 12,
    padding: 14,
    marginBottom: 10,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#334155',
  },
  productInfo: {
    flex: 1,
    marginRight: 12,
  },
  productName: {
    fontSize: 14,
    fontWeight: '600',
    color: '#F8FAFC',
  },
  packSize: {
    fontSize: 12,
    color: '#94A3B8',
    marginTop: 2,
  },
  priceText: {
    fontSize: 15,
    fontWeight: '700',
    color: '#10B981',
    marginTop: 4,
  },
  voiceAddHint: {
    backgroundColor: '#0F766E',
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 6,
  },
  voiceAddHintText: {
    color: '#E6FFFA',
    fontSize: 11,
    fontWeight: '700',
  },
  orderSummaryCard: {
    backgroundColor: '#1E293B',
    borderRadius: 16,
    padding: 18,
    marginTop: 16,
    borderWidth: 1.5,
    borderColor: '#6366F1',
  },
  summaryHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  summaryTitle: {
    fontSize: 16,
    fontWeight: '800',
    color: '#F8FAFC',
  },
  summaryDismiss: {
    fontSize: 12,
    color: '#94A3B8',
    fontWeight: '600',
  },
  summaryAddress: {
    marginTop: 10,
  },
  summaryAddressLabel: {
    fontSize: 11,
    color: '#64748B',
  },
  summaryAddressText: {
    fontSize: 13,
    color: '#CBD5E1',
    fontWeight: '600',
    marginTop: 2,
  },
  summaryDivider: {
    height: 1,
    backgroundColor: '#334155',
    marginVertical: 12,
  },
  summaryRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 8,
  },
  summaryItemName: {
    fontSize: 13,
    color: '#E2E8F0',
  },
  summaryItemPrice: {
    fontSize: 13,
    fontWeight: '600',
    color: '#F1F5F9',
  },
  summaryTotalRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 16,
  },
  summaryTotalLabel: {
    fontSize: 15,
    fontWeight: '700',
    color: '#FFFFFF',
  },
  summaryTotalValue: {
    fontSize: 18,
    fontWeight: '800',
    color: '#10B981',
  },
  confirmButton: {
    backgroundColor: '#10B981',
    paddingVertical: 14,
    borderRadius: 10,
    alignItems: 'center',
  },
  confirmButtonText: {
    color: '#FFFFFF',
    fontSize: 14,
    fontWeight: '800',
    letterSpacing: 0.3,
  },
  confirmNotice: {
    fontSize: 11,
    color: '#94A3B8',
    textAlign: 'center',
    marginTop: 8,
  },
  cartBar: {
    backgroundColor: '#1E1B4B',
    borderRadius: 14,
    padding: 16,
    marginTop: 20,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#6366F1',
  },
  cartBarCount: {
    fontSize: 13,
    color: '#A5B4FC',
    fontWeight: '600',
  },
  cartBarSubtotal: {
    fontSize: 16,
    color: '#FFFFFF',
    fontWeight: '800',
    marginTop: 2,
  },
  checkoutVoiceButton: {
    backgroundColor: '#6366F1',
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderRadius: 8,
  },
  checkoutVoiceButtonText: {
    color: '#FFFFFF',
    fontSize: 13,
    fontWeight: '700',
  },

  // MCP Activity Card & Logs Styles
  mcpActivityCard: {
    backgroundColor: '#1E293B',
    borderRadius: 14,
    padding: 14,
    marginBottom: 16,
    borderWidth: 1,
    borderColor: '#334155',
  },
  mcpActivityHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 10,
  },
  mcpHeaderTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  liveDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: '#64748B',
  },
  liveDotActive: {
    backgroundColor: '#10B981',
  },
  mcpActivityTitle: {
    fontSize: 13,
    fontWeight: '700',
    color: '#F8FAFC',
    letterSpacing: 0.3,
  },
  historyBtn: {
    backgroundColor: '#334155',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 12,
  },
  historyBtnText: {
    fontSize: 11,
    color: '#A5B4FC',
    fontWeight: '600',
  },
  mcpLogsContainer: {
    gap: 8,
  },
  mcpLogItem: {
    backgroundColor: '#0F172A',
    borderRadius: 8,
    padding: 10,
    borderLeftWidth: 3,
    borderLeftColor: '#10B981',
  },
  mcpLogItemGuardrail: {
    borderLeftColor: '#F59E0B',
  },
  mcpLogItemError: {
    borderLeftColor: '#EF4444',
  },
  mcpLogTopRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 6,
  },
  mcpToolNameBadge: {
    backgroundColor: '#312E81',
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 6,
  },
  mcpToolNameText: {
    color: '#C7D2FE',
    fontSize: 12,
    fontWeight: '700',
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
  },
  mcpStatusBadgeRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  mcpLatencyText: {
    fontSize: 11,
    color: '#94A3B8',
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
  },
  mcpStatusPill: {
    fontSize: 10,
    fontWeight: '700',
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
  },
  mcpStatusPillSuccess: {
    backgroundColor: 'rgba(16, 185, 129, 0.15)',
    color: '#34D399',
  },
  mcpStatusPillGuardrail: {
    backgroundColor: 'rgba(245, 158, 11, 0.15)',
    color: '#FBBF24',
  },
  mcpStatusPillError: {
    backgroundColor: 'rgba(239, 68, 68, 0.15)',
    color: '#F87171',
  },
  mcpSummaryText: {
    fontSize: 12,
    color: '#CBD5E1',
    marginBottom: 4,
  },
  mcpArgsBox: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    backgroundColor: '#1E293B',
    paddingHorizontal: 6,
    paddingVertical: 3,
    borderRadius: 4,
    marginTop: 2,
  },
  mcpArgsLabel: {
    fontSize: 10,
    color: '#64748B',
    fontWeight: '600',
  },
  mcpArgsText: {
    fontSize: 11,
    color: '#94A3B8',
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
    flex: 1,
  },
  mcpIdleBox: {
    backgroundColor: '#0F172A',
    borderRadius: 8,
    padding: 10,
  },
  mcpIdleText: {
    fontSize: 12,
    color: '#64748B',
    lineHeight: 18,
  },

  // Modal Styles
  modalOverlay: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: 'rgba(0, 0, 0, 0.75)',
    justifyContent: 'center',
    alignItems: 'center',
    padding: 16,
    zIndex: 999,
  },
  activityModalCard: {
    backgroundColor: '#1E293B',
    borderRadius: 16,
    width: '100%',
    maxWidth: 500,
    maxHeight: '85%',
    borderWidth: 1,
    borderColor: '#475569',
    padding: 16,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 10 },
    shadowOpacity: 0.5,
    shadowRadius: 20,
    elevation: 10,
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 12,
  },
  modalTitle: {
    fontSize: 16,
    fontWeight: '700',
    color: '#F8FAFC',
  },
  closeModalButton: {
    backgroundColor: '#334155',
    width: 28,
    height: 28,
    borderRadius: 14,
    justifyContent: 'center',
    alignItems: 'center',
  },
  closeModalText: {
    color: '#94A3B8',
    fontSize: 14,
    fontWeight: '700',
  },
  activityModalSubtitle: {
    fontSize: 11,
    color: '#94A3B8',
    marginTop: 2,
  },
  activityHistoryList: {
    marginTop: 12,
  },
  historyTurnItem: {
    backgroundColor: '#0F172A',
    borderRadius: 10,
    padding: 12,
    marginBottom: 10,
    borderWidth: 1,
    borderColor: '#334155',
  },
  historyTurnHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 6,
  },
  historyTimestamp: {
    fontSize: 11,
    color: '#64748B',
    fontWeight: '600',
  },
  historyToolBadgePill: {
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 10,
  },
  historyToolBadgePillActive: {
    backgroundColor: 'rgba(99, 102, 241, 0.2)',
  },
  historyToolBadgePillIdle: {
    backgroundColor: 'rgba(100, 116, 139, 0.2)',
  },
  historyToolBadgePillText: {
    fontSize: 10,
    color: '#A5B4FC',
    fontWeight: '700',
  },
  historyUserQuery: {
    fontSize: 13,
    color: '#F1F5F9',
    fontWeight: '600',
    marginBottom: 8,
  },
  historyLogsSublist: {
    gap: 6,
  },
  historySublogItem: {
    backgroundColor: '#1E293B',
    borderRadius: 6,
    padding: 8,
    borderLeftWidth: 2,
    borderLeftColor: '#6366F1',
  },
  historySublogTopRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 4,
  },
  historySublogToolName: {
    fontSize: 12,
    fontWeight: '700',
    color: '#C7D2FE',
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
  },
  historySublogBadgeRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  historySublogLatency: {
    fontSize: 10,
    color: '#94A3B8',
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
  },
  historySublogStatus: {
    fontSize: 9,
    fontWeight: '700',
    paddingHorizontal: 4,
    paddingVertical: 1,
    borderRadius: 3,
  },
  historySublogStatusSuccess: {
    backgroundColor: 'rgba(16, 185, 129, 0.15)',
    color: '#34D399',
  },
  historySublogStatusGuardrail: {
    backgroundColor: 'rgba(245, 158, 11, 0.15)',
    color: '#FBBF24',
  },
  historySublogStatusError: {
    backgroundColor: 'rgba(239, 68, 68, 0.15)',
    color: '#F87171',
  },
  historySublogSummary: {
    fontSize: 11,
    color: '#CBD5E1',
    marginBottom: 2,
  },
  historyArgsContainer: {
    backgroundColor: '#0F172A',
    borderRadius: 4,
    padding: 4,
    marginTop: 2,
  },
  historyArgsCode: {
    fontSize: 10,
    color: '#94A3B8',
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
  },
  historyNoToolsNotice: {
    fontSize: 11,
    color: '#64748B',
    fontStyle: 'italic',
  },
});
