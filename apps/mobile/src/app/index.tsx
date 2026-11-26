import { useState, useEffect, useCallback } from 'react';
import {
  StyleSheet,
  View,
  Text,
  TouchableOpacity,
  ScrollView,
  ActivityIndicator,
  Animated,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useAudioPlayer } from 'expo-audio';
import { useVoiceRecorder } from '@/hooks/useVoiceRecorder';
import { VaakApi, ProductCardData, CartData } from '@/services/api';

const QUICK_PROMPTS = [
  '🥛 2L Amul Toned Milk',
  '🥚 6 Farm Fresh Eggs',
  '🍞 1 Packet Brown Bread',
  '🍌 1kg Fresh Bananas',
];

export default function VoiceHomeScreen() {
  const {
    isRecording,
    hasPermission,
    recordedUri,
    durationMillis,
    startRecording,
    stopRecording,
    requestPermission,
  } = useVoiceRecorder();

  // Audio player for recorded playback
  const player = useAudioPlayer(recordedUri || null);

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

  // Check backend health on mount
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

  // Pulsing animation when recording
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

  // Handle voice recording toggle
  const handleMicPress = async () => {
    if (isRecording) {
      setIsProcessing(true);
      const uri = await stopRecording();
      if (uri) {
        try {
          // Transcribe via backend
          const result = await VaakApi.uploadAudio(uri);
          setTranscript(result.transcript);

          // Process intent with conversational agent
          const chatRes = await VaakApi.sendChatMessage(result.transcript, result.session_id);
          setAssistantReply(chatRes.reply_text);
          setSuggestedProducts(chatRes.suggested_products);
        } catch (err) {
          console.error('Error processing audio:', err);
          setAssistantReply('I heard your voice, but had trouble connecting to the backend. Please check connection.');
        } finally {
          setIsProcessing(false);
        }
      } else {
        setIsProcessing(false);
      }
    } else {
      if (!hasPermission) {
        const granted = await requestPermission();
        if (!granted) {
          alert('Microphone permission is required to speak your grocery orders.');
          return;
        }
      }
      await startRecording();
    }
  };

  // Quick prompt chip simulation
  const handleQuickPrompt = async (promptText: string) => {
    const cleanPrompt = promptText.replace(/^[^\w\s]+/, '').trim();
    setTranscript(cleanPrompt);
    setIsProcessing(true);
    try {
      const res = await VaakApi.sendChatMessage(cleanPrompt);
      setAssistantReply(res.reply_text);
      setSuggestedProducts(res.suggested_products);
    } catch (err) {
      console.error('Error sending quick prompt:', err);
    } finally {
      setIsProcessing(false);
    }
  };

  // Add product to cart
  const handleAddToCart = async (product: ProductCardData) => {
    try {
      const updatedCart = await VaakApi.addCartItem({
        product_id: product.product_id,
        name: product.name,
        quantity: 1,
        unit_price: product.price,
        pack_size: product.pack_size,
        image_url: product.image_url,
      });
      setCart(updatedCart);
      setAssistantReply(`Added 1 ${product.name} to your cart.`);
    } catch (err) {
      console.error('Failed to add item to cart:', err);
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
            <Text style={styles.subtitle}>Voice Grocery Shopping • Zepto</Text>
          </View>
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
              {backendStatus === 'connected' ? 'Engine Online' : backendStatus === 'checking' ? 'Connecting...' : 'Engine Offline'}
            </Text>
          </TouchableOpacity>
        </View>

        {/* Assistant Dialog Bubble */}
        <View style={styles.assistantCard}>
          <Text style={styles.assistantBadge}>AI ASSISTANT</Text>
          <Text style={styles.assistantText}>{assistantReply}</Text>
          {transcript !== '' && (
            <View style={styles.transcriptBox}>
              <Text style={styles.transcriptLabel}>You said:</Text>
              <Text style={styles.transcriptText}>"{transcript}"</Text>
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
              ? 'Transcribing & Searching...'
              : 'Tap to Speak'}
          </Text>
          <Text style={styles.micStatusSubtitle}>
            {isRecording
              ? 'Tap button again to complete order request'
              : 'Speak in English, Hindi, or your language'}
          </Text>

          {/* Audio Playback test button */}
          {recordedUri && !isRecording && (
            <TouchableOpacity
              style={styles.playbackButton}
              onPress={() => player?.play()}
            >
              <Text style={styles.playbackText}>▶️ Play Last Audio Recording</Text>
            </TouchableOpacity>
          )}
        </View>

        {/* Quick Voice Suggestions */}
        <View style={styles.suggestionsSection}>
          <Text style={styles.sectionTitle}>Try saying or tapping:</Text>
          <View style={styles.chipsRow}>
            {QUICK_PROMPTS.map((prompt, idx) => (
              <TouchableOpacity
                key={idx}
                style={styles.chip}
                onPress={() => handleQuickPrompt(prompt)}
              >
                <Text style={styles.chipText}>{prompt}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>

        {/* Zepto Suggested Products */}
        {suggestedProducts.length > 0 && (
          <View style={styles.productsSection}>
            <Text style={styles.sectionTitle}>Matching Zepto Products</Text>
            {suggestedProducts.map((product) => (
              <View key={product.product_id} style={styles.productCard}>
                <View style={styles.productInfo}>
                  <Text style={styles.productName}>{product.name}</Text>
                  {product.pack_size && <Text style={styles.packSize}>{product.pack_size}</Text>}
                  <Text style={styles.priceText}>₹{product.price.toFixed(2)}</Text>
                </View>
                <TouchableOpacity
                  style={styles.addButton}
                  onPress={() => handleAddToCart(product)}
                >
                  <Text style={styles.addButtonText}>+ ADD</Text>
                </TouchableOpacity>
              </View>
            ))}
          </View>
        )}

        {/* Persistent Floating Cart Summary */}
        {cart.total_items > 0 && (
          <View style={styles.cartBar}>
            <View>
              <Text style={styles.cartBarCount}>
                🛒 {cart.total_items} {cart.total_items === 1 ? 'item' : 'items'}
              </Text>
              <Text style={styles.cartBarSubtotal}>Total: ₹{cart.subtotal.toFixed(2)}</Text>
            </View>
            <TouchableOpacity style={styles.viewCartButton}>
              <Text style={styles.viewCartButtonText}>Review Cart →</Text>
            </TouchableOpacity>
          </View>
        )}
      </ScrollView>
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
  statusPill: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#1E293B',
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 20,
    borderWidth: 1,
    borderColor: '#334155',
  },
  statusDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    marginRight: 6,
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
  assistantBadge: {
    fontSize: 10,
    fontWeight: '700',
    color: '#38BDF8',
    letterSpacing: 1,
    marginBottom: 6,
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
  playbackText: {
    color: '#E2E8F0',
    fontSize: 12,
    fontWeight: '600',
  },
  suggestionsSection: {
    marginTop: 20,
  },
  sectionTitle: {
    fontSize: 14,
    fontWeight: '700',
    color: '#CBD5E1',
    marginBottom: 10,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  chipsRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  chip: {
    backgroundColor: '#1E293B',
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 20,
    borderWidth: 1,
    borderColor: '#334155',
  },
  chipText: {
    fontSize: 12,
    color: '#E2E8F0',
    fontWeight: '500',
  },
  productsSection: {
    marginTop: 24,
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
  addButton: {
    backgroundColor: '#10B981',
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 8,
  },
  addButtonText: {
    color: '#FFFFFF',
    fontWeight: '700',
    fontSize: 12,
  },
  cartBar: {
    backgroundColor: '#1E1B4B',
    borderRadius: 14,
    padding: 16,
    marginTop: 24,
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
  viewCartButton: {
    backgroundColor: '#6366F1',
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderRadius: 8,
  },
  viewCartButtonText: {
    color: '#FFFFFF',
    fontSize: 13,
    fontWeight: '700',
  },
});
