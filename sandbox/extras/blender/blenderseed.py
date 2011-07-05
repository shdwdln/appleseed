
#
# This source file is part of appleseed.
# Visit http://appleseedhq.net/ for additional information and resources.
#
# This software is released under the MIT license.
#
# Copyright (c) 2010-2011 Francois Beaune
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#

# Imports.
import bpy
import math
import os


#
# Add-on information.
#

bl_info = {
    "name": "appleseed project format",
    "description": "Exports a scene to the appleseed project file format.",
    "author": "Franz Beaune",
    "version": (1, 1, 0),
    "blender": (2, 5, 8),   # we really need Blender 2.58 or newer
    "api": 36339,
    "location": "File > Export",
    "warning": "",
    "wiki_url": "",
    "tracker_url": "",
    "category": "Import-Export"}

script_name = "blenderseed.py"

def get_version_string():
    return "version " + ".".join(map(str, bl_info["version"]))


#
# Utilities.
#

def rad_to_deg(rad):
    return rad * 180.0 / math.pi

def scene_enumerator(self, context):
    matches = []
    for scene in bpy.data.scenes:
        matches.append((scene.name, scene.name, ""))
    return matches

def camera_enumerator(self, context):
    return object_enumerator('CAMERA')

def object_enumerator(type):
    matches = []
    for object in bpy.data.objects:
        if object.type == type:
            matches.append((object.name, object.name, ""))
    return matches


#
# Write a mesh object to disk in Wavefront OBJ format.
#

def write_mesh_object_to_disk(mesh, filepath):
    output_file = open(filepath, "w")

    # Write file header.
    output_file.write("# File generated by {0} {1}.\n".format(script_name, get_version_string()))

    # Write vertices.
    vertices = mesh.vertices
    output_file.write("# {0} vertices.\n".format(len(vertices)))
    for v in vertices:
        output_file.write("v {0} {1} {2}\n".format(v.co[0], v.co[2], -v.co[1]))

    # Write faces.
    faces = mesh.faces
    output_file.write("# {0} faces.\n".format(len(faces)))
    for f in faces:
        output_file.write("f")
        for fv in f.vertices:
            fv_index = fv + 1
            output_file.write(" " + str(fv_index))
        output_file.write("\n")

    output_file.close()


#
# AppleseedExportOperator class.
#

