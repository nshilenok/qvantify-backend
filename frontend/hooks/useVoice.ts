import { useCallback, useEffect, useRef, useState } from "react";
import { transcribeVoice } from "@/lib/api";
import type { VoiceState } from "@/lib/types";

type UseVoiceArgs = {
  projectId: string | null;
  uuid: string | null;
  onTranscript: (text: string, meta: { audioTokens: number }) => void;
};

export const useVoice = ({ projectId, uuid, onTranscript }: UseVoiceArgs) => {
  const [state, setState] = useState<VoiceState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [level, setLevel] = useState(0);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const dataArrayRef = useRef<Uint8Array<ArrayBuffer> | null>(null);
  const rafRef = useRef<number | null>(null);

  const cleanup = useCallback(() => {
    if (rafRef.current) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    if (audioContextRef.current) {
      audioContextRef.current.close().catch(() => {});
    }
    audioContextRef.current = null;
    analyserRef.current = null;
    dataArrayRef.current = null;
    recorderRef.current = null;
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
    }
    streamRef.current = null;
    chunksRef.current = [];
    setLevel(0);
  }, []);

  const processBlob = useCallback(
    async (blob: Blob) => {
      if (!projectId || !uuid) {
        setError("Session is not ready yet.");
        setState("idle");
        return;
      }
      setState("processing");
      try {
        const file = new File([blob], "voice.webm", { type: blob.type || "audio/webm" });
        const { text, audioTokens } = await transcribeVoice({ projectId, uuid, file });
        onTranscript(text, { audioTokens });
        setError(null);
      } catch (err) {
        const message = err instanceof Error ? err.message : "Transcription failed";
        setError(message);
      } finally {
        setState("idle");
      }
    },
    [onTranscript, projectId, uuid]
  );

  const start = useCallback(async () => {
    setError(null);
    const hostname = window.location.hostname;
    const isTrustedLocal =
      hostname === "localhost" ||
      hostname === "127.0.0.1" ||
      hostname === "::1" ||
      hostname === "lvh.me" ||
      hostname.endsWith(".lvh.me");
    if (!window.isSecureContext && !isTrustedLocal) {
      setError("Microphone requires HTTPS.");
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia) {
      setError("This browser doesn't support microphone access.");
      return;
    }
    if (typeof window.MediaRecorder === "undefined") {
      setError("Live recording isn't supported in this browser. Upload a clip instead.");
      fileInputRef.current?.click();
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      const recorder = new MediaRecorder(stream);
      streamRef.current = stream;
      recorderRef.current = recorder;
      chunksRef.current = [];
      try {
        const audioContext = new AudioContext();
        const source = audioContext.createMediaStreamSource(stream);
        const analyser = audioContext.createAnalyser();
        analyser.fftSize = 1024;
        const bufferLength = analyser.fftSize;
        const dataArray = new Uint8Array(new ArrayBuffer(bufferLength));
        source.connect(analyser);
        audioContextRef.current = audioContext;
        analyserRef.current = analyser;
        dataArrayRef.current = dataArray;
      } catch {
        audioContextRef.current = null;
        analyserRef.current = null;
        dataArrayRef.current = null;
      }
      recorder.addEventListener("dataavailable", (event) => {
        if (event.data && event.data.size > 0) {
          chunksRef.current.push(event.data);
        }
      });
      recorder.addEventListener("stop", () => {
        const chunks = chunksRef.current.slice();
        cleanup();
        if (!chunks.length) {
          setError("No audio captured.");
          setState("idle");
          return;
        }
        const blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
        processBlob(blob);
      });
      recorder.start();
      setState("recording");
      if (analyserRef.current && dataArrayRef.current) {
        const tick = () => {
          const analyserNode = analyserRef.current;
          const buffer = dataArrayRef.current;
          if (analyserNode && buffer) {
            analyserNode.getByteTimeDomainData(buffer);
            let sum = 0;
            for (let i = 0; i < buffer.length; i += 1) {
              const value = (buffer[i] - 128) / 128;
              sum += value * value;
            }
            const rms = Math.sqrt(sum / buffer.length);
            setLevel(rms);
          }
          rafRef.current = requestAnimationFrame(tick);
        };
        rafRef.current = requestAnimationFrame(tick);
      }
    } catch (err) {
      const rawMessage = err instanceof Error ? err.message : "";
      const friendlyMessage =
        err instanceof Error && err.name === "NotAllowedError"
          ? "Microphone permission not granted."
          : rawMessage || "Microphone permission not granted.";
      setError(friendlyMessage);
      cleanup();
    }
  }, [cleanup, processBlob]);

  const stop = useCallback(() => {
    if (recorderRef.current && recorderRef.current.state !== "inactive") {
      recorderRef.current.stop();
    }
  }, []);

  const handleFileChange = useCallback(
    async (event: React.ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0];
      event.target.value = "";
      if (!file) return;
      await processBlob(file);
    },
    [processBlob]
  );

  useEffect(() => {
    return () => cleanup();
  }, [cleanup]);

  return {
    state,
    error,
    level,
    start,
    stop,
    fileInputRef,
    handleFileChange,
  };
};
