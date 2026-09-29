# Characters - caretaker

Generated 2026-09-29 by scripts/build_character.py into characters.blend (scene `Characters`).
Blender is Z-up and the character faces -Y (his left is +X). glTF/three.js is Y-up: a Blender point (x, y, z) is (x, z, -y) in glTF, so he faces +Z there.

## Objects (collection `CHAR_caretaker`)

| Object | What | Verts | Tris (game mesh) |
|---|---|---|---|
| `RIG_caretaker` | armature, 66 deforming bones (+ 8 IK controls) | | |
| `BODY_caretaker` | skin; Armature then Multires (level 1 shown, level 0 is the game mesh) | 10582 | 21160 |
| `EYES_caretaker` | both eyeballs, rigid to `eye_L`/`eye_R` | 3216 | 6424 |
| `MOUTH_caretaker` | teeth, gums, tongue: upper to `head`, lower to `jaw` | 5756 | 11112 |

Height 1.80 m, eyes at 1.682 m. Materials (placeholders, plain PBR): `MAT_skin`, `MAT_mouth`, `MAT_teeth`, `MAT_gums`, `MAT_tongue`, `MAT_eye_white`, `MAT_iris`, `MAT_pupil`.

## Posing conventions

- **+X is flexion on every bone**: curl a finger, bend an elbow or knee, bend the spine forward, nod, open the jaw. It means the same thing on both sides.
- Y and Z are mirrored between sides: a value that rolls the left hand one way rolls the right hand the mirror-image way when negated. Mirror a left pose to the right with (x, -y, -z).
- Euler bones use order `XZY`. Quaternion bones: root, hips, spine, neck, head, upper arms, thighs.
- Limits are Limit Rotation constraints named `Limits` (Affect Transform on). glTF can't carry constraints, so each deforming bone also has `limits_deg` and `axes` custom properties, which export as node extras (`bone.userData` in three.js).
- IK: object properties `ik_arm_L/R`, `ik_leg_L/R` on `RIG_caretaker` (0 = FK, 1 = IK). Targets `ik_hand_*`, `ik_foot_*`; poles `pole_elbow_*`, `pole_knee_*`. Switching to IK at rest doesn't move anything.
- `forearm_twist_*` copies the hand's Y rotation, and the forearm skin ramps from elbow (none) to wrist (full), so pronation/supination on `hand_*` twists the forearm smoothly. In three.js, set `forearm_twist.rotation.y` yourself (the constraint doesn't export).
- Hand pose assets (Pose Mode asset shelf): `hand_relaxed`, `hand_flat`, `hand_fist`, `hand_point`, `hand_spread`, `hand_grip`, `hand_pinch`. They also export as one-frame glTF clips that key only the 38 hand bones, so they layer over body animation.
- **In three.js** the joints keep these exact local axes (checked on export). A joint's `quaternion` holds its rest orientation, so apply a pose on top of it instead of overwriting `rotation`: `bone.quaternion.copy(rest).multiply(q.setFromEuler(new Euler(x, y, z, 'YZX')))`. Order `YZX` in three.js is Blender's `XZY`. Export with `scripts/export_character.py`.

## Bones

Head positions in metres. Limits are degrees for the left side (right: X same, Y and Z negated and swapped).

