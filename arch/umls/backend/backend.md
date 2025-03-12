## Workflow of `AsyncAudioChat.Backend`


![!\[alt text\](image.png)](../images/image.png)

```
@startuml
title Backend Workflow

participant "Backend Thread" as backend
participant "STT Thread" as stt
participant "Input Preprocessing\nThread" as preproc
participant "LLM Thread" as llm
participant "TTS Thread" as tts
participant "Speaker Thread" as speaker

activate backend

backend -> backend: Initialize threads & queues
note right: Load config.json\nSetup text & audio queues

backend -> stt: start()
activate stt
backend -> stt: join()
stt --> backend: Speech transcribed to text
deactivate stt

backend -> preproc: start()
activate preproc
backend -> preproc: join()
preproc --> backend: Preprocessed input
deactivate preproc

par
    backend -> llm: start()
    activate llm
    
    backend -> tts: start()
    activate tts
    
    backend -> speaker: start()
    activate speaker
end

backend -> llm: join()
llm --> backend: LLM generation complete
deactivate llm

backend -> tts: join()
tts --> backend: Text-to-speech complete
deactivate tts

backend -> speaker: join()
speaker --> backend: Audio playback complete
deactivate speaker

deactivate backend

note over backend
  All operations are wrapped in 
  try-except to handle errors gracefully
end note

@enduml
```