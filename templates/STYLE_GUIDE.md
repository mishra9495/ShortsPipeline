# Zack D. Films style guide for ShortsPipeline (Blender, 30-35 s, 9:16 medical and science shorts)

**How reliable this is.** YouTube, TikTok and the fan wiki could not be opened from the research environment, so no frame of any Zack D. Films short was watched directly. The evidence comes from four places: the studio's own job posts, one contractor's portfolio, fan-wiki summaries seen through search snippets, measurements from this repo, and general knowledge of the channel.

- **[H]** means verified by an official post or measured in this repo.
- **[M]** means several sources agree, or a fan-wiki transcript backs it.
- **[L]** means it was inferred, or it is a build recommendation. Treat it as a starting value to tune against the contact sheet.

The owner's rules in `CLAUDE.md` override anything in this guide: no burned captions, Daniel voice only, nothing that looks like placeholder geometry, and `HOLD` means skip.

---

## 1) Format specs

| Spec | Zack D. Films evidence | Our build target | Conf. |
|---|---|---|---|
| Duration | Official posts: 20-45 s clips. The linked examples run 28-73 s (stitches 32, sharpener 28-35, robot ~32, Segway ~33, sacrifice 31, dream 53, bunker 72). | **30-35 s.** Frame range is `1..fr(duration)+36` (the template contract). | H / H |
| Resolution | 1080x1920 is assumed (the Shorts standard). The hiring test must be 9:16. | `resolution_x, resolution_y = 1080, 1920`, at 100% for finals | M |
| Aspect | 9:16 vertical | 9:16 | H |
| FPS | Not verified. Likely 24-30. | **30 fps delivery** (half the render cost). The existing 60 fps `brain-leaking-nose` is also acceptable. Never hard-code seconds as frames: use `F(t)`. | L |
| Shots per video | Estimated 10-18 per 30 s | **12-20 shots** for a 10-line script (1-2 per line) | L |
| Average shot length | Estimated 1.5-3 s | **1.5-3 s.** No shot is longer than 4 s, and no frame is static for more than about 1 s. | L |
| Narration words | Official: 65-150 in production, 65-95 in the writer test (about 30 s) | **90-100 words, 10 lines of 8-12 words** | H |
| Pace | Implied 130-190 wpm | **About 190 wpm.** Measured on the sneeze short with Daniel +15%: 117 words in 37.3 s = 188 wpm (208 while speaking). | H |
| Gap between lines | Almost no dead air | 0.1-0.4 s (repo measures 0.12-0.36 s) | H |
| Loudness | Not measured on Zack | **-14 LUFS integrated, -1 dBTP**. This is already done by the ffmpeg loudnorm step in `mix_template.py`. | M |
| Hook timing | Premise visual on screen in frame 1, stakes stated in the first sentence | Line 1 is 10-13 words and ends by about 3.5-4.5 s. Frame 1 is already moving. | M |
| Reveal timing | Internal or X-ray answer at about 60-70% of runtime | Lines 6-8 of 10 | L |
| Render | Not verified. A Flamenco render farm points to Cycles. | Cycles, adaptive sampling (threshold 0.03), OptiX denoise, motion blur on with `motion_blur_shutter = 0.5` | L |
| Color management | Clean, punchy, readable on a phone | `AgX` with the `AgX - Punchy` look and exposure about -0.35, as in the reference scene | L |

**Fix in the repo:** `templates/ROUTINE_PROMPT.md` STEP 3 still says "40-45 s at 130 WPM". It should say about 30-33 s at about 190 wpm.

---

## 2) Characters

- **Realism level [M]:** realistic adult humans just short of photoreal, the slightly uncanny "stock CG human" look. Proportions are about 7.5 heads tall. No cartoon eyes and no squash-and-stretch faces.
- **Recurring cast [M]:** Zack reuses a fixed ensemble (Bike Girl, Owl Mom, Robert, the mascot Jer). Familiar characters make shocks land harder, as when Jer is eaten in the bunker short. **For us:** keep `blend/char_hero.blend` and `blend/char_heroine.blend` as the permanent cast. Use the same face, hair and default outfit in every short so viewers recognize them.
- **Wardrobe [M]:**
  - Plain, logo-free modern clothes: tee, hoodie, jeans, sneakers, scrubs, hospital gown.
  - Fabric uses `kit.fabric(color, rough=0.8-0.9, sheen 0.5-0.6)` with normal-map or bump wrinkles.
  - There is no readable text anywhere on clothing.
