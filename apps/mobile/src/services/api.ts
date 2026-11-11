import { Platform } from 'react-native';
import * as LegacyFileSystem from 'expo-file-system/legacy';
import { File, UploadType } from 'expo-file-system';

// On Android emulator, 10.0.2.2 maps to the Linux host machine's localhost:8000
export const API_BASE_URL =
  Platform.OS === 'android' ? 'http://10.0.2.2:8000' : 'http://localhost:8000';

export interface ProductCardData {
  product_id: string;
  name: string;
  price: number;
  pack_size?: string | null;
  image_url?: string | null;
  is_available: boolean;
}

export interface ChatResponse {
  session_id: string;
  reply_text: string;
  suggested_products: ProductCardData[];
  action_type: string;
  detected_language?: string;
}

export interface CartItemData {
  id: string;
  product_id: string;
  name: string;
  quantity: number;
  unit_price: number;
  total_price: number;
  image_url?: string | null;
  pack_size?: string | null;
}

export interface CartData {
  items: CartItemData[];
  currency: string;
  subtotal: number;
  total_items: number;
}

export interface TranscribeResponse {
  session_id: string;
  transcript: string;
  detected_language?: string | null;
  confidence: number;
}

export class VaakApi {
  static async checkHealth(): Promise<{ status: string; environment?: string }> {
    try {
      const response = await fetch(`${API_BASE_URL}/health`);
      if (!response.ok) {
        throw new Error(`Health check returned status ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.warn('Backend health check failed:', error);
      throw error;
    }
  }

  static async sendChatMessage(message: string, sessionId?: string, language: string = 'auto'): Promise<ChatResponse> {
    const response = await fetch(`${API_BASE_URL}/api/v1/chat/message`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        message,
        session_id: sessionId || null,
        language: language || 'auto',
      }),
    });

    if (!response.ok) {
      throw new Error(`Chat API error: ${response.statusText}`);
    }

    return await response.json();
  }

  static async textToSpeech(text: string, language: string = 'en-IN'): Promise<{ audio_base64: string; format: string }> {
    const response = await fetch(`${API_BASE_URL}/api/v1/voice/tts`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        text,
        language,
      }),
    });

    if (!response.ok) {
      throw new Error(`TTS API error: ${response.statusText}`);
    }

    return await response.json();
  }

  static async getAudioFileSize(audioUri: string): Promise<number | null> {
    try {
      if (Platform.OS === 'web') {
        const res = await fetch(audioUri);
        const blob = await res.blob();
        return blob.size;
      }
      if (typeof LegacyFileSystem?.getInfoAsync === 'function') {
        const info = await LegacyFileSystem.getInfoAsync(audioUri);
        return info.exists && info.size !== undefined ? info.size : null;
      }
    } catch {
      return null;
    }
    return null;
  }

  static async uploadAudio(audioUri: string): Promise<TranscribeResponse> {
    const uploadUrl = `${API_BASE_URL}/api/v1/voice/transcribe`;

    // 0. Pre-validate audio file size on device (empty M4A header is ~258 bytes)
    if (Platform.OS !== 'web' && typeof LegacyFileSystem?.getInfoAsync === 'function') {
      try {
        const info = await LegacyFileSystem.getInfoAsync(audioUri);
        if (!info.exists || (info.size !== undefined && info.size < 300)) {
          console.warn('Recorded audio file is missing or zero duration (< 300 bytes):', info);
          return {
            session_id: '',
            transcript: '',
            confidence: 0,
          };
        }
      } catch (checkErr) {
        console.warn('Could not inspect audio file size prior to upload:', checkErr);
      }
    }

    // 1. Try native LegacyFileSystem.uploadAsync (native Android OkHttp stream, bypasses WinterCG FormData)
    if (Platform.OS !== 'web' && typeof LegacyFileSystem?.uploadAsync === 'function') {
      try {
        const result = await LegacyFileSystem.uploadAsync(uploadUrl, audioUri, {
          httpMethod: 'POST',
          uploadType: LegacyFileSystem.FileSystemUploadType.MULTIPART,
          fieldName: 'audio',
          mimeType: 'audio/m4a',
          headers: {
            Accept: 'application/json',
          },
        });

        if (result.status >= 200 && result.status < 300) {
          return JSON.parse(result.body);
        }
        throw new Error(`Voice transcribe failed with status ${result.status}: ${result.body}`);
      } catch (nativeErr) {
        console.warn('Legacy uploadAsync failed, falling back to File.upload:', nativeErr);
      }
    }

    // 2. Try modern Expo File.upload
    if (Platform.OS !== 'web' && typeof File !== 'undefined') {
      try {
        const file = new File(audioUri);
        const result = await file.upload(uploadUrl, {
          httpMethod: 'POST',
          uploadType: UploadType.MULTIPART,
          fieldName: 'audio',
          mimeType: 'audio/m4a',
          headers: {
            Accept: 'application/json',
          },
        });

        if (result.status >= 200 && result.status < 300) {
          return JSON.parse(result.body);
        }
        throw new Error(`Voice transcribe failed with status ${result.status}: ${result.body}`);
      } catch (fileErr) {
        console.warn('Modern File.upload failed, falling back to fetch:', fileErr);
      }
    }

    // 3. Web fallback
    const blob = await (await fetch(audioUri)).blob();
    if (!blob || blob.size < 300) {
      console.warn('Recorded web audio blob is empty or zero duration (< 300 bytes):', blob?.size);
      return {
        session_id: '',
        transcript: '',
        confidence: 0,
      };
    }
    const formData = new FormData();
    const isWebm = blob.type ? blob.type.includes('webm') : true;
    const filename = isWebm ? 'recording.webm' : 'recording.m4a';
    formData.append('audio', blob, filename);

    const response = await fetch(uploadUrl, {
      method: 'POST',
      body: formData,
      headers: {
        Accept: 'application/json',
      },
    });

    if (!response.ok) {
      throw new Error(`Voice transcribe failed: ${response.statusText}`);
    }

    return await response.json();
  }

  static async getCart(): Promise<CartData> {
    const response = await fetch(`${API_BASE_URL}/api/v1/cart`);
    if (!response.ok) {
      throw new Error(`Failed to fetch cart: ${response.statusText}`);
    }
    return await response.json();
  }

  static async addCartItem(item: {
    product_id: string;
    name: string;
    quantity: number;
    unit_price: number;
    pack_size?: string | null;
    image_url?: string | null;
  }): Promise<CartData> {
    const response = await fetch(`${API_BASE_URL}/api/v1/cart/items`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(item),
    });
    if (!response.ok) {
      throw new Error(`Failed to add item: ${response.statusText}`);
    }
    return await response.json();
  }

  static async updateCartItem(itemId: string, quantity: number): Promise<CartData> {
    const response = await fetch(`${API_BASE_URL}/api/v1/cart/items/${itemId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ quantity }),
    });
    if (!response.ok) {
      throw new Error(`Failed to update item: ${response.statusText}`);
    }
    return await response.json();
  }

  static async deleteCartItem(itemId: string): Promise<CartData> {
    const response = await fetch(`${API_BASE_URL}/api/v1/cart/items/${itemId}`, {
      method: 'DELETE',
    });
    if (!response.ok) {
      throw new Error(`Failed to delete item: ${response.statusText}`);
    }
    return await response.json();
  }
}
