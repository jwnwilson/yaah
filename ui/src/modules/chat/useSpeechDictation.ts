import { useCallback, useEffect, useRef, useState } from "react";

interface Options {
  onTranscript: (text: string) => void; // called with each FINAL transcript chunk
  lang?: string;
}

export function useSpeechDictation({ onTranscript, lang = "en-US" }: Options) {
  const Ctor =
    typeof window !== "undefined"
      ? (window.SpeechRecognition ?? window.webkitSpeechRecognition)
      : undefined;
  const supported = Boolean(Ctor);
  const [listening, setListening] = useState(false);
  const recRef = useRef<SpeechRecognitionLike | null>(null);
  const cbRef = useRef(onTranscript);
  cbRef.current = onTranscript;

  const stop = useCallback(() => {
    recRef.current?.stop();
  }, []);

  const start = useCallback(() => {
    if (!Ctor || recRef.current) return;
    const rec = new Ctor();
    rec.lang = lang;
    rec.continuous = true;
    rec.interimResults = false; // v1: commit only final chunks to the input
    rec.onresult = (e) => {
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const r = e.results[i];
        if (r.isFinal) cbRef.current(r[0].transcript.trim());
      }
    };
    const cleanup = () => {
      recRef.current = null;
      setListening(false);
    };
    rec.onend = cleanup;
    rec.onerror = cleanup;
    recRef.current = rec;
    rec.start();
    setListening(true);
  }, [Ctor, lang]);

  const toggle = useCallback(() => (listening ? stop() : start()), [listening, start, stop]);

  useEffect(() => () => recRef.current?.abort(), []); // stop on unmount

  return { supported, listening, start, stop, toggle };
}