class AppleseedExportOperator(bpy.types.Operator):
    bl_idname = "appleseed.export"
    bl_label = "Export"

    filepath = bpy.props.StringProperty(subtype='FILE_PATH')

    # In Blender 2.58 (since revision 36928), it is possible to pass a function to the 'items' argument to create a dynamic list.
    # See: http://projects.blender.org/scm/viewvc.php?view=rev&root=bf-blender&revision=36928
    selected_scene = bpy.props.EnumProperty(name="Scene", description="Select the scene to export", items=scene_enumerator)
    selected_camera = bpy.props.EnumProperty(name="Camera", description="Select the camera to export", items=camera_enumerator)

    def execute(self, context):
        self.__export(os.path.splitext(self.filepath)[0] + ".appleseed")
        return { 'FINISHED' }

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return { 'RUNNING_MODAL' }

    def __get_selected_scene(self):
        if self.selected_scene is not None and self.selected_scene in bpy.data.scenes:
            return bpy.data.scenes[self.selected_scene]
        else: return None

    def __get_selected_camera(self):
        if self.selected_camera is not None and self.selected_camera in bpy.data.objects:
            return bpy.data.objects[self.selected_camera]
        else: return None

    def __export(self, file_path):
        scene = self.__get_selected_scene()

        if scene is None:
            self.__error("No scene to export.")
            pass

        self.__progress("")
        self.__progress("Starting export of scene {0} to {1}...".format(scene.name, file_path))

        try:
            self._output_file = open(file_path, "w")
            self._indent = 0
            self.__emit_file_header()
            self.__emit_project(scene)
            self._output_file.close()
        except IOError:
            self.__error("Could not write to {0}.".format(file_path))
            return

        self.__progress("Finished exporting.")

    def __emit_file_header(self):
        self.__emit_line("<?xml version=\"1.0\" encoding=\"UTF-8\"?>")
        self.__emit_line("<!-- File generated by {0} {1}. -->".format(script_name, get_version_string()))

    def __emit_project(self, scene):
        self.__open_element("project")
        self.__emit_scene(scene)
        self.__emit_output(scene)
        self.__emit_configurations()
        self.__close_element("project")

    def __emit_scene(self, scene):
        self.__open_element("scene")
        self.__emit_camera(scene)
        self.__emit_assembly(scene)
        self.__emit_assembly_instance(scene)
        self.__close_element("scene")

    def __emit_camera(self, scene):
        camera = self.__get_selected_camera()

        if camera is None:
            self.__warning("No camera in the scene, exporting a default camera.")
            self.__emit_default_camera()
            return

        render = scene.render

        film_width = 32.0 / 1000                                # Blender's film width is hardcoded to 32 mm
        aspect_ratio = self.__get_frame_aspect_ratio(render)
        focal_length = camera.data.lens / 1000.0                # Blender's camera focal length is expressed in mm

        self.__open_element('camera name="' + camera.name + '" model="pinhole_camera"')
        self.__emit_parameter("film_width", film_width)
        self.__emit_parameter("aspect_ratio", aspect_ratio)
        self.__emit_parameter("focal_length", focal_length)
        self.__open_element("transform")

        origin = camera.matrix_world[3]
        forward = -camera.matrix_world[2]
        up = camera.matrix_world[1]
        target = origin + forward

        origin_str = str(origin[0]) + " " + str(origin[2]) + " " + str(-origin[1])
        target_str = str(target[0]) + " " + str(target[2]) + " " + str(-target[1])
        up_str =     str(    up[0]) + " " + str(    up[2]) + " " + str(    -up[1])

        self.__emit_line('<look_at origin="' + origin_str + '" target="' + target_str + '" up="' + up_str + '" />')
        self.__close_element("transform")
        self.__close_element("camera")

    def __emit_default_camera(self):
        self.__open_element('camera name="camera" model="pinhole_camera"')
        self.__emit_parameter("film_width", 0.024892)
        self.__emit_parameter("film_height", 0.018669)
        self.__emit_parameter("focal_length", 0.035)
        self.__close_element("camera")
        return

    def __emit_assembly(self, scene):
        self.__open_element('assembly name="' + scene.name + '"')
        self.__emit_objects(scene)
        self.__close_element("assembly")

    def __emit_objects(self, scene):
        for object in scene.objects:
            if not object.hide_render:  # skip non-renderable objects
                if object.type == 'MESH':
                    self.__emit_mesh_object(object)
                else:
                    self.__try_emit_non_mesh_object(object, scene)

    def __emit_mesh_object(self, object):
        if len(object.data.faces) == 0:
            self.__info("Skipping mesh object {0} since it has no faces.".format(object.name))
            return

        self.__progress("Exporting mesh object {0}...".format(object.name))

        if self.__emit_object(object.name, object.data):
            self.__emit_object_instance(object)

    def __try_emit_non_mesh_object(self, object, scene):
        try:
            mesh = object.to_mesh(scene, True, 'RENDER')

            if mesh is None:
                self.__info("Failed to convert object {0} to a mesh.".format(object.name))
                return

            if len(mesh.faces) == 0:
                self.__info("Skipping object {0} since it has no faces once converted to a mesh.".format(object.name))
                return

            if self.__emit_object(object.name, mesh):
                self.__emit_object_instance(object)

            bpy.data.meshes.remove(mesh)
        except RuntimeError:
            self.__info("Object {0} of type {1} is not convertible to a mesh.".format(object.name, object.type))

    def __emit_object(self, object_name, mesh):
        filename = object_name + ".obj"
        filepath = os.path.join(os.path.dirname(self.filepath), filename)

        try:
            write_mesh_object_to_disk(mesh, filepath)
        except IOError:
            self.__error("While exporting object " + object_name + ": could not write to " + filepath + ", skipping this object.")
            return False

        self.__open_element('object name="' + object_name + '" model="mesh_object"')
        self.__emit_parameter("filename", filename)
        self.__close_element("object")

        return True

    def __emit_object_instance(self, object):
        self.__open_element('object_instance name="' + object.name + '_inst" object="' + object.name + '.0"')
        self.__emit_transform(object.matrix_world)
        self.__close_element("object_instance")

    def __emit_assembly_instance(self, scene):
        self.__open_element('assembly_instance name="' + scene.name + '_inst" assembly="' + scene.name + '"')
        self.__close_element("assembly_instance")

    def __emit_output(self, scene):
        self.__open_element("output")
        self.__emit_frame(scene)
        self.__close_element("output")

    def __emit_frame(self, scene):
        camera = self.__get_selected_camera()
        render = scene.render

        width, height = self.__get_frame_resolution(render)

        self.__open_element("frame name=\"beauty\"")
        self.__emit_parameter("camera", "camera" if camera is None else camera.name)
        self.__emit_parameter("resolution", "{0} {1}".format(width, height))
        self.__emit_custom_prop(scene, "color_space", "srgb")
        self.__close_element("frame")

    def __get_frame_resolution(self, render):
        scale = render.resolution_percentage / 100.0
        width = int(render.resolution_x * scale)
        height = int(render.resolution_y * scale)
        return width, height

    def __get_frame_aspect_ratio(self, render):
        width, height = self.__get_frame_resolution(render)
        xratio = width * render.pixel_aspect_x
        yratio = height * render.pixel_aspect_y
        return xratio / yratio

    def __emit_configurations(self):
        self.__open_element("configurations")
        self.__emit_configuration("final", "base_final")
        self.__emit_configuration("interactive", "base_interactive")
        self.__close_element("configurations")

    def __emit_configuration(self, name, base):
        self.__open_element("configuration name=\"" + name + "\" base=\"" + base + "\"")
        self.__close_element("configuration")

    def __emit_transform(self, matrix):
        s = matrix.to_scale()
        t = matrix.to_translation()
        rx, ry, rz = map(rad_to_deg, matrix.to_euler())

        self.__open_element("transform")
        self.__emit_line('<scaling value="{0} {1} {2}" />'.format(s[0], s[2], s[1]))
        self.__emit_line('<rotation axis="1.0 0.0 0.0" angle="{0}" />'.format(rx))
        self.__emit_line('<rotation axis="0.0 1.0 0.0" angle="{0}" />'.format(rz))
        self.__emit_line('<rotation axis="0.0 0.0 1.0" angle="{0}" />'.format(-ry))
        self.__emit_line('<translation value="{0} {1} {2}" />'.format(t[0], t[2], -t[1]))
        self.__close_element("transform")

    def __emit_matrix(self, m):
        # Notes:
        #   appleseed use premultiplication (x' = M * x), so the translation vector is in the rightmost column;
        #   in appleseed, Y is up, so a point (x, y, z) in Blender will have coordinates (x, z, -y) in appleseed.
        self.__open_element("matrix")
        self.__emit_line("{0} {1} {2} {3}".format( m[0][0],  m[0][2], -m[0][1],  m[3][0]))
        self.__emit_line("{0} {1} {2} {3}".format( m[2][0],  m[2][2], -m[2][1],  m[3][2]))
        self.__emit_line("{0} {1} {2} {3}".format(-m[1][0], -m[1][2], +m[1][1], -m[3][1]))
        self.__emit_line("{0} {1} {2} {3}".format( m[0][3],  m[1][3],  m[2][3],  m[3][3]))
        self.__close_element("matrix")

    def __emit_custom_prop(self, object, prop_name, default_value):
        value = self.__get_custom_prop(object, prop_name, default_value)
        self.__emit_parameter(prop_name, value)

    def __get_custom_prop(self, object, prop_name, default_value):
        if prop_name in object:
            return object[prop_name]
        else:
            return default_value

    def __emit_parameter(self, name, value):
        self.__emit_line("<parameter name=\"" + name + "\" value=\"" + str(value) + "\" />")

    def __open_element(self, name):
        self.__emit_line("<" + name + ">")
        self.__indent()

    def __close_element(self, name):
        self.__unindent()
        self.__emit_line("</" + name + ">")

    def __emit_line(self, line):
        self.__emit_indent()
        self._output_file.write(line + "\n")

    def __indent(self):
        self._indent += 1

    def __unindent(self):
        assert self._indent > 0
        self._indent -= 1

    def __emit_indent(self):
        IndentSize = 4
        self._output_file.write(" " * self._indent * IndentSize)

    def __error(self, message):
        self.__print_message("error", message)
        self.report({ 'ERROR' }, message)

    def __warning(self, message):
        self.__print_message("warning", message)
        self.report({ 'WARNING' }, message)

    def __info(self, message):
        self.__print_message("info", message)
        self.report({ 'INFO' }, message)

    def __progress(self, message):
        if len(message) == 0:
            print("")
        else: self.__print_message("progress", message)

    def __print_message(self, severity, message):
        max_length = 8  # length of the longest severity string
        padding_count = max_length - len(severity)
        padding = " " * padding_count
        print("[{0}] {1}{2} : {3}".format(script_name, severity, padding, message))


#
# Hook into Blender.
#

def menu_func(self, context):
    default_path = os.path.splitext(bpy.data.filepath)[0] + ".appleseed"
    self.layout.operator(AppleseedExportOperator.bl_idname, text="appleseed (.appleseed)").filepath = default_path

def register():
    bpy.utils.register_module(__name__)
    bpy.types.INFO_MT_file_export.append(menu_func)

def unregister():
    bpy.types.INFO_MT_file_export.remove(menu_func)
    bpy.utils.unregister_module(__name__)


#
# Entry point.
#

if __name__ == "__main__":
    register()
