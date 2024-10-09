# LLM tends to generate `.show()` which does not work in a headless environment
import matplotlib.pyplot
matplotlib.pyplot.show = lambda *_args, **_kwargs: matplotlib.pyplot.savefig("plot.png")

# Disable progressbar for MoviePy which fills up the context window
import moviepy.editor

old_moviepy_editor_VideoClip_write_videofile = moviepy.editor.VideoClip.write_videofile
moviepy.editor.VideoClip.write_videofile = (
    lambda self, *args, **kwargs: old_moviepy_editor_VideoClip_write_videofile(
        self, *args, verbose=False, logger=None, **kwargs
    )
)