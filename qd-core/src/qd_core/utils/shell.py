"""Shell command execution utilities for QD2."""

import asyncio
import os
from typing import Dict, Optional


async def run_command_and_log_output_async(
    command: str,
    *args: str,
    env: Optional[Dict[str, str]] = None,
) -> int:
    """Run a shell command asynchronously and log its output.

    Args:
        command: The command to run.
        *args: Command arguments.
        env: Additional environment variables.

    Returns:
        The return code of the command.
    """
    from qd_core.utils.log import Log

    logger = Log("QD.Core.Shell").getlogger()

    full_env = os.environ.copy()
    if env:
        full_env.update(env)

    process = await asyncio.create_subprocess_exec(
        command, *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=full_env,
    )

    stdout, stderr = await process.communicate()

    if stdout:
        logger.debug("STDOUT: %s", stdout.decode())
    if stderr:
        logger.warning("STDERR: %s", stderr.decode())

    return process.returncode or 0


async def set_env_variable_and_run_command(
    command: list[str],
    env: Optional[Dict[str, str]] = None,
) -> int:
    """Set environment variables and run a command.

    Args:
        command: Command and arguments as a list.
        env: Environment variables to set.

    Returns:
        The return code of the command.
    """
    from qd_core.utils.log import Log

    logger = Log("QD.Core.Shell").getlogger()

    full_env = os.environ.copy()
    if env:
        full_env.update(env)

    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=full_env,
    )

    stdout, stderr = await process.communicate()

    if stdout:
        logger.debug("STDOUT: %s", stdout.decode())
    if stderr:
        logger.warning("STDERR: %s", stderr.decode())

    return process.returncode or 0
