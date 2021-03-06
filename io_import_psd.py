# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTIBILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

bl_info = {
    "name" : "Import PSD Images",
    "author" : "Kumopult <kumopult@qq.com>",
    "description" : "将PSD或PSB文件分层导入为网格",
    "blender" : (2, 93, 0),
    "version" : (0, 0, 1),
    "location" : "File > Import > Import PSD",
    "warning" : "本插件依赖psd-tools库运行, 请先依照文档说明安装依赖",
    "category" : "Import-Export",
    "doc_url": "https://github.com/kumopult/blender_ImportPSD",
    "tracker_url": "https://space.bilibili.com/1628026",
    # VScode调试：Ctrl + Shift + P
}

import bpy
from bpy_extras.image_utils import load_image
from mathutils import Vector, Matrix
from PIL import Image
from psd_tools import PSDImage

class PSD_OT_Import(bpy.types.Operator):
    bl_idname = 'import_psd.import'
    bl_label = 'PSD (.psd/.psb)'
    bl_options = {'REGISTER', 'PRESET', 'UNDO'}

    # ----------------------
    # File dialog properties
    files: bpy.props.CollectionProperty(type=bpy.types.OperatorFileListElement, options={'HIDDEN', 'SKIP_SAVE'})
    directory: bpy.props.StringProperty(maxlen=1024, subtype='FILE_PATH', options={'HIDDEN', 'SKIP_SAVE'})

    filter_image: bpy.props.BoolProperty(default=True, options={'HIDDEN', 'SKIP_SAVE'})
    filter_folder: bpy.props.BoolProperty(default=True, options={'HIDDEN', 'SKIP_SAVE'})

    # ----------------------
    # 导入设置
    align_center : bpy.props.BoolProperty(name='图像居中', default=True, description='让导入图像的中心对齐世界原点, 若取消勾选则是左上角对齐世界原点')
    pixel_size : bpy.props.FloatProperty(name='像素尺寸', default=0.01, description='图像每像素对应的尺寸')
    layer_height : bpy.props.FloatProperty(name='图层间距', default=0.01, description='图层网格的前后间距')
    pack_margin : bpy.props.IntProperty(name='图集边距', default=0, description='打包图集时各个图块间的间隔像素数, 适当留出可防止边缘混色')
    
    interpolation : bpy.props.EnumProperty(
        name='纹理插值',
        default='Linear',
        items=[
            ('Closest', 'Closest', '无插值, 适用于像素风'),
            ('Linear', 'Linear', '双线性插值, 最常用的插值算法'),
            ('Cubic', 'Cubic', '双三次线性插值, 比双线性更平滑'),
            ('Smart', 'Smart', '放大时使用三次插值; 缩小时使用线性插值'),
        ]
    )
    blend_method : bpy.props.EnumProperty(
        name='混合模式',
        default='CLIP',
        items=[
            ('OPAQUE', 'Opaque', '完全不透明'),
            ('CLIP', 'Alpha Clip', '只有透明和不透明, 没有半透明'),
            ('HASHED', 'Alpha Hashed', '有半透明效果, 但采样数少时会有噪点'),
            ('BLEND', 'Alpha Blend', '更稳定的半透明效果, 但透视关系会乱, 只能从正面看')
        ]
    )

    # ----------------------
    # 工具类
    class Space:
        def __init__(self, x, y, w, h):
            self.x = x
            self.y = y
            self.w = w
            self.h = h
        
        def fit(self, rect):
            return self.w >= rect.w and self.h >= rect.h
        
        def insert(self, rect):
            rect.put(self.x, self.y)
            if rect.w < rect.h:
                smaller_split = PSD_OT_Import.Space(self.x + rect.w, self.y, self.w - rect.w, rect.h)
                bigger_split =  PSD_OT_Import.Space(self.x, self.y + rect.h, self.w, self.h - rect.h)
            else:
                smaller_split = PSD_OT_Import.Space(self.x, self.y + rect.h, rect.w, self.h - rect.h)
                bigger_split =  PSD_OT_Import.Space(self.x + rect.w, self.y, self.w - rect.w, self.h)
                
            return smaller_split, bigger_split

    class Rect:
        def __init__(self, layer, index):
            self.layer = layer
            self.index = index
            self.w = layer.width
            self.h = layer.height
            self.weight = max(self.w, self.h) / min(self.w, self.h) * self.w * self.h
            
        def put(self, x, y):
            self.x = x
            self.y = y
        
        def create_mesh(self, size, height):
            mesh = bpy.data.meshes.new(self.layer.name)
            p1 = (            0, 0,              0)
            p2 = (            0, 0, self.h * -size)
            p3 = (self.w * size, 0, self.h * -size)
            p4 = (self.w * size, 0,              0)
            mesh.from_pydata(
                [p1, p2, p3, p4], 
                [(0, 1), (1, 2), (2, 3), (3, 0)], 
                [(0, 1, 2, 3)]
            )
            self.obj = bpy.data.objects.new(self.layer.name, mesh)
            self.obj.location = Vector([
                self.layer.left * size, 
                self.index * -height,
                self.layer.top * -size
            ])
            return self.obj
    
        def pack_uv(self, matrix):
            coords = Matrix([
                [self.x, self.y, 1],
                [self.x, self.y + self.h, 1],
                [self.x + self.w, self.y + self.h, 1],
                [self.x + self.w, self.y, 1],
            ])
            uv_layer = self.obj.data.uv_layers.new()
            for i, loop in enumerate(self.obj.data.loops):
                uv_layer.data[i].uv = tuple(matrix @ coords[loop.vertex_index])

    # ----------------------
    # 功能函数
    def pack(self, rects, size):
        rects.sort(key=lambda x:x.weight, reverse=True)
        empty_spaces = [self.Space(self.pack_margin, self.pack_margin, size[0] - self.pack_margin, size[1] - self.pack_margin)]
        
        for rect in rects:
            fit_flag = False
            for i in range(len(empty_spaces) - 1, -1, -1):
                space = empty_spaces[i]
                if space.fit(rect):
                    smaller_split, bigger_split = space.insert(rect)
                    empty_spaces.pop(i)
                    empty_spaces.append(bigger_split)
                    empty_spaces.append(smaller_split)
                    fit_flag = True
                    break
            if not fit_flag:
                print('Over Size:' + str(size))
                return False

        print('Fit Size:' + str(size))
        return True

    def import_psd(self, psd_name, psd_dir):
        src_psd = PSDImage.open(psd_dir + psd_name)
        # 图集打包
        pack_size = Vector([16, 16])
        size_index = 0
        size_factor = [
            Vector([2.0, 1.0]),
            Vector([0.5, 2.0]),
            Vector([2.0, 1.0])
        ]
        packed_rects = []
        for layer in src_psd.descendants():
            if not layer.is_group():
                rect = self.Rect(layer, len(packed_rects))
                rect.w += self.pack_margin
                rect.h += self.pack_margin
                packed_rects.append(rect)
        
        while not self.pack(packed_rects, pack_size):
            pack_size *= size_factor[size_index]
            size_index = (size_index + 1) % 3
        # 存储贴图
        pack_img = Image.new(mode='RGBA', size=(int(pack_size[0]), int(pack_size[1])), color=(0, 0, 0, 0))
        for rect in packed_rects:
            layer_img = rect.layer.composite()
            pack_img.paste(im=layer_img, box=[rect.x, rect.y])
        pack_img.save(psd_dir + psd_name.replace('.psd', '_pack.png').replace('.psb', '_pack.png'))
        tex = load_image(psd_name.replace('.psd', '_pack.png').replace('.psb', '_pack.png'), psd_dir)
        # 创建材质
        mat = bpy.data.materials.new(psd_name)
        mat.blend_method = self.blend_method
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        nodes.clear()
        out_node = nodes.new("ShaderNodeOutputMaterial")
        trans_node = nodes.new("ShaderNodeBsdfTransparent")
        emit_node = nodes.new("ShaderNodeEmission")
        mix_node = nodes.new("ShaderNodeMixShader")
        tex_node = nodes.new('ShaderNodeTexImage')
        tex_node.image = tex
        tex_node.interpolation = self.interpolation
        links.new(out_node.inputs[0], mix_node.outputs[0])
        links.new(mix_node.inputs[0], tex_node.outputs[1])
        links.new(mix_node.inputs[1], trans_node.outputs[0])
        links.new(mix_node.inputs[2], emit_node.outputs[0])
        links.new(emit_node.inputs[0], tex_node.outputs[0])
        # 创建网格
        colle = bpy.data.collections.new(psd_name)
        bpy.context.collection.children.link(colle)
        co_offset = Vector([-src_psd.width, 0, src_psd.height]) * 0.5 * self.pixel_size if self.align_center else Vector([0, 0, 0])
        co_offset += Vector([-0.5, 0, 0.5]) * self.pack_margin * self.pixel_size
        uv_matrix = Matrix([
            [1 / pack_size[0], 0, - self.pack_margin * 0.5 / pack_size[0]],
            [0, -1 / pack_size[1], 1 + self.pack_margin * 0.5 / pack_size[1]]
        ])
        for rect in packed_rects:
            obj = rect.create_mesh(self.pixel_size, self.layer_height)
            obj.data.materials.append(mat)
            obj.location += co_offset
            colle.objects.link(obj)
            rect.pack_uv(uv_matrix)

    # ----------------------
    # UI绘制
    def draw(self, context):
        layout = self.layout
        box = layout.box()
        box.label(text='网格设置', icon='MESH_GRID')
        box.prop(self, 'pixel_size')
        box.prop(self, 'layer_height')
        box.prop(self, 'pack_margin')
        box.prop(self, 'align_center')
        box = layout.box()
        box.label(text='材质设置', icon='MATERIAL_DATA')
        box.prop(self, 'interpolation')
        box.prop(self, 'blend_method')

    # ----------------------
    # 功能执行
    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        for file in self.files:
            if file.name.endswith('.psd') or file.name.endswith('.psb'):
                self.import_psd(file.name, self.directory)
            else:
                print(file.name + '不是psd或psb文件')

        return {'FINISHED'}

# ----------------------
# 注册

def import_psd_button(self, context):
    self.layout.operator(PSD_OT_Import.bl_idname, text=PSD_OT_Import.bl_label, icon='TEXTURE')

classes = (
    PSD_OT_Import,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.TOPBAR_MT_file_import.append(import_psd_button)
    print('hello kumopult!')

def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)
    bpy.types.TOPBAR_MT_file_import.remove(import_psd_button)
    print('goodbye kumopult!')