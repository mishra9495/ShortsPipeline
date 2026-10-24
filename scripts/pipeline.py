"""Shared helpers for the Shorts pipeline: render settings, lighting, cameras."""
import bpy
from mathutils import Vector


def setup_render(scene, samples=128, w=1080, h=1920, fps=30):
    scene.render.engine = "CYCLES"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "OPTIX"
    prefs.refresh_devices()
    for d in prefs.devices:
        d.use = d.type == "OPTIX"
    c = scene.cycles
    c.device = "GPU"
    c.samples = samples
    c.use_adaptive_sampling = True
    c.adaptive_threshold = 0.025
    c.use_denoising = True
    c.denoiser = "OPTIX"            # GPU AI denoiser (was CPU OpenImageDenoise) - much faster per frame
    c.denoising_prefilter = "ACCURATE"
    c.max_bounces = 6               # was 8
    c.diffuse_bounces = 2            # was 3
    c.glossy_bounces = 2             # was 3
    c.transmission_bounces = 4       # was 8 - car/windshield glass still looks right with fewer bounces
    c.volume_bounces = 1
    c.caustics_reflective = False
    c.caustics_refractive = False
    c.blur_glossy = 1.0
    scene.render.resolution_x, scene.render.resolution_y = w, h
    scene.render.resolution_percentage = 100
    scene.render.fps = fps
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.render.use_motion_blur = True
    scene.render.motion_blur_shutter = 0.5
    scene.render.image_settings.file_format = "PNG"


def sky_world(scene, sun_elev=0.35, sun_rot=0.6, strength=0.6):
    world = bpy.data.worlds.new("Sky")
    scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    nt.nodes.clear()
    sky = nt.nodes.new("ShaderNodeTexSky")
    sky.sun_elevation = sun_elev
    sky.sun_rotation = sun_rot
    sky.sun_disc = False
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.inputs["Strength"].default_value = strength
    outn = nt.nodes.new("ShaderNodeOutputWorld")
    nt.links.new(sky.outputs[0], bg.inputs[0])
    nt.links.new(bg.outputs[0], outn.inputs[0])
    return world


def area_light(name, loc, target, energy, size, color=(1, 1, 1)):
    data = bpy.data.lights.new(name, "AREA")
    data.energy = energy
    data.size = size
    data.color = color
    obj = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = loc
    look_at(obj, target)
    return obj


def sun_light(name, rot_euler, energy, color=(1, 0.96, 0.9), angle=0.02):
    data = bpy.data.lights.new(name, "SUN")
    data.energy = energy
    data.color = color
    data.angle = angle
    obj = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(obj)
    obj.rotation_euler = rot_euler
    return obj


def studio_lighting(scene):
    """Neutral 3-point + sky fill, used for character lookdev."""
    sky_world(scene, strength=0.35)
    area_light("Key", (1.6, -2.0, 2.3), (0, 0, 1.45), 450, 1.4, (1.0, 0.95, 0.88))
    area_light("Fill", (-2.2, -1.6, 1.6), (0, 0, 1.3), 120, 2.5, (0.85, 0.92, 1.0))
    area_light("Rim", (-0.8, 2.2, 2.4), (0, 0, 1.5), 380, 0.8, (0.9, 0.95, 1.0))
    floor = bpy.data.meshes.new("Floor")
    bpy.ops.mesh.primitive_plane_add(size=30)
    plane = bpy.context.active_object
    mat = bpy.data.materials.new("FloorMat")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.32, 0.36, 0.40, 1)
    bsdf.inputs["Roughness"].default_value = 0.6
    plane.data.materials.append(mat)


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def add_camera(scene, name, loc, target, lens=50, dof_dist=None, fstop=2.8):
    data = bpy.data.cameras.new(name)
    data.lens = lens
    data.sensor_width = 36
    data.dof.use_dof = True
    data.dof.focus_distance = dof_dist or (Vector(target) - Vector(loc)).length
    data.dof.aperture_fstop = fstop
    cam = bpy.data.objects.new(name, data)
    scene.collection.objects.link(cam)
    cam.location = loc
    look_at(cam, target)
    return cam
