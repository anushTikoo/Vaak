import { useState, useCallback, useEffect, useRef } from 'react';
import {
  useAudioRecorder,
  useAudioRecorderState,
  RecordingPresets,
  requestRecordingPermissionsAsync,
  getRecordingPermissionsAsync,
} from 'expo-audio';

export interface UseVoiceRecorderResult {
  isRecording: boolean;
  hasPermission: boolean | null;
  recordedUri: string | null;
  durationMillis: number;
  metering?: number;
  startRecording: () => Promise<void>;
  stopRecording: () => Promise<string | null>;
  cancelRecording: () => Promise<void>;
  requestPermission: () => Promise<boolean>;
}

export function useVoiceRecorder(): UseVoiceRecorderResult {
  const [hasPermission, setHasPermission] = useState<boolean | null>(null);
  const [lastRecordedUri, setLastRecordedUri] = useState<string | null>(null);
  const isStartingRef = useRef(false);

  // Initialize expo-audio recorder with high quality preset
  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const state = useAudioRecorderState(recorder, 100);

  // Check initial permissions
  useEffect(() => {
    (async () => {
      try {
        const response = await getRecordingPermissionsAsync();
        setHasPermission(response.granted);
      } catch (err) {
        console.warn('Error checking recording permissions:', err);
      }
    })();
  }, []);

  const requestPermission = useCallback(async (): Promise<boolean> => {
    try {
      const response = await requestRecordingPermissionsAsync();
      setHasPermission(response.granted);
      return response.granted;
    } catch (err) {
      console.error('Error requesting recording permissions:', err);
      setHasPermission(false);
      return false;
    }
  }, []);

  const startRecording = useCallback(async () => {
    if (isStartingRef.current || state.isRecording) {
      return;
    }
    isStartingRef.current = true;

    try {
      let granted = hasPermission;
      if (!granted) {
        granted = await requestPermission();
      }

      if (!granted) {
        console.warn('Microphone permission not granted');
        return;
      }

      setLastRecordedUri(null);
      await recorder.prepareToRecordAsync();
      recorder.record();
    } catch (err) {
      console.error('Failed to start audio recording:', err);
    } finally {
      isStartingRef.current = false;
    }
  }, [hasPermission, requestPermission, recorder, state.isRecording]);

  const stopRecording = useCallback(async (): Promise<string | null> => {
    if (!state.isRecording) {
      return lastRecordedUri;
    }

    try {
      await recorder.stop();
      // Wait for Android MediaRecorder to finalize audio container writing
      await new Promise((resolve) => setTimeout(resolve, 300));
      const uri = recorder.uri;
      setLastRecordedUri(uri);
      return uri;
    } catch (err) {
      console.error('Failed to stop recording:', err);
      return null;
    }
  }, [recorder, state.isRecording, lastRecordedUri]);

  const cancelRecording = useCallback(async () => {
    if (state.isRecording) {
      try {
        await recorder.stop();
      } catch (err) {
        console.warn('Error cancelling recording:', err);
      }
    }
    setLastRecordedUri(null);
  }, [recorder, state.isRecording]);

  return {
    isRecording: state.isRecording,
    hasPermission,
    recordedUri: lastRecordedUri || recorder.uri || null,
    durationMillis: state.durationMillis || 0,
    metering: state.metering,
    startRecording,
    stopRecording,
    cancelRecording,
    requestPermission,
  };
}
