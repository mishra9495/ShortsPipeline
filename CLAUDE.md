# ShortsPipeline — standing rules from the channel owner

3D animated medical/science Shorts in the style of Zack D Films. These rules come from the owner
and apply to every session and every scheduled run, until the owner changes them.

## Owner preferences (latest first)
- **Quality first, and real 3D models** (26 Oct 2026). The owner judged the first cloud-made Short
  ("hear-eyeballs") not good enough. Every object on screen must be a real, detailed 3D model,
  never a primitive standing in for one (a box for a sanding block, a cylinder for a lamp, torus
  tubes for an inner ear). If a shot would need a placeholder, find or build a proper model first.
- **No captions** unless the owner asks for them (25 Oct 2026).
- **~20 seconds** per Short (25 Oct 2026), not 40-45 s.
- **Voice:** Kokoro `am_fenrir`, polished: tight joins, no dead air, cleaned and levelled
  (see `queue/hear-eyeballs/vo.wav` pipeline in the PR #1 history).
- **No approval stops:** the owner said he does not need to approve each step any more;
  work through to the final video and report. (He only asked for step-by-step approval for one day.)
- **Every video gets its own look**: sets, palette and camera language chosen for the topic,
  not a reused template.
- Talk to the owner in **English**.

## Quality bar (check every item before a final render)
1. **Models.** Props, sets, machines and anatomy are real meshes with proper shape, bevels and
   detail. Sources, in order: owner's PC asset folders; CC0 / CC-BY libraries (Poly Haven,
   ambientCG, Sketchfab CC-licensed, NIH 3D, BodyParts3D, open-anatomy-3d); otherwise model it
   properly in Blender (subdivision, real proportions from reference). Record every asset's
   source and licence in the queue item's `metadata.txt`. The cloud sandbox blocks Poly Haven
   and ambientCG downloads; fetch those on the render PC instead of dropping to primitives.
2. **Anatomy** comes from real anatomical models (scan- or atlas-based), not procedural tubes.
3. **Hero.** Canonical hero = MPFB build on the PC (`scripts/build_character.py`) with real
   strand hair (`scripts/build_hair.py`). The MakeHuman-data rebuild
   (`scripts/build_hero_mhdata.py`) is a cloud fallback only (cap hair, older look).
   Subdivision level 2 at render on body and hair.
4. **Acting.** The character moves like a person: retargeted Mixamo clips (`scripts/retarget.py`)
   for body motion, facial expressions and lip-sync visemes, blinks, secondary motion.
   No static poses that only rotate eyes or jaw.
5. **Materials and light.** PBR texture sets at 2K or more; skin with subsurface scattering, no
   plastic look; cinematic lighting with a clear key, rim and mood per shot.
6. **Render.** Final frames render on the PC GPU (Cycles + OptiX, 128+ samples, motion blur),
   or at no less than 64 samples if a cloud render is unavoidable. Never ship low-sample CPU frames.
7. **Review gate.** Before the final render, render a full-resolution still of every shot, put
   them beside Zack D Films reference frames, and rebuild any shot that looks cheaper. Check
   for artefacts (black blotches from stacked transparency, clipping, popping) on the final frames.
8. **Sound.** Licensed or original only. Epidemic Sound downloads are not enabled on the
   owner's account, so use real recorded SFX from a licensed source on the PC when available;
   synthesized SFX are the fallback.

## Operational lessons (from the hear-eyeballs build)
- Cloud render workers: 11-frame chunks (they hit the 2-hour command limit otherwise), start them
  from a **branch name**, never a short commit SHA, and tell them never to ask for confirmation.
- Blender 5: `transform_apply()` applies location by default; new shape keys start at value 1.0.
- Objects faded to fully transparent must also be hidden (`hide_render`), or stacked
  transparency renders black blotches.
