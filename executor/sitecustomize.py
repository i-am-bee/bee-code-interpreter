import sys

original_import = __import__


def patched_import(name, globals=None, locals=None, fromlist=(), level=0):
    module = original_import(name, globals, locals, fromlist, level)

    if name == "matplotlib.pyplot":
        sys.modules["matplotlib.pyplot"].show = lambda: sys.modules[
            "matplotlib.pyplot"
        ].savefig("plot.png")
    elif name == "moviepy.editor":
        original_write_videofile = sys.modules[
            "moviepy.editor"
        ].VideoClip.write_videofile
        sys.modules["moviepy.editor"].VideoClip.write_videofile = (
            lambda self, *args, **kwargs: original_write_videofile(
                self, *args, verbose=False, logger=None, **kwargs
            )
        )

    return module


__builtins__["__import__"] = patched_import
