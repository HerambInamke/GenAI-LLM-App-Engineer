# Core Idea — Dead Air

**One line:** a 24/7 internet radio station run entirely by AI, where every factual claim on air is traceable to a stored headline.

## The pitch

Two AI hosts read real headlines, argue about them, play music, and take live phone calls. Across the dial, a rival AI station with its own personality broadcasts on the next "frequency" and feuds with them on air. Storylines (feuds, running jokes) persist across days. Listeners vote by phone or web on what happens next, and the hosts follow the result.

## Why it's interesting (as engineering)

| Hard problem | What Dead Air does |
|---|---|
| LLMs hallucinate | A **fact gate** strips any claim that doesn't cite a stored feed item |
| LLMs repeat themselves | **Episode memory** in a vector store plus an n-gram repetition check |
| Voice AI feels slow | **Chunked** generation (1–2 sentences), TTS starts on the first chunk |
| Agents drift off-plan | A **showrunner** plans 10-minute blocks with hard rules checked in code |
| Live interaction | **Barge-in**: a caller interrupts and playback stops within 300 ms |

## What "done" looks like

A recorded 15-minute episode with a feud and a live caller, playable from the archive, with a README results table showing latency, barge-in, fact-gate accuracy and repetition numbers.

## What it is not (v1)

No voice cloning of real people, no real defamation-risk content, no mobile apps, no monetization or accounts. Both stations and all hosts are fictional.

See [PRD.md](PRD.md) for requirements and [how-it-works.md](how-it-works.md) for the walkthrough.
