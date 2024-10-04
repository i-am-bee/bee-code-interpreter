import matplotlib.pyplot

# LLM tends to generate `.show()` which does not work in a headless environment
matplotlib.pyplot.show = lambda *_args, **_kwargs: matplotlib.pyplot.savefig("plot.png")
