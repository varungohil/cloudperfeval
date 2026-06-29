"""Run shell commands on the Swarm manager or an arbitrary cluster node.

`Shell.exec` runs on the configured `manager_host` (localhost or SSH). For
fault injection we sometimes need to run a command on a *specific* worker node
(the one hosting the faulted task); use `Shell.exec_on_node`.
"""

import os
import subprocess

from cloudperfeval.config import config


class Shell:
    """Stateless interface to run a single command and capture its output."""

    @staticmethod
    def exec(command: str, input_data=None, cwd=None, timeout=None) -> str:
        if timeout is None:
            timeout = config.get("shell_timeout", 30)

        manager_host = config.get("manager_host", "localhost")
        if manager_host == "localhost":
            return Shell.local_exec(command, input_data, cwd, timeout=timeout)

        ssh_user = config.get("ssh_user")
        ssh_key_path = config.get("ssh_key_path", "~/.ssh/id_rsa")
        return Shell.ssh_exec(manager_host, ssh_user, ssh_key_path, command, timeout=timeout)

    @staticmethod
    def exec_on_node(node_host: str, command: str, timeout=None) -> str:
        """Run a command on a specific node.

        If `node_host` is the manager_host (or localhost), run directly;
        otherwise SSH into it using the configured credentials.
        """
        if timeout is None:
            timeout = config.get("shell_timeout", 60)

        manager_host = config.get("manager_host", "localhost")
        if node_host in ("localhost", "", None) or node_host == manager_host:
            return Shell.exec(command, timeout=timeout)

        ssh_user = config.get("ssh_user")
        ssh_key_path = config.get("ssh_key_path", "~/.ssh/id_rsa")
        return Shell.ssh_exec(node_host, ssh_user, ssh_key_path, command, timeout=timeout)

    @staticmethod
    def local_exec(command: str, input_data=None, cwd=None, timeout=30) -> str:
        if input_data is not None:
            input_data = input_data.encode("utf-8")
        try:
            out = subprocess.run(
                command,
                input=input_data,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=True,
                cwd=cwd,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return f"[ERROR] Command timed out after {timeout}s: {command}"
        except Exception as e:
            raise RuntimeError(f"Failed to execute command: {command}\nError: {str(e)}")

        stdout = out.stdout.decode("utf-8", errors="replace")
        stderr = out.stderr.decode("utf-8", errors="replace")
        if out.returncode != 0:
            return f"[ERROR] Command execution failed (exit {out.returncode}): {stderr or stdout}"
        return stdout + stderr

    @staticmethod
    def ssh_exec(host: str, user: str, ssh_key_path: str, command: str, timeout=30) -> str:
        import paramiko  # lazy import so local-only runs need no paramiko

        ssh_key_path = os.path.expanduser(ssh_key_path)
        ssh_client = paramiko.SSHClient()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            ssh_client.connect(
                hostname=host, username=user, key_filename=ssh_key_path, timeout=timeout
            )
            stdin, stdout, stderr = ssh_client.exec_command(command, timeout=timeout)
            stdout.channel.settimeout(timeout)
            stderr.channel.settimeout(timeout)
            exit_status = stdout.channel.recv_exit_status()
            out = stdout.read().decode("utf-8", errors="replace")
            err = stderr.read().decode("utf-8", errors="replace")
            if exit_status != 0:
                return f"[ERROR] Command execution failed (exit {exit_status}): {err or out}"
            return out + err
        except Exception as e:
            raise RuntimeError(f"Failed to execute command via SSH: {command}\nError: {str(e)}")
        finally:
            ssh_client.close()