- **Skin shader [L, build recommendation]** (Principled BSDF):
  - Subsurface Weight 0.6-1.0, Radius (1.0, 0.2, 0.1), Scale 0.008-0.012 (scene units are meters).
  - Roughness 0.40-0.50 with a noise bump at strength 0.05-0.1 for pores.
  - Lips: Coat 0.1-0.2.
  - Eyes: wet, with roughness about 0.02 on the cornea and a visible specular catchlight from the key light.
- **Acting [M]:**
  - Expressions are restrained but readable (wince, shock, disgust, pain), held 0.4-0.8 s on close-ups.
  - Natural weight shifts. Hands touch the affected body part.
  - No lip sync, because the narrator speaks and the character does not. Keep the mouth closed or reacting (gasp, grimace).
- **Life signals:**
  - A blink every 2.5-4 s, lasting 0.12-0.15 s.
  - Breathing at 0.2-0.3 Hz: chest and shoulders move about 1-2 degrees.
  - Idle sway: `actor.wobble(t, seed, speed≈0.5)` at about 1-2 degrees on Spine and Neck.
  - A character is never frozen.
- **Body-part-only shorts [M]** (e.g. stitches): no face at all. The hero is one highly detailed body part (a foot or hand with nails, creases, pores and SSS). A doctor is implied off-screen through the tools only, and a gloved hand at most.
- **Non-human heroes [L]:** object or robot leads (the liquid-metal robot) are treated like characters: posed, given a small pacing or idle motion, and lit as heroes.

---

## 3) Animation and motion

- **Easing [M]:**
  - Every move eases in and out. Use `actor.smooth` (smootherstep).
  - Settles use `actor.overshoot(amount=0.08-0.15)`.
  - Impacts use `actor.spike(at, rise≈0.01, decay≈0.05-0.1)`.
  - Linear motion is allowed only for mechanical constant speed: spinning blades, a car before impact, a conveyor.
- **Weight [M]:**
  - Anticipation 0.13-0.27 s (4-8 frames at 30 fps) before big actions.
  - Follow-through and overlap 0.2-0.4 s on arms, head and hair after a stop.
  - Feet planted. No foot sliding.
- **Slow motion on the money moment [M]** (impact, injury, sneeze, fall, melt):
  - Time-warp only the animated action with `t_anim = warp(t)`: rate 0.25-0.5 for 0.6-1.5 s of screen time, ramping in and out over about 0.15 s.
  - Narration and camera keep running in real time.
  - One slow-motion beat per short, two at most.
- **Process animation [M].** This is the core of the medical shorts. Each line shows one visible transformation:
  - Closure and deformation: shape keys (e.g. wound edges pulled together as the thread tightens).
  - Growth: curve `bevel_factor_end` going 0 to 1 for vessels and fibers, Geometry Nodes or `build`-style reveals, or an animated gradient mask on material mix factors.
  - State changes by color: bake material color or mix factors per frame (red inflammation spreads, collagen goes yellow to red, the thread fades).
  - Mechanisms: spin-up over 0.3-0.5 s to a constant angular velocity, with chips or shavings as particles or simple curled meshes.
- **Simulation look [M]:** liquids, particles and smoke for the money shot (blood drops, saliva, spray, splash, smoke, liquid metal). Build them in code: a particle system or Geometry Nodes, metaballs or remesh for a melt puddle, and a Mantaflow liquid only if render time allows. There are no downloaded VDBs.
- **Motion blur:** on, shutter 0.5 (180 degrees) [L].
- **Constant motion rule [M]:** something on screen always moves: character, camera, particles or process. A frame held static for more than about 1 s counts as a defect.

