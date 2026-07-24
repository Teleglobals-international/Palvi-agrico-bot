# Palvi Agrico Voice Bot — Architecture

---

## Outbound Calling Architecture (Bot calls the farmer)

```
┌──────────────┐        ┌──────────────┐        ┌──────────────────┐
│              │  API    │              │  Dials  │                  │
│  Our System  │ ─────→  │    Twilio    │ ─────→  │  Farmer's Phone  │
│  (Trigger)   │        │  (Calling)   │        │                  │
│              │        │              │        │                  │
└──────────────┘        └──────┬───────┘        └────────┬─────────┘
                               │                         │
                               │ Sends farmer's          │ Farmer
                               │ voice as text           │ speaks
                               ▼                         │
                        ┌──────────────┐                 │
                        │              │                 │
                        │  Our Server  │ ←───────────────┘
                        │  (AWS EC2)   │
                        │              │
                        │  Bot Brain   │
                        │              │
                        └──────┬───────┘
                               │
                               │ Sends reply text
                               ▼
                        ┌──────────────┐
                        │  Sarvam AI   │
                        │  (Voice)     │
                        │              │
                        │  Converts    │
                        │  text to     │
                        │  Marathi     │
                        │  voice       │
                        └──────┬───────┘
                               │
                               │ Audio played
                               ▼
                        ┌──────────────────┐
                        │  Farmer hears    │
                        │  natural Marathi │
                        │  female voice    │
                        └──────────────────┘
```

---

## Inbound Calling Architecture (Farmer calls our number)

```
┌──────────────────┐        ┌──────────────┐        ┌──────────────────┐
│                  │  Calls  │              │  Sends  │                  │
│  Farmer's Phone  │ ─────→  │    Twilio    │ ─────→  │    Our Server    │
│                  │        │  (Receives)  │  call   │    (AWS EC2)     │
│                  │        │              │  info   │                  │
└──────────────────┘        └──────────────┘        └────────┬─────────┘
                                                             │
                                                             │ Same flow
                                                             │ as outbound
                                                             ▼
                                                    (Bot greets, listens,
                                                     responds, takes order)
```

---

## Services Used

| Service | What It Does | Used For |
|---------|-------------|----------|
| **Twilio** | Phone calling platform | Making calls, receiving calls, listening to farmer's voice and converting it to text |
| **Sarvam AI** | Indian language voice generator | Converting bot's Marathi text into natural human-like female voice (Marathwada/Vidarbha accent) |
| **AWS EC2** | Cloud computer | Running the bot's brain — decides what to say based on the sales script |
| **AWS DynamoDB** | Cloud database | Storing call history, farmer details, and orders |

---

## How Each Service Connects

```
Twilio ←→ Our Server (EC2) ←→ Sarvam AI
                 ↕
            DynamoDB
         (saves call data)
```

- **Twilio** handles the phone line (calling + voice recognition)
- **Our Server** is the brain (follows the sales script)
- **Sarvam AI** is the voice (speaks natural Marathi)
- **DynamoDB** is the memory (remembers everything)

---

## Summary

- **Outbound:** We trigger → Twilio calls farmer → Bot talks → Farmer responds → Bot continues
- **Inbound:** Farmer calls our number → Twilio connects to bot → Same conversation happens
- **Both use the same bot brain, same voice, same script — only the call direction is different.**
