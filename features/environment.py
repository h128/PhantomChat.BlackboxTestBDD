from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from phantomchat_blackbox.config import TestConfig
from phantomchat_blackbox.runtime import ExternalSystemController
from phantomchat_blackbox.world import TestWorld


def before_all(context) -> None:
    context.test_config = TestConfig.from_env()
    context.system_controller = ExternalSystemController(context.test_config)
    context.system_controller.start()
    context.world = TestWorld(context.test_config)


def before_scenario(context, scenario) -> None:
    context.world.reset_for_scenario()


def after_scenario(context, scenario) -> None:
    context.world.cleanup_scenario()


def after_all(context) -> None:
    context.world.close()
    context.system_controller.stop()