---

## 4) Camera language

- **Every shot moves [M]** (community observation: "the camera is almost always moving"). Minimum moves:
  - push-in at 3-8% of subject distance per second;
  - or orbit at 4-10 degrees per second;
  - or a slow pedestal or truck.
  - Keys use smootherstep, following the `cam()` pattern in `queue/brain-leaking-nose/scene.py`.
- **Handheld [L]:** micro-drift only. The current `cam(shake=0.0015)` value is fine. Use a real shake only on impacts: amplitude 5-15 mm, decaying in 0.2-0.4 s.
- **Lens set [L]:**

| Use | Focal length | f-stop |
|---|---|---|
| Establishing, wide | 24-35 mm | f/4-5.6 |
| Medium, face | 50-85 mm | f/2-2.8 |
| Extreme close-up of a body part or prop | 85-100 mm | f/1.8-2.8 |
| Macro, micro-scale, tiny objects made hero-sized | 100-150 mm | f/1.4-2.0 |

- **Signature sequence [M]:** medium or wide shot of the character, cut to an extreme close-up of the affected body part, then a push **through** the skin or an orifice into the X-ray or cross-section, then a micro shot (cells, bacteria, fibers), then back out to a reaction close-up.
- **Other moves seen in the references [L]:**
  - Push-in on the wound as the opening (stitches, confirmed).
  - Insert shots of props.
  - Low-angle hero shot.
  - Tracking shot alongside a moving vehicle.
  - Top-down over a ledge to show the drop height.
  - Dark interior to bright exterior for reveals.
  - Focus pull from foreground to subject on reveals.
- **Cutting [L]:**
  - Hard cuts on narration line starts. Cut at the line start time, or 1-2 frames before it.
  - A second cut inside long lines on a clause break.
  - Transitions: hard cuts, plus the fly-through match into and out of the body. No dissolves, wipes or zooms-to-black.
- **9:16 framing [M, platform knowledge]:**
  - Put eyes or the hero object on the upper-third line (about 640-760 px from the top).
  - Keep critical action inside x 60-900 and y 150-1420. The bottom ~25% is covered by the Shorts title and channel overlay, and the right ~15% by the buttons.
- **Default shot grammar for a 10-line medical short** (adapt per topic):

| Line | Shots | Type / lens | Move |
|---|---|---|---|
| 1 Hook | 1-2 | Extreme close-up of the problem, 85 mm, already in motion | Push-in |
| 2-3 Setup | 2-3 | Medium on the character (50 mm), close-up on hands or props (85 mm) | Slow orbit, push |
| 4-5 Escalation | 2-4 | Close-up / extreme close-up, one shot per consequence | Push, rack focus |
| 6-8 Reveal | 3-5 | Fly-through into X-ray or cross-section, then macro (100-150 mm) | Dolly through, orbit |
| 9 Payoff | 1-2 | Outcome close-up or wide | Slow push |
| 10 Closer | 1-2 | Final image that echoes frame 1 (loop) | Matching push-in |

---

## 5) Lighting and color

Treat all of this section as **[L] build recommendations**, matched to the "cinematic, clean, readable" descriptions.

- **People and world rig:**
  - Key: area light 1.0-1.5 m, about 45 degrees side and above, warm 4500-5000 K, RGB about (1.0, 0.88, 0.78).
  - Fill: area light 2 m on the opposite side at 25-33% of key energy, cool, RGB about (0.82, 0.90, 1.0).
  - Rim or back: 0.6-0.8 m at 70-100% of key, RGB about (0.92, 0.95, 1.0).
  - Reference energies at about 2-2.5 m: key 320 W, fill 80 W, rim 220 W (the brain-leaking-nose home rig).
- **World or HDRI:** strength 0.3-0.6, for reflections only. The subject should sit 1-1.5 stops brighter than the background.
- **Anatomy, X-ray and void:**
  - World strength 0.02-0.05, near-black or a deep gradient: blood red about (0.10, 0.01, 0.01) or deep blue about (0.01, 0.02, 0.05).
  - A strong rim plus emissive or SSS glow on organs.
  - Low key energies (the reference uses 12 W key and 6 W fill at about 0.8 m).
