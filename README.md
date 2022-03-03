# 这是做啥的？
blender导入所有图片格式时都只能导入为单层的纹理，而这个插件可以将psd或psb文件分层导入blender

# 安装方法
将`io_import_psd.py`复制进blender插件目录，然后在偏好设置中勾选`Import-Export: Import PSD Images`

这一钩大概率会报错，因为本插件需要依赖[psd_tools](https://github.com/psd-tools/psd-tools)运行。在使用前需要进入你的blender的python目录运行以下指令安装依赖：

![如何调用blender自带的python](/演示素材/如何调用blender的python.png)


    python -m pip install psd-tools

    # 如果网络不好连不上pip，可以试试改用下面这句
    python -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple psd-tools

psd-tools的依赖比较多，几乎包含了python图像处理全家桶，需要耗挺久时间来安装。我也不知道处理个psd为啥要用到这么多不同的图像处理库，搞得我小巧的blender一下就被填得满满的了。但也没办法谁让咱没技术呢，还是只能依赖别人的成果。等以后我变强到可以手撕psd文件再来写一个小巧点的吧

# 使用方法
顺利开启插件后点击左上方`文件-导入-PSD`，就可以把psd或psb文件直接导入了。选择其它格式的图片的话不会有任何反应

导入的图层全部为矩形网格，依下上顺序从后到前排列，间距为0.01。