| Bone | Parent | Head (Blender x, y, z) | Head (glTF) | Rotation | X | Y | Z | Axes |
|---|---|---|---|---|---|---|---|---|
| `root` |  | 0.000, 0.000, 0.000 | 0.000, 0.000, -0.000 | quaternion |  |  |  |  |
| `hips` | `root` | 0.000, 0.015, 0.930 | 0.000, 0.930, -0.015 | quaternion |  |  |  | whole body about the pelvis: +X tip forward, +Z lean to his right, +Y turn to his left (quaternion) |
| `spine_01` | `hips` | 0.000, -0.005, 1.040 | 0.000, 1.040, 0.005 | quaternion |  |  |  | +X bend forward, +Z lean to his right, +Y turn to his left (quaternion) |
| `spine_02` | `spine_01` | 0.000, 0.000, 1.170 | 0.000, 1.170, -0.000 | quaternion |  |  |  | +X bend forward, +Z lean to his right, +Y turn to his left (quaternion) |
| `spine_03` | `spine_02` | 0.000, 0.012, 1.300 | 0.000, 1.300, -0.012 | quaternion |  |  |  | +X bend forward, +Z lean to his right, +Y turn to his left (quaternion) |
| `neck` | `spine_03` | 0.000, 0.022, 1.470 | 0.000, 1.470, -0.022 | quaternion |  |  |  | +X nod forward, +Z tilt to his right, +Y turn to his left (quaternion) |
| `head` | `neck` | 0.000, -0.040, 1.615 | 0.000, 1.615, 0.040 | quaternion |  |  |  | +X nod forward, +Z tilt to his right, +Y turn to his left (quaternion) |
| `jaw` | `head` | 0.000, -0.050, 1.640 | 0.000, 1.640, 0.050 | xzy | -3..30 | locked | -8..8 | +X open, +Z chin to his right |
| `eye_L` | `head` | 0.035, -0.130, 1.682 | 0.035, 1.682, 0.130 | xzy | -30..25 | locked | -35..35 | +X look down, +Z look to his right (same on both eyes) |
| `clavicle_L` | `spine_03` | 0.020, -0.040, 1.455 | 0.020, 1.455, 0.040 | xzy | -15..35 | -10..10 | -20..20 | +X shrug up, +Z pull back (L) / forward (R) |
| `upperarm_L` | `clavicle_L` | 0.190, 0.010, 1.430 | 0.190, 1.430, -0.010 | quaternion |  |  |  | +X swing forward, +Z raise out to the side (L) / lower (R), Y twist (quaternion) |
| `forearm_L` | `upperarm_L` | 0.316, 0.008, 1.163 | 0.316, 1.163, -0.008 | xzy | -20..135 | locked | locked | +X bend the elbow (hinge only) |
| `forearm_twist_L` | `forearm_L` | 0.359, -0.032, 1.049 | 0.359, 1.049, 0.032 | xzy |  |  |  | driven: copies the hand's Y (pronation) to spread it along the forearm |
| `hand_L` | `forearm_L` | 0.401, -0.071, 0.935 | 0.401, 0.935, 0.071 | xzy | -70..80 | -85..85 | -35..25 | +X flex palm-ward, +Y pronate (L) / supinate (R), +Z radial deviation (L) / ulnar (R) |
| `palm_index_L` | `hand_L` | 0.407, -0.082, 0.922 | 0.407, 0.922, 0.082 | xzy | -5..10 | -5..5 | -8..8 | +X cup the palm (metacarpal), Z fan |
| `index_01_L` | `palm_index_L` | 0.430, -0.128, 0.868 | 0.430, 0.868, 0.128 | xzy | -30..95 | -5..5 | -25..25 | +X curl at the knuckle, +Z spread towards the thumb (L) / away (R) |
| `index_02_L` | `index_01_L` | 0.446, -0.156, 0.842 | 0.446, 0.842, 0.156 | xzy | -5..110 | locked | locked | +X curl (middle joint, hinge) |
| `index_03_L` | `index_02_L` | 0.447, -0.169, 0.819 | 0.447, 0.819, 0.169 | xzy | -15..85 | locked | locked | +X curl (end joint, hinge) |
| `palm_middle_L` | `hand_L` | 0.408, -0.078, 0.919 | 0.408, 0.919, 0.078 | xzy | -5..10 | -5..5 | -5..5 | +X cup the palm (metacarpal), Z fan |
| `middle_01_L` | `palm_middle_L` | 0.437, -0.106, 0.856 | 0.437, 0.856, 0.106 | xzy | -30..95 | -5..5 | -25..25 | +X curl at the knuckle, +Z spread towards the thumb (L) / away (R) |
| `middle_02_L` | `middle_01_L` | 0.458, -0.132, 0.826 | 0.458, 0.826, 0.132 | xzy | -5..110 | locked | locked | +X curl (middle joint, hinge) |
| `middle_03_L` | `middle_02_L` | 0.460, -0.144, 0.796 | 0.460, 0.796, 0.144 | xzy | -15..85 | locked | locked | +X curl (end joint, hinge) |
| `palm_ring_L` | `hand_L` | 0.409, -0.075, 0.919 | 0.409, 0.919, 0.075 | xzy | -5..20 | -10..10 | -10..10 | +X cup the palm (metacarpal), Z fan |
| `ring_01_L` | `palm_ring_L` | 0.443, -0.091, 0.854 | 0.443, 0.854, 0.091 | xzy | -30..95 | -5..5 | -25..25 | +X curl at the knuckle, +Z spread towards the thumb (L) / away (R) |
| `ring_02_L` | `ring_01_L` | 0.457, -0.104, 0.815 | 0.457, 0.815, 0.104 | xzy | -5..110 | locked | locked | +X curl (middle joint, hinge) |
| `ring_03_L` | `ring_02_L` | 0.456, -0.113, 0.788 | 0.456, 0.788, 0.113 | xzy | -15..85 | locked | locked | +X curl (end joint, hinge) |
| `palm_pinky_L` | `hand_L` | 0.408, -0.072, 0.919 | 0.408, 0.919, 0.072 | xzy | -5..30 | -15..15 | -12..12 | +X cup the palm (metacarpal), Z fan |
| `pinky_01_L` | `palm_pinky_L` | 0.434, -0.076, 0.855 | 0.434, 0.855, 0.076 | xzy | -30..95 | -5..5 | -25..25 | +X curl at the knuckle, +Z spread towards the thumb (L) / away (R) |
| `pinky_02_L` | `pinky_01_L` | 0.447, -0.068, 0.820 | 0.447, 0.820, 0.068 | xzy | -5..110 | locked | locked | +X curl (middle joint, hinge) |
| `pinky_03_L` | `pinky_02_L` | 0.451, -0.067, 0.796 | 0.451, 0.796, 0.067 | xzy | -15..85 | locked | locked | +X curl (end joint, hinge) |
| `thumb_01_L` | `hand_L` | 0.392, -0.100, 0.915 | 0.392, 0.915, 0.100 | xzy | -30..50 | -40..40 | -40..45 | +X across the palm, +Z away from the palm (L) / towards it (R), Y opposition twist |
| `thumb_02_L` | `thumb_01_L` | 0.391, -0.146, 0.900 | 0.391, 0.900, 0.146 | xzy | -15..65 | -10..10 | -10..10 | +X curl (middle joint) |
| `thumb_03_L` | `thumb_02_L` | 0.394, -0.168, 0.878 | 0.394, 0.878, 0.168 | xzy | -25..85 | locked | locked | +X curl (end joint, hinge) |
| `thigh_L` | `hips` | 0.090, -0.015, 0.915 | 0.090, 0.915, 0.015 | quaternion |  |  |  | +X swing forward, +Z swing out (L) / in (R), Y twist (quaternion) |
| `shin_L` | `thigh_L` | 0.153, 0.015, 0.470 | 0.153, 0.470, -0.015 | xzy | -5..150 | locked | locked | +X bend the knee (hinge only) |
| `foot_L` | `shin_L` | 0.182, 0.058, 0.082 | 0.182, 0.082, -0.058 | xzy | -45..50 | -15..15 | -25..25 | +X point the toes down, +Z toes in (L) / out (R), Y roll the sole |
| `toe_L` | `foot_L` | 0.240, -0.072, 0.025 | 0.240, 0.025, 0.072 | xzy | -40..60 | locked | locked | +X curl the toes down |

