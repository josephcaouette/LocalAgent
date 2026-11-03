"""Run one unit test against a copy of the pipeline instead of Z:\\workspace's, for example while a
battery is using the real one (a run loads the pipeline when it starts, so editing it mid-battery
would give later runs different code):

    python devtest.py PIPELINE_COPY.py TEST_unit.py

The copy is loaded as `run_langgraph_pipeline` before the test imports it; config and the other
modules still come from Z:\\workspace."""
import importlib.util
import os
import runpy
import sys

copy, test = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
sys.path.insert(0, r"Z:\workspace")
os.chdir(r"Z:\workspace")
spec = importlib.util.spec_from_file_location("run_langgraph_pipeline", copy)
module = importlib.util.module_from_spec(spec)
sys.modules["run_langgraph_pipeline"] = module
spec.loader.exec_module(module)
sys.argv = [test] + sys.argv[3:]
runpy.run_path(test, run_name="__main__")