- **Story moods [L]:**
  - Daylight interior by default.
  - Night only when the story requires it.
  - Flash or explosion: white-orange, with an exposure spike of +1.0 to +1.6 stops over 2-4 frames.
  - Decaying interior: dim, cool, slightly green, getting grimier.
  - Bleak reveal: desaturated grey-brown.
  - Outdoor: a soft Sky Texture, plus a Sun at strength 2-4 for morning light or an overcast large area light.
- **Color storytelling [M]** (stitches): use color changes to explain hidden biology without text. Bake per-frame color shifts on the relevant materials:
  - inflamed red about (0.55, 0.05, 0.04);
  - collagen yellow (0.85, 0.70, 0.30) shifting to pink-red;
  - vessels (0.45, 0.02, 0.02).
- **Grade:**
  - AgX Punchy with exposure about -0.35.
  - Compositor Hue/Saturation at saturation 1.05-1.15.
  - Slightly warm on people shots.
  - No film grain, no heavy teal-orange.
- **Chrome and metal heroes [L]:** Metallic 1.0, roughness 0.05-0.15. They need a strong environment to reflect, so add a few large emissive cards or a brighter world in those shots only.

---

## 6) Sets, props and detail level

- **Everyday sets [M]:** bathroom, kitchen, bedroom, living room, street, hospital, operating room, car interior, office, lab bench. Build **one dressed corner**, not a full room:
  - 5-15 hero props;
  - everything else falls into depth-of-field blur or darkness.
