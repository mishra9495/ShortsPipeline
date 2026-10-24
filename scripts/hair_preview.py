"""Quick headshot render to verify the new strand hair looks right before rebuilding the scene.
Run: blender -b blend/char_hero_hair.blend --python hair_preview.py -- <out.png>
"""
import sys

import bpy
from mathutils import Vector

sys.path.append(r"D:\ShortsPipeline\scripts")
import pipeline as P  # noqa: E402

OUT = sys.argv[sys.argv.index("--") + 1]
scene = bpy.context.scene
P.setup_render(scene, samples=128)
scene.render.resolution_percentage = 100
scene.render.filepath = OUT

P.sky_world(scene)
sun = bpy.data.lights.new("Sun", "SUN")
sun.energy = 4.0
sun_obj = bpy.data.objects.new("Sun", sun)
scene.collection.objects.link(sun_obj)
sun_obj.rotation_euler = (0.9, 0, 0.5)

key = bpy.data.lights.new("Key", "AREA")
key.energy = 300
key.size = 1.0
key_obj = bpy.data.objects.new("Key", key)
scene.collection.objects.link(key_obj)
body = bpy.data.objects["Hero.body"]
head_z = 1.65
key_obj.location = (0.6, -0.9, head_z + 0.3)
key_obj.rotation_euler = (1.1, 0, 2.5)

cam_data = bpy.data.cameras.new("PreviewCam")
cam_data.lens = 85
cam_obj = bpy.data.objects.new("PreviewCam", cam_data)
scene.collection.objects.link(cam_obj)
cam_obj.location = (0.0, -0.55, head_z + 0.03)
trk = cam_obj.constraints.new("TRACK_TO")
target = bpy.data.objects.new("Target", None)
scene.collection.objects.link(target)
target.location = (0, 0, head_z)
trk.target = target
trk.track_axis, trk.up_axis = "TRACK_NEGATIVE_Z", "UP_Y"
scene.camera = cam_obj

bpy.ops.render.render(write_still=True)
print("RENDERED", OUT)