Every `_L` bone has an `_R` mirror (x negated).

## Shape keys (`BODY_caretaker`)

Mouth shapes are lip-only: rotate `jaw` (+X, 0-30 deg) to open the mouth. In glTF these are morph targets with the same names.

| Key | Use |
|---|---|
| `mouth_wide` | EE / I / S: corners out and back |
| `mouth_round` | OO / W / O: lips forward, corners in |
| `mouth_press` | M / B / P: lips pressed and rolled in |
| `mouth_fv` | F / V: lower lip under the upper teeth |
| `lip_upper_up` | upper lip raised, shows the upper teeth |
| `mouth_smile` | corners up and out, cheeks lifted |
| `blink_L` | close the left eye |
| `blink_R` | close the right eye |

### Viseme mixes

For lip sync that emits the 15 Oculus / Ready Player Me visemes (`viseme_sil` ... `viseme_U`): weight each viseme's jaw angle and shape-key mix by its strength and add them up. The same table is on `BODY_caretaker` as the `visemes` extra.

| Viseme | Jaw (deg) | Shape keys |
|---|---|---|
| `sil` | 0 | - |
| `PP` | 0 | mouth_press 1.0 |
| `FF` | 4 | mouth_fv 1.0 |
| `TH` | 6 | lip_upper_up 0.5 |
| `DD` | 8 | mouth_wide 0.3 |
| `kk` | 10 | mouth_wide 0.2 |
| `CH` | 6 | mouth_round 0.5, lip_upper_up 0.4 |
| `SS` | 3 | mouth_wide 0.7 |
| `nn` | 6 | mouth_wide 0.2 |
| `RR` | 6 | mouth_round 0.6 |
| `aa` | 14 | - |
| `E` | 8 | mouth_wide 0.8, lip_upper_up 0.3 |
| `I` | 5 | mouth_wide 1.0 |
| `O` | 10 | mouth_round 0.8 |
| `U` | 4 | mouth_round 1.0 |

## Animation clips

Authored by `scripts/anim_character.py` (legs through IK, baked to FK keys on every frame). They play in place: move the character at `speed` metres per second along the clip's direction and the planted feet stay put. The speeds are also the rig node's `clips` extra.

| Clip | Seconds | Loops | Speed (m/s) |
|---|---|---|---|
| `idle` | 6.00 | yes | - |
| `walk` | 1.10 | yes | 1.000 |
| `strafe_left` | 0.75 | yes | 0.453 |
| `jump` | 2.20 | no | - |
| `crouch` | 3.60 | yes | - |
| `talk` | 6.00 | yes | - |
| `strafe_right` | 0.75 | yes | 0.453 |

`strafe_left` moves to his left (+X in Blender), `strafe_right` is its mirror. No clip keys the jaw or eyes, which the game drives (see `app/construct/`).

## Rebuild

```
blender -b --factory-startup --python scripts/build_character.py
blender -b characters.blend --python scripts/verify_character.py -- screenshots/characters all
```

Source: Blender Studio *Human Base Meshes* v1.4.1 (CC0), downloaded to `assets/` (gitignored). See the `ASSET_CREDITS` text block.