- **Object explainers [M]** (sharpener): the fan wiki lists no location. Use a neutral tabletop or a soft seamless backdrop, with only the hero object and its parts.
- **Scale [L]:** real-world sizes. Counter 0.9 m, door 2.0 m, desk 0.75 m, pencil 0.19 m × 7 mm. The camera makes small things hero-sized with a macro lens and shallow depth of field. Do not scale objects up.
- **Detail bar [M]** (the owner's quality rule):
  - Every hard edge is beveled (`kit.rbox(bevel≥0.005, segments 3)`).
  - Every material has roughness variation and a bump.
  - No flat untextured primitives.
  - Hero props get the extra parts that sell realism: screws, seams, labels shown as shapes only (never readable text), wear and dirt.
- **Kit coverage:**
  - Already in `scripts/kit.py`: `room`, `sofa`, `desk`, `lab_bench`, `or_table`, `surgical_lamp`, `vital_monitor`, `car`, `road`, `tree`, `street_lamp`, `brain`, plus `metal`, `glass`, `rubber`, `emissive` and `ceramic`.
  - Missing parts that the reference topics need: curved suture needle, suture thread, scissors, tweezers, a transparent-housing gadget, a cage with bars, a cliff edge with a river, a bunker door.
  - Build them with `kit.tube`, `kit.lathe`, `kit.cyl` and `kit.metal`, and add them to `kit.py` so later shorts can reuse them.
- **Cutaway housings [L]:** for "how it works" props, make the outer shell `kit.glass(rough 0.05-0.15)` or cut it with a Boolean, and keep the internal parts at full detail.

---

## 7) Internal, X-ray and cross-section visuals

The channel's core reveal, rated **[M]**: it is something only 3D can show, so give it about 25-35% of the runtime.

1. **X-ray shell.** Reuse the `XRayShell` node group in `queue/brain-leaking-nose/scene.py`:
   - Layer Weight "Facing" (blend 0.35), map range 0.15-0.9, then power 1.6, then times 0.5. That drives a mix of Transparent with Emission (0.32, 0.72, 1.0) at strength 2.
   - A scene driver `scene["xray"]` toggles it per shot (CONSTANT interpolation).
   - Inside the shell, organs use SSS plus Emission 0.5-2.0, so they glow and read against black.
2. **Cross-section.**
   - Boolean DIFFERENCE with an animated cutter box, plus Solidify, so the cut face shows tissue layers.
   - Layer colors: epidermis pale (0.85, 0.65, 0.55), dermis pink (0.80, 0.40, 0.40), fat yellow (0.95, 0.80, 0.45), muscle red (0.55, 0.08, 0.08), bone ivory (0.90, 0.86, 0.75).
   - Animate the cutter in over 0.3-0.5 s.
3. **Macro or micro scale.**
   - Cells: icospheres with displacement and SSS. Bacteria: capsules with noise and SSS. Fibers: curves.
   - Lens 100-150 mm at f/1.4-2.0, so there is strong depth of field and floating particles in the foreground blur.
4. **Fly-through transition [M].**
   - The camera dollies through the skin surface in 0.4-0.7 s.
   - At the crossing frame, cut or toggle to the X-ray set. The shell alpha snaps, and the camera `clip_start` is about 0.005.
   - Add an exposure spike of +0.8 stops over 2-4 frames (already in the reference scene) and sync a whoosh SFX.
5. **Staged color storytelling** (see §5). Each stage gets its own line and its own color change.
6. **Keep it readable.** One process per shot, with the hero structure centered on the upper-third line. No labels or text, so narration and color carry the meaning.

---

## 8) Script

- **Hook formulas** (the line is spoken while its visual is already on screen in frame 1):
  - "This is how [X] works." / "When you [do X], [Y happens]." [M]. The sharpener transcript opens: "When you insert a pencil into an electrical sharpener, the blade inside starts to precisely rotate."
  - "This man/woman [did X], and [shocking Y]." for real cases [M]. Repo hooks already use this, e.g. "This man held in a sneeze, and tore a hole in his own windpipe."
  - "This [object/robot] can [impossible thing]." [L]
  - "If you ever [danger], here's what happens / what to do." and "What happens if you [X]." [L]
  - "In [year], a [person]..." for true stories [L]
- **Structure for our 10 lines** (about 3.1 s per line) [M]:

| Lines | Time | Content |
|---|---|---|
| 1 | 0-3.5 s | Hook: the whole premise in one sentence |
| 2-3 | 3.5-9 s | Setup: who, what or where. Name and year for a real case. |
| 4-7 | 9-22 s | Escalation or mechanism: one cause, then one visible effect, per line |
| 6-8 | ~19-25 s | The internal reveal (X-ray, cross-section, macro) |
| 9 | 25-28 s | Payoff or outcome |
| 10 | 28-31 s | Closer: ironic verdict, "turns out..." fact, or "so next time..." tip |

- **Tone [M]:**
  - Deadpan, matter-of-fact, slightly ominous, with dark humor.
  - Short declarative sentences of 8-12 words, one fact each.
  - No hype words, no filler, no "did you know", no rhetorical questions in the narration.
  - Gore is described flatly; the calm voice against the shocking visual does the work.
  - Present tense, second person for process and what-if shorts ("Your wound is first threaded..."). Third person plus a name or year for real cases. Switch to "you" only for a closing tip.
- **Fact accuracy [H]:** Zack's writers fact-check before a research team reviews. Example: say "owner", not "inventor", of Segway. Every claim needs a source in `metadata.txt`.
- **Ending and loop [M]:**
  - End on the finished or payoff state, then a hard cut after the last word. The tail is the template's +36 frames; keep it short.
  - Frame the last image to echo frame 1: same angle and subject (healed wound against the open wound, reformed robot against the caged robot), so the replay is seamless.
  - Optionally write line 10 so it leads naturally into line 1 [L].
- **Fiction label [M]:** add " (fiction)" to the title for invented stories (as in "The Last Doomsday Bunker 😟 (fiction)"). Real-case dramatizations keep the repo's "This is a 3D animated dramatization..." line and YouTube's altered or synthetic content flag in the metadata.
- **Story variants [M]:**
  - Escalation ladder: one worse loss per line, then a one-line ironic verdict (bunker).
  - Chain or relay: each person wants what the previous one had (dream) [L].
  - Second-person dilemma (sacrifice) [L].
  - Use these sparingly. The medical and process format is our core.

---

## 9) Narration voice, music and SFX

- **Voice (owner's rule, non-negotiable):** ElevenLabs "Daniel", pauses trimmed, tempo +15%. One narrator in every short. Never Kokoro and never a child or guest voice, even though Zack occasionally uses one.
  - **Open conflict:** commit 1c744d4 added a Kokoro `am_fenrir` fallback, and `brain-leaking-nose/narration.json` runs at 222 wpm, faster than the 188 wpm reference. `logs/daily_20261027_0029.log` shows "no ElevenLabs API key". This has to be resolved before a final render.
- **Zack's narrator [L]:** calm, flat, low-energy, fast and even. Little inflection, almost no pauses.
- **Music [L]:**
  - A quiet ambient or suspense bed, or none. Soft piano for emotional pieces.
  - Mix at -18 dB under the voice and -12 dB in gaps.
  - Dip to near-silence 0.3-0.6 s before the reveal, and drop it completely at the shock moment (e.g. a fall).
- **SFX [L]:** about one hit per cut or visual event, every 1-3 s, sitting 6-10 dB below the voice.

| Category | Sounds |
|---|---|
| Camera and transitions | Whoosh on fast moves and on every fly-through; sub-boom on the reveal |
| Medical | Needle pierce, thread zip or tighten, scissors snip, wet squelch for tissue growth, heartbeat or monitor beep |
| Mechanical | Motor whir or spin-up, grinding, wood shaving, clink or settle |
| Accidents | Gravel slip or twig snap, impact thud, splash, glass |
| Liquid metal | Hum when the field turns on, wet metallic squelch, drip and slide |

- **Cue sync:** cue every SFX from beat times plus fractions (the `at(i, frac)` pattern), with the same constants in `scene.py` and `mix.py`.
- **Master:** -14 LUFS integrated, -1 dBTP (already handled by `mix_template.py`).

---

## 10) Titles, topics, descriptions and thumbnails

- **Title format [H]** (7 of 7 linked examples):
  - 4-7 words, Title Case, ending in exactly **one** emoji after a space.
  - No hashtags, no all-caps words, no colons.
- **Emoji meaning [H]:**

| Emoji | Signals |
|---|---|
| 🤔 | How-it-works or a dilemma |
| 😯 😮 | "Didn't know that" mechanism |
| 😱 😳 | Injury, accident or shock |
| 😢 😟 | Sad, moral or fiction |
| 😨 | Creepy biology |

- **Title formulas [M]:**
  - "How [X] Works 😯/🤔"
  - "The [Person] Who [Disaster] 😱"
  - "How This [Thing] [Odd Action] 😮"
  - "Would You [Dilemma]? 🤔"
  - "A [Thing] That [Shocking Effect] 😨"
  - "What Happens If You [X] 😳" [L]
  - "Why [People] [Weird Practice]" [L]
- **Topics:**
  - Zack covers history, human behavior, anatomy, how-it-works, accidents, engineering curiosities, fiction and moral stories [M].
  - Suggested mix for us [L]: about 70% body and injury explainers and real medical cases, about 20% "how this medical device or procedure works" (stitches, casts, MRI, defibrillator), about 10% survival dilemmas.
  - Pick topics with personal stakes (most people have had stitches), a hidden interior, and a satisfying visual process.
- **Sequels [M]:** split a big topic in two ("How Stitches Work" was followed by "How Stitches Are Removed").
- **Descriptions and tags [L]:** Zack's are minimal; Shorts reach comes from retention, not metadata. Keep our fuller `final/sneeze_short_youtube_metadata.txt` format (sources, dramatization disclosure, pinned-comment prompt). It costs nothing.
- **Thumbnail [M]:** in the Shorts feed, **frame 1 is the thumbnail**. Frame 1 must show the hero mid-action with the problem object visible and lit. No fade from black, no empty set, no title card.

---

## 11) What they do not do (and what we must not do)

- **Burned captions or subtitles:** not confirmed for Zack (imitation gigs add them). **We never burn them** (owner's rule). Optionally upload a sidecar SRT as YouTube closed captions.
- **On-screen text of any kind:** no title cards, labels, arrows, numbers or logos, and no readable text on props or clothes [M].
- **Intro or outro:** no intro, channel logo, greeting or "subscribe" bumper, and no end card [M].
- **Spoken call to action:** none. The engagement prompt goes in the pinned comment only [L].
- **Static frames:** none longer than about 1 s, and no slow or wasted openings [M].
- **Transitions:** no dissolves, wipes, or zooms to and from black [L].
- **Gore:** no graphic injury detail. Show the fall or impact and cut before the injury; medical gore stays mild and clinical [L].
- **Hype tone:** no exclamations, no questions to the viewer in narration, no side facts or jokes outside the cause-and-effect chain [M].
- **Characters:** no cartoon proportions or stylized eyes, and no placeholder geometry (box cars, capsule people) [owner's rule].
- **Facts:** no invented quotes or misattributions [H].
- **Assets:** no downloaded assets for us, even though Zack's contractors use BlenderKit. Everything is built in code (repo rule).

---

## 12) The reference videos: one key lesson each

| # | Video | Lesson | Conf. |
|---|---|---|---|
| 1 | **How Stitches Work 😯** (ttuKeS5k4Uo, 32 s, ~246M views, the channel's most viewed) | One hero body part; push in on the wound from frame 1; each line makes one visible change (thread, tighten, snip, redden, collagen, vessels, heal), with color-coded stages; the healed state loops back to the opening. **This is our template.** | M |
| 2 | **How Pencil Sharpeners Work 🤔** (RQ6-QBj-tYE, 28-35 s, ~14.5M) | Open on the action (pencil inserted); the money shot is a transparent-housing cutaway with a spinning cylindrical cutter and curling shavings; 4 plain sentences of about 66 words; end on the crisp finished tip. | L (the ID matched only to a near-identical wiki entry) |
| 3 | **How This Robot Melts And Reforms 😮** (xMSyfCh1wWE, ~32 s) | A solid-to-liquid-to-solid transformation is mesmerizing and loopable; a macro lens makes a 10 mm robot hero-sized; a mini prison-break arc gives a lab fact a story. | L |
| 4 | **The Segway Owner Who Fell Off A Cliff 😱** (c3aRLh3SoAs, ~33 s) | Irony that fits in the title; a true story told with exact facts (owner, not inventor); show the reverse toward the edge and the fall in slow motion, cut before any injury, and end hard on the irony. | L |
| 5 | **Would You Sacrifice Someone To Survive? 🤔** (6Ba6kREP1w4, 31 s) | A second-person moral-dilemma title drives comments. Content could not be verified at all. | L |
| 6 | **What You Have Is Someone Else's Dream 😢** (NIDOEKewKLg, 53 s) | An emotional chain format with a new character every few seconds; use it as a reference for emotional pacing, not as a topic template. Content unverified. | L |
| 7 | **The Last Doomsday Bunker 😟 (fiction)** (xcGZNNWPIA0, 72 s) | The "(fiction)" tag; an escalation ladder with one worse loss per beat; a one-line ironic verdict ("kept us alive... nothing left to live for"); familiar recurring characters make the shock land. Do not copy its narrator change. | M |
| 8 | **How Stitches Are Removed 🤔** (companion to #1, ~7.4M) | Turn a hit into a sequel: snip with sterile scissors, pull the thread out with tweezers. | L (title and summary only) |
| 9 | **Why Farmers Blowtorch Cow Udders** | The "Why [people] [weird practice]" title formula; one of the rare guest-voiced shorts (Sambucha). Content not researched. | L |
| 10 | **A Parasite That Causes Self-Sacrifice 😨** | The "A [thing] that [shocking effect]" formula with 😨 for creepy biology, which fits our niche. Content not researched. | L |

The channel page (https://www.youtube.com/@zackdfilms/videos) could not be reached. Rows 8-10 come from titles found during the research, not from watching. To confirm fps, resolution, shot counts and narration wording, run a follow-up with direct YouTube access, such as ffprobe on a downloaded Short or a transcript tool.