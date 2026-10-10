# Findings from the first experiments

Date: 2026-10-10. One pair of files: the raw clip `IMG_7821.MOV` and the finished video made from it by hand, `IMG_8318.MOV` (the reference). All numbers below were measured by `lab/lab.py` in the lab container (Docker on an M4 Pro, CPU only, 14 cores, 8 GB given to the VM). One clip is a small sample: treat every conclusion as "true for this clip" until more footage is run.

## What the reference shows she does

| | Raw | Reference |
|---|---|---|
| Length | 40.7 s | 37.6 s |
| Picture | HEVC 10-bit HDR (HLG, Dolby Vision), 1920x1080 stored sideways with a rotate flag, frame rate drifting around 30 | HEVC 8-bit ordinary colour, 1080x1920, exactly 30 fps |
| Loudness | -38.2 LUFS, peak -16.7 dB | -15.6 LUFS, peak -1.1 dB |
| Loudness range | 8.1 LU | 3.5 LU |
| Sound | mono 48 kHz | stereo 44.1 kHz |

Seen in the frames:

- subtitles, two or three words at a time, bold white with a shadow, numbers and names in yellow, the words lighting up as they are spoken;
- a yellow title with the name of the place ("G-Village") at the top, with a glow and a light sweep, on screen for most of the video;
- in the opening seconds the speaker is cut out of his background and placed over a picture of the house;
- colour is left almost as shot; there is no reframing.

What she cut: the last sentence ("Дякую за перегляд!") and the tail. The transcripts of the two files are otherwise word for word the same. **She did not cut pauses inside this take**; the three seconds are an editorial trim of the ending.

## Hypotheses

| # | Hypothesis | Verdict | Evidence |
|---|---|---|---|
| H0 | Her phone footage can be processed without surprises | **Yes, with care** | HDR, rotation and a drifting frame rate are all present. Tone-mapped to ordinary colour and constant 30 fps: 9.0 s for 40.7 s of video (4.5x real time), length unchanged to the millisecond, colour close to her result (ours slightly brighter). |
| H1 | Sound can be cleaned no worse than her app | **Levelling: yes. Denoising: not shown yet** | Levelling alone takes the clip from -38 to about -16 LUFS in half a second. Three denoisers on top (spectral 0.6 s, RNNoise 0.7 s, DeepFilterNet 5.5 s for the whole clip) measure within a decibel of levelling alone on this clip, which was recorded in a quiet room with a lapel mic. Whether any of them *sounds* better needs ears, and a noisy clip. Files to listen to: `out/IMG_7821.voice.*.wav`. |
| H2 | Stabilisation is good enough | **Not testable on this clip** | Shot on a tripod. The two-pass stabiliser runs and writes a side-by-side file (`out/IMG_7821.stable.mp4`), but there is nothing to judge. Needs a walking shot. |
| H3 | Ukrainian subtitles come out nearly ready | **Yes** | `large-v3-turbo` on CPU: language detected as Ukrainian (0.99), 89 words, one word marked unsure, 27-29 s for 40.7 s of speech (1.5x real time), plus a one-time 33 s to load the model. "G-Village", "22 будинки", "150 метрів квадратних" are right. The village name is heard as "Горанч" in the raw file and "Гаранч" in the reference: proper names need a person to confirm. |
| H4 | Pauses can be cut automatically | **Mechanically yes; not what this clip needed** | The speaker talks without pauses; the longest gap between words is 0.44 s. A fixed-threshold silence detector reported 11 "pauses" in the raw file only because the recording is 22 dB too quiet: silence must be judged relative to the speech level (or by a voice detector), never by an absolute threshold. The useful cut here was editorial (drop the last sentence), which is a job for text-based editing. |
| H5 | Subtitles in her style, with the right words highlighted | **Content: yes. Look: not yet** | The AI (DeepSeek Flash, no thinking, 1.4-2.4 s, about 800 tokens) picked the same kind of words she highlights: 22, 15, 10, 150, the place names. It also proposed a title ("G-Village котеджі") and "corrected" the village name to "Горенка", which is a guess: AI corrections of names must be shown as suggestions, not applied silently. The look made with ffmpeg's subtitle renderer is plainer than hers (no word-by-word fill, no glow on the title). Our own canvas renderer from Plan Highlighter can draw exactly this; the subtitle renderer in ffmpeg cannot be pushed much further. |
| H6 | The whole chain saves real time | **Promising** | Raw file to subtitled, levelled, trimmed video in 40-44 s for a 40.7 s clip over two runs: about 29 s speech recognition, 1-1.4 s AI, 9-13 s render. The result is 1080x1920, 30 fps, -17.0 LUFS (hers: -15.6). That is machine time with no one at the screen. How long the same work takes her by hand is not known yet; that number decides this hypothesis. |
| H7 | Mac as the engine, phone as the remote | **Not tested** | Docker hung once when a container was given the Downloads folder (most likely a macOS permission prompt nobody saw) and had to be force-restarted. Media must live in a folder the engine owns, not in Downloads/Documents/Desktop. |
| H8 | Cutting the speaker out of the background | **Not tested** | Seen in the reference, not in the original plan. Needs a segmentation model and a look at hair and edges. |

## What this changes in the plan

1. **Text is the main interface.** Recognition is good enough that the transcript can drive everything: the cut (drop a sentence, as she did), the subtitles, the highlights, the title. This matters more than pause removal.
2. **Rendering belongs to our own engine.** Subtitles and titles in her style are overlays with timing, which is what Plan Highlighter's renderer already does; ffmpeg should decode, cut, mix and encode, not draw text.
3. **Speech recognition is the slow step**, about 70% of the time. On Apple hardware outside Docker it should be several times faster; inside Docker it is CPU-only. Worth measuring natively before deciding where the engine runs.
4. **AI suggestions need a review step.** Highlights are safe to apply by default; changes to words are not.
5. **Levelling is the audio feature**; denoising is an option to verify on noisy footage, not a headline.
6. **Unknowns that need more footage:** a walking shot (stabilisation), a noisy location (denoising), a take with real pauses and retakes (cutting), an interview with two voices.

## Side by side

Left: her finished video. Right: the lab's output from the raw file, with no manual step.

![reference and lab output](img/reference-vs-lab.jpg)

The words, the highlighted number and the title are there. What is missing is the finish: her subtitles fill in word by word and sit larger and lower, and her title has a glow and a light sweep. That gap is the reason for principle 4 in the plan.
