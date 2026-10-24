"""Load a retargeted action (saved by retarget.py) onto the hero in the CURRENT .blend, and
place it on an NLA strip starting at a given frame -- the normal way to combine several
retargeted clips (walk, fall, swim, climb...) into one shot timeline.

Not run standalone; import and call `apply(rig, action_path, action_name, start_frame)` from a
scene-building script, once per clip. Example:
    import apply_retargeted_action as AA
    AA.apply(rig, r"D:\ShortsPipeline\blend\anims\Walking.blend", "Walking", start_frame=1)
    AA.apply(rig, r"D:\ShortsPipeline\blend\anims\FallingIdle.blend", "FallingIdle", start_frame=61)
"""
import bpy


def apply(rig, action_path, action_name, start_frame, track_name=None):
    if action_name not in bpy.data.actions:
        with bpy.data.libraries.load(action_path) as (src, dst):
            dst.actions = [action_name]
    action = bpy.data.actions[action_name]

    if rig.animation_data is None:
        rig.animation_data_create()
    if rig.animation_data.action is None:
        # First clip: drive directly so later clips can go on NLA tracks layered above it.
        rig.animation_data.action = action
        if action.slots:
            rig.animation_data.action_slot = action.slots[0]
        return action

    track = rig.animation_data.nla_tracks.new()
    track.name = track_name or action_name
    strip = track.strips.new(action_name, int(start_frame), action)
    return strip
