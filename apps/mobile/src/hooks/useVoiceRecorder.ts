import { useState, useCallback, useEffect, useRef, useMemo } from 'react';
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
  const [lastRecordedDuration, setLastRecordedDuration] = useState<number>(0);
  const isStartingRef = useRef(false);
  const recordingStartTimeRef = useRef<number | null>(null);
  const isRecordingRef = useRef(false);

  // Initialize expo-audio recorder with high quality preset and active metering
  const recordingOptions = useMemo(
    () => ({
      ...RecordingPresets.HIGH_QUALITY,
      isMeteringEnabled: true,
    }),
    []
  );

  const recorder = useAudioRecorder(recordingOptions);
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
      setLastRecordedDuration(0);
      await recorder.prepareToRecordAsync();
      recorder.record();
      isRecordingRef.current = true;
      recordingStartTimeRef.current = Date.now();
    } catch (err) {
      console.error('Failed to start audio recording:', err);
      isRecordingRef.current = false;
    } finally {
      isStartingRef.current = false;
    }
  }, [hasPermission, requestPermission, recorder, state.isRecording]);

  const stopRecording = useCallback(async (): Promise<string | null> => {
    if (!isRecordingRef.current && !state.isRecording) {
      return lastRecordedUri;
    }

    try {
      // Ensure minimum recording duration on Android to avoid MediaRecorder "stop failed"
      if (recordingStartTimeRef.current) {
        const elapsed = Date.now() - recordingStartTimeRef.current;
        if (elapsed < 600) {
          await new Promise((resolve) => setTimeout(resolve, 600 - elapsed));
        }
      }

      const stopResult = (await recorder.stop()) as { url?: string; durationMillis?: number } | undefined;
      // Wait for Android MediaRecorder to finalize audio container writing
      await new Promise((resolve) => setTimeout(resolve, 200));

      const finalDuration =
        stopResult?.durationMillis ||
        (recordingStartTimeRef.current ? Date.now() - recordingStartTimeRef.current : 0);
      setLastRecordedDuration(finalDuration);

      const uri = stopResult?.url || recorder.uri;
      setLastRecordedUri(uri);
      return uri;
    } catch (err) {
      console.error('Failed to stop recording:', err);
      return null;
    } finally {
      isRecordingRef.current = false;
      recordingStartTimeRef.current = null;
    }
  }, [recorder, state.isRecording, lastRecordedUri]);

  const cancelRecording = useCallback(async () => {
    if (isRecordingRef.current || state.isRecording) {
      try {
        await recorder.stop();
      } catch (err) {
        console.warn('Error cancelling recording:', err);
      }
    }
    isRecordingRef.current = false;
    setLastRecordedUri(null);
    setLastRecordedDuration(0);
    recordingStartTimeRef.current = null;
  }, [recorder, state.isRecording]);

  return {
    isRecording: state.isRecording,
    hasPermission,
    recordedUri: lastRecordedUri || recorder.uri || null,
    durationMillis: state.isRecording ? state.durationMillis || 0 : lastRecordedDuration,
    metering: state.metering,
    startRecording,
    stopRecording,
    cancelRecording,
    requestPermission,
  };
}
